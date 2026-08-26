"""Application settings loaded from environment variables and .env file."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

# Resolve project root: this file is at backend/app/config/settings.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

    
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
    )
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Database
    database_url: str = "postgresql+asyncpg://razorbuy:razorbuy_dev_2026@localhost:5432/razorbuy"

    # Razorpay
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # LLM
    llm_provider: str = "local"
    local_llm_base_url: str = "http://localhost:11434"
    local_llm_model: str = "qwen2.5:7b"
    hosted_llm_api_key: str = ""
    hosted_llm_model: str = ""

    # App
    app_env: str = "development"
    app_debug: bool = True
    secret_key: str = "change-me-in-production"

    # Agent
    agent_max_steps: int = 20
    agent_timeout_seconds: int = 120

    # Payment
    payment_timeout_seconds: int = 30
    inventory_reservation_minutes: int = 15


@lru_cache()
def get_settings() -> Settings:
    return Settings()