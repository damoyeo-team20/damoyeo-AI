"""개인 선호 입력의 결정론적 응답 가드레일.

범위 밖 입력에 잡담으로 답하지 않고, 이 화면에서 받을 수 있는 개인 선호를 다시 안내한다.
정상 추출 완료 응답도 고정 문구로 반환해 불필요한 LLM 호출을 만들지 않는다.
"""

from app.graph.preference_state import PreferenceState


async def guide_preference_input(_state: PreferenceState) -> dict:
    return {
        "preferences": [],
        "assistant_reply": (
            "좋아하거나 피하고 싶은 음식, 음주 여부, 원하는 분위기나 활동을 알려주세요."
        ),
    }


async def acknowledge_preferences(_state: PreferenceState) -> dict:
    return {"assistant_reply": "말씀해주신 내용을 선호에 반영했어요."}
