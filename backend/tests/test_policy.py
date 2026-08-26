"""Comprehensive policy engine tests — 24 test cases."""

import pytest
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select, update

from app.database.models import (
    Merchant, User, Product, Inventory, MerchantPolicy
)
from app.policy.engine import PolicyEngine
from app.policy.schemas import PolicyAction, PolicyEvaluationRequest


# ─── Fixtures ────────────────────────────────

@pytest.fixture
async def policy_data(db_session):
    """Create a complete test environment for policy tests."""
    merchant = Merchant(name="Policy Test Store", currency="INR", status="active")
    db_session.add(merchant)
    await db_session.flush()

    user = User(
        name="Policy Test User",
        email=f"policytest_{uuid4().hex[:8]}@test.com",
        autonomous_spending_limit=Decimal("3000.00"),
    )
    db_session.add(user)
    await db_session.flush()

    policy = MerchantPolicy(
        merchant_id=merchant.id,
        max_autonomous_transaction_amount=Decimal("3000.00"),
        max_discount_percent=Decimal("10.00"),
        max_discount_amount=Decimal("300.00"),
        negotiation_enabled=True,
        auto_purchase_enabled=True,
        confirmation_threshold=Decimal("5000.00"),
        max_payment_attempts=2,
        refund_requires_human=True,
        restricted_categories=["restricted_cat"],
        restricted_products=[],
        version=1,
    )
    db_session.add(policy)
    await db_session.flush()

    product = Product(
        merchant_id=merchant.id,
        sku=f"POL_{uuid4().hex[:6]}",
        name="Policy Test Product",
        category="electronics",
        price=Decimal("2500.00"),
        features={"anc": True},
    )
    db_session.add(product)
    await db_session.flush()

    inventory = Inventory(
        product_id=product.id,
        available_quantity=10,
        reserved_quantity=0,
    )
    db_session.add(inventory)
    await db_session.commit()

    return {
        "merchant_id": str(merchant.id),
        "user_id": str(user.id),
        "product_id": str(product.id),
        "product_sku": product.sku,
    }


def make_request(data, **overrides) -> PolicyEvaluationRequest:
    """Helper to create a PolicyEvaluationRequest with defaults."""
    defaults = {
        "action": PolicyAction.CREATE_ORDER,
        "merchant_id": data["merchant_id"],
        "user_id": data["user_id"],
        "amount": 2500.0,
        "product_id": data["product_id"],
        "product_category": "electronics",
        "quantity": 1,
    }
    defaults.update(overrides)
    return PolicyEvaluationRequest(**defaults)


# ─── Transaction Limit Tests ─────────────────

