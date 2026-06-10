"""Environment-based application configuration.

Settings are loaded once and cached. Everything that varies between
environments (dev / staging / prod) is read from environment variables or a
local `.env` file — no environment-specific values are hardcoded.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    APP_NAME: str = "Elangovan Associates"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    # NoDecode: keep pydantic-settings from JSON-parsing the env value so the
    # comma-separated string is handled by the validator below.
    CORS_ORIGINS: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    # ---- Database ----
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/elangovan"

    # ---- JWT / Security ----
    JWT_SECRET_KEY: str = "CHANGE_ME"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30

    # ---- Initial Super Admin ----
    SUPERADMIN_EMAIL: str = "admin@keplercrew.com"
    SUPERADMIN_PASSWORD: str = "ChangeMe!2026"

    # ---- Invoice module ----
    # Auto-generated invoice numbers look like: {PREFIX}-YYYYMMDD-NNN
    INVOICE_NUMBER_PREFIX: str = "EA"

    # ---- Cloudflare R2 ----
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = "elangovan-files"
    R2_PUBLIC_BASE_URL: str = ""

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors(cls, v: object) -> object:
        """Accept a comma-separated string from the environment."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
