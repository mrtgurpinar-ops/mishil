from typing import List
import os
from pydantic import Field, field_validator

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:
    from pydantic import BaseModel as BaseSettings
    SettingsConfigDict = dict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # General App Config
    APP_NAME: str = "mishil"
    APP_TITLE: str = "Mishil API - Baby Sleep & Routines"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Security & Authentication
    JWT_SECRET: str = Field(
        default="mishil_default_dev_jwt_secret_key_change_in_production_32_bytes",
        description="Secret key for signing JWT tokens"
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200  # 30 days for mobile apps
    API_KEY_HEADER_NAME: str = "X-Mishil-API-Key"
    STATIC_API_KEY: str = "mishil_mobile_client_key_v1"

    # Database
    DATABASE_URL: str = "sqlite:///./mishil.db"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        if isinstance(v, str) and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v

    # RevenueCat & Subscription
    REVENUECAT_WEBHOOK_SECRET: str = "rc_webhook_secret_example_key"
    TRIAL_DURATION_DAYS: int = 3

    # Audio & Cry Analysis Constraints
    MAX_AUDIO_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB
    ALLOWED_AUDIO_MIME_TYPES: List[str] = [
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/m4a",
        "audio/x-m4a",
        "audio/mp4",
        "audio/mpeg",
        "audio/mp3",
        "audio/aac",
        "application/octet-stream"  # Mobile client upload fallbacks
    ]

    # CORS
    CORS_ORIGINS: List[str] = ["*"]


settings = Settings()
