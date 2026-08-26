"""SQLAlchemy ORM models — all tables for RazorBuy."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    String, Integer, Numeric, Boolean, Text, DateTime,
    ForeignKey, CheckConstraint, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base
from app.database.enums import (
    OrderStatus, PaymentStatus, CartStatus,
    SessionStatus, ReservationStatus
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────
# USERS
# ──────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    autonomous_spending_limit: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("3000.00")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    orders: Mapped[list["Order"]] = relationship(back_populates="user")
    carts: Mapped[list["Cart"]] = relationship(back_populates="user")
    sessions: Mapped[list["AgentSession"]] = relationship(back_populates="user")


# ──────────────────────────────────────────────
# MERCHANTS
# ──────────────────────────────────────────────
class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    products: Mapped[list["Product"]] = relationship(back_populates="merchant")
    policies: Mapped[list["MerchantPolicy"]] = relationship(back_populates="merchant")
    orders: Mapped[list["Order"]] = relationship(back_populates="merchant")


# ──────────────────────────────────────────────
# PRODUCTS
# ──────────────────────────────────────────────
class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    features: Mapped[dict] = mapped_column(JSONB, default=dict)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    merchant: Mapped["Merchant"] = relationship(back_populates="products")
    inventory: Mapped["Inventory"] = relationship(
        back_populates="product", uselist=False
    )

    __table_args__ = (
        Index("idx_products_category", "category"),
        Index("idx_products_price", "price"),
        Index("idx_products_merchant", "merchant_id"),
        Index("idx_products_active", "active"),
        Index("idx_products_features", "features", postgresql_using="gin"),
    )


# ──────────────────────────────────────────────
# INVENTORY
# ──────────────────────────────────────────────
class Inventory(Base):
    __tablename__ = "inventory"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), primary_key=True
    )
    available_quantity: Mapped[int] = mapped_column(Integer, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    product: Mapped["Product"] = relationship(back_populates="inventory")

    __table_args__ = (
        CheckConstraint("available_quantity >= 0", name="positive_available"),
        CheckConstraint("reserved_quantity >= 0", name="positive_reserved"),
    )


# ──────────────────────────────────────────────
# MERCHANT POLICIES
# ──────────────────────────────────────────────
class MerchantPolicy(Base):
    __tablename__ = "merchant_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    max_autonomous_transaction_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("3000.00")
    )
    max_discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("10.00")
    )
    max_discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("300.00")
    )
    negotiation_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_purchase_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    confirmation_threshold: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("3000.00")
    )
    max_payment_attempts: Mapped[int] = mapped_column(Integer, default=2)
    refund_requires_human: Mapped[bool] = mapped_column(Boolean, default=True)
    restricted_categories: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list
    )
    restricted_products: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    merchant: Mapped["Merchant"] = relationship(back_populates="policies")

    __table_args__ = (
        UniqueConstraint("merchant_id", "version", name="uq_merchant_policy_version"),
    )


# ──────────────────────────────────────────────
# CARTS
# ──────────────────────────────────────────────
class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=CartStatus.ACTIVE.value
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="carts")
    items: Mapped[list["CartItem"]] = relationship(
        back_populates="cart", cascade="all, delete-orphan"
    )


# ──────────────────────────────────────────────
# CART ITEMS
# ──────────────────────────────────────────────
class CartItem(Base):
    __tablename__ = "cart_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cart_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("carts.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    cart: Mapped["Cart"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()

    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_quantity"),
    )


# ──────────────────────────────────────────────
# ORDERS
# ──────────────────────────────────────────────
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    cart_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("carts.id"), nullable=True
    )
    items: Mapped[dict] = mapped_column(JSONB, default=list)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00")
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(
        String(30), default=OrderStatus.DRAFT.value
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    policy_decision: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    merchant: Mapped["Merchant"] = relationship(back_populates="orders")
    user: Mapped["User"] = relationship(back_populates="orders")
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    reservations: Mapped[list["InventoryReservation"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_orders_user", "user_id"),
        Index("idx_orders_merchant", "merchant_id"),
        Index("idx_orders_status", "status"),
        Index("idx_orders_idempotency", "idempotency_key"),
    )


# ──────────────────────────────────────────────
# INVENTORY RESERVATIONS
# ──────────────────────────────────────────────
class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=ReservationStatus.ACTIVE.value
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    order: Mapped["Order"] = relationship(back_populates="reservations")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_reserve_qty"),
        Index("idx_reservations_order", "order_id"),
        Index("idx_reservations_status", "status"),
        Index("idx_reservations_expires", "expires_at"),
    )


# ──────────────────────────────────────────────
# PAYMENTS
# ──────────────────────────────────────────────
class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), default="razorpay")
    provider_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_signature: Mapped[str | None] = mapped_column(String(512), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(
        String(30), default=PaymentStatus.PENDING.value
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    order: Mapped["Order"] = relationship(back_populates="payments")

    __table_args__ = (
        Index("idx_payments_order", "order_id"),
        Index("idx_payments_provider_order", "provider_order_id"),
        Index("idx_payments_status", "status"),
        Index("idx_payments_idempotency", "idempotency_key"),
    )


# ──────────────────────────────────────────────
# AGENT SESSIONS
# ──────────────────────────────────────────────
class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    conversation_history: Mapped[dict] = mapped_column(JSONB, default=list)
    state: Mapped[str] = mapped_column(
        String(30), default=SessionStatus.ACTIVE.value
    )
    max_steps: Mapped[int] = mapped_column(Integer, default=20)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="sessions")
    actions: Mapped[list["AgentAction"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


# ──────────────────────────────────────────────
# AGENT ACTIONS
# ──────────────────────────────────────────────
class AgentAction(Base):
    __tablename__ = "agent_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_sessions.id"), nullable=False
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    session: Mapped["AgentSession"] = relationship(back_populates="actions")

    __table_args__ = (
        Index("idx_actions_session", "session_id"),
    )


# ──────────────────────────────────────────────
# AUDIT EVENTS (Append-only)
# ──────────────────────────────────────────────
class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    actor: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    policy_decision: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason_codes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    __table_args__ = (
        Index("idx_audit_session", "session_id"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )