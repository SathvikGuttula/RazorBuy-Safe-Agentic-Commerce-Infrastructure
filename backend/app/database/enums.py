"""All status enums for the application. Single source of truth."""

import enum


class OrderStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_POLICY = "PENDING_POLICY"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    APPROVED = "APPROVED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAYMENT_PROCESSING = "PAYMENT_PROCESSING"
    PAID = "PAID"
    COMPLETED = "COMPLETED"
    POLICY_REJECTED = "POLICY_REJECTED"
    CANCELLED = "CANCELLED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_UNKNOWN = "PAYMENT_UNKNOWN"
    INVENTORY_UNAVAILABLE = "INVENTORY_UNAVAILABLE"
    PRICE_CHANGED = "PRICE_CHANGED"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"


class CartStatus(str, enum.Enum):
    ACTIVE = "active"
    CONVERTED = "converted"
    ABANDONED = "abandoned"


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"
    TIMEOUT = "timeout"


class ReservationStatus(str, enum.Enum):
    ACTIVE = "active"
    COMMITTED = "committed"
    RELEASED = "released"
    EXPIRED = "expired"


class ActorType(str, enum.Enum):
    AGENT = "agent"
    SYSTEM = "system"
    USER = "user"
    POLICY_ENGINE = "policy_engine"
    PAYMENT_SERVICE = "payment_service"


class AuditResult(str, enum.Enum):
    SUCCESS = "SUCCESS"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    PENDING = "PENDING"
    ESCALATED = "ESCALATED"