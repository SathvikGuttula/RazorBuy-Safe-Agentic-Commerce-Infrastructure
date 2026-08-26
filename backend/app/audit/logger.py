"""
Audit Logger — append-only event recording.

Every meaningful action in the system passes through here.
The audit_events table has DB-level triggers preventing UPDATE and DELETE.
This module never modifies existing events.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditEvent

logger = logging.getLogger(__name__)


def _hash_input(data: Optional[dict]) -> Optional[str]:
    """Create a SHA-256 hash of input data for integrity verification."""
    if not data:
        return None
    try:
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()
    except Exception:
        return None


async def log_event(
    db: AsyncSession,
    actor: str,
    action: str,
    status: str,
    session_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    input_data: Optional[dict[str, Any]] = None,
    result: Optional[str] = None,
    policy_decision: Optional[dict[str, Any]] = None,
    reason_codes: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> AuditEvent:
    """
    Record an audit event. This is append-only.

    Usage:
        await log_event(
            db=db,
            actor="policy_engine",
            action="EVALUATE_POLICY",
            status="BLOCKED",
            resource_type="order",
            resource_id=str(order.id),
            reason_codes=["AMOUNT_EXCEEDS_LIMIT"],
            result="BLOCKED",
        )
    """
    event = AuditEvent(
        session_id=session_id,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        input_hash=_hash_input(input_data),
        result=result or status,
        policy_decision=policy_decision,
        reason_codes=reason_codes or [],
        status=status,
        metadata_=metadata or {},
    )
    db.add(event)
    await db.flush()

    # Log to application logger as well for observability
    log_level = logging.WARNING if status in ("BLOCKED", "FAILED") else logging.INFO
    logger.log(
        log_level,
        f"AUDIT | {action} | {status} | "
        f"actor={actor} resource={resource_type}:{resource_id} "
        f"reasons={reason_codes}",
    )

    return event


async def log_policy_decision(
    db: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: str,
    decision: dict,
    session_id: Optional[str] = None,
) -> AuditEvent:
    """Convenience method for logging policy decisions."""
    allowed = decision.get("allowed", False)
    requires_confirmation = decision.get("requires_confirmation", False)
    reason_codes = decision.get("reason_codes", [])

    if allowed:
        status = "SUCCESS"
        result = "APPROVED"
    elif requires_confirmation:
        status = "ESCALATED"
        result = "CONFIRMATION_REQUIRED"
    else:
        status = "BLOCKED"
        result = "REJECTED"

    return await log_event(
        db=db,
        actor="policy_engine",
        action=action,
        status=status,
        session_id=session_id,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        policy_decision=decision,
        reason_codes=reason_codes,
    )


async def log_payment_event(
    db: AsyncSession,
    action: str,
    order_id: str,
    payment_id: Optional[str],
    status: str,
    amount: Optional[float] = None,
    error: Optional[str] = None,
    session_id: Optional[str] = None,
) -> AuditEvent:
    """Convenience method for logging payment events."""
    metadata = {}
    if amount is not None:
        metadata["amount"] = amount
    if error:
        metadata["error"] = error

    return await log_event(
        db=db,
        actor="payment_service",
        action=action,
        status=status,
        session_id=session_id,
        resource_type="payment",
        resource_id=payment_id or order_id,
        result=status,
        reason_codes=[error] if error else [],
        metadata=metadata,
    )


async def log_agent_action(
    db: AsyncSession,
    session_id: str,
    tool_name: str,
    arguments: dict,
    result_data: Optional[dict],
    status: str,
    latency_ms: Optional[int] = None,
) -> AuditEvent:
    """Convenience method for logging agent tool calls."""
    metadata = {}
    if latency_ms is not None:
        metadata["latency_ms"] = latency_ms

    return await log_event(
        db=db,
        actor="agent",
        action="AGENT_TOOL_CALL",
        status=status,
        session_id=session_id,
        resource_type="tool",
        resource_id=tool_name,
        input_data=arguments,
        result=status,
        reason_codes=[tool_name],
        metadata=metadata,
    )