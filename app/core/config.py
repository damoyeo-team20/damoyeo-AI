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
    # AI -> Back 호출에 실어 보내는 공유 비밀값. Back과 반드시 같은 값이어야 한다.
    internal_api_key: str = ""

    # DB (AI 서비스가 직접 소유하는 preference_vocabulary 등)
    database_url: str = "postgresql+asyncpg://localhost:5432/damoyeo_ai"

    # TODO: 임시 플래그. Place Verifier(영업 검증)가 Gemini google_search 할당량 문제로 테스트를 막고 있어서
    # 우회용으로 추가함 (2026-08-20). 원인(할당량) 해결되면 이 플래그와 관련 분기를 지운다.
    skip_business_hours_verification: bool = False

    # LangSmith
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = ""
    langsmith_endpoint: str = "https://api.smith.langchain.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def configure_langsmith(settings: Settings | None = None) -> None:
    """`.env`는 pydantic-settings로만 읽히고 os.environ에는 반영되지 않으므로,
    langsmith/langchain 라이브러리가 직접 읽는 환경변수로 명시적으로 옮겨줘야 트레이싱이 켜진다.
    """
    settings = settings or get_settings()
    if not settings.langsmith_tracing:
        return
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    # 구버전 langchain 트레이싱 경로 호환용.
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint
