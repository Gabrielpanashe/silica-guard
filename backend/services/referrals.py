from typing import List, Optional

from services import notifications

# The AI Risk Engine (/api/screen) is English-only (see SILICAGUARD.md Section
# 9.1 scope decision) so it has no Shona of its own to relay to the miner.
# Rather than invent new Shona text, reuse the doctor-approved fixed REFER_NOW
# message from Section 10 (offline Dart fallback engine) as a generic
# "you're being referred" SMS for any REFER_NOW referral that didn't come
# through USSD's own decision tree (which already has its own Shona message).
GENERIC_REFER_NOW_SHONA_MESSAGE = (
    "Zvakafanana nemamiriro ane njodzi. Enda kuchipatara Kwekwe nhasi kuti upiwe X-ray."
)


def create_referral_and_notify(
    conn,
    screening_id: int,
    miner_id: int,
    miner_name: str,
    phone_number: str,
    mine_site: Optional[str],
    risk_level: str,
    shona_message: str,
    contributing_factors: Optional[List[str]] = None,
) -> None:
    """Only acts on REFER_NOW. Creates the referrals row that Section 6's
    schema already had a place for, then sends real SMS via Africa's Talking.
    pre_alert_sent reflects the actual hospital SMS API call result, not just
    an attempted/logged intent."""
    if risk_level != "REFER_NOW":
        return

    cur = conn.execute(
        """INSERT INTO referrals (screening_id, miner_id, hospital, pre_alert_sent, status)
           VALUES (?, ?, 'Kwekwe District Hospital', 0, 'PENDING')""",
        (screening_id, miner_id),
    )
    referral_id = cur.lastrowid
    conn.commit()

    notifications.send_miner_result(phone_number, risk_level, shona_message)
    prealert_sent = notifications.send_hospital_prealert(
        miner_name,
        phone_number,
        mine_site,
        risk_level,
        ", ".join(contributing_factors) if contributing_factors else "N/A",
    )

    if prealert_sent:
        conn.execute(
            "UPDATE referrals SET pre_alert_sent = 1 WHERE id = ?", (referral_id,)
        )
        conn.commit()
