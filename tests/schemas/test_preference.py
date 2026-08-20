import pytest
from pydantic import ValidationError

from app.schemas.preference import PreferenceExtractRequest, PreferenceExtractResponse


def test_preference_request_only_requires_current_submission_messages():
    request = PreferenceExtractRequest(messages=["매운 음식 좋아해"])

    assert request.model_dump(by_alias=True) == {"messages": ["매운 음식 좋아해"]}


def test_preference_response_uses_reply_and_extracted_preferences_field_names():
    response = PreferenceExtractResponse(reply="말씀해주신 내용을 선호에 반영했어요.")

    assert response.model_dump(by_alias=True) == {
        "extractedPreferences": [],
        "reply": "말씀해주신 내용을 선호에 반영했어요.",
    }


@pytest.mark.parametrize("messages", [[], ["  ", "\n"]])
def test_preference_request_rejects_empty_messages(messages):
    with pytest.raises(ValidationError):
        PreferenceExtractRequest(messages=messages)
