from fastapi import APIRouter

from app.schemas.vocabulary import VocabularyListResponse
from app.services.vocabulary_client import fetch_vocabulary

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/preference-vocabulary", response_model=VocabularyListResponse)
async def get_preference_vocabulary() -> VocabularyListResponse:
    # force_refresh=True: 이 API는 외부(Back 등)가 최신 상태를 조회하는 용도이므로
    # Preference 파이프라인용 인메모리 캐시에 기대지 않는다. 조회한 값으로 캐시도 함께 갱신된다.
    vocabulary = await fetch_vocabulary(force_refresh=True)
    return VocabularyListResponse(vocabulary=vocabulary)
