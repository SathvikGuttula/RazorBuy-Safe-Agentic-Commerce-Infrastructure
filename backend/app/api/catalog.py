"""Catalog API — product search, retrieval, and inventory checks."""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.connection import get_db
from app.database.models import Product, Inventory

router = APIRouter()


# ─── Response Schemas ────────────────────────

class ProductSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sku: str
    name: str
    category: str
    price: float
    currency: str
    features: dict
    inventory_available: int


class ProductDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sku: str
    name: str
    description: Optional[str]
    category: str
    price: float
    currency: str
    features: dict
    tags: list[str]
    active: bool
    inventory_available: int
    inventory_reserved: int


class SearchResponse(BaseModel):
    products: list[ProductSummary]
    total_found: int


class InventoryResponse(BaseModel):
    product_id: str
    sku: str
    available: bool
    available_quantity: int
    reserved_quantity: int
    required_quantity: int


# ─── Endpoints ───────────────────────────────

@router.get("/products", response_model=SearchResponse)
async def search_products(
    query: Optional[str] = Query(None, max_length=500),
    category: Optional[str] = Query(None),
    max_price: Optional[float] = Query(None, gt=0),
    min_price: Optional[float] = Query(None, ge=0),
    has_feature: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Deterministic product search. SQL filters before LLM sees results."""
    conditions = [Product.active == True]

    if query:
        pattern = f"%{query}%"
        conditions.append(
            (Product.name.ilike(pattern))
            | (Product.description.ilike(pattern))
            | (Product.category.ilike(pattern))
        )

    if category:
        conditions.append(Product.category.ilike(f"%{category}%"))

    if max_price is not None:
        conditions.append(Product.price <= Decimal(str(max_price)))

    if min_price is not None:
        conditions.append(Product.price >= Decimal(str(min_price)))

    if has_feature:
        conditions.append(Product.features[has_feature].as_string() == "true")

    stmt = (
        select(Product)
        .options(selectinload(Product.inventory))
        .where(and_(*conditions))
        .order_by(Product.price.asc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    products = result.scalars().all()

    count_stmt = select(Product).where(and_(*conditions))
    count_result = await db.execute(count_stmt)
    total = len(count_result.scalars().all())

    return SearchResponse(
        products=[
            ProductSummary(
                id=str(p.id),
                sku=p.sku,
                name=p.name,
                category=p.category,
                price=float(p.price),
                currency=p.currency,
                features=p.features or {},
                inventory_available=(p.inventory.available_quantity if p.inventory else 0),
            )
            for p in products
        ],
        total_found=total,
    )


@router.get("/products/{product_id}", response_model=ProductDetail)
async def get_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single product by UUID or SKU."""
    stmt = select(Product).options(selectinload(Product.inventory))

    try:
        uid = UUID(product_id)
        stmt = stmt.where(Product.id == uid)
    except ValueError:
        stmt = stmt.where(Product.sku == product_id)

    result = await db.execute(stmt)
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    inv = product.inventory
    return ProductDetail(
        id=str(product.id),
        sku=product.sku,
        name=product.name,
        description=product.description,
        category=product.category,
        price=float(product.price),
        currency=product.currency,
        features=product.features or {},
        tags=product.tags or [],
        active=product.active,
        inventory_available=inv.available_quantity if inv else 0,
        inventory_reserved=inv.reserved_quantity if inv else 0,
    )


@router.get("/inventory/{product_id}", response_model=InventoryResponse)
async def check_inventory(
    product_id: str,
    required_quantity: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """Check if a product has sufficient inventory."""
    stmt = select(Product).options(selectinload(Product.inventory))
    try:
        uid = UUID(product_id)
        stmt = stmt.where(Product.id == uid)
    except ValueError:
        stmt = stmt.where(Product.sku == product_id)

    result = await db.execute(stmt)
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    inv = product.inventory
    available = inv.available_quantity if inv else 0

    return InventoryResponse(
        product_id=str(product.id),
        sku=product.sku,
        available=available >= required_quantity,
        available_quantity=available,
        reserved_quantity=inv.reserved_quantity if inv else 0,
        required_quantity=required_quantity,
    )