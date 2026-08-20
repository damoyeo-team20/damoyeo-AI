from fastapi import APIRouter

from app.graph.build_graph import get_candidates_graph
from app.graph.nodes.n2_context_parser import parse_meeting_context
from app.graph.nodes.n8_revision_router import route_revision
from app.schemas.candidates import CandidatesRequest, CandidatesResponse, CandidatesStatus
from app.schemas.meeting_context import MeetingContextRequest, MeetingContextResponse
from app.schemas.revise import ReviseRequest, ReviseResponse

router = APIRouter(prefix="/ai/meetings/{meeting_id}", tags=["meetings"])


@router.post("/context", response_model=MeetingContextResponse)
async def parse_context(
    meeting_id: int, payload: MeetingContextRequest
) -> MeetingContextResponse:
    return await parse_meeting_context(payload.purpose, payload.ui_inputs)


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


@router.post("/revise", response_model=ReviseResponse)
async def revise(meeting_id: int, payload: ReviseRequest) -> ReviseResponse:
    return await route_revision(payload.feedback, payload.current_candidates)
