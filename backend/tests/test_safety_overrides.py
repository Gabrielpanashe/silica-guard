from models import ScreeningAnswerIn
from services.safety_overrides import apply_safety_overrides, triggered_red_flags


def _answer(code, value, score=1):
    return ScreeningAnswerIn(question_code=code, answer_value=value, answer_score=score)


def test_no_red_flags_leaves_result_untouched():
    answers = [_answer("PPE_USE", "always_n95", 0)]
    result = {"tier": "GREEN", "confidence": 0.9, "contributing_factors": [], "explanation_english": "fine"}

    out = apply_safety_overrides(answers, dict(result))

    assert out == result


def test_severe_breathlessness_forces_red_even_if_model_said_green():
    answers = [_answer("BREATHLESSNESS", "severe", 5)]
    result = {
        "tier": "GREEN",
        "confidence": 0.9,
        "contributing_factors": ["looked fine otherwise"],
        "explanation_english": "Low risk overall",
    }

    out = apply_safety_overrides(answers, result)

    assert out["tier"] == "RED"
    assert any("BREATHLESSNESS" in f for f in out["contributing_factors"])
    assert "override" in out["explanation_english"].lower()


def test_current_tb_forces_red():
    answers = [_answer("TB_HISTORY", "current", 4)]
    result = {"tier": "YELLOW", "confidence": 0.7, "contributing_factors": [], "explanation_english": "x"}

    out = apply_safety_overrides(answers, result)

    assert out["tier"] == "RED"


def test_prior_lung_diagnosis_forces_red():
    answers = [_answer("PRIOR_LUNG_DIAGNOSIS", "yes", 5)]
    result = {"tier": "ORANGE", "confidence": 0.7, "contributing_factors": [], "explanation_english": "x"}

    out = apply_safety_overrides(answers, result)

    assert out["tier"] == "RED"


def test_already_red_is_not_modified_or_duplicated():
    answers = [_answer("CHEST_PAIN", "severe", 5)]
    result = {"tier": "RED", "confidence": 0.95, "contributing_factors": ["already red"], "explanation_english": "x"}

    out = apply_safety_overrides(answers, dict(result))

    assert out == result  # untouched — no duplicate override note appended


def test_non_severe_values_do_not_trigger():
    answers = [
        _answer("BREATHLESSNESS", "moderate", 3),
        _answer("CHEST_PAIN", "sometimes", 3),
        _answer("TB_HISTORY", "past", 3),
    ]
    assert triggered_red_flags(answers) == []
