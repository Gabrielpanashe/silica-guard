from datetime import datetime, timedelta, timezone
from typing import List, Optional

from services import notifications

# Urgency windows per SILICAGUARD.md Section 7 Pillar 2 (fixed by the
# reference doc, not a clinical judgment call): RED is urgent (48h), ORANGE
# is routine (14 days). Facility matching and the reminder/escalation
# cascade (day 3, day 7, day 14) are Smart Referral Router work — not built
# yet; only the initial deadline is set here.
_URGENCY_WINDOW = {
    "RED": timedelta(hours=48),
    "ORANGE": timedelta(days=14),
}

# The AI Risk Engine (/api/screen) is English-only (see CLAUDE.md) so it has
# no Shona of its own to relay to the miner. Rather than invent new Shona
# text, reuse the doctor-approved fixed high-risk message from the USSD
# decision tree (services/ussd_handler.py) as a generic "you're being
# referred" SMS for any AI-triggered referral that didn't come through USSD
# itself (which already has its own Shona message).
GENERIC_REFERRAL_SHONA_MESSAGE = (
    "Zvakafanana nemamiriro ane njodzi. Enda kuchipatara Kwekwe nhasi kuti upiwe X-ray."
)


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
    """Only acts on ORANGE/RED. Creates the referrals row, then sends real SMS
    via Africa's Talking. pre_alert_sent reflects the actual hospital SMS API
    call result, not just an attempted/logged intent."""
    if tier not in _URGENCY_WINDOW:
        return

    deadline = datetime.now(timezone.utc) + _URGENCY_WINDOW[tier]

    cur = conn.execute(
        """INSERT INTO referrals (screening_id, miner_id, hospital, deadline, pre_alert_sent, status)
           VALUES (?, ?, 'Kwekwe District Hospital', ?, 0, 'open')""",
        (screening_id, miner_id, deadline.strftime("%Y-%m-%d %H:%M:%S")),
    )
    referral_id = cur.lastrowid
    conn.commit()

    notifications.send_miner_result(phone_number, tier, shona_message)
    prealert_sent = notifications.send_hospital_prealert(
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
