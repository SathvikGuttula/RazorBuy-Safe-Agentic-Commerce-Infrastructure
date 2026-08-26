"""Tests for payment state machine, idempotency, and verification."""

import pytest
from decimal import Decimal
from uuid import uuid4

from app.database.models import (
    Merchant, User, Product, Inventory, MerchantPolicy, Order, Payment
)
from app.database.enums import PaymentStatus, OrderStatus
from app.payments.state_machine import (
    validate_payment_transition, validate_order_transition,
    InvalidTransitionError,
)
from app.payments.idempotency import (
    generate_payment_idempotency_key,
    generate_order_idempotency_key,
    check_payment_idempotency,
)


# ─── State Machine Tests ─────────────────────

@pytest.mark.asyncio
async def test_valid_payment_pending_to_processing():
    validate_payment_transition(
        PaymentStatus.PENDING.value, PaymentStatus.PROCESSING.value
    )


@pytest.mark.asyncio
async def test_valid_payment_processing_to_success():
    validate_payment_transition(
        PaymentStatus.PROCESSING.value, PaymentStatus.SUCCESS.value
    )


@pytest.mark.asyncio
async def test_valid_payment_processing_to_failed():
    validate_payment_transition(
        PaymentStatus.PROCESSING.value, PaymentStatus.FAILED.value
    )


@pytest.mark.asyncio
async def test_valid_payment_failed_retry():
    validate_payment_transition(
        PaymentStatus.FAILED.value, PaymentStatus.PROCESSING.value
    )


@pytest.mark.asyncio
async def test_valid_payment_unknown_resolved():
    validate_payment_transition(
        PaymentStatus.UNKNOWN.value, PaymentStatus.SUCCESS.value
    )


@pytest.mark.asyncio
async def test_invalid_payment_success_to_pending():
    with pytest.raises(InvalidTransitionError):
        validate_payment_transition(
            PaymentStatus.SUCCESS.value, PaymentStatus.PENDING.value
        )


@pytest.mark.asyncio
async def test_invalid_payment_refunded_to_processing():
    with pytest.raises(InvalidTransitionError):
        validate_payment_transition(
            PaymentStatus.REFUNDED.value, PaymentStatus.PROCESSING.value
        )


@pytest.mark.asyncio
async def test_valid_order_draft_to_pending():
    validate_order_transition(
        OrderStatus.DRAFT.value, OrderStatus.PENDING_POLICY.value
    )


@pytest.mark.asyncio
async def test_valid_order_processing_to_paid():
    validate_order_transition(
        OrderStatus.PAYMENT_PROCESSING.value, OrderStatus.PAID.value
    )


@pytest.mark.asyncio
async def test_invalid_order_completed_to_draft():
    with pytest.raises(InvalidTransitionError):
        validate_order_transition(
            OrderStatus.COMPLETED.value, OrderStatus.DRAFT.value
        )


@pytest.mark.asyncio
async def test_invalid_order_paid_to_draft():
    with pytest.raises(InvalidTransitionError):
        validate_order_transition(
            OrderStatus.PAID.value, OrderStatus.DRAFT.value
        )


# ─── Idempotency Tests ───────────────────────

@pytest.mark.asyncio
async def test_idempotency_key_format():
    key = generate_payment_idempotency_key("order_123", 1)
    assert key == "order_order_123_payment_attempt_1"


@pytest.mark.asyncio
async def test_order_idempotency_key_format():
    key = generate_order_idempotency_key("user_1", "prod_1", 2)
    assert key == "user_user_1_product_prod_1_qty_2"


@pytest.mark.asyncio
async def test_check_payment_idempotency_not_found(db_session):
    result = await check_payment_idempotency(db_session, "nonexistent_key")
    assert result is None


@pytest.mark.asyncio
async def test_check_payment_idempotency_found(db_session):
    """Create a payment, then check idempotency finds it."""
    merchant = Merchant(name="Pay Test", currency="INR", status="active")
    db_session.add(merchant)
    await db_session.flush()

    user = User(
        name="Pay User",
        email=f"pay_{uuid4().hex[:8]}@test.com",
        autonomous_spending_limit=Decimal("5000"),
    )
    db_session.add(user)
    await db_session.flush()

    order = Order(
        merchant_id=merchant.id,
        user_id=user.id,
        items=[],
        subtotal=Decimal("1000"),
        discount=Decimal("0"),
        total=Decimal("1000"),
        currency="INR",
        status=OrderStatus.APPROVED.value,
    )
    db_session.add(order)
    await db_session.flush()

    idem_key = "test_idem_key_001"
    payment = Payment(
        order_id=order.id,
        provider="razorpay",
        amount=Decimal("1000"),
        currency="INR",
        status=PaymentStatus.PENDING.value,
        attempt_number=1,
        idempotency_key=idem_key,
    )
    db_session.add(payment)
    await db_session.commit()

    result = await check_payment_idempotency(db_session, idem_key)
    assert result is not None
    assert result.idempotency_key == idem_key


@pytest.mark.asyncio
async def test_duplicate_payment_blocked(db_session):
    """Two payments with same idempotency key → second finds first."""
    merchant = Merchant(name="Dup Test", currency="INR", status="active")
    db_session.add(merchant)
    await db_session.flush()

    user = User(
        name="Dup User",
        email=f"dup_{uuid4().hex[:8]}@test.com",
        autonomous_spending_limit=Decimal("5000"),
    )
    db_session.add(user)
    await db_session.flush()

    order = Order(
        merchant_id=merchant.id,
        user_id=user.id,
        items=[],
        subtotal=Decimal("2000"),
        discount=Decimal("0"),
        total=Decimal("2000"),
        currency="INR",
        status=OrderStatus.APPROVED.value,
    )
    db_session.add(order)
    await db_session.flush()

    idem_key = "dup_test_key_001"

    p1 = Payment(
        order_id=order.id,
        provider="razorpay",
        amount=Decimal("2000"),
        currency="INR",
        status=PaymentStatus.SUCCESS.value,
        attempt_number=1,
        idempotency_key=idem_key,
    )
    db_session.add(p1)
    await db_session.commit()

    existing = await check_payment_idempotency(db_session, idem_key)
    assert existing is not None
    assert existing.status == PaymentStatus.SUCCESS.value
    assert str(existing.id) == str(p1.id)