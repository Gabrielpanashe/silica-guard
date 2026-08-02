"""
Sends real SMS via Africa's Talking (same account/sandbox as USSD, different
product). SMS is the only notification channel in this project (see
CLAUDE.md) — it reaches a miner regardless of whether he has a smartphone or
data.

In sandbox mode, Africa's Talking only delivers to phone numbers registered
as "Simulator Numbers" in the sandbox dashboard — sending to an arbitrary
real number will appear to succeed (the API call returns 201) but nothing
actually arrives on an unregistered phone.

Calls the Africa's Talking REST API directly with httpx rather than the
`africastalking` SDK — the SDK is built on `requests`/`urllib3`, which fails
with SSLError: WRONG_VERSION_NUMBER against this API in this environment
(likely local network/security software fingerprinting differently per HTTP
client). httpx and plain curl both connect fine; this was confirmed by
testing all three directly before deciding to bypass the SDK.

Failures are logged, not raised — a notification failing should never break
the referral/screening transaction that triggered it.
"""

import logging
import os

import httpx

logger = logging.getLogger("silicaguard.notifications")

# Doctor-approved facility info — not invented here.
HOSPITAL_INFO_EN = (
    "Kwekwe District Hospital: Corner Robert Mugabe / Sixth Ave. Tel: 055-24000."
)

_AT_SMS_URL = "https://api.sandbox.africastalking.com/version1/messaging"


def _send_sms(to: str, message: str) -> bool:
    headers = {
        "apiKey": os.getenv("AT_API_KEY"),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    data = {
        "username": os.getenv("AT_USERNAME", "sandbox"),
        "to": to,
        "message": message,
    }
    try:
        response = httpx.post(_AT_SMS_URL, headers=headers, data=data, timeout=10)
        response.raise_for_status()
        logger.info("SMS to %s: %s", to, response.text)
        return True
    except Exception:
        logger.exception("Failed to send SMS to %s", to)
        return False


def send_miner_result(phone_number: str, risk_level: str, shona_message: str) -> bool:
    """Doctor-approved Shona explanation (shona_message) + English facility info
    (from Section 9.2, not invented) + a line telling the miner what to do with
    this message at the hospital."""
    body = (
        f"{shona_message}\n\n"
        f"{HOSPITAL_INFO_EN}\n"
        "Show this message to the nurse when you arrive."
    )
    return _send_sms(phone_number, body)


def send_hospital_prealert(
    miner_name: str,
    phone_number: str,
    mine_site: str | None,
    risk_level: str,
    contributing_factors_summary: str,
) -> bool:
    """Returns True only if the SMS API call succeeded, so the caller can set
    referrals.pre_alert_sent accurately instead of assuming success."""
    nurse_phone = os.getenv("HOSPITAL_NURSE_PHONE")
    if not nurse_phone:
        logger.warning(
            "HOSPITAL_NURSE_PHONE not set — skipping hospital pre-alert SMS"
        )
        return False
    body = (
        f"New {risk_level} referral from SilicaGuard screening. "
        f"Miner: {miner_name}, Phone: {phone_number}, "
        f"Site: {mine_site or 'unknown'}. Factors: {contributing_factors_summary}"
    )
    return _send_sms(nurse_phone, body)
