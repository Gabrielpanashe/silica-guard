"""Hard red-flag safety overrides — CLAUDE.md non-negotiable rule: "Hard
red-flag overrides live in Python code, outside the model call. The model
can never downgrade a RED."

This is deliberately a separate module from ai_risk_engine.py and is called
from routers/screening.py *after* assess_risk() returns, regardless of
whether that result came from a real Gemini call or (in tests) a mock. The
prompt text in prompts/risk_engine_prompt.txt states the same rule under
"IMPORTANT SAFETY RULE" for the model's own reasoning, but per SKILL.md
("How to call the AI" #5) prompt text alone is not enforcement — a model
can misread, drift, or simply get it wrong. This module is the actual
enforcement: it never asks the model anything, it only reads the raw
answers the miner gave.

Mirrors the four RED conditions in risk_engine_prompt.txt's safety rule
exactly, keyed to the answer_value strings defined in questions.py. If a
question's options ever change, this table must be updated in the same
change (see the "shared codes" gotcha in SKILL.md).
"""

from typing import List

from models import ScreeningAnswerIn

RED_FLAG_VALUES = {
    "BREATHLESSNESS": {"severe"},  # getting dressed / resting
    "CHEST_PAIN": {"severe"},
    "TB_HISTORY": {"current"},
    "PRIOR_LUNG_DIAGNOSIS": {"yes"},
}


def triggered_red_flags(answers: List[ScreeningAnswerIn]) -> List[str]:
    """Question codes among these answers whose value is a hard RED trigger."""
    return [
        answer.question_code
        for answer in answers
        if answer.answer_value in RED_FLAG_VALUES.get(answer.question_code, set())
    ]


def apply_safety_overrides(answers: List[ScreeningAnswerIn], result: dict) -> dict:
    """Forces result['tier'] to RED if any hard red-flag answer is present,
    regardless of what the model classified. Never downgrades — if the model
    already said RED, or no red flag is present, the tier is left untouched.
    Mutates and returns `result` so contributing_factors/explanation stay in
    sync with the final tier for the audit trail (the non-negotiable rule
    that every screening stores AI input and output together)."""
    flags = triggered_red_flags(answers)
    if not flags:
        return result

    if result.get("tier") != "RED":
        result["tier"] = "RED"
        result["contributing_factors"] = list(result.get("contributing_factors", [])) + [
            f"Hard safety override ({', '.join(flags)}) — classified RED regardless of AI-suggested tier"
        ]
        result["explanation_english"] = (
            (result.get("explanation_english") or "").rstrip(". ")
            + f". Hard safety override applied: {', '.join(flags)} always means RED, per non-negotiable clinical rule."
        ).lstrip(". ")

    return result
