"""`/ai/preferences/extract`가 실행하는 Preference 하위 파이프라인의 상태.

라우터가 입력 범위를 먼저 판별하고, 정상 선호 입력만 추출기로 보낸다. 범위 밖 입력은 LLM과
대화하지 않고 고정 가드레일 안내로 되돌린다. 외부 API 계약(app/schemas/preference.py)은 이
내부 분기와 무관하게 그대로 유지된다.
"""

from typing import Literal, TypedDict

from app.schemas.preference import ExtractedPreference


class PreferenceState(TypedDict, total=False):
    # 입력
    message: str

    # 라우터 산출물 — 정상 선호 입력인지, 화면 범위 밖 입력인지 판별한 값.
    route: Literal["IN_SCOPE", "OUT_OF_SCOPE"]

    # 추출/가드레일 노드 산출물
    preferences: list[ExtractedPreference]
    assistant_reply: str | None
