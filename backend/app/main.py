"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.connection import init_db, close_db
from app.api.catalog import router as catalog_router
from app.api.policies import router as policies_router
from app.api.orders import router as orders_router
from app.api.payments import router as payments_router
from app.api.audit import router as audit_router
from app.api.agent import router as agent_router
from app.config.settings import get_settings

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
from app.payments.razorpay_client import get_razorpay_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    rp = get_razorpay_client()
    if not rp.is_configured:
        logging.warning("⚠️  RAZORPAY KEYS NOT CONFIGURED. Payments will run in MOCK MODE.")
    yield
    await close_db()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="RazorBuy API",
    description="Safe Agentic Commerce Infrastructure",
    version="0.5.0",
    lifespan=lifespan,
)

# Parse CORS origins from env (comma-separated). Default to localhost:3000
_cors_origins = [
    o.strip()
    for o in getattr(settings, "cors_origins", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
from app.api.system import router as system_router
app.include_router(system_router, prefix="/api", tags=["system"])
app.include_router(catalog_router, prefix="/api", tags=["catalog"])
app.include_router(policies_router, prefix="/api", tags=["policies"])
app.include_router(orders_router, prefix="/api", tags=["orders"])
app.include_router(payments_router, prefix="/api", tags=["payments"])
app.include_router(audit_router, prefix="/api", tags=["audit"])
app.include_router(agent_router, prefix="/api", tags=["agent"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "razorbuy"}