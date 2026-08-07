from models import ScreeningAnswerIn
from services.explanation_shona import GREEN_DEFAULT_EXPLANATION, personalised_explanation_shona


def _answer(code, value, score):
    return ScreeningAnswerIn(question_code=code, answer_value=value, answer_score=score)


def test_all_clean_answers_returns_green_default():
    answers = [_answer("PPE_USE", "always_n95", 0), _answer("WET_DRILLING", "always", 0)]

    assert personalised_explanation_shona(answers) == GREEN_DEFAULT_EXPLANATION


def test_picks_the_single_weakest_answer():
    answers = [
        _answer("PPE_USE", "sometimes", 2),
        _answer("BREATHLESSNESS", "severe", 5),  # highest score — should win
        _answer("COUGH_DURATION", "mild", 3),
    ]

    line = personalised_explanation_shona(answers)

    assert "kufema" in line.lower()  # Shona for "breathe" — confirms it picked BREATHLESSNESS


def test_every_result_gets_a_non_empty_line():
    # No answer has a template entry at all — must still not return nothing.
    answers = [ScreeningAnswerIn(question_code="UNKNOWN_CODE", answer_value="whatever", answer_score=9)]

    line = personalised_explanation_shona(answers)

    assert isinstance(line, str) and len(line) > 0


def test_matches_same_weakest_answer_as_advice_line():
    """Not identical text, but both should be about the same underlying
    factor — same selection logic, same answer set."""
    from services.advice_engine import personalised_advice_line

    answers = [
        _answer("PPE_USE", "sometimes", 2),
        _answer("TB_HISTORY", "current", 5),  # highest score — should win in both
        _answer("COUGH_DURATION", "mild", 3),
    ]

    advice = personalised_advice_line(answers)
    explanation = personalised_explanation_shona(answers)

    assert "TB" in advice
    assert "TB" in explanation
