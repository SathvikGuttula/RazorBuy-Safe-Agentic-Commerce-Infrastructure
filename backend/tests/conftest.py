"""Shared test fixtures for RazorBuy."""

import pytest
from decimal import Decimal
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

from app.main import app
from app.database.connection import init_db, engine, Base, async_session_factory
from app.database.models import (
    Merchant, User, Product, Inventory, MerchantPolicy,
)


@pytest.fixture(autouse=True)
async def setup_and_clean_db():
    """Drop and recreate all tables for each test. Guarantees clean schema."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        tables = [
            "audit_events", "agent_actions", "agent_sessions",
            "inventory_reservations", "payments", "orders",
            "cart_items", "carts", "inventory",
            "merchant_policies", "products", "users", "merchants",
        ]
        for table in tables:
            try:
                await conn.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
            except Exception:
                pass


@pytest.fixture
async def client():
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session():
    """Fresh DB session for each test."""
    async with async_session_factory() as session:
        yield session


@pytest.fixture
async def seed_catalog(db_session):
    """Seed catalog data for tests that need products."""
    merchant = Merchant(name="Test Store", currency="INR", status="active")
    db_session.add(merchant)
    await db_session.flush()

    user = User(
        name="Test Buyer",
        email="buyer_catalog@test.com",
        autonomous_spending_limit=Decimal("3000.00"),
    )
    db_session.add(user)
    await db_session.flush()

    policy = MerchantPolicy(
        merchant_id=merchant.id,
        max_autonomous_transaction_amount=Decimal("3000.00"),
        max_discount_percent=Decimal("10.00"),
        max_discount_amount=Decimal("300.00"),
        negotiation_enabled=True,
        auto_purchase_enabled=True,
        confirmation_threshold=Decimal("5000.00"),
        max_payment_attempts=2,
        refund_requires_human=True,
        restricted_categories=[],
        restricted_products=[],
        version=1,
    )
    db_session.add(policy)
    await db_session.flush()

    products_data = [
        {"sku": "P101", "name": "SoundMax ANC Pro", "category": "wireless_earbuds",
         "price": 2499, "features": {"anc": True, "battery_hours": 35}, "stock": 25},
        {"sku": "P102", "name": "BassBud Lite", "category": "wireless_earbuds",
         "price": 1299, "features": {"anc": False, "battery_hours": 20}, "stock": 50},
        {"sku": "P103", "name": "NoiseFree Elite", "category": "wireless_earbuds",
         "price": 3499, "features": {"anc": True, "battery_hours": 40}, "stock": 15},
        {"sku": "P201", "name": "AudioKing OverEar", "category": "headphones",
         "price": 4999, "features": {"anc": True, "battery_hours": 50}, "stock": 12},
        {"sku": "P202", "name": "StudioMax Pro", "category": "headphones",
         "price": 7999, "features": {"anc": True, "battery_hours": 60}, "stock": 8},
        {"sku": "P301", "name": "BoomBox Mini", "category": "speakers",
         "price": 1499, "features": {"waterproof": True, "battery_hours": 12}, "stock": 35},
    ]

    for p in products_data:
        product = Product(
            merchant_id=merchant.id,
            sku=p["sku"],
            name=p["name"],
            description=f"Test product {p['sku']}",
            category=p["category"],
            price=Decimal(str(p["price"])),
            currency="INR",
            features=p["features"],
            tags=[],
            active=True,
        )
        db_session.add(product)
        await db_session.flush()

        inv = Inventory(
            product_id=product.id,
            available_quantity=p["stock"],
            reserved_quantity=0,
        )
        db_session.add(inv)

    await db_session.commit()

    return {
        "merchant_id": str(merchant.id),
        "user_id": str(user.id),
    }