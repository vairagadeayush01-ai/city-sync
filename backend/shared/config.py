"""
CitySync — Application Configuration
Loads all settings from environment variables / .env file.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(
        "postgresql+asyncpg://citysync:citysync_secret@localhost:5432/citysync"
    )
    database_url_sync: str = Field(
        "postgresql://citysync:citysync_secret@localhost:5432/citysync"
    )

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = Field("redis://localhost:6379/0")

    # ── MinIO ─────────────────────────────────────────────────────────────────
    minio_endpoint: str = Field("localhost:9000")
    minio_access_key: str = Field("citysync_minio")
    minio_secret_key: str = Field("citysync_minio_secret")
    minio_bucket: str = Field("citysync")
    minio_secure: bool = Field(False)

    # ── Groq API with optional Portkey gateway ────────────────────────────────
    portkey_api_key: str = Field("")
    portkey_config_id: str = Field("")
    portkey_base_url: str = Field("https://api.portkey.ai/v1")
    groq_api_key: str = Field("")
    groq_fallback_api_key: str = Field("")
    groq_base_url: str = Field("https://api.groq.com/openai/v1")
    groq_model: str = Field("qwen/qwen3.8-27b")
    mock_ai: bool = Field(True)

    # ── Mapbox ────────────────────────────────────────────────────────────────
    mapbox_token: str = Field("")
    mock_map: bool = Field(False)

    # ── Twilio ────────────────────────────────────────────────────────────────
    twilio_account_sid: str = Field("")
    twilio_auth_token: str = Field("")
    twilio_from_number: str = Field("")
    twilio_phone_number: str = Field("")
    twilio_whatsapp_number: str = Field("whatsapp:+14155238886")
    mock_notifications: bool = Field(True)

    # ── SendGrid ──────────────────────────────────────────────────────────────
    sendgrid_api_key: str = Field("")
    sendgrid_from_email: str = Field("alerts@citysync.in")
    mock_email: bool = Field(True)

    # ── Privacy / Security ────────────────────────────────────────────────────
    hmac_secret_key: str = Field("citysync-default-hmac-secret-change-in-prod")
    jwt_secret_key: str = Field("citysync-default-jwt-secret-change-in-prod")
    jwt_algorithm: str = Field("HS256")
    jwt_expire_minutes: int = Field(1440)

    # ── Webhook signing ───────────────────────────────────────────────────────
    webhook_hmac_secret: str = Field("citysync-webhook-signing-secret")

    # ── App ───────────────────────────────────────────────────────────────────
    app_env: str = Field("development")
    log_level: str = Field("INFO")
    cors_origins: str = Field("http://localhost:5173,http://localhost:3000")

    # ── Ports ─────────────────────────────────────────────────────────────────
    gateway_port: int = Field(8000)
    routing_port: int = Field(8001)
    verification_port: int = Field(8002)
    dept_portal_port: int = Field(3000)
    dept_portal_url: str = Field("http://localhost:3000/webhook")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
