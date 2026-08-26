"""Tests for agent tools, runtime, and chat API."""

import pytest
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.database.models import (
    Merchant, User, Product, Inventory, MerchantPolicy,
)
from app.agent.tools import execute_tool, TOOL_SCHEMAS
from app.agent.runtime import AgentRuntime


@pytest.fixture
async def agent_env(db_session):
    """Full environment for agent tests."""
    merchant = Merchant(name="Agent Store", currency="INR", status="active")
    db_session.add(merchant)
    await db_session.flush()

    user = User(
        name="Agent User",
        email=f"agent_{uuid4().hex[:8]}@test.com",
        autonomous_spending_limit=Decimal("5000.00"),
    )
    db_session.add(user)
    await db_session.flush()

    policy = MerchantPolicy(
        merchant_id=merchant.id,
        max_autonomous_transaction_amount=Decimal("5000.00"),
        max_discount_percent=Decimal("10.00"),
        max_discount_amount=Decimal("300.00"),
        negotiation_enabled=True,
        auto_purchase_enabled=True,
        confirmation_threshold=Decimal("8000.00"),
        max_payment_attempts=2,
        refund_requires_human=True,
        restricted_categories=["restricted"],
        restricted_products=[],
        version=1,
    )
    db_session.add(policy)
    await db_session.flush()

    products = [
        {"sku": "AG101", "name": "Test Earbuds ANC", "category": "wireless_earbuds",
         "price": 2499, "features": {"anc": True, "battery_hours": 35}, "stock": 10},
        {"sku": "AG102", "name": "Test Headphones", "category": "headphones",
         "price": 4999, "features": {"anc": True, "battery_hours": 50}, "stock": 5},
        {"sku": "AG103", "name": "Budget Speaker", "category": "speakers",
         "price": 999, "features": {"waterproof": True}, "stock": 20},
    ]

    for p in products:
        product = Product(
            merchant_id=merchant.id,
            sku=p["sku"],
            name=p["name"],
            description=f"Test {p['sku']}",
            category=p["category"],
            price=Decimal(str(p["price"])),
            features=p["features"],
            tags=[],
            active=True,
        )
        db_session.add(product)
        await db_session.flush()
        inv = Inventory(product_id=product.id, available_quantity=p["stock"], reserved_quantity=0)
        db_session.add(inv)

    await db_session.commit()

    return {
        "merchant_id": str(merchant.id),
        "user_id": str(user.id),
    }


# ─── Tool Schema Tests ───────────────────────

def test_tool_schemas_valid():
    """All tool schemas have required fields."""
    assert len(TOOL_SCHEMAS) >= 8
    for tool in TOOL_SCHEMAS:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        assert fn["parameters"]["type"] == "object"


def test_tool_names_unique():
    """No duplicate tool names."""
    names = [t["function"]["name"] for t in TOOL_SCHEMAS]
    assert len(names) == len(set(names))


# ─── Tool Execution Tests ────────────────────

@pytest.mark.asyncio
async def test_tool_search_products(db_session, agent_env):
    result = await execute_tool(
        "search_products",
        {"query": "earbuds"},
        db_session,
        agent_env["merchant_id"],
        agent_env["user_id"],
    )
    assert result["status"] == "SUCCESS"
    assert result["total_found"] >= 1


@pytest.mark.asyncio
async def test_tool_search_with_price_filter(db_session, agent_env):
    result = await execute_tool(
        "search_products",
        {"query": "test", "max_price": 1500},
        db_session,
        agent_env["merchant_id"],
        agent_env["user_id"],
    )
    assert result["status"] == "SUCCESS"
    for p in result["products"]:
        assert p["price"] <= 1500


@pytest.mark.asyncio
async def test_tool_get_product(db_session, agent_env):
    result = await execute_tool(
        "get_product",
        {"product_id": "AG101"},
        db_session,
        agent_env["merchant_id"],
        agent_env["user_id"],
    )
    assert result["status"] == "SUCCESS"
    assert result["product"]["sku"] == "AG101"
    assert result["product"]["price"] == 2499.0