@pytest.mark.asyncio
async def test_transaction_within_limit(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(policy_data, amount=2500.0)
    decision = await engine.evaluate(req)
    assert decision.allowed is True
    assert "WITHIN_TRANSACTION_LIMIT" in decision.reason_codes


@pytest.mark.asyncio
async def test_transaction_exceeds_merchant_limit(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(policy_data, amount=4000.0)
    decision = await engine.evaluate(req)
    assert decision.allowed is False
    assert decision.requires_confirmation is True
    assert "AMOUNT_EXCEEDS_MERCHANT_LIMIT" in decision.reason_codes


@pytest.mark.asyncio
async def test_transaction_exceeds_confirmation_threshold(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(policy_data, amount=6000.0)
    decision = await engine.evaluate(req)
    assert decision.allowed is False
    assert decision.requires_confirmation is False
    assert decision.is_blocked() is True


@pytest.mark.asyncio
async def test_transaction_at_exact_limit(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(policy_data, amount=3000.0)
    decision = await engine.evaluate(req)
    assert decision.allowed is True


@pytest.mark.asyncio
async def test_transaction_zero_amount(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(policy_data, amount=0)
    decision = await engine.evaluate(req)
    assert decision.allowed is False
    assert "INVALID_AMOUNT" in decision.reason_codes


# ─── Discount Tests ──────────────────────────

@pytest.mark.asyncio
async def test_discount_within_limits(db_session, policy_data):
    engine = PolicyEngine(db_session)
    result = await engine.calculate_discount(
        merchant_id=policy_data["merchant_id"],
        original_price=2500.0,
        requested_discount_percent=10.0,
    )
    assert result.allowed_discount == 250.0
    assert result.final_price == 2250.0
    assert result.was_capped is False


@pytest.mark.asyncio
async def test_discount_exceeds_percent_capped(db_session, policy_data):
    engine = PolicyEngine(db_session)
    result = await engine.calculate_discount(
        merchant_id=policy_data["merchant_id"],
        original_price=2500.0,
        requested_discount_percent=50.0,
    )
    assert result.allowed_discount == 250.0
    assert result.was_capped is True
    assert result.final_price == 2250.0


@pytest.mark.asyncio
async def test_discount_exceeds_amount_capped(db_session, policy_data):
    engine = PolicyEngine(db_session)
    result = await engine.calculate_discount(
        merchant_id=policy_data["merchant_id"],
        original_price=5000.0,
        requested_discount_amount=500.0,
    )
    assert result.allowed_discount == 300.0
    assert result.was_capped is True


@pytest.mark.asyncio
async def test_discount_percent_stricter_than_amount(db_session, policy_data):
    engine = PolicyEngine(db_session)
    result = await engine.calculate_discount(
        merchant_id=policy_data["merchant_id"],
        original_price=2000.0,
        requested_discount_amount=250.0,
    )
    assert result.allowed_discount == 200.0
    assert result.was_capped is True


@pytest.mark.asyncio
async def test_discount_negotiation_disabled(db_session, policy_data):
    from uuid import UUID
    stmt = (
        update(MerchantPolicy)
        .where(MerchantPolicy.merchant_id == UUID(policy_data["merchant_id"]))
        .values(negotiation_enabled=False)
    )
    await db_session.execute(stmt)
    await db_session.commit()

    engine = PolicyEngine(db_session)
    result = await engine.calculate_discount(
        merchant_id=policy_data["merchant_id"],
        original_price=2500.0,
        requested_discount_percent=5.0,
    )
    assert result.allowed_discount == 0.0
    assert result.was_capped is True
    assert "NEGOTIATION_DISABLED" in result.reason_codes


# ─── Inventory Tests ─────────────────────────

@pytest.mark.asyncio
async def test_inventory_available(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(policy_data, quantity=5)
    decision = await engine.evaluate(req)
    assert "INVENTORY_AVAILABLE" in decision.reason_codes


@pytest.mark.asyncio
async def test_inventory_unavailable(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(policy_data, quantity=999)
    decision = await engine.evaluate(req)
    assert decision.allowed is False
    assert "INVENTORY_UNAVAILABLE" in decision.reason_codes


# ─── Price Integrity Tests ───────────────────

@pytest.mark.asyncio
async def test_price_matches(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(policy_data, amount=2500.0, original_price=2500.0)
    decision = await engine.evaluate(req)
    assert "PRICE_VERIFIED" in decision.reason_codes


@pytest.mark.asyncio
async def test_price_mismatch(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(policy_data, amount=1000.0, original_price=1000.0)
    decision = await engine.evaluate(req)
    assert "PRICE_MISMATCH" in decision.reason_codes
    assert decision.allowed is False


# ─── Restriction Tests ───────────────────────

@pytest.mark.asyncio
async def test_category_restricted(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(policy_data, product_category="restricted_cat")
    decision = await engine.evaluate(req)
    assert decision.allowed is False
    assert "CATEGORY_RESTRICTED" in decision.reason_codes


@pytest.mark.asyncio
async def test_product_allowed(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(policy_data, product_category="electronics")
    decision = await engine.evaluate(req)
    assert "PRODUCT_ALLOWED" in decision.reason_codes


# ─── Payment Retry Tests ─────────────────────

@pytest.mark.asyncio
async def test_payment_retry_within_limit(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(
        policy_data,
        action=PolicyAction.EXECUTE_PAYMENT,
        amount=2500.0,
        payment_attempt=1,
    )
    decision = await engine.evaluate(req)
    assert decision.allowed is True
    assert "WITHIN_RETRY_LIMIT" in decision.reason_codes


@pytest.mark.asyncio
async def test_payment_retry_exceeds_limit(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(
        policy_data,
        action=PolicyAction.EXECUTE_PAYMENT,
        amount=2500.0,
        payment_attempt=3,
    )
    decision = await engine.evaluate(req)
    assert decision.allowed is False
    assert "RETRY_LIMIT_REACHED" in decision.reason_codes


# ─── Refund Tests ────────────────────────────

@pytest.mark.asyncio
async def test_refund_requires_human(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(
        policy_data,
        action=PolicyAction.REQUEST_REFUND,
        amount=2500.0,
    )
    decision = await engine.evaluate(req)
    assert decision.allowed is False
    assert decision.requires_human_review is True
    assert "REFUND_REQUIRES_HUMAN" in decision.reason_codes


# ─── Auto-Purchase Tests ─────────────────────

@pytest.mark.asyncio
async def test_auto_purchase_disabled(db_session, policy_data):
    from uuid import UUID
    stmt = (
        update(MerchantPolicy)
        .where(MerchantPolicy.merchant_id == UUID(policy_data["merchant_id"]))
        .values(auto_purchase_enabled=False)
    )
    await db_session.execute(stmt)
    await db_session.commit()

    engine = PolicyEngine(db_session)
    req = make_request(policy_data, amount=1000.0)
    decision = await engine.evaluate(req)
    assert decision.allowed is False
    assert decision.requires_confirmation is True
    assert "AUTO_PURCHASE_DISABLED" in decision.reason_codes


# ─── Edge Cases ──────────────────────────────

@pytest.mark.asyncio
async def test_invalid_merchant_id(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(policy_data, merchant_id=str(uuid4()))
    decision = await engine.evaluate(req)
    assert decision.allowed is False
    assert "POLICY_NOT_FOUND" in decision.reason_codes


@pytest.mark.asyncio
async def test_invalid_user_id(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(policy_data, user_id=str(uuid4()))
    decision = await engine.evaluate(req)
    assert decision.allowed is False
    assert "USER_NOT_FOUND" in decision.reason_codes


@pytest.mark.asyncio
async def test_multiple_violations(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(
        policy_data,
        amount=6000.0,
        product_category="restricted_cat",
        quantity=999,
    )
    decision = await engine.evaluate(req)
    assert decision.allowed is False
    assert "AMOUNT_EXCEEDS_MERCHANT_LIMIT" in decision.reason_codes
    assert "CATEGORY_RESTRICTED" in decision.reason_codes
    assert "INVENTORY_UNAVAILABLE" in decision.reason_codes


@pytest.mark.asyncio
async def test_cancel_always_allowed(db_session, policy_data):
    engine = PolicyEngine(db_session)
    req = make_request(policy_data, action=PolicyAction.CANCEL_ORDER)
    decision = await engine.evaluate(req)
    assert decision.allowed is True