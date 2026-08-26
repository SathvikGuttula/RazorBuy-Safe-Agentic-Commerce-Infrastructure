"""Audit event schemas — structured types for the immutable audit trail."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any

from pydantic import BaseModel, Field, ConfigDict


class AuditActor(str, Enum):
    AGENT = "agent"
    SYSTEM = "system"
    USER = "user"
    POLICY_ENGINE = "policy_engine"
    PAYMENT_SERVICE = "payment_service"
    ORDER_SERVICE = "order_service"


class AuditAction(str, Enum):
    SEARCH_PRODUCTS = "SEARCH_PRODUCTS"
    VIEW_PRODUCT = "VIEW_PRODUCT"
    CHECK_INVENTORY = "CHECK_INVENTORY"

    EVALUATE_POLICY = "EVALUATE_POLICY"
    CALCULATE_DISCOUNT = "CALCULATE_DISCOUNT"
    POLICY_UPDATED = "POLICY_UPDATED"

    CREATE_ORDER = "CREATE_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    CONFIRM_ORDER = "CONFIRM_ORDER"

    CREATE_PAYMENT = "CREATE_PAYMENT"
    VERIFY_PAYMENT = "VERIFY_PAYMENT"
    PAYMENT_SUCCESS = "PAYMENT_SUCCESS"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_TIMEOUT = "PAYMENT_TIMEOUT"
    DUPLICATE_PAYMENT_BLOCKED = "DUPLICATE_PAYMENT_BLOCKED"

    AGENT_TOOL_CALL = "AGENT_TOOL_CALL"
    AGENT_STEP = "AGENT_STEP"
    AGENT_LOOP_DETECTED = "AGENT_LOOP_DETECTED"
    AGENT_SESSION_START = "AGENT_SESSION_START"
    AGENT_SESSION_END = "AGENT_SESSION_END"

    PROMPT_INJECTION_DETECTED = "PROMPT_INJECTION_DETECTED"
    INVALID_TOOL_CALL = "INVALID_TOOL_CALL"
    AMOUNT_MANIPULATION_BLOCKED = "AMOUNT_MANIPULATION_BLOCKED"
    UNAUTHORIZED_ACTION = "UNAUTHORIZED_ACTION"


class AuditResult(str, Enum):
    SUCCESS = "SUCCESS"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    PENDING = "PENDING"
    ESCALATED = "ESCALATED"
    CAPPED = "CAPPED"


class AuditEventCreate(BaseModel):
    session_id: Optional[str] = None
    actor: str
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    input_data: Optional[dict[str, Any]] = None
    result: str
    policy_decision: Optional[dict[str, Any]] = None
    reason_codes: list[str] = Field(default_factory=list)
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: str
    session_id: Optional[str] = None
    actor: str
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    result: Optional[str] = None
    policy_decision: Optional[dict] = None
    reason_codes: list[str]
    status: str
    metadata: dict


class AuditSummary(BaseModel):
    total_events: int
    blocked_actions: int
    failed_payments: int
    successful_payments: int
    policy_violations: int
    agent_sessions: int
    recent_events: list[AuditEventResponse]