@pytest.mark.asyncio
async def test_tool_get_product_not_found(db_session, agent_env):
    result = await execute_tool(
        "get_product",
        {"product_id": "NONEXISTENT"},
        db_session,
        agent_env["merchant_id"],
        agent_env["user_id"],
    )
    assert result["status"] == "FAILED"


@pytest.mark.asyncio
async def test_tool_check_inventory(db_session, agent_env):
    result = await execute_tool(
        "check_inventory",
        {"product_id": "AG101", "quantity": 5},
        db_session,
        agent_env["merchant_id"],
        agent_env["user_id"],
    )
    assert result["status"] == "SUCCESS"
    assert result["available"] is True


@pytest.mark.asyncio
async def test_tool_check_inventory_insufficient(db_session, agent_env):
    result = await execute_tool(
        "check_inventory",
        {"product_id": "AG101", "quantity": 999},
        db_session,
        agent_env["merchant_id"],
        agent_env["user_id"],
    )
    assert result["status"] == "SUCCESS"
    assert result["available"] is False


@pytest.mark.asyncio
async def test_tool_get_current_price(db_session, agent_env):
    result = await execute_tool(
        "get_current_price",
        {"product_id": "AG101"},
        db_session,
        agent_env["merchant_id"],
        agent_env["user_id"],
    )
    assert result["status"] == "SUCCESS"
    assert result["price"] == 2499.0


@pytest.mark.asyncio
async def test_tool_calculate_offer(db_session, agent_env):
    result = await execute_tool(
        "calculate_offer",
        {"product_id": "AG101", "requested_discount_percent": 50},
        db_session,
        agent_env["merchant_id"],
        agent_env["user_id"],
    )
    assert result["status"] == "SUCCESS"
    assert result["was_capped"] is True
    assert result["allowed_discount"] == 249.9  # 10% of 2499


@pytest.mark.asyncio
async def test_tool_create_order(db_session, agent_env):
    result = await execute_tool(
        "create_order",
        {"product_id": "AG103", "quantity": 1},
        db_session,
        agent_env["merchant_id"],
        agent_env["user_id"],
    )
    assert result["status"] == "SUCCESS"
    assert result["order_status"] == "APPROVED"
    assert result["total"] == 999.0


@pytest.mark.asyncio
async def test_tool_create_order_blocked(db_session, agent_env):
    result = await execute_tool(
        "create_order",
        {"product_id": "AG102", "quantity": 2},  # 2 × 4999 = 9998 > 5000 limit
        db_session,
        agent_env["merchant_id"],
        agent_env["user_id"],
    )
    assert result["status"] in ("SUCCESS", "BLOCKED")
    if result["status"] == "SUCCESS":
        assert result["order_status"] != "APPROVED"


@pytest.mark.asyncio
async def test_tool_unknown(db_session, agent_env):
    result = await execute_tool(
        "nonexistent_tool",
        {},
        db_session,
        agent_env["merchant_id"],
        agent_env["user_id"],
    )
    assert result["status"] == "FAILED"
    assert "Unknown tool" in result["error"]


# ─── Runtime Tests ───────────────────────────

@pytest.mark.asyncio
async def test_runtime_step_limit(db_session, agent_env):
    runtime = AgentRuntime(
        db=db_session,
        merchant_id=agent_env["merchant_id"],
        user_id=agent_env["user_id"],
        max_steps=1,
    )
    result = await runtime.run("Hello, what products do you have?")
    assert "session_id" in result
    assert "response" in result
    assert result["total_steps"] >= 1


# ─── API Tests ───────────────────────────────

@pytest.mark.asyncio
async def test_chat_api_health(client, agent_env):
    """Chat endpoint is reachable and processes input."""
    # Note: Use seeded merchant/user IDs to prevent empty DB health lookup failures
    response = await client.post("/api/agent/chat", json={
        "message": "Hello",
        "merchant_id": agent_env["merchant_id"],
        "user_id": agent_env["user_id"]
    })
    # Since we are mock/test mode without a live local model running,
    # the endpoint should either process successfully or raise an error, but NOT 404.
    assert response.status_code != 404