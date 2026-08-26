"""Payment and Order state machines with enforced transitions.

No arbitrary string statuses. No invalid transitions. Fail closed.
"""

from app.database.enums import OrderStatus, PaymentStatus


# ─── Valid Order Transitions ─────────────────
VALID_ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.DRAFT: {
        OrderStatus.PENDING_POLICY,
        OrderStatus.CANCELLED,
    },
    OrderStatus.PENDING_POLICY: {
        OrderStatus.APPROVED,
        OrderStatus.AWAITING_CONFIRMATION,
        OrderStatus.POLICY_REJECTED,
        OrderStatus.HUMAN_REVIEW,
        OrderStatus.CANCELLED,
    },
    OrderStatus.AWAITING_CONFIRMATION: {
        OrderStatus.APPROVED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.APPROVED: {
        OrderStatus.PAYMENT_PENDING,
        OrderStatus.INVENTORY_UNAVAILABLE,
        OrderStatus.PRICE_CHANGED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.PAYMENT_PENDING: {
        OrderStatus.PAYMENT_PROCESSING,
        OrderStatus.PRICE_CHANGED,
        OrderStatus.INVENTORY_UNAVAILABLE,
        OrderStatus.CANCELLED,
    },
    OrderStatus.PAYMENT_PROCESSING: {
        OrderStatus.PAID,
        OrderStatus.PAYMENT_FAILED,
        OrderStatus.PAYMENT_UNKNOWN,
    },
    OrderStatus.PAID: {
        OrderStatus.COMPLETED,
    },
    OrderStatus.COMPLETED: set(),  # terminal
    OrderStatus.POLICY_REJECTED: set(),  # terminal
    OrderStatus.CANCELLED: set(),  # terminal
    OrderStatus.PAYMENT_FAILED: {
        OrderStatus.PAYMENT_PENDING,  # retry
        OrderStatus.CANCELLED,
    },
    OrderStatus.PAYMENT_UNKNOWN: {
        OrderStatus.PAID,
        OrderStatus.PAYMENT_FAILED,
        OrderStatus.HUMAN_REVIEW,
    },
    OrderStatus.INVENTORY_UNAVAILABLE: set(),  # terminal
    OrderStatus.PRICE_CHANGED: {
        OrderStatus.AWAITING_CONFIRMATION,
        OrderStatus.CANCELLED,
    },
    OrderStatus.HUMAN_REVIEW: {
        OrderStatus.APPROVED,
        OrderStatus.CANCELLED,
    },
}

# ─── Valid Payment Transitions ───────────────
VALID_PAYMENT_TRANSITIONS: dict[PaymentStatus, set[PaymentStatus]] = {
    PaymentStatus.PENDING: {
        PaymentStatus.PROCESSING,
    },
    PaymentStatus.PROCESSING: {
        PaymentStatus.SUCCESS,
        PaymentStatus.FAILED,
        PaymentStatus.UNKNOWN,
    },
    PaymentStatus.FAILED: {
        PaymentStatus.PROCESSING,  # retry
    },
    PaymentStatus.UNKNOWN: {
        PaymentStatus.SUCCESS,
        PaymentStatus.FAILED,
        PaymentStatus.PROCESSING,
    },
    PaymentStatus.SUCCESS: {
        PaymentStatus.REFUND_PENDING,
    },
    PaymentStatus.REFUND_PENDING: {
        PaymentStatus.REFUNDED,
    },
    PaymentStatus.REFUNDED: set(),  # terminal
}


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    def __init__(self, current: str, target: str, entity: str = "entity"):
        self.current = current
        self.target = target
        super().__init__(
            f"Invalid {entity} transition: {current} → {target}"
        )


def validate_order_transition(current: str, target: str) -> None:
    """Validate and enforce order state transition. Raises if invalid."""
    try:
        current_enum = OrderStatus(current)
        target_enum = OrderStatus(target)
    except ValueError as e:
        raise InvalidTransitionError(current, target, "order") from e

    allowed = VALID_ORDER_TRANSITIONS.get(current_enum, set())
    if target_enum not in allowed:
        raise InvalidTransitionError(current, target, "order")


def validate_payment_transition(current: str, target: str) -> None:
    """Validate and enforce payment state transition. Raises if invalid."""
    try:
        current_enum = PaymentStatus(current)
        target_enum = PaymentStatus(target)
    except ValueError as e:
        raise InvalidTransitionError(current, target, "payment") from e

    allowed = VALID_PAYMENT_TRANSITIONS.get(current_enum, set())
    if target_enum not in allowed:
        raise InvalidTransitionError(current, target, "payment")