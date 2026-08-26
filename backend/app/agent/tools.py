"""Agent tool definitions and implementations.

Each tool has:
1. A schema dict (OpenAI-compatible) for the LLM
2. An async execute function that calls real backend services

The LLM proposes tool calls. The backend executes them deterministically.
Financial tools go through the policy engine. The LLM cannot bypass it.
"""

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ─── Tool Schemas (for LLM) ──────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search the product catalog. Returns matching products with prices and inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text, e.g. 'wireless earbuds'"},
                    "category": {"type": "string", "description": "Category filter, e.g. 'headphones'"},
                    "max_price": {"type": "number", "description": "Maximum price in INR"},
                    "min_price": {"type": "number", "description": "Minimum price in INR"},
                    "has_feature": {"type": "string", "description": "Required feature key, e.g. 'anc'"},
                    "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product",
            "description": "Get full details of a specific product by SKU (e.g. P101) or ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product SKU or UUID"},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": "Check if a product has enough stock for the desired quantity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product SKU or UUID"},
                    "quantity": {"type": "integer", "description": "Desired quantity", "default": 1},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_price",
            "description": "Get the authoritative current price of a product. Always use this before ordering.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product SKU or UUID"},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_offer",
            "description": "Calculate a merchant-approved discount. Returns the maximum allowed discount.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product SKU or UUID"},
                    "requested_discount_percent": {"type": "number", "description": "Requested discount %"},
                    "requested_discount_amount": {"type": "number", "description": "Requested discount in INR"},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": "Create a purchase order. The system will verify price, inventory, and policy automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Product SKU or UUID"},
                    "quantity": {"type": "integer", "description": "Quantity to order", "default": 1},
                    "discount_amount": {"type": "number", "description": "Approved discount amount", "default": 0},
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Get the status and details of an existing order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order UUID"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_order",
            "description": "Cancel an existing order. Inventory will be released.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order UUID"},
                    "reason": {"type": "string", "description": "Cancellation reason"},
                },
                "required": ["order_id"],
            },
        },
    },
]


# ─── Tool Executors ──────────────────────────

