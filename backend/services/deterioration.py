"""Longitudinal Deterioration Detection — SILICAGUARD.md Section 10, AI
module 2: "on every re-screen, compares current answers against the
worker's most recent previous screening. Any adverse movement in symptom or
exposure trajectory raises the tier one level even where absolute values
wouldn't warrant it. Says so explicitly when there's insufficient prior
data rather than inferring."

Implemented in Python against the stored answer_score values, not asked of
the model — tier escalation is a safety decision, the same reasoning that
puts the hard red-flag overrides (services/safety_overrides.py) outside the
model call rather than inside the prompt.
"""

from typing import List, Optional, Sequence

from models import ScreeningAnswerIn

TIER_ORDER = ["GREEN", "YELLOW", "ORANGE", "RED"]

# Symptom/exposure codes tracked for trajectory. A rise in answer_score on
# any of these between screenings counts as worsening. Deliberately excludes
# purely historical/one-off codes (TB_HISTORY, PRIOR_LUNG_DIAGNOSIS,
# YEARS_UNDERGROUND, JOB_ROLE) that don't represent a re-measurable trend.
DETERIORATION_CODES = {
    "COUGH_DURATION",
    "BREATHLESSNESS",
    "CHEST_PAIN",
    "WEIGHT_LOSS",
    "PPE_USE",
    "WET_DRILLING",
}


def compare_to_previous(
    current_answers: List[ScreeningAnswerIn],
    previous_screening_id: Optional[int],
    previous_answer_rows: Sequence,
) -> dict:
    """previous_answer_rows: screening_answers rows (question_code,
    answer_score) for the worker's previous screening, or empty/None if
    there isn't one yet."""
    if not previous_screening_id or not previous_answer_rows:
        return {
            "compared_to_screening_id": None,
            "changed": False,
            "summary": "No previous screening on record — this is a baseline, not a comparison.",
        }

    previous_scores = {
        row["question_code"]: row["answer_score"] for row in previous_answer_rows
    }

    worsened = []
    for answer in current_answers:
        if answer.question_code not in DETERIORATION_CODES:
            continue
        prev_score = previous_scores.get(answer.question_code)
        if prev_score is not None and answer.answer_score > prev_score:
            worsened.append(answer.question_code)

    if worsened:
        summary = (
            "Deterioration since last screening: "
            + ", ".join(worsened)
            + " worsened compared to the previous screening."
        )
    else:
        summary = "No worsening detected compared to the previous screening."

    return {
        "compared_to_screening_id": previous_screening_id,
        "changed": bool(worsened),
        "summary": summary,
    }


def escalate_tier_if_worsened(tier: str, changed: bool) -> str:
    """Bumps the tier one level if `changed` is True. RED has nowhere higher
    to go. Never used to move a tier down — only ever called with the
    already-safety-overridden tier as input."""
    if not changed or tier not in TIER_ORDER:
        return tier
    idx = TIER_ORDER.index(tier)
    return TIER_ORDER[min(idx + 1, len(TIER_ORDER) - 1)]
