"""Recovery service — payment timeout reconciliation.

Core rule: if a payment times out, DO NOT assume failure and DO NOT blind-retry.
Mark UNKNOWN → query the provider → resolve the actual state → fail closed.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Payment, Order
from app.database.enums import PaymentStatus, OrderStatus
from app.payments.razorpay_client import get_razorpay_client
from app.payments.state_machine import (
    validate_payment_transition, validate_order_transition
)
from app.audit.logger import log_payment_event, log_event

logger = logging.getLogger(__name__)


class RecoveryError(Exception):
    pass


def _advance_payment_to_processing(payment: Payment) -> None:
    if payment.status == PaymentStatus.PENDING.value:
        validate_payment_transition(payment.status, PaymentStatus.PROCESSING.value)
        payment.status = PaymentStatus.PROCESSING.value


def _advance_order_to_processing(order: Order) -> None:
    if order.status == OrderStatus.PAYMENT_PENDING.value:
        validate_order_transition(order.status, OrderStatus.PAYMENT_PROCESSING.value)
        order.status = OrderStatus.PAYMENT_PROCESSING.value


async def mark_payment_unknown(db: AsyncSession, payment_id: str) -> Payment:
    """
    DEMO/TEST UTILITY — simulates a payment timeout.
    Transitions PROCESSING → UNKNOWN. In production this would be done
    by the timeout handler, never by an endpoint.
    """
    payment = await _get_payment(db, payment_id)
    validate_payment_transition(payment.status, PaymentStatus.UNKNOWN.value)
    payment.status = PaymentStatus.UNKNOWN.value
    payment.error_code = "TIMEOUT"
    payment.error_description = "Payment request timed out — status unknown"

    order = await _get_order(db, str(payment.order_id))
    _advance_order_to_processing(order)
    validate_order_transition(order.status, OrderStatus.PAYMENT_UNKNOWN.value)
    order.status = OrderStatus.PAYMENT_UNKNOWN.value

    await db.flush()

    await log_payment_event(
        db=db, action="PAYMENT_TIMEOUT", order_id=str(payment.order_id),
        payment_id=str(payment.id), status="PENDING",
        amount=float(payment.amount), error="TIMEOUT",
    )
    return payment


async def reconcile_payment(db: AsyncSession, payment_id: str) -> Payment:
    """
    Resolve an UNKNOWN/stuck payment by querying the provider.
    Never creates a duplicate payment. Fails closed if still unknown.
    """
    payment = await _get_payment(db, payment_id)
    order = await _get_order(db, str(payment.order_id))

    if payment.status not in (
        PaymentStatus.UNKNOWN.value,
        PaymentStatus.PROCESSING.value,
        PaymentStatus.PENDING.value,
    ):
        return payment  # already resolved — idempotent

    if not payment.provider_order_id:
        raise RecoveryError("Payment has no provider order id to reconcile")

    client = get_razorpay_client()
    try:
        provider_order = await client.fetch_order(payment.provider_order_id)
    except Exception as e:
        # Provider unreachable — stay UNKNOWN, escalate. Fail closed.
        await log_event(
            db=db, actor="payment_service", action="RECONCILE_PAYMENT",
            status="ESCALATED", resource_type="payment",
            resource_id=str(payment.id), result="STILL_UNKNOWN",
            reason_codes=["PROVIDER_UNREACHABLE"],
        )
        return payment

    provider_status = str(provider_order.get("status", "")).lower()

    _advance_payment_to_processing(payment)
    _advance_order_to_processing(order)

    if provider_status == "paid":
        validate_payment_transition(payment.status, PaymentStatus.SUCCESS.value)
        payment.status = PaymentStatus.SUCCESS.value
        payment.error_code = None
        payment.error_description = None

        if order.status == OrderStatus.PAYMENT_UNKNOWN.value:
            validate_order_transition(order.status, OrderStatus.PAID.value)
        else:
            validate_order_transition(order.status, OrderStatus.PAID.value)
        order.status = OrderStatus.PAID.value

        await log_payment_event(
            db=db, action="PAYMENT_SUCCESS", order_id=str(order.id),
            payment_id=str(payment.id), status="SUCCESS",
            amount=float(payment.amount),
        )
    elif provider_status in ("created", "attempted"):
        # No successful payment at provider → safe to mark FAILED.
        validate_payment_transition(payment.status, PaymentStatus.FAILED.value)
        payment.status = PaymentStatus.FAILED.value
        payment.error_code = "NOT_PAID_AT_PROVIDER"
        payment.error_description = f"Provider order status: {provider_status}"

        if order.status == OrderStatus.PAYMENT_UNKNOWN.value:
            validate_order_transition(order.status, OrderStatus.PAYMENT_FAILED.value)
            order.status = OrderStatus.PAYMENT_FAILED.value
        elif order.status == OrderStatus.PAYMENT_PROCESSING.value:
            validate_order_transition(order.status, OrderStatus.PAYMENT_FAILED.value)
            order.status = OrderStatus.PAYMENT_FAILED.value

        await log_payment_event(
            db=db, action="PAYMENT_FAILED", order_id=str(order.id),
            payment_id=str(payment.id), status="FAILED",
            amount=float(payment.amount), error="NOT_PAID_AT_PROVIDER",
        )
    else:
        # Genuinely unknown — do NOT retry blindly. Escalate.
        await log_event(
            db=db, actor="payment_service", action="RECONCILE_PAYMENT",
            status="ESCALATED", resource_type="payment",
            resource_id=str(payment.id), result="STILL_UNKNOWN",
            reason_codes=["PROVIDER_STATUS_AMBIGUOUS"],
            metadata={"provider_status": provider_status},
        )

    await db.flush()
    return payment


async def _get_payment(db: AsyncSession, payment_id: str) -> Payment:
    try:
        pid = uuid.UUID(payment_id)
    except ValueError:
        raise RecoveryError("Invalid payment_id")
    result = await db.execute(select(Payment).where(Payment.id == pid))
    payment = result.scalar_one_or_none()
    if not payment:
        raise RecoveryError("Payment not found")
    return payment


async def _get_order(db: AsyncSession, order_id: str) -> Order:
    result = await db.execute(
        select(Order).where(Order.id == uuid.UUID(order_id))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise RecoveryError("Order not found")
    return order