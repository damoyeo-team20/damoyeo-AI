import pytest
from pydantic import ValidationError

from app.schemas.meeting_context import (
    CandidateDate,
    ChatTurn,
    ContextFinalizeRequest,
    ContextMessageRequest,
)


def test_context_message_request_accepts_empty_history():
    request = ContextMessageRequest(message="너무 시끄러운 곳은 피하고 싶어요")

    assert request.history == []
    assert request.message == "너무 시끄러운 곳은 피하고 싶어요"


@pytest.mark.parametrize("message", ["", "   ", "\n"])
def test_context_message_request_rejects_blank_message(message):
    with pytest.raises(ValidationError):
        ContextMessageRequest(message=message)


def test_context_finalize_request_requires_at_least_one_user_turn():
    with pytest.raises(ValidationError):
        ContextFinalizeRequest(
            history=[ChatTurn(role="ASSISTANT", content="안녕하세요, 어떤 모임인가요?")]
        )


def test_context_finalize_request_accepts_history_with_user_turn():
    request = ContextFinalizeRequest(
        history=[
            ChatTurn(role="USER", content="오랜만에 만나서 저녁 먹고 이야기하려고요"),
            ChatTurn(role="ASSISTANT", content="편안한 저녁 자리로 준비할게요."),
        ]
    )

    assert len(request.history) == 2


def test_context_message_request_allows_missing_candidate_dates():
    request = ContextMessageRequest(message="너무 시끄러운 곳은 피하고 싶어요")

    assert request.candidate_dates is None


def test_context_message_request_accepts_valid_candidate_dates():
    request = ContextMessageRequest(
        message="30일로 바꿔줘",
        candidateDates=[
            {"date": "2026-08-23", "selected": True},
            {"date": "2026-08-30", "selected": False},
        ],
    )

    assert request.candidate_dates == [
        CandidateDate(date="2026-08-23", selected=True),
        CandidateDate(date="2026-08-30", selected=False),
    ]


def test_context_message_request_rejects_empty_candidate_dates():
    with pytest.raises(ValidationError):
        ContextMessageRequest(message="30일로 바꿔줘", candidateDates=[])


def test_context_message_request_rejects_duplicate_candidate_dates():
    with pytest.raises(ValidationError):
        ContextMessageRequest(
            message="30일로 바꿔줘",
            candidateDates=[
                {"date": "2026-08-23", "selected": True},
                {"date": "2026-08-23", "selected": False},
            ],
        )


@pytest.mark.parametrize(
    "selected_flags",
    [
        [False, False],
        [True, True],
    ],
)
def test_context_message_request_rejects_wrong_selected_count(selected_flags):
    with pytest.raises(ValidationError):
        ContextMessageRequest(
            message="30일로 바꿔줘",
            candidateDates=[
                {"date": "2026-08-23", "selected": selected_flags[0]},
                {"date": "2026-08-30", "selected": selected_flags[1]},
            ],
        )
