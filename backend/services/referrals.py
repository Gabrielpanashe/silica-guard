import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db_models import Facility, Referral
from services import email_notifications, notifications
from services.facility_matching import select_facility

# Urgency windows per SILICAGUARD.md Section 7 Pillar 2 (fixed by the
# reference doc, not a clinical judgment call): RED is urgent (48h), ORANGE
# is routine (14 days). Reused by services/referral_cascade.py for the
# reminder/escalation cascade rather than re-hardcoded there.
_URGENCY_WINDOW = {
    "RED": timedelta(hours=48),
    "ORANGE": timedelta(days=14),
}

_DEFAULT_HOSPITAL_NAME = "Kwekwe District Hospital"

# Referral code (14 August 2026, master doc v6.0 Section 1.1) — the QR
# referral card reframed as a short human-readable code, e.g. "SG-4K7Q":
# sent to the miner by SMS, included in the facility pre-alert, and typed
# by hospital staff into a lookup page (routers/referral_lookup.py) to
# confirm attendance. Charset excludes 0/O and 1/I — a code read off a
# phone screen or handwritten at a nurse's desk shouldn't hinge on telling
# those apart.
_CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1I")
_CODE_LENGTH = 4
_CODE_MAX_ATTEMPTS = 20


def _generate_referral_code(db: Session) -> str:
    for _ in range(_CODE_MAX_ATTEMPTS):
        candidate = "SG-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        if db.scalar(select(Referral).where(Referral.referral_code == candidate)) is None:
            return candidate
    # With a ~32^4 (~1M) code space this is not realistically reachable at
    # pilot scale — raising rather than silently returning a colliding code
    # is the safer failure mode for something a hospital will look up by.
    raise RuntimeError("Could not generate a unique referral code after {} attempts".format(_CODE_MAX_ATTEMPTS))


def create_referral_and_notify(
    db: Session,
    screening_id: int,
    miner_id: int,
    miner_name: str,
    phone_number: str,
    mine_site: Optional[str],
    tier: str,
    shona_message: str,
    contributing_factors: Optional[List[str]] = None,
) -> Optional[Referral]:
    """Only acts on ORANGE/RED (returns None otherwise). Creates the
    referrals row (facility-matched — see services/facility_matching.py),
    then sends real SMS via Africa's Talking. pre_alert_sent reflects the
    actual hospital SMS API call result, not just an attempted/logged
    intent.

    Returns the created Referral (with .referral_code/.facility name/etc
    already populated) so the caller — routers/screening.py — can surface
    the real code in POST /api/screen's own response. Previously discarded
    entirely; see ScreeningResult's referral_code field docstring for why
    that was a real gap, not just an unused return value."""
    if tier not in _URGENCY_WINDOW:
        return None

    deadline = datetime.now(timezone.utc).replace(tzinfo=None) + _URGENCY_WINDOW[tier]

    # select_facility() is pure, dict-in/dict-out logic (deliberately DB-
    # agnostic, see services/facility_matching.py and its own unit tests) —
    # ORM rows are converted to plain dicts here rather than changing that
    # module to expect attribute access.
    facility_rows = [
        {"id": f.id, "name": f.name, "level": f.level} for f in db.scalars(select(Facility)).all()
    ]
    facility = select_facility(tier, mine_site, facility_rows)
    facility_id = facility["id"] if facility else None
    facility_name = facility["name"] if facility else _DEFAULT_HOSPITAL_NAME

    referral = Referral(
        screening_id=screening_id,
        miner_id=miner_id,
        hospital=facility_name,
        facility_id=facility_id,
        referral_code=_generate_referral_code(db),
        deadline=deadline,
        pre_alert_sent=0,
        status="open",
    )
    db.add(referral)
    db.commit()
    db.refresh(referral)

    notifications.send_miner_result(
        miner_id, phone_number, tier, shona_message, referral_code=referral.referral_code
    )
    prealert_sent = notifications.send_hospital_prealert(
        miner_id,
        miner_name,
        phone_number,
        mine_site,
        tier,
        ", ".join(contributing_factors) if contributing_factors else "N/A",
        referral_code=referral.referral_code,
    )

    if prealert_sent:
        referral.pre_alert_sent = 1
        referral.status = "pre_alerted"
        db.commit()

    # Demo-only email pre-alert (10 August) — a second, independent channel
    # alongside the SMS pre-alert above. Deliberately doesn't affect
    # pre_alert_sent/status — that field's contract is "the SMS to the
    # nurse's phone succeeded" and email failing/succeeding shouldn't
    # change what it means. Never raises; a failed email must never break
    # a screening that otherwise completed successfully.
    email_notifications.send_referral_alert_email(
        miner_id,
        miner_name,
        phone_number,
        mine_site,
        tier,
        facility_name,
        deadline.strftime("%Y-%m-%d %H:%M UTC"),
        contributing_factors,
    )

    return referral
