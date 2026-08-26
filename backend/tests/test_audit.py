"""Tests for the audit logging system."""

import pytest
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select, func

from app.database.models import (
    Merchant, User, Product, Inventory, MerchantPolicy,
    Order, AuditEvent,
)
from app.database.enums import OrderStatus
from app.audit.logger import (
    log_event, log_policy_decision, log_payment_event, log_agent_action
)


@pytest.fixture
async def audit_env(db_session):
    """Minimal environment for audit tests."""
    merchant = Merchant(name="Audit Store", currency="INR", status="active")
    db_session.add(merchant)
    await db_session.flush()

    user = User(
        name="Audit User",
        email=f"audit_{uuid4().hex[:8]}@test.com",
        autonomous_spending_limit=Decimal("5000"),
    )
    db_session.add(user)
    await db_session.commit()

    return {
        "merchant_id": str(merchant.id),
        "user_id": str(user.id),
    }


@pytest.mark.asyncio
async def test_log_basic_event(db_session, audit_env):
    """Basic audit event is recorded correctly."""
    event = await log_event(
        db=db_session,
        actor="system",
        action="HEALTH_CHECK",
        status="SUCCESS",
        result="OK",
    )
    await db_session.commit()

    assert event.id is not None
    assert event.actor == "system"
    assert event.action == "HEALTH_CHECK"
    assert event.status == "SUCCESS"


@pytest.mark.asyncio
async def test_log_policy_blocked(db_session, audit_env):
    """Policy rejection is logged with reason codes."""
    decision = {
        "allowed": False,
        "requires_confirmation": False,
        "reason_codes": ["AMOUNT_EXCEEDS_MERCHANT_LIMIT"],
        "policy_version": 1,
    }

    event = await log_policy_decision(
        db=db_session,
        action="EVALUATE_POLICY",
        resource_type="order",
        resource_id="order_123",
        decision=decision,
    )
    await db_session.commit()

    assert event.status == "BLOCKED"
    assert event.result == "REJECTED"
    assert "AMOUNT_EXCEEDS_MERCHANT_LIMIT" in event.reason_codes


@pytest.mark.asyncio
async def test_log_policy_approved(db_session, audit_env):
    """Policy approval is logged correctly."""
    decision = {
        "allowed": True,
        "requires_confirmation": False,
        "reason_codes": ["WITHIN_TRANSACTION_LIMIT", "INVENTORY_AVAILABLE"],
        "policy_version": 1,
    }

    event = await log_policy_decision(
        db=db_session,
        action="EVALUATE_POLICY",
        resource_type="order",
        resource_id="order_456",
        decision=decision,
    )
    await db_session.commit()

    assert event.status == "SUCCESS"
    assert event.result == "APPROVED"


@pytest.mark.asyncio
async def test_log_policy_confirmation_required(db_session, audit_env):
    """Policy requiring confirmation is logged as escalated."""
    decision = {
        "allowed": False,
        "requires_confirmation": True,
        "reason_codes": ["CONFIRMATION_REQUIRED"],
        "policy_version": 1,
    }

    event = await log_policy_decision(
        db=db_session,
        action="EVALUATE_POLICY",
        resource_type="order",
        resource_id="order_789",
        decision=decision,
    )
    await db_session.commit()

    assert event.status == "ESCALATED"
    assert event.result == "CONFIRMATION_REQUIRED"


@pytest.mark.asyncio
async def test_log_payment_success(db_session, audit_env):
    """Payment success is logged."""
    event = await log_payment_event(
        db=db_session,
        action="PAYMENT_SUCCESS",
        order_id="order_123",
        payment_id="pay_456",
        status="SUCCESS",
        amount=2499.0,
    )
    await db_session.commit()

    assert event.actor == "payment_service"
    assert event.status == "SUCCESS"
    assert event.metadata_.get("amount") == 2499.0


@pytest.mark.asyncio
async def test_log_payment_failed(db_session, audit_env):
    """Payment failure is logged with error."""
    event = await log_payment_event(
        db=db_session,
        action="PAYMENT_FAILED",
        order_id="order_123",
        payment_id="pay_789",
        status="FAILED",
        error="SIGNATURE_INVALID",
    )
    await db_session.commit()

    assert event.status == "FAILED"
    assert "SIGNATURE_INVALID" in event.reason_codes


@pytest.mark.asyncio
async def test_log_agent_tool_call(db_session, audit_env):
    """Agent tool call is logged with arguments and latency."""
    event = await log_agent_action(
        db=db_session,
        session_id = str(uuid4()),
        tool_name="search_products",
        arguments={"query": "earbuds", "max_price": 3000},
        result_data={"products_found": 3},
        status="SUCCESS",
        latency_ms=150,
    )
    await db_session.commit()

    assert event.actor == "agent"
    assert event.action == "AGENT_TOOL_CALL"
    assert event.resource_id == "search_products"
    assert event.metadata_.get("latency_ms") == 150


@pytest.mark.asyncio
async def test_log_event_input_hash(db_session, audit_env):
    """Input data is hashed for integrity."""
    event = await log_event(
        db=db_session,
        actor="agent",
        action="CREATE_ORDER",
        status="SUCCESS",
        input_data={"product_id": "P101", "quantity": 1},
    )
    await db_session.commit()

    assert event.input_hash is not None
    assert len(event.input_hash) == 64  # SHA-256 hex


@pytest.mark.asyncio
async def test_log_event_append_only(db_session, audit_env):
    """Audit events can be created but the table has DB triggers against modification."""
    event = await log_event(
        db=db_session,
        actor="system",
        action="TEST_APPEND",
        status="SUCCESS",
    )
    await db_session.commit()

    # Verify the event exists
    stmt = select(AuditEvent).where(AuditEvent.id == event.id)
    result = await db_session.execute(stmt)
    found = result.scalar_one_or_none()
    assert found is not None
    assert found.action == "TEST_APPEND"


@pytest.mark.asyncio
async def test_multiple_events_ordering(db_session, audit_env):
    """Multiple events are recorded and queryable."""
    for i in range(5):
        await log_event(
            db=db_session,
            actor="system",
            action=f"EVENT_{i}",
            status="SUCCESS",
        )
    await db_session.commit()

    count_result = await db_session.execute(
        select(func.count()).select_from(AuditEvent)
    )
    total = count_result.scalar()
    assert total >= 5


@pytest.mark.asyncio
async def test_audit_api_endpoint(client, audit_env):
    """Audit API returns events."""
    response = await client.get("/api/audit")
    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_audit_summary_endpoint(client, audit_env):
    """Audit summary API returns statistics."""
    response = await client.get("/api/audit/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total_events" in data
    assert "blocked_actions" in data
    assert "policy_violations" in data
    assert "recent_events" in data