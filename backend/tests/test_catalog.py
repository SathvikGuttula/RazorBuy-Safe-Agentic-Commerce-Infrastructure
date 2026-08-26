"""Tests for the catalog API."""

import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_search_all_products(client, seed_catalog):
    response = await client.get("/api/products")
    assert response.status_code == 200
    data = response.json()
    assert "products" in data
    assert "total_found" in data
    assert data["total_found"] >= 6


@pytest.mark.asyncio
async def test_search_by_query(client, seed_catalog):
    response = await client.get("/api/products?query=earbuds")
    assert response.status_code == 200
    data = response.json()
    assert data["total_found"] > 0
    for p in data["products"]:
        assert "earbuds" in p["name"].lower() or "earbuds" in p["category"].lower()


@pytest.mark.asyncio
async def test_search_by_max_price(client, seed_catalog):
    response = await client.get("/api/products?max_price=1500")
    assert response.status_code == 200
    data = response.json()
    for p in data["products"]:
        assert p["price"] <= 1500


@pytest.mark.asyncio
async def test_search_by_category(client, seed_catalog):
    response = await client.get("/api/products?category=headphones")
    assert response.status_code == 200
    data = response.json()
    assert data["total_found"] >= 2
    for p in data["products"]:
        assert "headphone" in p["category"].lower()


@pytest.mark.asyncio
async def test_search_by_feature(client, seed_catalog):
    response = await client.get("/api/products?has_feature=anc")
    assert response.status_code == 200
    data = response.json()
    assert data["total_found"] >= 3
    for p in data["products"]:
        assert p["features"].get("anc") is True


@pytest.mark.asyncio
async def test_search_no_results(client, seed_catalog):
    response = await client.get("/api/products?query=xyznonexistent123")
    assert response.status_code == 200
    data = response.json()
    assert data["total_found"] == 0
    assert len(data["products"]) == 0


@pytest.mark.asyncio
async def test_get_product_by_sku(client, seed_catalog):
    response = await client.get("/api/products/P101")
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "P101"
    assert data["name"] == "SoundMax ANC Pro"
    assert data["price"] == 2499.0


@pytest.mark.asyncio
async def test_get_product_not_found(client, seed_catalog):
    response = await client.get("/api/products/NONEXISTENT")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_check_inventory(client, seed_catalog):
    response = await client.get("/api/inventory/P101")
    assert response.status_code == 200
    data = response.json()
    assert data["sku"] == "P101"
    assert data["available"] is True
    assert data["available_quantity"] > 0


@pytest.mark.asyncio
async def test_check_inventory_insufficient(client, seed_catalog):
    response = await client.get("/api/inventory/P101?required_quantity=99999")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False