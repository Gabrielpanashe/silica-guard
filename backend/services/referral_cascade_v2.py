"""The reminder and escalation cascade for referrals keyed to a result.

`docs/IMPLEMENTATION_PLAN.md` item 1.10's planned half, and §10.4.

**Why this exists rather than extending the v1 cascade.** A v2 referral is
keyed to a `screening_results` row and a `persons` row; `screening_id` and
`miner_id` are null. `services/referral_cascade.py` reads
`referral.screening.tier` and `referral.miner.phone`, so handed a v2 row it
raises `AttributeError` on the first attribute — and its per-row `try/except`,
which exists so one bad row cannot abort the batch, catches that, logs it,
and skips the row. **Every tick. Permanently.** A v2 referral therefore never
reminded, never escalated, and sailed past its deadline with nothing but a
repeating exception to show for it, which is the metric this whole system is
judged on going quietly unmeasured. Reproduced before being fixed; see
`tests/test_referral_cascade_v2.py`.

Two differences from v1 beyond the keys, both of which are the point:

  **Timing comes from the instrument, not from this file.** v1 computes
  everything from `created_at` plus windows hardcoded in
  `services/referrals.py`. A v2 referral carries a `deadline` that
  `referrals_v2.create_for_result()` read out of `instrument_intervals` --
  the Clinical Lead's stated referral window per condition and tier (§12.2
  item 8). Reminders are fractions of that window rather than fixed offsets,
  so changing the clinical window changes the chasing with it and nobody has
  to remember to edit two places.

  **Nothing is sent, and that is recorded rather than hidden.** No
  patient-facing string is approved yet (item 1.6b), and §8.4 forbids
  inventing one. So each action advances the referral's state and returns
  what it *would* have sent, exactly as `screening_v2` reports
  `not_sent_reason` instead of improvising a sentence. The alternative --
  waiting for the words before tracking deadlines at all -- is what produced
  the silent skip above.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_fresh_session
from db_models import Referral

logger = logging.getLogger("silicaguard.referral_cascade_v2")

#: A referral in one of these is still being chased.
ACTIONABLE_STATUSES = ("open", "pre_alerted", "reminded")

#: Reminders at these fractions of the referral window, so a 48-hour window
#: and a 14-day one are chased in proportion rather than on one timetable.
#: Expressed as fractions and not offsets precisely so that this file holds
#: no clinical number: the window itself is the Clinical Lead's.
REMINDER_FRACTIONS = (0.5, 0.8)

#: Why nothing is sent. Reported on every action rather than logged once, so
#: a reader of the referral's history can see that the chase happened and the
#: message did not.
NOT_SENT_REASON = (
    "no approved patient-facing text exists for a referral reminder yet "
    "(item 1.6b); the cascade advanced the referral and sent nothing"
)


@dataclass(frozen=True)
class CascadeAction:
    """What is due for one referral."""

    action: str                      # "remind" | "escalate"
    new_status: str
    new_stage: int = 0
    due_at: datetime | None = None
    message_codes: tuple[str, ...] = ()
    not_sent_reason: str | None = None


@dataclass
class CascadeRun:
    """What one pass did, for the caller and for the log."""

    reminded: int = 0
    escalated: int = 0
    nothing_due: int = 0
    #: Rows this cascade is not responsible for, counted rather than skipped
    #: in silence -- the v1 cascade's silent skip is the defect this module
    #: was written for, and repeating it here would be worse than funny.
    not_mine: int = 0
    failed: int = 0
    unsent_messages: list[str] = field(default_factory=list)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_v2(referral: Referral) -> bool:
    """A referral keyed to a result rather than to a v1 screening.

    `result_id` is the discriminator because that is what §10.4 made the
    key: a referral is always for one condition at one tier, and a v1 row
    cannot say which.
    """
    return referral.result_id is not None


def next_action(
    referral: Referral,
    tier: str,
    *,
    now: datetime | None = None,
) -> CascadeAction | None:
    """What is due for this referral, or None.

    Pure: no database access, `now` injected, the same pattern as
    `services/deterioration.py` and the v1 cascade. `tier` is passed in
    rather than read, because it lives on the result row and this function
    does not read rows.
    """
    now = now or _utcnow()

    if referral.status not in ACTIONABLE_STATUSES:
        return None
    if referral.deadline is None:
        # Without a window there is nothing to be proportional to.
        # `referrals_v2.referral_window()` raises rather than defaulting when
        # the instrument states none, so this is a row from before that or a
        # tier that generates no referral -- either way, not something to
        # invent a schedule for.
        return None

    created = referral.created_at or referral.deadline
    window = referral.deadline - created
    if window <= timedelta(0):
        window = timedelta(hours=1)

    if now >= referral.deadline:
        return CascadeAction(
            action="escalate",
            new_status="escalated",
            new_stage=referral.reminder_stage or 0,
            due_at=referral.deadline,
            message_codes=("referral.escalation.facility.sms",),
            not_sent_reason=NOT_SENT_REASON,
        )

    for stage, fraction in enumerate(REMINDER_FRACTIONS, start=1):
        due_at = created + window * fraction
        if (referral.reminder_stage or 0) < stage and now >= due_at:
            return CascadeAction(
                action="remind",
                new_status="reminded",
                new_stage=stage,
                due_at=due_at,
                message_codes=("referral.reminder.worker.sms",),
                not_sent_reason=NOT_SENT_REASON,
            )

    return None


def _tier_for(db: Session, referral: Referral) -> str | None:
    from db_models import ScreeningResult

    result = db.get(ScreeningResult, referral.result_id)
    return result.tier if result else None


def process_due(db: Session, now: datetime | None = None) -> CascadeRun:
    """Advance every v2 referral that has something due.

    Each row is wrapped individually so one bad row cannot abort the batch --
    the same reasoning as v1, and with the lesson from it applied: a row this
    cascade is **not responsible for** is counted as `not_mine` rather than
    being allowed to raise and be logged as a failure, because that is how a
    structural mismatch becomes a repeating exception nobody reads.
    """
    now = now or _utcnow()
    run = CascadeRun()

    referral_ids = db.scalars(
        select(Referral.id).where(Referral.status.in_(ACTIONABLE_STATUSES))
    ).all()

    for referral_id in referral_ids:
        try:
            referral = db.get(Referral, referral_id)
            if referral is None or not is_v2(referral):
                run.not_mine += 1
                continue

            tier = _tier_for(db, referral)
            if tier is None:
                # A referral whose result has gone is a referral nobody can
                # explain. Counted, not guessed at.
                run.not_mine += 1
                continue

            action = next_action(referral, tier, now=now)
            if action is None:
                run.nothing_due += 1
                continue

            referral.status = action.new_status
            referral.reminder_stage = action.new_stage
            db.commit()

            if action.action == "remind":
                run.reminded += 1
            else:
                run.escalated += 1
            run.unsent_messages.extend(action.message_codes)

            logger.info(
                "v2 referral %s: %s (tier=%s stage=%s) -- nothing sent: %s",
                referral.referral_code, action.action, tier, action.new_stage,
                action.not_sent_reason,
            )
        except Exception:  # noqa: BLE001 - one row must not abort the batch
            db.rollback()
            run.failed += 1
            logger.exception(
                "v2 referral cascade failed for referral id=%s", referral_id
            )

    return run


def run_scheduled() -> CascadeRun:
    """The scheduler's entry point. Opens its own session and never raises:
    a job that raises can take the scheduler thread with it."""
    db = get_fresh_session()
    try:
        run = process_due(db)
        if run.reminded or run.escalated or run.failed:
            logger.info(
                "v2 referral cascade: %s reminded, %s escalated, %s not due, "
                "%s not mine, %s failed",
                run.reminded, run.escalated, run.nothing_due, run.not_mine,
                run.failed,
            )
        return run
    finally:
        db.close()
