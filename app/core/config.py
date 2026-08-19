import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM (Gemini)
    google_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"

    # External APIs
    kakao_rest_api_key: str = ""
    google_calendar_client_id: str = ""
    google_calendar_client_secret: str = ""

    # Backend (Vocabulary API 등)
    backend_api_base_url: str = "http://localhost:8080"

    # LangSmith
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "damoyeo-ai"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def configure_langsmith(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if not settings.langsmith_tracing:
        return
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
