"""Order API — create, retrieve, confirm, and cancel orders."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.database.models import Merchant, User
from app.database.enums import OrderStatus
from app.commerce.orders import (
    create_order, get_order, cancel_order, OrderCreationError
)
from app.payments.state_machine import validate_order_transition
from app.audit.logger import log_event

router = APIRouter()


class CreateOrderRequest(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1, le=1000)  # allow large qty for inventory tests
    discount_amount: float = Field(default=0.0, ge=0)
    user_id: Optional[str] = None
    merchant_id: Optional[str] = None
    session_id: Optional[str] = None
    idempotency_key: Optional[str] = None  # client-supplied unique key

class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    subtotal: float
    discount: float
    total: float
    currency: str
    items: list
    idempotency_key: Optional[str] = None
    policy_decision: Optional[dict] = None
    created_at: str


class CancelOrderRequest(BaseModel):
    reason: str = Field(default="User cancelled", max_length=500)


async def _get_default_ids(db: AsyncSession) -> tuple[str, str]:
    m = (await db.execute(select(Merchant).limit(1))).scalar_one_or_none()
    u = (await db.execute(select(User).limit(1))).scalar_one_or_none()
    if not m or not u:
        raise HTTPException(404, "No merchant or user found. Run seed_db.py")
    return str(m.id), str(u.id)


def _to_response(order) -> OrderResponse:
    return OrderResponse(
        id=str(order.id),
        status=order.status,
        subtotal=float(order.subtotal),
        discount=float(order.discount),
        total=float(order.total),
        currency=order.currency,
        items=order.items,
        idempotency_key=order.idempotency_key,
        policy_decision=order.policy_decision,
        created_at=order.created_at.isoformat(),
    )


@router.post("/orders", response_model=OrderResponse)
async def create_order_endpoint(
    request: CreateOrderRequest,
    db: AsyncSession = Depends(get_db),
):
    merchant_id, user_id = request.merchant_id, request.user_id
    if not merchant_id or not user_id:
        merchant_id, user_id = await _get_default_ids(db)

    try:
        order = await create_order(
            db=db, user_id=user_id, merchant_id=merchant_id,
            product_id=request.product_id, quantity=request.quantity,
            discount_amount=request.discount_amount,
            session_id=request.session_id,
            client_idempotency_key=request.idempotency_key,
        )
        await db.commit()
    except OrderCreationError as e:
        await db.commit()  # persist audit events
        raise HTTPException(
            status_code=400,
            detail={"message": str(e), "reason_codes": e.reason_codes},
        )
    return _to_response(order)


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order_endpoint(order_id: str, db: AsyncSession = Depends(get_db)):
    order = await get_order(db, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return _to_response(order)


@router.post("/orders/{order_id}/confirm", response_model=OrderResponse)
async def confirm_order_endpoint(order_id: str, db: AsyncSession = Depends(get_db)):
    """User explicitly confirms an order that was AWAITING_CONFIRMATION."""
    order = await get_order(db, order_id)
    if not order:
        raise HTTPException(404, "Order not found")

    try:
        validate_order_transition(order.status, OrderStatus.APPROVED.value)
    except Exception as e:
        raise HTTPException(400, str(e))

    order.status = OrderStatus.APPROVED.value
    await db.flush()

    await log_event(
        db=db, actor="user", action="CONFIRM_ORDER", status="SUCCESS",
        resource_type="order", resource_id=str(order.id), result="APPROVED",
    )
    await db.commit()
    return _to_response(order)


@router.post("/orders/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order_endpoint(
    order_id: str,
    request: CancelOrderRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        order = await cancel_order(db, order_id)
        await db.commit()
    except Exception as e:
        raise HTTPException(400, str(e))
    return _to_response(order)