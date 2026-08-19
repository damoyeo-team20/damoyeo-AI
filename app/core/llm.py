from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import get_settings


def get_llm(temperature: float = 0.0, model: str | None = None) -> ChatGoogleGenerativeAI:
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model=model or settings.gemini_model,
        google_api_key=settings.google_api_key,
        temperature=temperature,
    )
