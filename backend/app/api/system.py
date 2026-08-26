"""System status endpoint for demo - shows safety config."""

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.database.connection import get_db
from app.payments.razorpay_client import get_razorpay_client
from app.config.settings import get_settings

router = APIRouter()


@router.get("/system/status")
async def system_status(db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    rp = get_razorpay_client()

    # Check DB connectivity
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    return {
        "app_env": settings.app_env,
        "debug": settings.app_debug,
        "database": db_status,
        "llm_provider": settings.llm_provider,
        "razorpay_configured": rp.is_configured,
        "policy_engine": "DETERMINISTIC",
        "audit_log": "APPEND_ONLY",
        "core_principle": "LLM is never the authority for financial actions",
    }