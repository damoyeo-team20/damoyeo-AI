"""`/ai/preferences/extract`가 실행하는 Preference 하위 파이프라인의 상태.

하나의 프롬프트로 뭉치지 않고 라우터/추출/스몰톡 세 노드로 분리했다.
외부 API 계약(app/schemas/preference.py)은 이 분리와 무관하게 그대로 유지된다.
"""

from typing import TypedDict

from app.schemas.preference import ExtractedPreference


class PreferenceState(TypedDict, total=False):
    # 입력
    message: str

    # 라우터 산출물 — 원본 발화를 선호 관련/잡담으로 분리한 것
    preference_text: str | None
    smalltalk_text: str | None

    # 추출/스몰톡 노드 산출물
    preferences: list[ExtractedPreference]
    assistant_reply: str | None
