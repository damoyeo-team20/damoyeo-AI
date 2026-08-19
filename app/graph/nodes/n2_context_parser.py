"""N2 Meeting Context Parser.

주최자의 자연어 요청을 해석한다. 지역/시간은 UI 입력이 항상 우선이며, LLM은 이 값을 추론하지 않는다.
`POST /ai/meetings/{meetingId}/context`가 호출한다.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.core.llm import get_llm
from app.prompts.n2_context_parser import SYSTEM_PROMPT, USER_TEMPLATE
from app.schemas.meeting_context import (
    MeetingContext,
    MeetingContextResponse,
    UiConflict,
    UiInputs,
)


class _ConflictDraft(BaseModel):
    field: Literal["region", "date", "time"]
    mentioned_value: str
    question: str


class _ContextExtraction(BaseModel):
    activity_hints: list[str] = Field(default_factory=list)
    meeting_tone: str | None = None
    explicit_constraints: list[str] = Field(default_factory=list)
    conflicts: list[_ConflictDraft] = Field(default_factory=list)


def _ui_value_for(field: str, ui_inputs: UiInputs) -> str:
    if field == "region":
        return ui_inputs.region
    if field == "date":
        return f"{ui_inputs.date_range.start} ~ {ui_inputs.date_range.end}"
    return f"{ui_inputs.time_range.start} ~ {ui_inputs.time_range.end}"


async def parse_meeting_context(
    host_message: str, ui_inputs: UiInputs
) -> MeetingContextResponse:
    llm = get_llm().with_structured_output(_ContextExtraction)
    system = SYSTEM_PROMPT.format(ui_inputs=ui_inputs.model_dump(by_alias=True))
    user = USER_TEMPLATE.format(host_message=host_message)

    result: _ContextExtraction = await llm.ainvoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )

    conflicts = [
        UiConflict(
            field=draft.field,
            ui_value=_ui_value_for(draft.field, ui_inputs),
            mentioned_value=draft.mentioned_value,
            question=draft.question,
        )
        for draft in result.conflicts
    ]
    return MeetingContextResponse(
        meeting_context=MeetingContext(
            activity_hints=result.activity_hints,
            meeting_tone=result.meeting_tone,
            explicit_constraints=result.explicit_constraints,
        ),
        conflicts_with_ui=conflicts,
    )
