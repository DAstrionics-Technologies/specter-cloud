from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql://specter:specter@postgres:5432/specter"
    ENVIRONMENT: str = "development"
    REDIS_URL: str = "redis://redis:6379"

    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]

    # Session cookie attributes. Defaults are dev-friendly (HTTP localhost).
    # In production, override via env: SESSION_COOKIE_SECURE=true and
    # SESSION_COOKIE_SAMESITE=none if dashboard and API are on different
    # eTLD+1 domains.
    SESSION_COOKIE_SECURE: bool = False
    SESSION_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"


settings = Settings()
