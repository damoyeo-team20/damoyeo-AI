"""Kakao Local API 클라이언트. candidates 파이프라인의 L5 노드가 사용한다."""

import httpx
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.errors import AIServiceError

_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


class KakaoPlace(BaseModel):
    kakao_place_id: str
    name: str
    address: str
    category: str
    # 장소 상세페이지 URL. 응답의 place_url 필드.
    place_url: str | None = None
    # Kakao 응답의 x=경도(longitude), y=위도(latitude) — 이름이 직관과 반대라 뒤집지 않도록 주의.
    latitude: float | None = None
    longitude: float | None = None


async def search_places(keyword: str, region: str, size: int = 5) -> list[KakaoPlace]:
    settings = get_settings()
    if not settings.kakao_rest_api_key:
        raise AIServiceError(
            code="KAKAO_API_KEY_MISSING",
            message="KAKAO_REST_API_KEY가 설정되어 있지 않습니다.",
            status_code=500,
            # 설정 문제라 같은 요청을 재시도해도 결과가 바뀌지 않는다.
            retryable=False,
        )

    headers = {"Authorization": f"KakaoAK {settings.kakao_rest_api_key}"}
    params = {"query": f"{region} {keyword}", "size": size}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(_SEARCH_URL, headers=headers, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # docs/api-design2-backend.md 6장의 PLACE_PROVIDER_ERROR(502)에 대응.
            # 우리는 Kakao 하나만 쓰지만 문서는 장소 제공자 실패를 이 code로 통칭한다.
            raise AIServiceError(
                code="PLACE_PROVIDER_ERROR",
                message=f"Kakao Local API 호출 실패: {exc}",
                status_code=502,
                retryable=True,
            ) from exc

    documents = response.json().get("documents", [])
    return [
        KakaoPlace(
            kakao_place_id=doc["id"],
            name=doc["place_name"],
            address=doc.get("road_address_name") or doc["address_name"],
            category=doc.get("category_name", ""),
            place_url=doc.get("place_url"),
            latitude=_to_float(doc.get("y")),
            longitude=_to_float(doc.get("x")),
        )
        for doc in documents
    ]


def _to_float(value: object) -> float | None:
    """좌표는 문자열로 내려온다. 값이 없거나 숫자가 아니면 좌표 없이 진행한다."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
