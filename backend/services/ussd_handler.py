from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_fresh_session
from db_models import Miner, Screening, ScreeningAnswer
from questions import SCREENING_QUESTIONS
import functools
from typing import Callable

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


def _deliver(
    screening_id: int,
    miner_id: int,
    miner_name: str,
    mine_site: str | None,
    phone_number: str,
    tier: str,
    shona: str,
) -> None:
    """Send what this screening owes the miner and the facility.

    **Opens its own session**, because this runs after the USSD response has
    gone back to the gateway and the session `_save_screening` used is closed
    by then. Everything it needs is passed by value for the same reason: an
    ORM instance loaded on a closed session is a detached row.
    """
    db = get_fresh_session()
    try:
        if tier in ("ORANGE", "RED"):
            create_referral_and_notify(
                db,
                screening_id=screening_id,
                miner_id=miner_id,
                miner_name=miner_name,
                phone_number=phone_number,
                mine_site=mine_site,
                tier=tier,
                shona_message=shona,
            )
        else:
            # GREEN/YELLOW never get a referral, but the miner only saw this
            # result once, live, during the USSD session -- send it by SMS
            # too so it isn't lost the moment the call ends (7 August 2026,
            # CLAUDE.md: "Everyone receives their result... by SMS").
            notifications.send_screening_result_sms(miner_id, phone_number, tier, shona)
    finally:
        db.close()


def _save_screening(
    phone_number: str,
    answers: List[dict],
    tier: str,
    shona: str,
    english: str,
    defer: Callable[[Callable[[], None]], None] | None = None,
) -> None:
    """Persist the screening, then send -- or hand the sending to `defer`.

    **Why `defer` exists, measured rather than assumed.** On the ORANGE/RED
    path the sending makes three synchronous outbound calls: the miner's
    result SMS, the hospital pre-alert SMS and the demonstration email. Each
    carries a 10-second timeout, so a merely slow gateway costs 6 seconds on
    one turn and the worst case is around 30. `CLAUDE.md`'s rule is **under
    3 s per turn, hard ceiling well under 10 s**, and Africa's Talking
    terminates the session at 10 -- at which point a miner who has just
    answered every question sees an error instead of "go to Kwekwe District
    Hospital within 48 hours". The screening survives, because it is committed
    before any send; what is lost is the one screen that tells him what to do.

    So the router passes FastAPI's `BackgroundTasks.add_task`, which runs
    after the response has gone back. `defer=None` keeps the old inline
    behaviour for a caller with no request to hang work off.

    The proper fix is `docs/IMPLEMENTATION_PLAN.md` §9: a `queued` status on
    `notifications` and delivery by the scheduler, with receipts. This is the
    bounded version that stops the session being killed in the meantime.
    """
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

        # Read what the sending needs while the session is open, and pass it
        # by value: the deferred call runs after this session is closed.
        miner = db.get(Miner, miner_id)
        send = functools.partial(
            _deliver,
            screening_id=screening.id,
            miner_id=miner_id,
            miner_name=miner.name,
            mine_site=miner.mine_site,
            phone_number=phone_number,
            tier=tier,
            shona=shona,
        )
    finally:
        db.close()

    # After the commit and outside the session, either way. The screening is
    # already durable at this point, which is what lets the sending be moved
    # off the turn at all -- rule 7, fail toward recording.
    if defer is not None:
        defer(send)
    else:
        send()


def handle_ussd(
    session_id: str,
    phone_number: str,
    text: str,
    defer: Callable[[Callable[[], None]], None] | None = None,
) -> str:
    """Pure decision tree — no AI call, and no outbound network call on the
    turn when `defer` is given.

    `CLAUDE.md`: **no language-model call inside a USSD session; under 3 s per
    turn, hard ceiling well under 10 s.** The first half is enforced by
    `tests/test_content_runtime_rule.py`'s import graph. The second half was
    not enforced by anything, and was being broken: the final turn sent two
    SMS messages and an email synchronously, each with a 10-second timeout.
    `defer` moves that off the turn — see `_save_screening`.

    The database work stays on the turn, deliberately: §10.7's budget is
    roughly 150 ms per round trip to Supabase and two or three queries fit
    with margin, while a gateway round trip does not.
    """
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

    _save_screening(phone_number, answers, tier, shona, english, defer=defer)

    return f"END {shona}"