async def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    db: AsyncSession,
    merchant_id: str,
    user_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Execute a tool call against real backend services.
    The LLM's arguments are validated and the backend is authoritative.
    """
    try:
        if tool_name == "search_products":
            return await _search_products(arguments, db)
        elif tool_name == "get_product":
            return await _get_product(arguments, db)
        elif tool_name == "check_inventory":
            return await _check_inventory(arguments, db)
        elif tool_name == "get_current_price":
            return await _get_current_price(arguments, db)
        elif tool_name == "calculate_offer":
            return await _calculate_offer(arguments, db, merchant_id)
        elif tool_name == "create_order":
            return await _create_order(arguments, db, merchant_id, user_id, session_id)
        elif tool_name == "get_order":
            return await _get_order(arguments, db)
        elif tool_name == "cancel_order":
            return await _cancel_order(arguments, db)
        else:
            return {"error": f"Unknown tool: {tool_name}", "status": "FAILED"}
    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}", exc_info=True)
        return {"error": str(e), "tool": tool_name, "status": "FAILED"}


async def _search_products(args: dict, db: AsyncSession) -> dict:
    from sqlalchemy import select, and_
    from sqlalchemy.orm import selectinload
    from app.database.models import Product

    conditions = [Product.active == True]
    query = args.get("query", "")
    if query:
        pattern = f"%{query}%"
        conditions.append(
            (Product.name.ilike(pattern))
            | (Product.description.ilike(pattern))
            | (Product.category.ilike(pattern))
        )

    category = args.get("category")
    if category:
        conditions.append(Product.category.ilike(f"%{category}%"))

    max_price = args.get("max_price")
    if max_price:
        from decimal import Decimal
        conditions.append(Product.price <= Decimal(str(max_price)))

    min_price = args.get("min_price")
    if min_price:
        from decimal import Decimal
        conditions.append(Product.price >= Decimal(str(min_price)))

    has_feature = args.get("has_feature")
    if has_feature:
        conditions.append(Product.features[has_feature].as_string() == "true")

    limit = min(args.get("limit", 5), 20)

    stmt = (
        select(Product)
        .options(selectinload(Product.inventory))
        .where(and_(*conditions))
        .order_by(Product.price.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    products = result.scalars().all()

    return {
        "status": "SUCCESS",
        "total_found": len(products),
        "products": [
            {
                "id": str(p.id),
                "sku": p.sku,
                "name": p.name,
                "category": p.category,
                "price": float(p.price),
                "currency": p.currency,
                "features": p.features or {},
                "inventory": p.inventory.available_quantity if p.inventory else 0,
            }
            for p in products
        ],
    }


async def _get_product(args: dict, db: AsyncSession) -> dict:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.database.models import Product
    from uuid import UUID

    product_id = args.get("product_id", "")
    stmt = select(Product).options(selectinload(Product.inventory))
    try:
        stmt = stmt.where(Product.id == UUID(product_id))
    except ValueError:
        stmt = stmt.where(Product.sku == product_id)

    result = await db.execute(stmt)
    p = result.scalar_one_or_none()
    if not p:
        return {"status": "FAILED", "error": "Product not found"}

    return {
        "status": "SUCCESS",
        "product": {
            "id": str(p.id),
            "sku": p.sku,
            "name": p.name,
            "description": p.description,
            "category": p.category,
            "price": float(p.price),
            "currency": p.currency,
            "features": p.features or {},
            "tags": p.tags or [],
            "inventory": p.inventory.available_quantity if p.inventory else 0,
        },
    }


async def _check_inventory(args: dict, db: AsyncSession) -> dict:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.database.models import Product
    from uuid import UUID

    product_id = args.get("product_id", "")
    quantity = args.get("quantity", 1)

    stmt = select(Product).options(selectinload(Product.inventory))
    try:
        stmt = stmt.where(Product.id == UUID(product_id))
    except ValueError:
        stmt = stmt.where(Product.sku == product_id)

    result = await db.execute(stmt)
    p = result.scalar_one_or_none()
    if not p:
        return {"status": "FAILED", "error": "Product not found"}

    avail = p.inventory.available_quantity if p.inventory else 0
    return {
        "status": "SUCCESS",
        "product_id": str(p.id),
        "sku": p.sku,
        "available": avail >= quantity,
        "available_quantity": avail,
        "requested_quantity": quantity,
    }


async def _get_current_price(args: dict, db: AsyncSession) -> dict:
    from sqlalchemy import select
    from app.database.models import Product
    from uuid import UUID

    product_id = args.get("product_id", "")
    stmt = select(Product)
    try:
        stmt = stmt.where(Product.id == UUID(product_id))
    except ValueError:
        stmt = stmt.where(Product.sku == product_id)

    result = await db.execute(stmt)
    p = result.scalar_one_or_none()
    if not p:
        return {"status": "FAILED", "error": "Product not found"}

    return {
        "status": "SUCCESS",
        "product_id": str(p.id),
        "sku": p.sku,
        "price": float(p.price),
        "currency": p.currency,
    }


async def _calculate_offer(args: dict, db: AsyncSession, merchant_id: str) -> dict:
    from sqlalchemy import select
    from app.database.models import Product
    from app.policy.engine import PolicyEngine
    from uuid import UUID

    product_id = args.get("product_id", "")
    stmt = select(Product)
    try:
        stmt = stmt.where(Product.id == UUID(product_id))
    except ValueError:
        stmt = stmt.where(Product.sku == product_id)

    result = await db.execute(stmt)
    p = result.scalar_one_or_none()
    if not p:
        return {"status": "FAILED", "error": "Product not found"}

    engine = PolicyEngine(db)
    calc = await engine.calculate_discount(
        merchant_id=merchant_id,
        original_price=float(p.price),
        requested_discount_amount=args.get("requested_discount_amount"),
        requested_discount_percent=args.get("requested_discount_percent"),
    )

    return {
        "status": "SUCCESS",
        "original_price": calc.original_price,
        "allowed_discount": calc.allowed_discount,
        "final_price": calc.final_price,
        "discount_percent": calc.discount_percent_applied,
        "was_capped": calc.was_capped,
        "cap_reason": calc.cap_reason,
    }


async def _create_order(
    args: dict, db: AsyncSession, merchant_id: str, user_id: str, session_id: str | None
) -> dict:
    from app.commerce.orders import create_order, OrderCreationError

    try:
        order = await create_order(
            db=db,
            user_id=user_id,
            merchant_id=merchant_id,
            product_id=args["product_id"],
            quantity=args.get("quantity", 1),
            discount_amount=args.get("discount_amount", 0),
            session_id=session_id,
        )
        return {
            "status": "SUCCESS",
            "order_id": str(order.id),
            "order_status": order.status,
            "total": float(order.total),
            "currency": order.currency,
            "items": order.items,
            "policy_decision": order.policy_decision,
        }
    except OrderCreationError as e:
        return {
            "status": "BLOCKED",
            "error": str(e),
            "reason_codes": e.reason_codes,
        }


async def _get_order(args: dict, db: AsyncSession) -> dict:
    from app.commerce.orders import get_order

    order = await get_order(db, args.get("order_id", ""))
    if not order:
        return {"status": "FAILED", "error": "Order not found"}

    return {
        "status": "SUCCESS",
        "order_id": str(order.id),
        "order_status": order.status,
        "total": float(order.total),
        "currency": order.currency,
        "items": order.items,
    }


async def _cancel_order(args: dict, db: AsyncSession) -> dict:
    from app.commerce.orders import cancel_order, OrderCreationError

    try:
        order = await cancel_order(db, args.get("order_id", ""))
        return {
            "status": "SUCCESS",
            "order_id": str(order.id),
            "order_status": order.status,
        }
    except OrderCreationError as e:
        return {"status": "FAILED", "error": str(e)}