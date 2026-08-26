"""Tests for order creation, policy enforcement, and inventory reservation."""

import pytest
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.database.models import (
    Merchant, User, Product, Inventory, MerchantPolicy, Order,
    InventoryReservation,
)
from app.database.enums import OrderStatus, ReservationStatus
from app.commerce.orders import create_order, cancel_order, OrderCreationError


@pytest.fixture
async def order_data(db_session):
    """Set up data for order tests. Policy limit = 10000 to allow multi-qty."""
    merchant = Merchant(name="Order Test Store", currency="INR", status="active")
    db_session.add(merchant)
    await db_session.flush()

    user = User(
        name="Order Test User",
        email=f"ordertest_{uuid4().hex[:8]}@test.com",
        autonomous_spending_limit=Decimal("10000.00"),
    )
    db_session.add(user)
    await db_session.flush()

    policy = MerchantPolicy(
        merchant_id=merchant.id,
        max_autonomous_transaction_amount=Decimal("10000.00"),
        max_discount_percent=Decimal("10.00"),
        max_discount_amount=Decimal("300.00"),
        negotiation_enabled=True,
        auto_purchase_enabled=True,
        confirmation_threshold=Decimal("15000.00"),
        max_payment_attempts=2,
        refund_requires_human=True,
        restricted_categories=["restricted"],
        restricted_products=[],
        version=1,
    )
    db_session.add(policy)
    await db_session.flush()

    product = Product(
        merchant_id=merchant.id,
        sku=f"ORD_{uuid4().hex[:6]}",
        name="Order Test Product",
        category="electronics",
        price=Decimal("2000.00"),
        features={"anc": True},
    )
    db_session.add(product)
    await db_session.flush()

    inventory = Inventory(
        product_id=product.id,
        available_quantity=10,
        reserved_quantity=0,
    )
    db_session.add(inventory)
    await db_session.commit()

    return {
        "merchant_id": str(merchant.id),
        "user_id": str(user.id),
        "product_id": str(product.id),
    }


@pytest.mark.asyncio
async def test_create_order_success(db_session, order_data):
    """Valid order within policy → APPROVED."""
    order = await create_order(
        db=db_session,
        user_id=order_data["user_id"],
        merchant_id=order_data["merchant_id"],
        product_id=order_data["product_id"],
        quantity=1,
    )
    assert order.status == OrderStatus.APPROVED.value
    assert float(order.total) == 2000.0
    assert order.idempotency_key is not None


@pytest.mark.asyncio
async def test_create_order_with_discount(db_session, order_data):
    """Order with valid discount → correct total."""
    order = await create_order(
        db=db_session,
        user_id=order_data["user_id"],
        merchant_id=order_data["merchant_id"],
        product_id=order_data["product_id"],
        quantity=1,
        discount_amount=100.0,
    )
    assert float(order.total) == 1900.0
    assert float(order.discount) == 100.0


@pytest.mark.asyncio
async def test_create_order_inventory_reserved(db_session, order_data):
    """Creating an order should reserve inventory."""
    from uuid import UUID

    order = await create_order(
        db=db_session,
        user_id=order_data["user_id"],
        merchant_id=order_data["merchant_id"],
        product_id=order_data["product_id"],
        quantity=3,
    )
    assert order.status == OrderStatus.APPROVED.value

    inv_stmt = select(Inventory).where(
        Inventory.product_id == UUID(order_data["product_id"])
    )
    inv_result = await db_session.execute(inv_stmt)
    inv = inv_result.scalar_one_or_none()
    assert inv.available_quantity == 7
    assert inv.reserved_quantity == 3


@pytest.mark.asyncio
async def test_create_order_insufficient_inventory(db_session, order_data):
    """Order with quantity > inventory → blocked."""
    with pytest.raises(OrderCreationError) as exc_info:
        await create_order(
            db=db_session,
            user_id=order_data["user_id"],
            merchant_id=order_data["merchant_id"],
            product_id=order_data["product_id"],
            quantity=999,
        )
    assert "INVENTORY_UNAVAILABLE" in exc_info.value.reason_codes


@pytest.mark.asyncio
async def test_create_order_exceeds_limit(db_session, order_data):
    """Order amount > autonomous limit → AWAITING_CONFIRMATION."""
    order = await create_order(
        db=db_session,
        user_id=order_data["user_id"],
        merchant_id=order_data["merchant_id"],
        product_id=order_data["product_id"],
        quantity=6,  # 6 × 2000 = 12000 > 10000 limit, < 15000 threshold
    )
    assert order.status == OrderStatus.AWAITING_CONFIRMATION.value


@pytest.mark.asyncio
async def test_create_order_idempotent(db_session, order_data):
    """Same order request twice → returns same order."""
    order1 = await create_order(
        db=db_session,
        user_id=order_data["user_id"],
        merchant_id=order_data["merchant_id"],
        product_id=order_data["product_id"],
        quantity=1,
    )
    order2 = await create_order(
        db=db_session,
        user_id=order_data["user_id"],
        merchant_id=order_data["merchant_id"],
        product_id=order_data["product_id"],
        quantity=1,
    )
    assert order1.id == order2.id


@pytest.mark.asyncio
async def test_create_order_product_not_found(db_session, order_data):
    """Non-existent product → error."""
    with pytest.raises(OrderCreationError):
        await create_order(
            db=db_session,
            user_id=order_data["user_id"],
            merchant_id=order_data["merchant_id"],
            product_id=str(uuid4()),
            quantity=1,
        )


@pytest.mark.asyncio
async def test_cancel_order_releases_inventory(db_session, order_data):
    """Cancelling an order should release reserved inventory."""
    from uuid import UUID

    order = await create_order(
        db=db_session,
        user_id=order_data["user_id"],
        merchant_id=order_data["merchant_id"],
        product_id=order_data["product_id"],
        quantity=5,
    )

    cancelled = await cancel_order(db_session, str(order.id))
    assert cancelled.status == OrderStatus.CANCELLED.value

    inv_stmt = select(Inventory).where(
        Inventory.product_id == UUID(order_data["product_id"])
    )
    inv_result = await db_session.execute(inv_stmt)
    inv = inv_result.scalar_one_or_none()
    assert inv.available_quantity == 10
    assert inv.reserved_quantity == 0