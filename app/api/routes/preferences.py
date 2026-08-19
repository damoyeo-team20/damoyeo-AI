from fastapi import APIRouter

from app.graph.build_preference_graph import get_preference_graph
from app.schemas.preference import PreferenceExtractRequest, PreferenceExtractResponse

router = APIRouter(prefix="/ai/preferences", tags=["preferences"])


@router.post("/extract", response_model=PreferenceExtractResponse)
async def extract(payload: PreferenceExtractRequest) -> PreferenceExtractResponse:
    graph = get_preference_graph()
    result = await graph.ainvoke({"message": payload.message})

    return PreferenceExtractResponse(
        preferences=result.get("preferences", []),
        assistant_reply=result.get("assistant_reply"),
    )
