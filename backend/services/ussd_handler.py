from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_fresh_session
from db_models import Miner, Screening, ScreeningAnswer
from questions import SCREENING_QUESTIONS
from services import notifications
from services.referrals import create_referral_and_notify
from services.tier_messages import TIER_MESSAGES

# Session state as a plain dict, keyed by Africa's Talking's sessionId — no Redis
# for MVP. A session that's abandoned mid-flow (miner hangs up) leaks its entry
# here for the life of the process; acceptable for MVP scale, worth revisiting
# if this ever needs to run for weeks without a restart.
_sessions: Dict[str, dict] = {}

# Doctor-approved fixed Shona/English result text. USSD uses its own
# decision-tree logic and wording — no live AI call, no auto-translation.
# Confidence is fixed at 0.75 to mark this as rule-based rather than
# AI-derived.
_DANGEROUS_TRIGGERS = {
    ("BREATHLESSNESS", "severe"),
    ("CHEST_PAIN", "severe"),
    ("TB_HISTORY", "current"),
    ("PRIOR_LUNG_DIAGNOSIS", "yes"),
}


def _new_session() -> dict:
    # pending_index = the question index we just displayed and are awaiting an
    # answer for; None means no question has been shown yet this session.
    return {"pending_index": None, "answers": []}


def _render_question(index: int) -> str:
    question = SCREENING_QUESTIONS[index]
    lines = [question["shona"]]
    lines += [
        f"{i}. {opt['label_shona']}"
        for i, opt in enumerate(question["options"], start=1)
    ]
    return "CON " + "\n".join(lines)


def _classify(answers: List[dict]) -> Tuple[str, str, str]:
    """Four-tier split (GREEN/YELLOW/ORANGE/RED). The dangerous-trigger vs.
    score>=12 branches map 1:1 onto the pre-v4.0 REFER_NOW logic, now split
    into RED (a hard safety trigger fired) vs ORANGE (score alone crossed
    the threshold, no trigger) rather than one merged bucket — see
    services/referrals.py for the same RED/ORANGE urgency split. Message
    text comes from services/tier_messages.py (shared with the AI-driven
    /api/screen path, 7 August 2026); the ORANGE message in particular still
    reads as urgent ("today") inherited from the old REFER_NOW copy and
    should get an explicit Clinical Lead pass for its new 14-day-window
    tier."""
    total_score = sum(a["answer_score"] for a in answers)
    is_dangerous = any(
        (a["question_code"], a["answer_value"]) in _DANGEROUS_TRIGGERS
        for a in answers
    )

    if is_dangerous:
        tier = "RED"
    elif total_score >= 12:
        tier = "ORANGE"
    elif total_score >= 6:
        tier = "YELLOW"
    else:
        tier = "GREEN"

    shona, english = TIER_MESSAGES[tier]
    return tier, shona, english


def _find_or_create_miner(db: Session, phone_number: str) -> int:
    miner = db.scalar(select(Miner).where(Miner.phone == phone_number))
    if miner is not None:
        return miner.id
    miner = Miner(name="USSD Self-Screen", phone=phone_number, mine_site=None)
    db.add(miner)
    db.commit()
    return miner.id


def _save_screening(
    phone_number: str,
    answers: List[dict],
    tier: str,
    shona: str,
    english: str,
) -> None:
    # Own session, not threaded in from a caller — handle_ussd() below has
    # no request-scoped Session (it's driven by the Africa's Talking webhook
    # router, not a FastAPI Depends chain), same reasoning as
    # services/notifications._log_notification.
    db = get_fresh_session()
    try:
        miner_id = _find_or_create_miner(db, phone_number)
        screening = Screening(
            miner_id=miner_id,
            screened_by="USSD_SELF",
            channel="USSD",
            tier=tier,
            risk_confidence=0.75,
            ai_explanation_shona=shona,
            ai_explanation_english=english,
            fallback_used=1,
        )
        db.add(screening)
        db.flush()  # need screening.id for the answers below, before commit

        for answer in answers:
            db.add(
                ScreeningAnswer(
                    screening_id=screening.id,
                    question_code=answer["question_code"],
                    question_text=answer["question_text"],
                    answer_value=answer["answer_value"],
                    answer_score=answer["answer_score"],
                )
            )
        db.commit()

        if tier in ("ORANGE", "RED"):
            miner = db.get(Miner, miner_id)
            create_referral_and_notify(
                db,
                screening_id=screening.id,
                miner_id=miner_id,
                miner_name=miner.name,
                phone_number=phone_number,
                mine_site=miner.mine_site,
                tier=tier,
                shona_message=shona,
            )
        else:
            # GREEN/YELLOW never get a referral, but the miner only saw this
            # result once, live, during the USSD session — send it by SMS
            # too so it isn't lost the moment the call ends (7 August 2026,
            # CLAUDE.md: "Everyone receives their result... by SMS").
            notifications.send_screening_result_sms(miner_id, phone_number, tier, shona)
    finally:
        db.close()


def handle_ussd(session_id: str, phone_number: str, text: str) -> str:
    """Pure decision tree — no AI call, must return in milliseconds per the
    Africa's Talking 10-second hard limit (non-negotiable rule, see
    CLAUDE.md)."""
    session = _sessions.setdefault(session_id, _new_session())
    last_input = text.split("*")[-1] if text else ""
    pending_index = session["pending_index"]

    if pending_index is not None:
        question = SCREENING_QUESTIONS[pending_index]
        try:
            option = question["options"][int(last_input) - 1]
        except (ValueError, IndexError):
            return _render_question(pending_index)  # invalid choice — re-show same question

        session["answers"].append(
            {
                "question_code": question["code"],
                "question_text": question["shona"],
                "answer_value": option["value"],
                "answer_score": option["score"],
            }
        )

    next_index = len(session["answers"])
    if next_index < len(SCREENING_QUESTIONS):
        session["pending_index"] = next_index
        return _render_question(next_index)

    tier, shona, english = _classify(session["answers"])
    answers = session["answers"]
    del _sessions[session_id]

    _save_screening(phone_number, answers, tier, shona, english)

    return f"END {shona}"
