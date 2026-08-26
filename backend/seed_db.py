"""Seed the database with test data.

Run from the backend/ directory with venv activated:
    python seed_db.py
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal

# Ensure app package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select
from app.database.connection import async_session_factory, init_db, engine
from app.database.models import (
    User, Merchant, Product, Inventory, MerchantPolicy
)


# ─── Seed Data ───────────────────────────────

PRODUCTS = [
    # Wireless Earbuds (6)
    {"sku": "P101", "name": "SoundMax ANC Pro", "category": "wireless_earbuds",
     "price": 2499, "description": "Premium ANC earbuds with 35h battery and deep bass.",
     "features": {"anc": True, "battery_hours": 35, "bluetooth": "5.3", "water_resistant": False},
     "tags": ["anc", "premium", "long-battery"], "stock": 25},

    {"sku": "P102", "name": "BassBud Lite", "category": "wireless_earbuds",
     "price": 1299, "description": "Budget-friendly earbuds with punchy bass.",
     "features": {"anc": False, "battery_hours": 20, "bluetooth": "5.1", "water_resistant": False},
     "tags": ["budget", "bass"], "stock": 50},

    {"sku": "P103", "name": "NoiseFree Elite", "category": "wireless_earbuds",
     "price": 3499, "description": "Top-tier noise cancellation with 40h playtime.",
     "features": {"anc": True, "battery_hours": 40, "bluetooth": "5.3", "water_resistant": True},
     "tags": ["anc", "premium", "waterproof"], "stock": 15},

    {"sku": "P104", "name": "BeatDrop Sport", "category": "wireless_earbuds",
     "price": 1999, "description": "IPX7 sport earbuds with secure fit.",
     "features": {"anc": False, "battery_hours": 28, "bluetooth": "5.2", "water_resistant": True},
     "tags": ["sport", "waterproof"], "stock": 30},

    {"sku": "P105", "name": "ClearTone Mini", "category": "wireless_earbuds",
     "price": 2799, "description": "Compact ANC earbuds with crystal-clear calls.",
     "features": {"anc": True, "battery_hours": 30, "bluetooth": "5.2", "water_resistant": False},
     "tags": ["anc", "compact", "calls"], "stock": 20},

    {"sku": "P106", "name": "PulseWave X1", "category": "wireless_earbuds",
     "price": 999, "description": "Entry-level wireless earbuds.",
     "features": {"anc": False, "battery_hours": 15, "bluetooth": "5.0", "water_resistant": False},
     "tags": ["budget", "entry-level"], "stock": 100},

    # Headphones (4)
    {"sku": "P201", "name": "AudioKing OverEar", "category": "headphones",
     "price": 4999, "description": "Over-ear ANC headphones with 50h battery.",
     "features": {"anc": True, "battery_hours": 50, "bluetooth": "5.3", "foldable": True},
     "tags": ["anc", "over-ear", "premium"], "stock": 12},

    {"sku": "P202", "name": "StudioMax Pro", "category": "headphones",
     "price": 7999, "description": "Studio-grade headphones with Hi-Res audio.",
     "features": {"anc": True, "battery_hours": 60, "bluetooth": "5.3", "foldable": True},
     "tags": ["anc", "studio", "hi-res"], "stock": 8},

    {"sku": "P203", "name": "BassHeavy 500", "category": "headphones",
     "price": 2999, "description": "Bass-focused on-ear headphones.",
     "features": {"anc": False, "battery_hours": 40, "bluetooth": "5.1", "foldable": True},
     "tags": ["bass", "on-ear"], "stock": 20},

    {"sku": "P204", "name": "TravelQuiet ANC", "category": "headphones",
     "price": 5499, "description": "Travel headphones with adaptive ANC.",
     "features": {"anc": True, "battery_hours": 45, "bluetooth": "5.2", "foldable": True},
     "tags": ["anc", "travel", "adaptive"], "stock": 10},

    # Speakers (4)
    {"sku": "P301", "name": "BoomBox Mini", "category": "speakers",
     "price": 1499, "description": "Portable Bluetooth speaker with 12h battery.",
     "features": {"waterproof": True, "battery_hours": 12, "bluetooth": "5.1", "watts": 10},
     "tags": ["portable", "waterproof"], "stock": 35},

    {"sku": "P302", "name": "SoundTower 360", "category": "speakers",
     "price": 3999, "description": "360-degree room-filling sound.",
     "features": {"waterproof": False, "battery_hours": 20, "bluetooth": "5.2", "watts": 30},
     "tags": ["360", "room-filling"], "stock": 15},

    {"sku": "P303", "name": "PartyBlast XL", "category": "speakers",
     "price": 6999, "description": "Party speaker with RGB lights and deep bass.",
     "features": {"waterproof": True, "battery_hours": 24, "bluetooth": "5.3", "watts": 60},
     "tags": ["party", "rgb", "loud"], "stock": 7},

    {"sku": "P304", "name": "PocketSound", "category": "speakers",
     "price": 799, "description": "Ultra-compact pocket speaker.",
     "features": {"waterproof": False, "battery_hours": 8, "bluetooth": "5.0", "watts": 5},
     "tags": ["compact", "budget"], "stock": 60},

    # Smartwatches (3)
    {"sku": "P401", "name": "FitTrack Pro", "category": "smartwatches",
     "price": 3999, "description": "Fitness smartwatch with heart rate and GPS.",
     "features": {"heart_rate": True, "gps": True, "spo2": False, "battery_days": 7},
     "tags": ["fitness", "gps"], "stock": 18},

    {"sku": "P402", "name": "SmartBand Lite", "category": "smartwatches",
     "price": 1499, "description": "Affordable fitness band with notifications.",
     "features": {"heart_rate": True, "gps": False, "spo2": False, "battery_days": 14},
     "tags": ["fitness", "budget", "band"], "stock": 40},

    {"sku": "P403", "name": "ChronoMax Ultra", "category": "smartwatches",
     "price": 8999, "description": "Premium smartwatch with AMOLED, GPS, SpO2.",
     "features": {"heart_rate": True, "gps": True, "spo2": True, "battery_days": 5},
     "tags": ["premium", "amoled", "gps", "spo2"], "stock": 6},

    # Accessories (3)
    {"sku": "P501", "name": "QuickCharge 65W", "category": "accessories",
     "price": 1299, "description": "GaN 65W USB-C fast charger.",
     "features": {"watts": 65, "ports": 2, "gan": True, "usb_c": True},
     "tags": ["charger", "fast-charge", "gan"], "stock": 45},

    {"sku": "P502", "name": "MagSafe Duo Pad", "category": "accessories",
     "price": 2499, "description": "15W wireless charging pad with MagSafe.",
     "features": {"watts": 15, "magsafe": True, "qi": True, "dual": True},
     "tags": ["wireless-charger", "magsafe"], "stock": 22},

    {"sku": "P503", "name": "CableKit Premium", "category": "accessories",
     "price": 499, "description": "3-in-1 braided cable (USB-C, Lightning, Micro).",
     "features": {"length_m": 1.5, "braided": True, "connectors": 3},
     "tags": ["cable", "3-in-1"], "stock": 80},
]


async def seed():
    """Seed the database with test data."""
    await init_db()

    async with async_session_factory() as session:
        # Check if already seeded
        existing = await session.execute(select(Merchant))
        if existing.scalar_one_or_none():
            print("Database already seeded. Skipping.")
            return

        # 1. Create merchant
        merchant = Merchant(
            name="RazorBuy Demo Store",
            currency="INR",
            status="active",
        )
        session.add(merchant)
        await session.flush()
        print(f"Created merchant: {merchant.name} ({merchant.id})")

        # 2. Create user
        user = User(
            name="Test Buyer",
            email="buyer@test.com",
            autonomous_spending_limit=Decimal("3000.00"),
        )
        session.add(user)
        await session.flush()
        print(f"Created user: {user.name} ({user.id})")

        # 3. Create merchant policy
        policy = MerchantPolicy(
            merchant_id=merchant.id,
            max_autonomous_transaction_amount=Decimal("3000.00"),
            max_discount_percent=Decimal("10.00"),
            max_discount_amount=Decimal("300.00"),
            negotiation_enabled=True,
            auto_purchase_enabled=True,
            confirmation_threshold=Decimal("3000.00"),
            max_payment_attempts=2,
            refund_requires_human=True,
            restricted_categories=[],
            restricted_products=[],
            version=1,
        )
        session.add(policy)
        await session.flush()
        print(f"Created policy: v{policy.version}")

        # 4. Create products + inventory
        for p in PRODUCTS:
            product = Product(
                merchant_id=merchant.id,
                sku=p["sku"],
                name=p["name"],
                description=p["description"],
                category=p["category"],
                price=Decimal(str(p["price"])),
                currency="INR",
                features=p["features"],
                tags=p["tags"],
                active=True,
            )
            session.add(product)
            await session.flush()

            inventory = Inventory(
                product_id=product.id,
                available_quantity=p["stock"],
                reserved_quantity=0,
            )
            session.add(inventory)

        await session.commit()
        print(f"\nSeeded {len(PRODUCTS)} products with inventory.")
        print("Done!")


if __name__ == "__main__":
    asyncio.run(seed())