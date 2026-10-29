from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "MedV Microservice"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # LLM Configuration
    LLM_PROVIDER: str = "gemini"  # "gemini", "openai", or "mock"
    LLM_MODEL: str = "gemini-3.5-flash"
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None

    # Alternative standard environment variables
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
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


settings = Settings()
