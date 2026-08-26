"""
Deterministic policy rules.

Each rule is a pure function: input → (allowed, reason_codes).
No LLM involvement. No database access. No side effects.
These functions receive already-fetched data and apply business logic.
"""

from decimal import Decimal
from typing import Optional

from app.policy.schemas import ReasonCode


def check_transaction_limit(
    amount: float,
    merchant_max: float,
    user_max: float,
    confirmation_threshold: float,
) -> tuple[bool, bool, list[str]]:
    """
    Check if the transaction amount is within limits.

    Returns: (allowed, requires_confirmation, reason_codes)

    Logic:
    - amount <= min(merchant_max, user_max): allowed
    - amount > confirmation_threshold: requires confirmation
    - amount > merchant_max or user_max: blocked
    """
    reasons = []

    if amount <= 0:
        return False, False, [ReasonCode.INVALID_AMOUNT.value]

    effective_limit = min(merchant_max, user_max)

    if amount > merchant_max:
        reasons.append(ReasonCode.AMOUNT_EXCEEDS_MERCHANT_LIMIT.value)
    else:
        reasons.append(ReasonCode.WITHIN_TRANSACTION_LIMIT.value)

    if amount > user_max:
        reasons.append(ReasonCode.AMOUNT_EXCEEDS_USER_LIMIT.value)

    if amount > effective_limit:
        if amount <= confirmation_threshold:
            # Between limit and threshold — could confirm
            return False, True, reasons + [ReasonCode.CONFIRMATION_REQUIRED.value]
        else:
            # Above threshold — blocked
            return False, False, reasons

    return True, False, reasons


def check_discount_limits(
    original_price: float,
    requested_discount_amount: Optional[float],
    requested_discount_percent: Optional[float],
    max_discount_percent: float,
    max_discount_amount: float,
) -> tuple[float, bool, list[str]]:
    """
    Calculate the allowed discount, capped by both percent and amount limits.
    Whichever restriction is stricter wins.

    Returns: (allowed_discount_amount, was_capped, reason_codes)
    """
    reasons = []

    if original_price <= 0:
        return 0.0, False, [ReasonCode.INVALID_AMOUNT.value]

    # Calculate the maximum allowed discount from both constraints
    max_from_percent = original_price * (max_discount_percent / 100.0)
    max_from_amount = max_discount_amount

    # The stricter (lower) limit wins
    effective_max_discount = min(max_from_percent, max_from_amount)

    # Determine what was requested
    if requested_discount_amount is not None:
        requested = requested_discount_amount
    elif requested_discount_percent is not None:
        requested = original_price * (requested_discount_percent / 100.0)
    else:
        return 0.0, False, [ReasonCode.WITHIN_DISCOUNT_LIMIT.value]

    if requested < 0:
        requested = 0.0

    # Check individual limits for reason codes
    if requested_discount_percent is not None and requested_discount_percent > max_discount_percent:
        reasons.append(ReasonCode.DISCOUNT_EXCEEDS_PERCENT_LIMIT.value)

    if requested_discount_amount is not None and requested_discount_amount > max_discount_amount:
        reasons.append(ReasonCode.DISCOUNT_EXCEEDS_AMOUNT_LIMIT.value)

    if max_from_percent < max_from_amount:
        cap_source = "percent"
    else:
        cap_source = "amount"

    # Cap the discount
    if requested > effective_max_discount:
        allowed = effective_max_discount
        was_capped = True
        if not reasons:
            if cap_source == "percent":
                reasons.append(ReasonCode.DISCOUNT_EXCEEDS_PERCENT_LIMIT.value)
            else:
                reasons.append(ReasonCode.DISCOUNT_EXCEEDS_AMOUNT_LIMIT.value)
    else:
        allowed = requested
        was_capped = False
        reasons.append(ReasonCode.WITHIN_DISCOUNT_LIMIT.value)

    return round(allowed, 2), was_capped, reasons


def check_inventory(
    available_quantity: int,
    reserved_quantity: int,
    required_quantity: int,
) -> tuple[bool, list[str]]:
    """Check if sufficient inventory is available (not counting reserved)."""
    effective_available = available_quantity  # reserved is already subtracted at DB level

    if effective_available >= required_quantity:
        return True, [ReasonCode.INVENTORY_AVAILABLE.value]
    else:
        return False, [ReasonCode.INVENTORY_UNAVAILABLE.value]


def check_price_integrity(
    authoritative_price: float,
    proposed_price: float,
    tolerance: float = 0.01,
) -> tuple[bool, list[str]]:
    """
    Verify that the proposed price matches the authoritative price.
    The LLM cannot supply the final payment amount.

    tolerance: allowed floating-point difference (₹0.01)
    """
    if abs(authoritative_price - proposed_price) <= tolerance:
        return True, [ReasonCode.PRICE_VERIFIED.value]
    else:
        return False, [ReasonCode.PRICE_MISMATCH.value]


def check_product_restrictions(
    product_id: str,
    product_category: str,
    restricted_products: list[str],
    restricted_categories: list[str],
) -> tuple[bool, list[str]]:
    """Check if the product or its category is restricted."""
    reasons = []

    if product_id in restricted_products:
        reasons.append(ReasonCode.PRODUCT_RESTRICTED.value)

    if product_category.lower() in [c.lower() for c in restricted_categories]:
        reasons.append(ReasonCode.CATEGORY_RESTRICTED.value)

    if reasons:
        return False, reasons
    else:
        return True, [ReasonCode.PRODUCT_ALLOWED.value]


def check_payment_retry(
    attempt_number: int,
    max_attempts: int,
) -> tuple[bool, list[str]]:
    """Check if the payment attempt is within the retry limit."""
    if attempt_number <= max_attempts:
        return True, [ReasonCode.WITHIN_RETRY_LIMIT.value]
    else:
        return False, [ReasonCode.RETRY_LIMIT_REACHED.value]


def check_refund_policy(
    refund_requires_human: bool,
) -> tuple[bool, bool, list[str]]:
    """
    Check refund authorization.
    Returns: (allowed, requires_human_review, reason_codes)
    """
    if refund_requires_human:
        return False, True, [ReasonCode.REFUND_REQUIRES_HUMAN.value]
    else:
        return True, False, [ReasonCode.REFUND_ALLOWED.value]


def check_auto_purchase(
    auto_purchase_enabled: bool,
) -> tuple[bool, list[str]]:
    """Check if autonomous purchasing is enabled."""
    if auto_purchase_enabled:
        return True, [ReasonCode.AUTO_PURCHASE_ALLOWED.value]
    else:
        return False, [ReasonCode.AUTO_PURCHASE_DISABLED.value]


def check_negotiation(
    negotiation_enabled: bool,
) -> tuple[bool, list[str]]:
    """Check if price negotiation is enabled."""
    if negotiation_enabled:
        return True, []
    else:
        return False, [ReasonCode.NEGOTIATION_DISABLED.value]