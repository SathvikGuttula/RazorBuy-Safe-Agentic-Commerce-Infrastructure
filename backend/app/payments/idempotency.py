"""Idempotency keys for financial operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Payment, Order


async def check_payment_idempotency(db: AsyncSession, idempotency_key: str) -> Payment | None:
    result = await db.execute(select(Payment).where(Payment.idempotency_key == idempotency_key))
    return result.scalar_one_or_none()


async def check_order_idempotency(db: AsyncSession, idempotency_key: str) -> Order | None:
    result = await db.execute(select(Order).where(Order.idempotency_key == idempotency_key))
    return result.scalar_one_or_none()


def generate_payment_idempotency_key(order_id: str, attempt: int) -> str:
    return f"order_{order_id}_payment_attempt_{attempt}"


def generate_order_idempotency_key(
    user_id: str,
    product_id: str,
    quantity: int,
    discount_amount: float = 0.0,
    client_key: str | None = None,
) -> str:
    """Deterministic order key. Optional client_key makes each caller unique."""
    if client_key:
        return f"client_{client_key}"
    d = f"{float(discount_amount):.2f}"
    return f"user_{user_id}_product_{product_id}_qty_{quantity}_d_{d}"