from models import ScreeningAnswerIn
from services.advice_engine import GREEN_DEFAULT_ADVICE, personalised_advice_line


def _answer(code, value, score):
    return ScreeningAnswerIn(question_code=code, answer_value=value, answer_score=score)


def test_all_clean_answers_returns_green_default():
    answers = [_answer("PPE_USE", "always_n95", 0), _answer("WET_DRILLING", "always", 0)]

    assert personalised_advice_line(answers) == GREEN_DEFAULT_ADVICE


def test_picks_the_single_weakest_answer():
    answers = [
        _answer("PPE_USE", "sometimes", 2),
        _answer("BREATHLESSNESS", "severe", 5),  # highest score — should win
        _answer("COUGH_DURATION", "mild", 3),
    ]

    line = personalised_advice_line(answers)

    assert "breathlessness" in line.lower() or "urgent" in line.lower()


def test_every_result_gets_a_non_empty_line():
    # No answer has a template entry at all — must still not return nothing.
    answers = [ScreeningAnswerIn(question_code="UNKNOWN_CODE", answer_value="whatever", answer_score=9)]

    line = personalised_advice_line(answers)

    assert isinstance(line, str) and len(line) > 0
