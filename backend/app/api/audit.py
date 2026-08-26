"""Audit API — query the immutable audit trail."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.database.models import AuditEvent
from app.audit.schemas import AuditSummary

router = APIRouter()


class AuditEventOut(BaseModel):
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


class AuditListResponse(BaseModel):
    events: list[AuditEventOut]
    total: int


@router.get("/audit", response_model=AuditListResponse)
async def get_audit_log(
    session_id: Optional[str] = Query(None),
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Query the audit trail. Append-only — no create/update/delete endpoints.
    """
    conditions = []

    if session_id:
        conditions.append(AuditEvent.session_id == session_id)
    if actor:
        conditions.append(AuditEvent.actor == actor)
    if action:
        conditions.append(AuditEvent.action == action)
    if status:
        conditions.append(AuditEvent.status == status)
    if resource_type:
        conditions.append(AuditEvent.resource_type == resource_type)

    # Count
    count_stmt = select(func.count()).select_from(AuditEvent)
    if conditions:
        from sqlalchemy import and_
        count_stmt = count_stmt.where(and_(*conditions))
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    # Fetch
    stmt = select(AuditEvent).order_by(desc(AuditEvent.timestamp))
    if conditions:
        from sqlalchemy import and_
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    events = result.scalars().all()

    return AuditListResponse(
        events=[
            AuditEventOut(
                id=str(e.id),
                timestamp=e.timestamp.isoformat(),
                session_id=str(e.session_id) if e.session_id else None,
                actor=e.actor,
                action=e.action,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                result=e.result,
                policy_decision=e.policy_decision,
                reason_codes=e.reason_codes or [],
                status=e.status,
                metadata=e.metadata_ or {},
            )
            for e in events
        ],
        total=total,
    )


@router.get("/audit/summary", response_model=AuditSummary)
async def get_audit_summary(
    db: AsyncSession = Depends(get_db),
):
    """Get audit summary statistics for the merchant dashboard."""
    # Total events
    total_result = await db.execute(
        select(func.count()).select_from(AuditEvent)
    )
    total = total_result.scalar() or 0

    # Blocked actions
    blocked_result = await db.execute(
        select(func.count()).select_from(AuditEvent)
        .where(AuditEvent.status == "BLOCKED")
    )
    blocked = blocked_result.scalar() or 0

    # Failed payments
    failed_result = await db.execute(
        select(func.count()).select_from(AuditEvent)
        .where(AuditEvent.action == "PAYMENT_FAILED")
    )
    failed_payments = failed_result.scalar() or 0

    # Successful payments
    success_result = await db.execute(
        select(func.count()).select_from(AuditEvent)
        .where(AuditEvent.action == "PAYMENT_SUCCESS")
    )
    success_payments = success_result.scalar() or 0

    # Policy violations (blocked by policy)
    violation_result = await db.execute(
        select(func.count()).select_from(AuditEvent)
        .where(AuditEvent.actor == "policy_engine")
        .where(AuditEvent.status == "BLOCKED")
    )
    violations = violation_result.scalar() or 0

    # Agent sessions
    session_result = await db.execute(
        select(func.count(func.distinct(AuditEvent.session_id)))
        .select_from(AuditEvent)
        .where(AuditEvent.session_id.isnot(None))
    )
    sessions = session_result.scalar() or 0

    # Recent 10 events
    recent_stmt = (
        select(AuditEvent)
        .order_by(desc(AuditEvent.timestamp))
        .limit(10)
    )
    recent_result = await db.execute(recent_stmt)
    recent = recent_result.scalars().all()

    return AuditSummary(
        total_events=total,
        blocked_actions=blocked,
        failed_payments=failed_payments,
        successful_payments=success_payments,
        policy_violations=violations,
        agent_sessions=sessions,
        recent_events=[
            AuditEventOut(
                id=str(e.id),
                timestamp=e.timestamp.isoformat(),
                session_id=str(e.session_id) if e.session_id else None,
                actor=e.actor,
                action=e.action,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                result=e.result,
                policy_decision=e.policy_decision,
                reason_codes=e.reason_codes or [],
                status=e.status,
                metadata=e.metadata_ or {},
            )
            for e in recent
        ],
    )