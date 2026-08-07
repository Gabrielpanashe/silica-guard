from datetime import datetime, timedelta, timezone
from typing import List, Optional

from services import notifications
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


def create_referral_and_notify(
    conn,
    screening_id: int,
    miner_id: int,
    miner_name: str,
    phone_number: str,
    mine_site: Optional[str],
    tier: str,
    shona_message: str,
    contributing_factors: Optional[List[str]] = None,
) -> None:
    """Only acts on ORANGE/RED. Creates the referrals row (facility-matched —
    see services/facility_matching.py), then sends real SMS via Africa's
    Talking. pre_alert_sent reflects the actual hospital SMS API call
    result, not just an attempted/logged intent."""
    if tier not in _URGENCY_WINDOW:
        return

    deadline = datetime.now(timezone.utc) + _URGENCY_WINDOW[tier]

    facilities = conn.execute("SELECT * FROM facilities").fetchall()
    facility = select_facility(tier, mine_site, facilities)
    facility_id = facility["id"] if facility else None
    facility_name = facility["name"] if facility else _DEFAULT_HOSPITAL_NAME

    cur = conn.execute(
        """INSERT INTO referrals (screening_id, miner_id, hospital, facility_id, deadline, pre_alert_sent, status)
           VALUES (?, ?, ?, ?, ?, 0, 'open')""",
        (screening_id, miner_id, facility_name, facility_id, deadline.strftime("%Y-%m-%d %H:%M:%S")),
    )
    referral_id = cur.lastrowid
    conn.commit()

    notifications.send_miner_result(miner_id, phone_number, tier, shona_message)
    prealert_sent = notifications.send_hospital_prealert(
        miner_id,
        miner_name,
        phone_number,
        mine_site,
        tier,
        ", ".join(contributing_factors) if contributing_factors else "N/A",
    )

    if prealert_sent:
        conn.execute(
            "UPDATE referrals SET pre_alert_sent = 1, status = 'pre_alerted' WHERE id = ?",
            (referral_id,),
        )
        conn.commit()
