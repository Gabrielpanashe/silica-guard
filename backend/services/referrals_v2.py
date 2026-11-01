"""Referrals keyed to a result, and the outcome that closes them.

Master Reference v1.0 §10.4, and `docs/IMPLEMENTATION_PLAN.md` item 1.10.

**A referral belongs to a result, not to a session.** A session produces one
result per condition, and a referral is always for a particular condition at a
particular tier. A worker referred for silicosis and later also flagged for
tuberculosis needs two referrals with two deadlines, not one row whose meaning
depends on which result you read it against. The v1 table keyed referrals to a
screening, which worked only because there was exactly one condition.

**Closing a referral captures the outcome, not merely attendance.** §10.4's
own addition, and the whole of the Section 9 machine-learning roadmap depends
on it: without the radiological or clinical finding, the pilot produces an
operational result and no labelled dataset. With it, every completed referral
is a training example nobody else in the country holds. That is why `outcome`
is a closed vocabulary rather than free text -- free text is not a label.

**The referral window comes from the instrument, not from this module.** §12.2
items 7 and 8: the tier-three window is unstated in the current draft while
the v1 code hardcodes 14 days, and the re-screen intervals conflict between
drafts. `instrument_intervals` is where the Clinical Lead states them, so this
module reads them and refuses rather than inventing a default -- a deadline is
a clinical instruction with a number on it.
"""

from __future__ import annotations

import json
import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_models import Facility, Referral, ScreeningResult, ScreeningSession
from services.facility_matching import select_facility

#: Same alphabet and length as v1: four characters from a 32-symbol set with
#: no 0/O or 1/I. Unchanged deliberately -- a referral code is short-lived and
#: read aloud at a nurse's desk, and the register-wide code that needed six
#: characters is the participant code, not this one (§12 item 4).
CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1I")
CODE_LENGTH = 4
_CODE_MAX_ATTEMPTS = 20

#: Tiers that generate a referral at all.
REFERRING_TIERS = ("ORANGE", "RED")

#: §10.4's structured outcome. A closed set, because the point of capturing it
#: is a labelled dataset and free text is not a label.
OUTCOMES = (
    "attended_imaging_normal",
    "attended_imaging_abnormal",
    "attended_no_imaging",
    "not_attended",
    "other",
)


class ReferralError(ValueError):
    """The referral cannot be created or closed: an unreadable result, a tier
    that does not refer, a missing window, or an unknown outcome."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def generate_code(db: Session) -> str:
    """Collision-checked. Raises rather than returning a colliding code: a
    hospital looks a worker up by this, and two workers behind one code is a
    clinical safety event rather than an inconvenience."""
    for _ in range(_CODE_MAX_ATTEMPTS):
        candidate = "SG-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if db.scalar(select(Referral).where(Referral.referral_code == candidate)) is None:
            return candidate
    raise ReferralError(
        f"could not generate an unused referral code in {_CODE_MAX_ATTEMPTS} "
        "attempts. With a ~32^4 space at pilot scale this means something is "
        "wrong with the table, not that the space is exhausted."
    )


def referral_window(instrument: dict, condition: str, tier: str) -> timedelta:
    """The deadline, from the instrument.

    Raises when the Clinical Lead has not stated one. That is deliberate and
    is the §12.2 item 8 correction in code: the v1 path hardcodes 48 hours for
    RED and 14 days for ORANGE in `services/referrals.py:17`, numbers that
    appear in no approved document. A deadline is a clinical instruction with
    a number on it, so an absent number is a missing instruction rather than a
    reason to pick one.
    """
    for row in instrument.get("intervals") or []:
        if row.get("condition") == condition and row.get("tier") == tier:
            hours = row.get("referral_window_hours")
            if hours:
                return timedelta(hours=int(hours))
    raise ReferralError(
        f"instrument {instrument.get('code')} v{instrument.get('version')} "
        f"states no referral window for {condition}/{tier}. §12.2 item 8: the "
        "window is the Clinical Lead's to state, per condition and tier, and "
        "the system must not substitute a number of its own."
    )


def create_for_result(
    db: Session,
    result: ScreeningResult,
    instrument: dict,
    *,
    site_text: str | None = None,
) -> Referral | None:
    """One referral for one result. Returns None for a tier that does not
    refer, which is not a failure.

    Does **not** send anything. Messaging is the caller's step, so that a
    messaging failure cannot roll back a referral -- §10.3: "if messaging
    fails, the screening and the referral both stand and the message is
    retried, with the failure recorded".
    """
    if result.tier not in REFERRING_TIERS:
        return None

    session = db.get(ScreeningSession, result.session_id)
    if session is None:
        raise ReferralError(
            f"result {result.id} names session {result.session_id}, which does "
            "not exist. A referral with no person behind it is unreachable."
        )

    window = referral_window(instrument, result.condition_code, result.tier)

    facility_rows = [
        {"id": f.id, "name": f.name, "level": f.level}
        for f in db.scalars(select(Facility)).all()
    ]
    site = site_text or session.site_text
    facility = select_facility(result.tier, site, facility_rows)

    reasons = {
        "tier": result.tier,
        "scored_tier": result.scored_tier,
        "condition": result.condition_code,
        "override_fired": bool(result.override_fired),
        "override_rule_codes": (result.override_rule_codes or "").split(",")
        if result.override_rule_codes
        else [],
        "deterioration_changed": bool(result.deterioration_changed),
        "instrument": f"{result.instrument_code} v{result.instrument_version}",
    }

    referral = Referral(
        result_id=result.id,
        person_id=session.person_id,
        condition_code=result.condition_code,
        hospital=facility["name"] if facility else None,
        facility_id=facility["id"] if facility else None,
        referral_code=generate_code(db),
        deadline=_utcnow() + window,
        contributing_reasons=json.dumps(reasons, sort_keys=True),
        pre_alert_sent=0,
        status="open",
    )
    db.add(referral)
    db.flush()
    return referral


def close_with_outcome(
    db: Session,
    referral_code: str,
    outcome: str,
    *,
    recorded_by: str,
    notes: str | None = None,
) -> Referral:
    """Close a referral with what actually happened.

    The outcome is returned to the person's record rather than only marking
    attendance, which is the difference between an operational pilot and a
    labelled dataset (§10.4).
    """
    if outcome not in OUTCOMES:
        raise ReferralError(
            f"unknown outcome {outcome!r}; expected one of {OUTCOMES}. The set "
            "is closed because the point of capturing it is a labelled "
            "dataset, and free text is not a label."
        )

    referral = db.scalar(
        select(Referral).where(Referral.referral_code == referral_code)
    )
    if referral is None:
        raise ReferralError(f"no referral with code {referral_code!r}")

    referral.outcome = outcome
    referral.outcome_notes = notes
    referral.outcome_recorded_at = _utcnow()
    referral.outcome_recorded_by = recorded_by
    referral.closed_at = _utcnow()
    referral.status = "closed"
    #: An outcome that says the person attended is attendance, whether or not
    #: anybody pressed the confirm button first. The two were recordable
    #: independently in v1 and could disagree.
    if outcome.startswith("attended") and referral.attended_at is None:
        referral.attended_at = _utcnow()
    db.flush()
    return referral


def for_person(db: Session, person_id: int) -> list[Referral]:
    return list(
        db.scalars(
            select(Referral)
            .where(Referral.person_id == person_id)
            .order_by(Referral.created_at.desc(), Referral.id.desc())
        ).all()
    )
