"""
STUBBED — no Africa's Talking SMS account or WhatsApp Cloud API sandbox is set
up yet. Every function here logs what it *would* send instead of sending it.

Once real credentials exist (AT_API_KEY + SMS product enabled, or
WHATSAPP_TOKEN + WHATSAPP_PHONE_ID), replace the body of each function with a
real API call — the call sites in routers/screening.py and
services/ussd_handler.py don't need to change, since they only care that these
functions exist and don't raise.
"""

import logging

logger = logging.getLogger("silicaguard.notifications")


def send_miner_result(phone_number: str, risk_level: str, shona_message: str) -> None:
    """TODO: send via WhatsApp Cloud API if the number has WhatsApp, else SMS
    via Africa's Talking. Must end with the hospital address/phone and the
    line 'Show this message to the nurse when you arrive.' per the doctor's
    guidance — do not invent that wording here, get it from the doctor."""
    logger.info(
        "[STUB] would message miner %s (risk=%s): %s",
        phone_number,
        risk_level,
        shona_message,
    )


def send_hospital_prealert(
    miner_name: str,
    phone_number: str,
    mine_site: str | None,
    risk_level: str,
    contributing_factors_summary: str,
) -> None:
    """TODO: send via SMS/WhatsApp to the outreach nurse's number (needs a new
    env var, e.g. HOSPITAL_NURSE_PHONE, once real sending is wired in)."""
    logger.info(
        "[STUB] would pre-alert hospital: New %s from screening. "
        "Miner %s, phone %s, %s. Factors: %s",
        risk_level,
        miner_name,
        phone_number,
        mine_site or "mine site unknown",
        contributing_factors_summary,
    )
