"""Order service — policy, discount cap, inventory, audit."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import Order, Product, Inventory, InventoryReservation
from app.database.enums import OrderStatus, ReservationStatus
from app.payments.state_machine import validate_order_transition
from app.payments.idempotency import check_order_idempotency, generate_order_idempotency_key
from app.policy.engine import PolicyEngine
from app.policy.schemas import PolicyAction, PolicyEvaluationRequest
from app.audit.logger import log_event, log_policy_decision
from app.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class OrderCreationError(Exception):
    def __init__(self, message: str, reason_codes: list[str] | None = None):
        self.reason_codes = reason_codes or []
        super().__init__(message)


async def create_order(
    db: AsyncSession,
    user_id: str,
    merchant_id: str,
    product_id: str,
    quantity: int,
    discount_amount: float = 0.0,
    session_id: Optional[str] = None,
    client_idempotency_key: Optional[str] = None,
) -> Order:
    try:
        uid = uuid.UUID(user_id)
        mid = uuid.UUID(merchant_id)
    except ValueError:
        raise OrderCreationError("Invalid user or merchant ID format", ["INVALID_ID"])

    stmt = select(Product).options(selectinload(Product.inventory))
    try:
        stmt = stmt.where(Product.id == uuid.UUID(product_id))
    except ValueError:
        stmt = stmt.where(Product.sku == product_id)

    product = (await db.execute(stmt)).scalar_one_or_none()
    if not product:
        raise OrderCreationError("Product not found", ["PRODUCT_NOT_FOUND"])
    if not product.active:
        raise OrderCreationError("Product is inactive", ["PRODUCT_INACTIVE"])

    authoritative_price = float(product.price)

    idempotency_key = generate_order_idempotency_key(
        str(uid), str(product.id), quantity, discount_amount, client_idempotency_key
    )
    existing = await check_order_idempotency(db, idempotency_key)
    if existing:
        return existing

    policy_engine = PolicyEngine(db)
    subtotal_float = authoritative_price * quantity
    capped_discount = 0.0
    discount_capped = False

    if discount_amount and discount_amount > 0:
        calc = await policy_engine.calculate_discount(
            merchant_id=str(mid),
            original_price=subtotal_float,
            requested_discount_amount=discount_amount,
        )
        capped_discount = calc.allowed_discount
        discount_capped = calc.was_capped

    total_amount = subtotal_float - capped_discount
    decision = await policy_engine.evaluate(PolicyEvaluationRequest(
        action=PolicyAction.CREATE_ORDER,
        merchant_id=str(mid),
        user_id=str(uid),
        amount=total_amount,
        original_price=authoritative_price,
        discount_amount=capped_discount,
        product_id=str(product.id),
        product_category=product.category,
        quantity=quantity,
    ))

    if decision.is_blocked():
        await log_policy_decision(
            db=db, action="CREATE_ORDER", resource_type="product",
            resource_id=str(product.id),
            decision=decision.model_dump(mode="json"),
            session_id=session_id,
        )
        raise OrderCreationError(
            f"Policy blocked: {', '.join(decision.reason_codes)}",
            decision.reason_codes,
        )

    inv = product.inventory
    if not inv or inv.available_quantity < quantity:
        raise OrderCreationError("Insufficient inventory", ["INVENTORY_UNAVAILABLE"])

    inv.available_quantity -= quantity
    inv.reserved_quantity += quantity

    subtotal = Decimal(str(subtotal_float))
    discount = Decimal(str(min(capped_discount, subtotal_float)))
    total = subtotal - discount

    order_status = (
        OrderStatus.APPROVED.value if decision.allowed
        else OrderStatus.AWAITING_CONFIRMATION.value
    )

    decision_dict = decision.model_dump(mode="json")
    if discount_capped:
        decision_dict.setdefault("details", {})["discount_capped"] = True
        decision_dict["details"]["requested_discount"] = discount_amount
        decision_dict["details"]["capped_discount"] = capped_discount

    order = Order(
        merchant_id=mid,
        user_id=uid,
        items=[{
            "product_id": str(product.id),
            "sku": product.sku,
            "name": product.name,
            "quantity": quantity,
            "unit_price": authoritative_price,
            "subtotal": float(subtotal),
        }],
        subtotal=subtotal,
        discount=discount,
        total=total,
        currency=product.currency,
        status=order_status,
        idempotency_key=idempotency_key,
        policy_decision=decision_dict,
        session_id=uuid.UUID(session_id) if session_id else None,
    )
    db.add(order)
    await db.flush()

    db.add(InventoryReservation(
        order_id=order.id,
        product_id=product.id,
        quantity=quantity,
        expires_at=datetime.now(timezone.utc) + timedelta(
            minutes=settings.inventory_reservation_minutes
        ),
    ))
    await db.flush()

    await log_event(
        db=db, actor="order_service", action="CREATE_ORDER",
        status="SUCCESS" if decision.allowed else "ESCALATED",
        session_id=session_id, resource_type="order", resource_id=str(order.id),
        input_data={"product_id": str(product.id), "quantity": quantity,
                    "requested_discount": discount_amount},
        result=order_status, policy_decision=decision_dict,
        reason_codes=decision.reason_codes,
        metadata={"total": float(total), "discount_capped": discount_capped},
    )
    return order


async def get_order(db: AsyncSession, order_id: str) -> Optional[Order]:
    try:
        oid = uuid.UUID(order_id)
    except ValueError:
        return None
    return (await db.execute(select(Order).where(Order.id == oid))).scalar_one_or_none()


async def cancel_order(db: AsyncSession, order_id: str) -> Order:
    order = await get_order(db, order_id)
    if not order:
        raise OrderCreationError("Order not found")

    validate_order_transition(order.status, OrderStatus.CANCELLED.value)
    order.status = OrderStatus.CANCELLED.value

    res_result = await db.execute(
        select(InventoryReservation).where(InventoryReservation.order_id == order.id)
    )
    for res in res_result.scalars().all():
        if res.status == ReservationStatus.ACTIVE.value:
            res.status = ReservationStatus.RELEASED.value
            inv = (await db.execute(
                select(Inventory).where(Inventory.product_id == res.product_id)
            )).scalar_one_or_none()
            if inv:
                inv.available_quantity += res.quantity
                inv.reserved_quantity -= res.quantity

    await db.flush()
    await log_event(
        db=db, actor="order_service", action="CANCEL_ORDER", status="SUCCESS",
        resource_type="order", resource_id=str(order.id), result="CANCELLED",
    )
    return order