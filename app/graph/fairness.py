"""참여자별 만족도와 그룹 공정성 점수를 계산하는 순수 Python 로직.

LLM은 장소와 선호의 의미 관계만 ``DIRECT / PARTIAL / NONE``으로 판정한다. 이 모듈은 그
판정값에 요청의 ``sentiment``와 ``strength``를 결합해 개인 만족도 ``u_i(c)``를 만들고,
평균 만족도 ``S(c)``와 최저 만족도 ``F(c)``를 고정 수식으로 집계한다.

외부 API에는 점수를 노출하지 않는다. 계산값은 후보 순서를 결정하는 내부 근거로만 사용한다.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from langsmith import traceable

from app.schemas.candidates import ParticipantInput
from app.schemas.preference import Sentiment, Strength


class PreferenceRelation(str, Enum):
    """후보가 선호 대상과 얼마나 직접 관련되는지 나타내는 제한된 의미 판정."""

    DIRECT = "DIRECT"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


_RELATION_VALUE: dict[PreferenceRelation, float] = {
    PreferenceRelation.DIRECT: 1.0,
    PreferenceRelation.PARTIAL: 0.5,
    PreferenceRelation.NONE: 0.0,
}

_STRENGTH_WEIGHT: dict[Strength, float] = {
    Strength.WEAK: 1.0,
    Strength.MODERATE: 2.0,
    Strength.STRONG: 3.0,
}


@dataclass(frozen=True, slots=True)
class CandidateFairnessScore:
    """후보 하나의 내부 계산 결과."""

    participant_satisfaction: dict[int, float]
    group_satisfaction: float
    minimum_satisfaction: float
    score: float
    vetoed: bool
    matched_preference_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GroupFairnessScore:
    """개인 만족도 배열을 집계한 ``S(c)``, ``F(c)``와 최종 점수."""

    group_satisfaction: float
    minimum_satisfaction: float
    score: float


def calculate_group_fairness(satisfaction_values: list[float]) -> GroupFairnessScore:
    """``Score(c) = 100 * (0.7*S(c) + 0.3*F(c))``를 그대로 계산한다."""

    if not satisfaction_values:
        raise ValueError("참여자 만족도가 최소 1개 필요합니다.")
    if any(value < 0.0 or value > 1.0 for value in satisfaction_values):
        raise ValueError("참여자 만족도는 0과 1 사이여야 합니다.")

    group_satisfaction = sum(satisfaction_values) / len(satisfaction_values)
    minimum_satisfaction = min(satisfaction_values)
    score = 100.0 * ((0.7 * group_satisfaction) + (0.3 * minimum_satisfaction))
    return GroupFairnessScore(
        group_satisfaction=group_satisfaction,
        minimum_satisfaction=minimum_satisfaction,
        score=score,
    )


def _trace_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """LangSmith에 공정성 계산 근거만 읽기 쉬운 형태로 남긴다."""

    participants: list[ParticipantInput] = inputs["participants"]
    relations: Mapping[tuple[int, str], PreferenceRelation] = inputs["relations"]
    return {
        "kakaoPlaceId": inputs.get("candidate_id"),
        "participants": [
            {
                "userId": participant.user_id,
                "preferences": [
                    {
                        "vocabularyCode": preference.vocabulary_code,
                        "sentiment": preference.sentiment.value,
                        "strength": preference.strength.value,
                    }
                    for preference in participant.preferences
                ],
            }
            for participant in participants
        ],
        "preferenceRelations": [
            {
                "userId": user_id,
                "vocabularyCode": vocabulary_code,
                "relation": relation.value,
            }
            for (user_id, vocabulary_code), relation in sorted(relations.items())
        ],
    }


def _trace_output(result: CandidateFairnessScore) -> dict[str, Any]:
    """API에는 노출하지 않는 내부 점수만 LangSmith 출력으로 직렬화한다."""

    return {
        "participantSatisfaction": [
            {"userId": user_id, "value": satisfaction}
            for user_id, satisfaction in result.participant_satisfaction.items()
        ],
        "S": result.group_satisfaction,
        "F": result.minimum_satisfaction,
        "score": result.score,
        "vetoed": result.vetoed,
        "matchedPreferenceCodes": list(result.matched_preference_codes),
    }


@traceable(
    name="fairness_score",
    run_type="chain",
    tags=["fairness", "deterministic"],
    process_inputs=_trace_inputs,
    process_outputs=_trace_output,
)
def calculate_candidate_fairness(
    participants: list[ParticipantInput],
    relations: Mapping[tuple[int, str], PreferenceRelation],
    *,
    candidate_id: str | None = None,
) -> CandidateFairnessScore:
    """후보 하나의 ``u_i(c)``, ``S(c)``, ``F(c)``와 최종 점수를 계산한다.

    ``relations``에는 각 ``(userId, vocabularyCode)`` 쌍이 반드시 있어야 한다. 모델 출력의
    완전성·ID 실존 여부는 호출부가 먼저 검증한다. ``candidate_id``는 계산에는 쓰지 않고
    LangSmith에서 후보별 계산 trace를 구분하는 용도로만 사용한다.

    알레르기 코드는 안전 조건이므로 후보와 DIRECT 관계일 때 점수 경쟁 전에 veto한다. 최신
    제품 결정에 따라 일반 ``STRONG + NEGATIVE``는 veto하지 않고 만족도 0까지 내려갈 수 있다.
    """

    participant_satisfaction: dict[int, float] = {}
    matched_codes: list[str] = []
    vetoed = False

    for participant in participants:
        if not participant.preferences:
            participant_satisfaction[participant.user_id] = 0.5
            continue

        weighted_sum = 0.0
        total_weight = 0.0
        for preference in participant.preferences:
            key = (participant.user_id, preference.vocabulary_code)
            relation = relations[key]
            relation_value = _RELATION_VALUE[relation]
            direction = 1.0 if preference.sentiment is Sentiment.POSITIVE else -1.0
            satisfaction = 0.5 + (0.5 * direction * relation_value)
            weight = _STRENGTH_WEIGHT[preference.strength]

            weighted_sum += weight * satisfaction
            total_weight += weight

            if preference.sentiment is Sentiment.POSITIVE and relation is not PreferenceRelation.NONE:
                matched_codes.append(preference.vocabulary_code)

            if (
                preference.vocabulary_code.endswith("_ALLERGY")
                and relation is PreferenceRelation.DIRECT
            ):
                vetoed = True

        participant_satisfaction[participant.user_id] = weighted_sum / total_weight

    group = calculate_group_fairness(list(participant_satisfaction.values()))

    return CandidateFairnessScore(
        participant_satisfaction=participant_satisfaction,
        group_satisfaction=group.group_satisfaction,
        minimum_satisfaction=group.minimum_satisfaction,
        score=group.score,
        vetoed=vetoed,
        matched_preference_codes=tuple(dict.fromkeys(matched_codes)),
    )
