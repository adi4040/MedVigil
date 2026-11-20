from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


API_DIR = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = API_DIR.parents[1]


class Settings(BaseSettings):
    APP_NAME: str = "MedV Microservice"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # LLM Configuration
    LLM_PROVIDER: str = "gemini"  # "gemini", "openai", or "mock"
    LLM_MODEL: str = "gemini-3.5-flash"
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None

    # Alternative standard environment variables
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None

    # PostgreSQL Database Configuration
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "medv_user"
    POSTGRES_PASSWORD: str = "medv_password"
    POSTGRES_DB: str = "medv_db"
    DATABASE_URL: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=(REPOSITORY_ROOT / ".env", API_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    def get_effective_api_key(self) -> Optional[str]:
        if self.LLM_API_KEY:
            return self.LLM_API_KEY
        if self.LLM_PROVIDER.lower() in ("gemini", "google"):
            return self.GEMINI_API_KEY or self.OPENAI_API_KEY
        return self.OPENAI_API_KEY or self.GEMINI_API_KEY

    def get_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    def get_async_database_url(self) -> str:
        """Returns PostgreSQL URL formatted for asyncpg async engine."""
        if self.DATABASE_URL:
            if self.DATABASE_URL.startswith("postgresql://"):
                return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def get_sync_database_url(self) -> str:
        """Returns PostgreSQL URL formatted for psycopg / alembic sync operations."""
        if self.DATABASE_URL:
            if self.DATABASE_URL.startswith("postgresql+asyncpg://"):
                return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
