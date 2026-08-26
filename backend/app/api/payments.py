"""Payment API — create, verify, reconcile. Fail closed on uncertainty."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.database.models import Payment, Order, Product, InventoryReservation
from app.database.enums import PaymentStatus, OrderStatus, ReservationStatus
from app.payments.razorpay_client import get_razorpay_client, RazorpayClientError
from app.payments.verification import verify_and_complete_payment, VerificationError
from app.payments.idempotency import generate_payment_idempotency_key
from app.payments.state_machine import (
    validate_payment_transition, validate_order_transition
)
from app.policy.engine import PolicyEngine
from app.policy.schemas import PolicyAction, PolicyEvaluationRequest
from app.services.recovery_service import (
    reconcile_payment, mark_payment_unknown, RecoveryError
)
from app.audit.logger import log_event, log_payment_event
from app.config.settings import get_settings

router = APIRouter()


class CreatePaymentRequest(BaseModel):
    order_id: str


class VerifyPaymentRequest(BaseModel):
    order_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    provider: str
    provider_order_id: Optional[str] = None
    provider_payment_id: Optional[str] = None
    key_id: Optional[str] = None
    amount: float
    currency: str
    status: str
    attempt_number: int
    created_at: str


def _to_response(p: Payment, key_id: Optional[str] = None) -> PaymentResponse:
    settings = get_settings()
    return PaymentResponse(
        id=str(p.id),
        order_id=str(p.order_id),
        provider=p.provider,
        provider_order_id=p.provider_order_id,
        provider_payment_id=p.provider_payment_id,
        key_id=key_id or settings.razorpay_key_id,
        amount=float(p.amount),
        currency=p.currency,
        status=p.status,
        attempt_number=p.attempt_number,
        created_at=p.created_at.isoformat(),
    )


@router.post("/payments/create", response_model=PaymentResponse)
async def create_payment(
    request: CreatePaymentRequest, db: AsyncSession = Depends(get_db)
):
    try:
        oid = UUID(request.order_id)
    except ValueError:
        raise HTTPException(400, "Invalid order_id")

    order = (await db.execute(select(Order).where(Order.id == oid))).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")

    if order.status not in (
        OrderStatus.APPROVED.value,
        OrderStatus.PAYMENT_PENDING.value,
        OrderStatus.PAYMENT_FAILED.value,
    ):
        raise HTTPException(400, f"Order status '{order.status}' does not allow payment")

    # ── DUPLICATE PROTECTION ──
    existing_payments = (await db.execute(
        select(Payment).where(Payment.order_id == oid)
    )).scalars().all()

    for p in existing_payments:
        if p.status in (
            PaymentStatus.PENDING.value,
            PaymentStatus.PROCESSING.value,
            PaymentStatus.UNKNOWN.value,
            PaymentStatus.SUCCESS.value,
        ):
            if p.status == PaymentStatus.SUCCESS.value:
                await log_event(
                    db=db, actor="payment_service",
                    action="DUPLICATE_PAYMENT_BLOCKED", status="BLOCKED",
                    resource_type="payment", resource_id=str(p.id),
                    reason_codes=["DUPLICATE_PAYMENT_BLOCKED"],
                )
                await db.commit()
            return _to_response(p)

    # ── PRICE RE-VERIFICATION ──
    for item in (order.items or []):
        prod = (await db.execute(
            select(Product).where(Product.id == UUID(item["product_id"]))
        )).scalar_one_or_none()
        if prod and abs(float(prod.price) - float(item["unit_price"])) > 0.01:
            validate_order_transition(order.status, OrderStatus.PRICE_CHANGED.value)
            order.status = OrderStatus.PRICE_CHANGED.value
            await db.commit()
            raise HTTPException(409, "Price changed — order halted for reconfirmation")

    # ── INVENTORY RESERVATION RE-CHECK ──
    now = datetime.now(timezone.utc)
    reservations = (await db.execute(
        select(InventoryReservation).where(
            InventoryReservation.order_id == oid,
            InventoryReservation.status == ReservationStatus.ACTIVE.value,
            InventoryReservation.expires_at > now,
        )
    )).scalars().all()

    if not reservations:
        validate_order_transition(order.status, OrderStatus.INVENTORY_UNAVAILABLE.value)
        order.status = OrderStatus.INVENTORY_UNAVAILABLE.value
        await db.commit()
        raise HTTPException(409, "Inventory reservation expired — order halted")

    # ── POLICY CHECK ──
    attempt_number = len(existing_payments) + 1
    engine = PolicyEngine(db)
    decision = await engine.evaluate(PolicyEvaluationRequest(
        action=PolicyAction.EXECUTE_PAYMENT,
        merchant_id=str(order.merchant_id),
        user_id=str(order.user_id),
        amount=float(order.total),
        payment_attempt=attempt_number,
    ))
    if decision.is_blocked():
        await db.commit()
        raise HTTPException(403, {
            "message": "Payment blocked by policy",
            "reason_codes": decision.reason_codes,
        })

    # ── Create Razorpay Order ──
    client = get_razorpay_client()
    try:
        rp_order = await client.create_order(
            amount_inr=float(order.total), receipt=request.order_id
        )
    except RazorpayClientError as e:
        raise HTTPException(502, f"Payment provider error: {e}")

    payment = Payment(
        order_id=oid,
        provider="razorpay",
        provider_order_id=rp_order["id"],
        amount=order.total,
        currency=order.currency,
        status=PaymentStatus.PENDING.value,
        attempt_number=attempt_number,
        idempotency_key=generate_payment_idempotency_key(
            request.order_id, attempt_number
        ),
    )
    db.add(payment)
    await db.flush()

    validate_payment_transition(payment.status, PaymentStatus.PROCESSING.value)
    payment.status = PaymentStatus.PROCESSING.value

    if order.status in (OrderStatus.APPROVED.value, OrderStatus.PAYMENT_FAILED.value):
        validate_order_transition(order.status, OrderStatus.PAYMENT_PENDING.value)
        order.status = OrderStatus.PAYMENT_PENDING.value

    await log_payment_event(
        db=db, action="CREATE_PAYMENT", order_id=str(order.id),
        payment_id=str(payment.id), status="SUCCESS",
        amount=float(payment.amount),
    )
    await db.commit()
    return _to_response(payment, key_id=client._key_id)


@router.post("/payments/verify", response_model=PaymentResponse)
async def verify_payment(
    request: VerifyPaymentRequest, db: AsyncSession = Depends(get_db)
):
    order = (await db.execute(select(Order).where(Order.id == UUID(request.order_id)))).scalar_one_or_none()
    if order and order.status == OrderStatus.PAYMENT_PENDING.value:
        validate_order_transition(order.status, OrderStatus.PAYMENT_PROCESSING.value)
        order.status = OrderStatus.PAYMENT_PROCESSING.value
        await db.flush()

    try:
        payment = await verify_and_complete_payment(
            db=db,
            order_id=request.order_id,
            razorpay_order_id=request.razorpay_order_id,
            razorpay_payment_id=request.razorpay_payment_id,
            razorpay_signature=request.razorpay_signature,
        )
    except VerificationError as e:
        await db.commit()
        raise HTTPException(400, str(e))

    await log_payment_event(
        db=db, action="PAYMENT_SUCCESS", order_id=request.order_id,
        payment_id=str(payment.id), status="SUCCESS",
        amount=float(payment.amount),
    )
    await db.commit()
    return _to_response(payment)


@router.post("/payments/{payment_id}/reconcile", response_model=PaymentResponse)
async def reconcile_payment_endpoint(
    payment_id: str, db: AsyncSession = Depends(get_db)
):
    try:
        payment = await reconcile_payment(db, payment_id)
        await db.commit()
    except RecoveryError as e:
        raise HTTPException(404, str(e))
    return _to_response(payment)


@router.post("/payments/{payment_id}/mark-unknown", response_model=PaymentResponse)
async def mark_unknown_endpoint(
    payment_id: str, db: AsyncSession = Depends(get_db)
):
    try:
        payment = await mark_payment_unknown(db, payment_id)
        await db.commit()
    except Exception as e:
        raise HTTPException(400, str(e))
    return _to_response(payment)


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(payment_id: str, db: AsyncSession = Depends(get_db)):
    try:
        pid = UUID(payment_id)
    except ValueError:
        raise HTTPException(400, "Invalid payment_id")
    payment = (await db.execute(
        select(Payment).where(Payment.id == pid)
    )).scalar_one_or_none()
    if not payment:
        raise HTTPException(404, "Payment not found")
    return _to_response(payment)