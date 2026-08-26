"""
Policy Engine — the deterministic gatekeeper for all financial actions.

The LLM proposes. This engine decides.
No LLM output can override a policy decision.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import (
    MerchantPolicy, User, Product, Inventory
)
from app.policy.schemas import (
    PolicyAction, PolicyDecision, PolicyEvaluationRequest,
    DiscountCalculationResult, ReasonCode
)
from app.policy.rules import (
    check_transaction_limit,
    check_discount_limits,
    check_inventory,
    check_price_integrity,
    check_product_restrictions,
    check_payment_retry,
    check_refund_policy,
    check_auto_purchase,
    check_negotiation,
)


class PolicyEngine:
    """
    Deterministic, rule-based policy evaluation.

    Usage:
        engine = PolicyEngine(db_session)
        decision = await engine.evaluate(request)
        if decision.allowed:
            # proceed
        elif decision.requires_confirmation:
            # ask user
        else:
            # block
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Main Evaluation Entry Point ─────────

    async def evaluate(self, request: PolicyEvaluationRequest) -> PolicyDecision:
        """
        Evaluate a policy request against all applicable rules.
        This is the ONLY method the rest of the application should call.
        """
        # 1. Fetch merchant policy
        policy = await self._get_policy(request.merchant_id)
        if not policy:
            return PolicyDecision(
                allowed=False,
                reason_codes=[ReasonCode.POLICY_NOT_FOUND.value],
                details={"error": "No policy found for merchant"},
            )

        # 2. Fetch user
        user = await self._get_user(request.user_id)
        if not user:
            return PolicyDecision(
                allowed=False,
                reason_codes=[ReasonCode.USER_NOT_FOUND.value],
                policy_version=policy.version,
                details={"error": "User not found"},
            )

        # 3. Route to action-specific evaluation
        if request.action == PolicyAction.CREATE_ORDER:
            return await self._evaluate_create_order(request, policy, user)
        elif request.action == PolicyAction.APPLY_DISCOUNT:
            return await self._evaluate_apply_discount(request, policy, user)
        elif request.action == PolicyAction.NEGOTIATE_PRICE:
            return await self._evaluate_negotiate(request, policy, user)
        elif request.action == PolicyAction.EXECUTE_PAYMENT:
            return await self._evaluate_execute_payment(request, policy, user)
        elif request.action == PolicyAction.REQUEST_REFUND:
            return await self._evaluate_refund(request, policy, user)
        elif request.action == PolicyAction.CANCEL_ORDER:
            return self._evaluate_cancel(request, policy)
        else:
            return PolicyDecision(
                allowed=False,
                reason_codes=["UNKNOWN_ACTION"],
                policy_version=policy.version,
            )

    # ─── Discount Calculation (for agent tool) ─

    async def calculate_discount(
        self,
        merchant_id: str,
        original_price: float,
        requested_discount_amount: Optional[float] = None,
        requested_discount_percent: Optional[float] = None,
    ) -> DiscountCalculationResult:
        """
        Calculate a bounded discount. Used by the agent's calculate_offer tool.
        The LLM proposes a discount; this function caps it to policy limits.
        """
        policy = await self._get_policy(merchant_id)
        if not policy:
            return DiscountCalculationResult(
                original_price=original_price,
                requested_discount=requested_discount_amount or 0,
                allowed_discount=0,
                final_price=original_price,
                discount_percent_applied=0,
                was_capped=True,
                cap_reason="No policy found",
                reason_codes=[ReasonCode.POLICY_NOT_FOUND.value],
            )

        # Check if negotiation is even allowed
        neg_allowed, neg_reasons = check_negotiation(policy.negotiation_enabled)
        if not neg_allowed:
            return DiscountCalculationResult(
                original_price=original_price,
                requested_discount=requested_discount_amount or 0,
                allowed_discount=0,
                final_price=original_price,
                discount_percent_applied=0,
                was_capped=True,
                cap_reason="Negotiation disabled",
                reason_codes=neg_reasons,
            )

        allowed, was_capped, reasons = check_discount_limits(
            original_price=original_price,
            requested_discount_amount=requested_discount_amount,
            requested_discount_percent=requested_discount_percent,
            max_discount_percent=float(policy.max_discount_percent),
            max_discount_amount=float(policy.max_discount_amount),
        )

        final_price = round(original_price - allowed, 2)
        pct_applied = round((allowed / original_price) * 100, 2) if original_price > 0 else 0

        cap_reason = None
        if was_capped:
            max_from_pct = original_price * (float(policy.max_discount_percent) / 100)
            if max_from_pct < float(policy.max_discount_amount):
                cap_reason = f"Capped by percent limit ({policy.max_discount_percent}%)"
            else:
                cap_reason = f"Capped by amount limit (₹{policy.max_discount_amount})"

        return DiscountCalculationResult(
            original_price=original_price,
            requested_discount=requested_discount_amount or (
                original_price * (requested_discount_percent or 0) / 100
            ),
            allowed_discount=allowed,
            final_price=final_price,
            discount_percent_applied=pct_applied,
            was_capped=was_capped,
            cap_reason=cap_reason,
            reason_codes=reasons,
        )

    # ─── Action-Specific Evaluators ──────────

    async def _evaluate_create_order(
        self, request: PolicyEvaluationRequest, policy: MerchantPolicy, user: User
    ) -> PolicyDecision:
        """Evaluate a CREATE_ORDER request against all applicable rules."""
        all_reasons = []
        blocked = False
        requires_confirmation = False

        amount = request.amount or 0

        # Rule 1: Transaction limit
        txn_allowed, txn_confirm, txn_reasons = check_transaction_limit(
            amount=amount,
            merchant_max=float(policy.max_autonomous_transaction_amount),
            user_max=float(user.autonomous_spending_limit),
            confirmation_threshold=float(policy.confirmation_threshold),
        )
        all_reasons.extend(txn_reasons)
        if not txn_allowed:
            if txn_confirm:
                requires_confirmation = True
            else:
                blocked = True

        # Rule 2: Product/category restrictions
        if request.product_id and request.product_category:
            restricted_products = [
                str(p) for p in (policy.restricted_products or [])
            ]
            rest_allowed, rest_reasons = check_product_restrictions(
                product_id=request.product_id,
                product_category=request.product_category,
                restricted_products=restricted_products,
                restricted_categories=policy.restricted_categories or [],
            )
            all_reasons.extend(rest_reasons)
            if not rest_allowed:
                blocked = True

        # Rule 3: Inventory check
        if request.product_id:
            inv = await self._get_inventory(request.product_id)
            if inv:
                inv_allowed, inv_reasons = check_inventory(
                    available_quantity=inv.available_quantity,
                    reserved_quantity=inv.reserved_quantity,
                    required_quantity=request.quantity,
                )
                all_reasons.extend(inv_reasons)
                if not inv_allowed:
                    blocked = True
            else:
                all_reasons.append(ReasonCode.INVENTORY_UNAVAILABLE.value)
                blocked = True

        # Rule 4: Price integrity (if original_price is provided)
        if request.product_id and request.original_price is not None:
            product = await self._get_product(request.product_id)
            if product:
                price_allowed, price_reasons = check_price_integrity(
                    authoritative_price=float(product.price),
                    proposed_price=request.original_price,
                )
                all_reasons.extend(price_reasons)
                if not price_allowed:
                    blocked = True

        # Rule 5: Auto-purchase check
        if not blocked and not requires_confirmation:
            auto_allowed, auto_reasons = check_auto_purchase(
                policy.auto_purchase_enabled
            )
            all_reasons.extend(auto_reasons)
            if not auto_allowed:
                requires_confirmation = True

        return PolicyDecision(
            allowed=not blocked and not requires_confirmation,
            requires_confirmation=requires_confirmation and not blocked,
            requires_human_review=False,
            reason_codes=all_reasons,
            policy_version=policy.version,
            details={
                "amount": amount,
                "merchant_limit": float(policy.max_autonomous_transaction_amount),
                "user_limit": float(user.autonomous_spending_limit),
            },
        )

    async def _evaluate_apply_discount(
        self, request: PolicyEvaluationRequest, policy: MerchantPolicy, user: User
    ) -> PolicyDecision:
        """Evaluate an APPLY_DISCOUNT request."""
        all_reasons = []
        blocked = False

        # Check negotiation enabled
        neg_allowed, neg_reasons = check_negotiation(policy.negotiation_enabled)
        all_reasons.extend(neg_reasons)
        if not neg_allowed:
            blocked = True

        # Check discount limits
        if not blocked and request.original_price:
            _, was_capped, disc_reasons = check_discount_limits(
                original_price=request.original_price,
                requested_discount_amount=request.discount_amount,
                requested_discount_percent=request.discount_percent,
                max_discount_percent=float(policy.max_discount_percent),
                max_discount_amount=float(policy.max_discount_amount),
            )
            all_reasons.extend(disc_reasons)
            # Note: discount exceeding limits is capped, not blocked.
            # But if the agent insists on the uncapped amount, it's blocked.
            # The calculate_discount method handles capping.
            # Here we just check if the requested discount is within limits.
            if was_capped:
                # The discount was too high — the engine will cap it,
                # but the action itself is "allowed with modification"
                pass

        return PolicyDecision(
            allowed=not blocked,
            reason_codes=all_reasons,
            policy_version=policy.version,
        )

    async def _evaluate_negotiate(
        self, request: PolicyEvaluationRequest, policy: MerchantPolicy, user: User
    ) -> PolicyDecision:
        """Evaluate a NEGOTIATE_PRICE request (same as discount)."""
        return await self._evaluate_apply_discount(request, policy, user)

    async def _evaluate_execute_payment(
        self, request: PolicyEvaluationRequest, policy: MerchantPolicy, user: User
    ) -> PolicyDecision:
        """Evaluate an EXECUTE_PAYMENT request."""
        all_reasons = []
        blocked = False

        amount = request.amount or 0

        # Rule 1: Transaction limit
        txn_allowed, txn_confirm, txn_reasons = check_transaction_limit(
            amount=amount,
            merchant_max=float(policy.max_autonomous_transaction_amount),
            user_max=float(user.autonomous_spending_limit),
            confirmation_threshold=float(policy.confirmation_threshold),
        )
        all_reasons.extend(txn_reasons)
        if not txn_allowed and not txn_confirm:
            blocked = True

        # Rule 2: Payment retry limit
        if request.payment_attempt is not None:
            retry_allowed, retry_reasons = check_payment_retry(
                attempt_number=request.payment_attempt,
                max_attempts=policy.max_payment_attempts,
            )
            all_reasons.extend(retry_reasons)
            if not retry_allowed:
                blocked = True

        return PolicyDecision(
            allowed=not blocked,
            requires_confirmation=txn_confirm and not blocked,
            reason_codes=all_reasons,
            policy_version=policy.version,
        )

    async def _evaluate_refund(
        self, request: PolicyEvaluationRequest, policy: MerchantPolicy, user: User
    ) -> PolicyDecision:
        """Evaluate a REQUEST_REFUND request."""
        allowed, requires_human, reasons = check_refund_policy(
            policy.refund_requires_human
        )

        return PolicyDecision(
            allowed=allowed,
            requires_human_review=requires_human,
            reason_codes=reasons,
            policy_version=policy.version,
        )

    def _evaluate_cancel(
        self, request: PolicyEvaluationRequest, policy: MerchantPolicy
    ) -> PolicyDecision:
        """Cancel is generally allowed. No special policy rules."""
        return PolicyDecision(
            allowed=True,
            reason_codes=["CANCEL_ALLOWED"],
            policy_version=policy.version,
        )

    # ─── Database Helpers ────────────────────

    async def _get_policy(self, merchant_id: str) -> Optional[MerchantPolicy]:
        """Fetch the latest policy version for a merchant."""
        try:
            mid = UUID(merchant_id)
        except ValueError:
            return None

        stmt = (
            select(MerchantPolicy)
            .where(MerchantPolicy.merchant_id == mid)
            .order_by(desc(MerchantPolicy.version))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_user(self, user_id: str) -> Optional[User]:
        """Fetch a user by ID."""
        try:
            uid = UUID(user_id)
        except ValueError:
            return None

        stmt = select(User).where(User.id == uid)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_product(self, product_id: str) -> Optional[Product]:
        """Fetch a product by UUID or SKU."""
        stmt = select(Product)
        try:
            uid = UUID(product_id)
            stmt = stmt.where(Product.id == uid)
        except ValueError:
            stmt = stmt.where(Product.sku == product_id)

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_inventory(self, product_id: str) -> Optional[Inventory]:
        """Fetch inventory for a product."""
        product = await self._get_product(product_id)
        if not product:
            return None

        stmt = select(Inventory).where(Inventory.product_id == product.id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()