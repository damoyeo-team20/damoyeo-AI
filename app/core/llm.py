from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import get_settings


def get_llm(temperature: float = 0.0, model: str | None = None) -> ChatGoogleGenerativeAI:
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model=model or settings.gemini_model,
        google_api_key=settings.google_api_key,
        temperature=temperature,
    )


def extract_text_content(content: object) -> str:
    """with_structured_output을 쓰지 않은 일반 ainvoke() 응답의 content를 평문으로 정규화한다."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        return "\n".join(parts)
    return str(content)
