import pytest

from app.graph.fairness import (
    PreferenceRelation,
    calculate_candidate_fairness,
    calculate_group_fairness,
)
from app.schemas.candidates import ParticipantInput, ParticipantPreference
from app.schemas.preference import Sentiment, Strength


def _preference(
    code: str,
    sentiment: Sentiment,
    strength: Strength = Strength.MODERATE,
) -> ParticipantPreference:
    return ParticipantPreference(
        vocabulary_code=code,
        sentiment=sentiment,
        strength=strength,
        raw_value=code,
    )


def test_confirmed_presentation_example_prefers_balanced_candidate():
    uneven = calculate_group_fairness([1.0, 1.0, 0.0])
    balanced = calculate_group_fairness([0.6, 0.6, 0.6])

    assert uneven.group_satisfaction == pytest.approx(2 / 3)
    assert uneven.minimum_satisfaction == 0.0
    assert uneven.score == pytest.approx(46.6666667)
    assert round(uneven.score, 1) == 46.7
    assert balanced.score == pytest.approx(60.0)
    assert balanced.score > uneven.score


def test_sentiment_relation_and_strength_build_participant_satisfaction():
    participants = [
        ParticipantInput(
            user_id=1,
            preferences=[
                _preference("SPICY_FOOD", Sentiment.POSITIVE, Strength.WEAK),
                _preference("SEAFOOD", Sentiment.NEGATIVE, Strength.STRONG),
            ],
        )
    ]
    relations = {
        (1, "SPICY_FOOD"): PreferenceRelation.DIRECT,
        (1, "SEAFOOD"): PreferenceRelation.PARTIAL,
    }

    result = calculate_candidate_fairness(participants, relations)

    # (1*1.0 + 3*0.25) / 4 = 0.4375
    assert result.participant_satisfaction[1] == pytest.approx(0.4375)
    assert result.matched_preference_codes == ("SPICY_FOOD",)


def test_participant_without_preferences_is_neutral():
    participants = [ParticipantInput(user_id=1, preferences=[])]

    result = calculate_candidate_fairness(participants, {})

    assert result.participant_satisfaction == {1: 0.5}
    assert result.score == pytest.approx(50.0)


def test_strong_negative_direct_match_is_zero_but_not_vetoed():
    participants = [
        ParticipantInput(
            user_id=1,
            preferences=[
                _preference("SPICY_INTOLERANT", Sentiment.NEGATIVE, Strength.STRONG)
            ],
        )
    ]

    result = calculate_candidate_fairness(
        participants,
        {(1, "SPICY_INTOLERANT"): PreferenceRelation.DIRECT},
    )

    assert result.participant_satisfaction[1] == 0.0
    assert result.vetoed is False


def test_direct_allergy_conflict_is_vetoed():
    participants = [
        ParticipantInput(
            user_id=1,
            preferences=[
                _preference("SHELLFISH_ALLERGY", Sentiment.NEGATIVE, Strength.STRONG)
            ],
        )
    ]

    result = calculate_candidate_fairness(
        participants,
        {(1, "SHELLFISH_ALLERGY"): PreferenceRelation.DIRECT},
    )

    assert result.vetoed is True


def test_group_fairness_rejects_out_of_range_value():
    with pytest.raises(ValueError):
        calculate_group_fairness([1.1])
