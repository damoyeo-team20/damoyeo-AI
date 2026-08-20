from fastapi import APIRouter

from app.graph.build_preference_graph import get_preference_graph
from app.schemas.preference import PreferenceExtractRequest, PreferenceExtractResponse

router = APIRouter(prefix="/ai/preferences", tags=["preferences"])


@router.post("/extract", response_model=PreferenceExtractResponse)
async def extract(payload: PreferenceExtractRequest) -> PreferenceExtractResponse:
    graph = get_preference_graph()
    # 그래프/노드는 단일 문자열 계약을 그대로 유지 — 배열을 받는 건 API 경계에서만 처리한다.
    message = ". ".join(m.strip() for m in payload.messages if m.strip())
    result = await graph.ainvoke({"message": message})

    return PreferenceExtractResponse(
        preferences=result.get("preferences", []),
        reply=result.get("assistant_reply"),
    )
