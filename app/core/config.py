from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql://specter:specter@timescaledb:5432/specter"
    ENVIRONMENT: str = "development"
    REDIS_URL: str = "redis://redis:6379"


settings = Settings()
