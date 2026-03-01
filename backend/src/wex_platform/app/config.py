"""Application configuration via Pydantic Settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

# Resolve .env from backend/ regardless of CWD
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Central configuration loaded from environment variables / .env file."""

    # Database
    database_url: str = "sqlite+aiosqlite:///./wex_platform.db"

    # AI
    gemini_api_key: str = ""
    google_maps_api_key: str = ""

    # Auth / JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440

    # External services
    sendgrid_api_key: str = ""
    supply_alert_from: str = ""
    supply_alert_to: str = ""

    # CORS / Frontend
    cors_origins: str = "http://localhost:3000"
    frontend_url: str = "https://warehouseexchange.com"

    # Aircall
    aircall_number_id: str = ""
    aircall_api_id: str = ""
    aircall_api_token: str = ""
    aircall_webhook_token: str = ""
    aircall_buyer_number_id: str = ""

    # Vapi Voice Agent
    vapi_api_key: str = ""
    vapi_server_secret: str = ""
    vapi_phone_number_id: str = ""
    vapi_voice_id: str = ""

    # Admin
    admin_password: str = "wex2026"

    # General
    debug: bool = True

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list.

        In debug mode, returns ["*"] to allow any origin (LAN IPs, etc.).
        """
        if self.debug:
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
