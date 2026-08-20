from fastapi import APIRouter

from app.core.errors import AIServiceError
from app.graph.build_graph import get_candidates_graph
from app.graph.nodes.n2_context_parser import finalize_meeting_context, generate_context_reply
from app.graph.nodes.n3_schedule_resolver import resolve_schedule
from app.schemas.candidates import (
    ActionRequired,
    ActionRequiredType,
    CandidatesRequest,
    CandidatesResponse,
    CandidatesStatus,
)
from app.schemas.meeting_context import (
    ContextFinalizeRequest,
    ContextFinalizeResponse,
    ContextMessageRequest,
    ContextMessageResponse,
)
from app.schemas.schedule import ScheduleRequest, ScheduleResponse

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


@router.post("/schedule", response_model=ScheduleResponse)
async def schedule(meeting_id: int, payload: ScheduleRequest) -> ScheduleResponse:
    return await resolve_schedule(payload)


@router.post("/candidates", response_model=CandidatesResponse)
async def get_candidates(meeting_id: int, payload: CandidatesRequest) -> CandidatesResponse:
    if payload.meeting.id != meeting_id:
        raise AIServiceError(
            code="MEETING_ID_MISMATCH",
            message="path의 meetingId와 body의 meeting.id가 다릅니다.",
            status_code=400,
            retryable=False,
        )

    applied_duration = payload.confirmed_slot.duration_minutes
    # 참여자별 구분은 여기서 없앤다 — 후보 선정은 항상 집단 수준으로 판단하기 때문.
    preferences = [pref for p in payload.participants for pref in p.preferences]

    graph = get_candidates_graph()
    result = await graph.ainvoke(
        {
            "meeting": payload.meeting,
            "confirmed_slot": payload.confirmed_slot,
            "participant_preferences": preferences,
            "meeting_memory_summary": (payload.meeting_memory or {}).get("summary"),
            "excluded_external_place_ids": payload.excluded_external_place_ids,
        }
    )

    action_required = result.get("action_required")
    if action_required is not None:
        return CandidatesResponse(
            request_id=payload.request_id,
            status=CandidatesStatus.CONFLICT,
            applied_duration_minutes=applied_duration,
            action_required=action_required,
        )

    suggestions = result.get("suggestions", [])
    timed_out = result.get("verification_timed_out", False)

    if not suggestions:
        # 검증이 시간 안에 하나도 끝나지 않았다면 "후보가 없다"고 단정할 수 없다 —
        # 아직 판단하지 못한 것이므로 재시도 가능한 timeout으로 알린다.
        if timed_out:
            raise AIServiceError(
                code="CANDIDATE_GENERATION_TIMEOUT",
                message="제한 시간 안에 후보 검증을 완료하지 못했습니다.",
                status_code=504,
                retryable=True,
            )
        return CandidatesResponse(
            request_id=payload.request_id,
            status=CandidatesStatus.NO_CANDIDATE,
            applied_duration_minutes=applied_duration,
            meeting_tags=result.get("meeting_tags", []),
            action_required=ActionRequired(
                type=ActionRequiredType.NO_CANDIDATE,
                message="조건에 맞는 장소를 찾지 못했습니다.",
            ),
        )

    return CandidatesResponse(
        request_id=payload.request_id,
        status=CandidatesStatus.OK,
        applied_duration_minutes=applied_duration,
        summary=result.get("summary", ""),
        meeting_tags=result.get("meeting_tags", []),
        suggestions=suggestions,
        verification_timed_out=timed_out,
    )
