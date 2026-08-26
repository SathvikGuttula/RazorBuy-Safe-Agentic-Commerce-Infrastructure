"""Policy engine schemas — all types for deterministic policy evaluation."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any

from pydantic import BaseModel, Field


class PolicyAction(str, Enum):
    CREATE_ORDER = "CREATE_ORDER"
    APPLY_DISCOUNT = "APPLY_DISCOUNT"
    EXECUTE_PAYMENT = "EXECUTE_PAYMENT"
    REQUEST_REFUND = "REQUEST_REFUND"
    CANCEL_ORDER = "CANCEL_ORDER"
    NEGOTIATE_PRICE = "NEGOTIATE_PRICE"


class ReasonCode(str, Enum):
    # Transaction
    WITHIN_TRANSACTION_LIMIT = "WITHIN_TRANSACTION_LIMIT"
    AMOUNT_EXCEEDS_MERCHANT_LIMIT = "AMOUNT_EXCEEDS_MERCHANT_LIMIT"
    AMOUNT_EXCEEDS_USER_LIMIT = "AMOUNT_EXCEEDS_USER_LIMIT"

    # Discount
    WITHIN_DISCOUNT_LIMIT = "WITHIN_DISCOUNT_LIMIT"
    DISCOUNT_EXCEEDS_PERCENT_LIMIT = "DISCOUNT_EXCEEDS_PERCENT_LIMIT"
    DISCOUNT_EXCEEDS_AMOUNT_LIMIT = "DISCOUNT_EXCEEDS_AMOUNT_LIMIT"
    NEGOTIATION_DISABLED = "NEGOTIATION_DISABLED"

    # Inventory
    INVENTORY_AVAILABLE = "INVENTORY_AVAILABLE"
    INVENTORY_UNAVAILABLE = "INVENTORY_UNAVAILABLE"

    # Price
    PRICE_VERIFIED = "PRICE_VERIFIED"
    PRICE_MISMATCH = "PRICE_MISMATCH"

    # Restrictions
    PRODUCT_ALLOWED = "PRODUCT_ALLOWED"
    PRODUCT_RESTRICTED = "PRODUCT_RESTRICTED"
    CATEGORY_RESTRICTED = "CATEGORY_RESTRICTED"

    # Payment
    WITHIN_RETRY_LIMIT = "WITHIN_RETRY_LIMIT"
    RETRY_LIMIT_REACHED = "RETRY_LIMIT_REACHED"
    DUPLICATE_PAYMENT_BLOCKED = "DUPLICATE_PAYMENT_BLOCKED"

    # Refund
    REFUND_ALLOWED = "REFUND_ALLOWED"
    REFUND_REQUIRES_HUMAN = "REFUND_REQUIRES_HUMAN"

    # Authorization
    AUTO_PURCHASE_ALLOWED = "AUTO_PURCHASE_ALLOWED"
    AUTO_PURCHASE_DISABLED = "AUTO_PURCHASE_DISABLED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"

    # General
    INVALID_AMOUNT = "INVALID_AMOUNT"
    POLICY_NOT_FOUND = "POLICY_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"


class PolicyDecision(BaseModel):
    """Immutable result of a policy evaluation. The LLM cannot override this."""
    allowed: bool
    requires_confirmation: bool = False
    requires_human_review: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    policy_version: int = 0
    details: dict[str, Any] = Field(default_factory=dict)

    def is_blocked(self) -> bool:
        return not self.allowed and not self.requires_confirmation

    def needs_action(self) -> bool:
        return self.requires_confirmation or self.requires_human_review


class PolicyEvaluationRequest(BaseModel):
    """Input to the policy engine. All fields are verified by the backend."""
    action: PolicyAction
    merchant_id: str
    user_id: str
    amount: Optional[float] = None
    original_price: Optional[float] = None
    discount_amount: Optional[float] = None
    discount_percent: Optional[float] = None
    product_id: Optional[str] = None
    product_category: Optional[str] = None
    order_id: Optional[str] = None
    payment_attempt: Optional[int] = None
    quantity: int = Field(default=1, ge=1)


class DiscountCalculationResult(BaseModel):
    """Result of bounded discount calculation."""
    original_price: float
    requested_discount: float
    allowed_discount: float
    final_price: float
    discount_percent_applied: float
    was_capped: bool
    cap_reason: Optional[str] = None
    reason_codes: list[str] = Field(default_factory=list)


class PolicyUpdateRequest(BaseModel):
    """Merchant policy update — creates a new version."""
    max_autonomous_transaction_amount: Optional[float] = None
    max_discount_percent: Optional[float] = None
    max_discount_amount: Optional[float] = None
    negotiation_enabled: Optional[bool] = None
    auto_purchase_enabled: Optional[bool] = None
    confirmation_threshold: Optional[float] = None
    max_payment_attempts: Optional[int] = None
    refund_requires_human: Optional[bool] = None
    restricted_categories: Optional[list[str]] = None
    restricted_products: Optional[list[str]] = None