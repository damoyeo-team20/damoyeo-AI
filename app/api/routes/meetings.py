from fastapi import APIRouter

from app.graph.build_graph import get_candidates_graph
from app.graph.nodes.n2_context_parser import finalize_meeting_context, generate_context_reply
from app.schemas.candidates import CandidatesRequest, CandidatesResponse, CandidatesStatus
from app.schemas.meeting_context import (
    ContextFinalizeRequest,
    ContextFinalizeResponse,
    ContextMessageRequest,
    ContextMessageResponse,
)

router = APIRouter(prefix="/ai/meetings/{meeting_id}", tags=["meetings"])


@router.post("/context/messages", response_model=ContextMessageResponse)
async def context_message(
    meeting_id: int, payload: ContextMessageRequest
) -> ContextMessageResponse:
    return await generate_context_reply(payload.history, payload.message)


@router.post("/context", response_model=ContextFinalizeResponse)
async def finalize_context(
    meeting_id: int, payload: ContextFinalizeRequest
) -> ContextFinalizeResponse:
    return await finalize_meeting_context(payload.history)


@router.post("/candidates", response_model=CandidatesResponse)
async def get_candidates(meeting_id: int, payload: CandidatesRequest) -> CandidatesResponse:
    graph = get_candidates_graph()
    result = await graph.ainvoke(
        {
            "confirmed_slot": payload.confirmed_slot,
            "region": payload.region,
            "purpose": payload.purpose,
            "meeting_context": payload.meeting_context,
            "participant_preferences": payload.participant_preferences,
            "blocked_domains": payload.blocked_domains,
        }
    )

    if result.get("conflict"):
        return CandidatesResponse(
            status=CandidatesStatus.CONFLICT,
            conflict=result["conflict"],
            candidates=[],
            excluded=result.get("excluded", []),
        )

    return CandidatesResponse(
        status=CandidatesStatus.OK,
        meeting_tags=result.get("meeting_tags", []),
        candidates=result.get("final_candidates", []),
        excluded=result.get("excluded", []),
        verification_timed_out=result.get("verification_timed_out", False),
    )
