"""Policy API — view, update, and evaluate merchant policies."""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.database.models import Merchant, MerchantPolicy
from app.policy.engine import PolicyEngine
from app.policy.schemas import (
    PolicyEvaluationRequest, PolicyDecision,
    PolicyUpdateRequest, DiscountCalculationResult,
)

router = APIRouter()


# ─── Response Schemas ────────────────────────

class PolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    merchant_id: str
    max_autonomous_transaction_amount: float
    max_discount_percent: float
    max_discount_amount: float
    negotiation_enabled: bool
    auto_purchase_enabled: bool
    confirmation_threshold: float
    max_payment_attempts: int
    refund_requires_human: bool
    restricted_categories: list[str]
    restricted_products: list[str]
    version: int


# ─── Endpoints ───────────────────────────────

@router.get("/policies", response_model=PolicyResponse)
async def get_policy(
    merchant_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get the current policy for a merchant."""
    if merchant_id:
        try:
            mid = UUID(merchant_id)
        except ValueError:
            raise HTTPException(400, "Invalid merchant_id")
        stmt = (
            select(MerchantPolicy)
            .where(MerchantPolicy.merchant_id == mid)
            .order_by(desc(MerchantPolicy.version))
            .limit(1)
        )
    else:
        merchant_stmt = select(Merchant).limit(1)
        merchant_result = await db.execute(merchant_stmt)
        merchant = merchant_result.scalar_one_or_none()
        if not merchant:
            raise HTTPException(404, "No merchants found")
        stmt = (
            select(MerchantPolicy)
            .where(MerchantPolicy.merchant_id == merchant.id)
            .order_by(desc(MerchantPolicy.version))
            .limit(1)
        )

    result = await db.execute(stmt)
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, "No policy found")

    return PolicyResponse(
        id=str(policy.id),
        merchant_id=str(policy.merchant_id),
        max_autonomous_transaction_amount=float(policy.max_autonomous_transaction_amount),
        max_discount_percent=float(policy.max_discount_percent),
        max_discount_amount=float(policy.max_discount_amount),
        negotiation_enabled=policy.negotiation_enabled,
        auto_purchase_enabled=policy.auto_purchase_enabled,
        confirmation_threshold=float(policy.confirmation_threshold),
        max_payment_attempts=policy.max_payment_attempts,
        refund_requires_human=policy.refund_requires_human,
        restricted_categories=policy.restricted_categories or [],
        restricted_products=[str(p) for p in (policy.restricted_products or [])],
        version=policy.version,
    )


@router.put("/policies", response_model=PolicyResponse)
async def update_policy(
    update: PolicyUpdateRequest,
    merchant_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Update merchant policy. Creates a new version."""
    if not merchant_id:
        merchant_stmt = select(Merchant).limit(1)
        merchant_result = await db.execute(merchant_stmt)
        merchant = merchant_result.scalar_one_or_none()
        if not merchant:
            raise HTTPException(404, "No merchants found")
        merchant_id = str(merchant.id)

    try:
        mid = UUID(merchant_id)
    except ValueError:
        raise HTTPException(400, "Invalid merchant_id")

    stmt = (
        select(MerchantPolicy)
        .where(MerchantPolicy.merchant_id == mid)
        .order_by(desc(MerchantPolicy.version))
        .limit(1)
    )
    result = await db.execute(stmt)
    current = result.scalar_one_or_none()
    if not current:
        raise HTTPException(404, "No existing policy to update")

    new_policy = MerchantPolicy(
        merchant_id=mid,
        max_autonomous_transaction_amount=Decimal(str(
            update.max_autonomous_transaction_amount
            if update.max_autonomous_transaction_amount is not None
            else current.max_autonomous_transaction_amount
        )),
        max_discount_percent=Decimal(str(
            update.max_discount_percent
            if update.max_discount_percent is not None
            else current.max_discount_percent
        )),
        max_discount_amount=Decimal(str(
            update.max_discount_amount
            if update.max_discount_amount is not None
            else current.max_discount_amount
        )),
        negotiation_enabled=(
            update.negotiation_enabled
            if update.negotiation_enabled is not None
            else current.negotiation_enabled
        ),
        auto_purchase_enabled=(
            update.auto_purchase_enabled
            if update.auto_purchase_enabled is not None
            else current.auto_purchase_enabled
        ),
        confirmation_threshold=Decimal(str(
            update.confirmation_threshold
            if update.confirmation_threshold is not None
            else current.confirmation_threshold
        )),
        max_payment_attempts=(
            update.max_payment_attempts
            if update.max_payment_attempts is not None
            else current.max_payment_attempts
        ),
        refund_requires_human=(
            update.refund_requires_human
            if update.refund_requires_human is not None
            else current.refund_requires_human
        ),
        restricted_categories=(
            update.restricted_categories
            if update.restricted_categories is not None
            else current.restricted_categories
        ),
        restricted_products=(
            [UUID(p) for p in update.restricted_products]
            if update.restricted_products is not None
            else current.restricted_products
        ),
        version=current.version + 1,
    )
    db.add(new_policy)
    await db.flush()

    return PolicyResponse(
        id=str(new_policy.id),
        merchant_id=str(new_policy.merchant_id),
        max_autonomous_transaction_amount=float(new_policy.max_autonomous_transaction_amount),
        max_discount_percent=float(new_policy.max_discount_percent),
        max_discount_amount=float(new_policy.max_discount_amount),
        negotiation_enabled=new_policy.negotiation_enabled,
        auto_purchase_enabled=new_policy.auto_purchase_enabled,
        confirmation_threshold=float(new_policy.confirmation_threshold),
        max_payment_attempts=new_policy.max_payment_attempts,
        refund_requires_human=new_policy.refund_requires_human,
        restricted_categories=new_policy.restricted_categories or [],
        restricted_products=[str(p) for p in (new_policy.restricted_products or [])],
        version=new_policy.version,
    )


@router.post("/policies/evaluate", response_model=PolicyDecision)
async def evaluate_policy(
    request: PolicyEvaluationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Evaluate a policy decision. Used by agent runtime and testing."""
    engine = PolicyEngine(db)
    decision = await engine.evaluate(request)
    return decision


@router.post("/policies/calculate-discount", response_model=DiscountCalculationResult)
async def calculate_discount_endpoint(
    merchant_id: str,
    original_price: float,
    requested_discount_amount: Optional[float] = None,
    requested_discount_percent: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
):
    """Calculate a bounded discount."""
    engine = PolicyEngine(db)
    result = await engine.calculate_discount(
        merchant_id=merchant_id,
        original_price=original_price,
        requested_discount_amount=requested_discount_amount,
        requested_discount_percent=requested_discount_percent,
    )
    return result