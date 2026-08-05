from models import ScreeningAnswerIn
from services.deterioration import compare_to_previous, escalate_tier_if_worsened


def _answer(code, score):
    return ScreeningAnswerIn(question_code=code, answer_value="x", answer_score=score)


def test_no_previous_screening_says_so_explicitly():
    result = compare_to_previous([_answer("COUGH_DURATION", 3)], None, [])

    assert result["compared_to_screening_id"] is None
    assert result["changed"] is False
    assert "no previous screening" in result["summary"].lower()


def test_worsened_symptom_detected():
    previous_rows = [{"question_code": "BREATHLESSNESS", "answer_score": 0}]
    current = [_answer("BREATHLESSNESS", 5)]

    result = compare_to_previous(current, previous_screening_id=88, previous_answer_rows=previous_rows)

    assert result["compared_to_screening_id"] == 88
    assert result["changed"] is True
    assert "BREATHLESSNESS" in result["summary"]


def test_unchanged_or_improved_is_not_flagged():
    previous_rows = [{"question_code": "COUGH_DURATION", "answer_score": 5}]
    current = [_answer("COUGH_DURATION", 3)]  # improved, not worsened

    result = compare_to_previous(current, previous_screening_id=88, previous_answer_rows=previous_rows)

    assert result["changed"] is False


def test_non_tracked_code_ignored():
    # TB_HISTORY is historical, not a re-measurable trend code.
    previous_rows = [{"question_code": "TB_HISTORY", "answer_score": 0}]
    current = [_answer("TB_HISTORY", 4)]

    result = compare_to_previous(current, previous_screening_id=88, previous_answer_rows=previous_rows)

    assert result["changed"] is False


def test_escalate_tier_bumps_one_level():
    assert escalate_tier_if_worsened("GREEN", True) == "YELLOW"
    assert escalate_tier_if_worsened("YELLOW", True) == "ORANGE"
    assert escalate_tier_if_worsened("ORANGE", True) == "RED"


def test_escalate_tier_caps_at_red():
    assert escalate_tier_if_worsened("RED", True) == "RED"


def test_escalate_tier_no_change_when_not_worsened():
    assert escalate_tier_if_worsened("GREEN", False) == "GREEN"
