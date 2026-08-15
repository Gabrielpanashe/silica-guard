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

Every send is also persisted to the `notifications` table (5 August 2026 —
SILICAGUARD.md Section 7's target schema, "every SMS sent, for audit and
delivery reporting", previously only ever a log line). Each public function
below opens and closes its own short-lived DB connection for this rather
than accepting a `conn` parameter threaded in from the caller — matches the
existing precedent in services/referral_cascade.py's run_scheduled_cascade
(background/audit concerns manage their own connection), and is more
correct for an audit trail: a notification that was actually sent should be
logged even if the caller's surrounding transaction later fails.
"""

import logging
import os

import httpx

from database import get_fresh_session
from db_models import Notification

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


def _log_notification(
    worker_id: int, template: str, payload: str, delivery_status: str, channel: str = "sms"
) -> None:
    """Best-effort audit write — a logging failure must never surface as if
    the SMS itself failed, so this swallows its own exceptions. `channel`
    defaults to 'sms' (every existing call site is unaffected); 10 August
    added 'email' for services/email_notifications.py's referral alert —
    same notifications table, so both channels show up in one audit trail
    rather than two."""
    db = get_fresh_session()
    try:
        db.add(
            Notification(
                worker_id=worker_id,
                channel=channel,
                template=template,
                payload=payload,
                delivery_status=delivery_status,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to log notification (template=%s, worker_id=%s)", template, worker_id
        )
    finally:
        db.close()


def send_miner_result(worker_id: int, phone_number: str, tier: str, shona_message: str) -> bool:
    """Doctor-approved Shona explanation (shona_message) + English facility info
    + a line telling the miner what to do with this message at the hospital."""
    body = (
        f"{shona_message}\n\n"
        f"{HOSPITAL_INFO_EN}\n"
        "Show this message to the nurse when you arrive."
    )
    ok = _send_sms(phone_number, body)
    _log_notification(worker_id, "miner_result", body, "sent" if ok else "failed")
    return ok


def send_screening_result_sms(worker_id: int, phone_number: str, tier: str, shona_message: str) -> bool:
    """Result-only SMS for GREEN/YELLOW screenings, which never trigger a
    referral (see services/referrals.create_referral_and_notify's
    ORANGE/RED-only gate). Deliberately a separate function from
    send_miner_result rather than a reuse with different inputs — that
    function's body always ends with "Show this message to the nurse when
    you arrive", which is wrong here: there is no facility visit to show it
    at. Added 7 August 2026 so every tier gets an SMS, per CLAUDE.md's
    project identity: "Everyone receives their result... by SMS.\""""
    body = f"SilicaGuard: {shona_message}"
    ok = _send_sms(phone_number, body)
    _log_notification(worker_id, "screening_result", body, "sent" if ok else "failed")
    return ok


def send_hospital_prealert(
    worker_id: int,
    miner_name: str,
    phone_number: str,
    mine_site: str | None,
    tier: str,
    contributing_factors_summary: str,
) -> bool:
    """Returns True only if the SMS API call succeeded, so the caller can set
    referrals.pre_alert_sent accurately instead of assuming success."""
    body = (
        f"New {tier} referral from SilicaGuard screening. "
        f"Miner: {miner_name}, Phone: {phone_number}, "
        f"Site: {mine_site or 'unknown'}. Factors: {contributing_factors_summary}"
    )
    nurse_phone = os.getenv("HOSPITAL_NURSE_PHONE")
    if not nurse_phone:
        logger.warning(
            "HOSPITAL_NURSE_PHONE not set — skipping hospital pre-alert SMS"
        )
        _log_notification(worker_id, "hospital_prealert", body, "skipped")
        return False
    ok = _send_sms(nurse_phone, body)
    _log_notification(worker_id, "hospital_prealert", body, "sent" if ok else "failed")
    return ok


# --- Smart Referral Router reminder/escalation cascade (5 August 2026) ---
# DRAFT COPY, same caveat as advice_engine.py: not yet Clinical-Lead-signed
# off. Fired by services/referral_cascade.py, itself triggered by the
# APScheduler job in main.py — never called synchronously from a request.


def send_referral_reminder(worker_id: int, phone_number: str, tier: str, stage: int) -> bool:
    """Sent to the miner when a referral is still open partway through its
    urgency window (RED: ~24h in; ORANGE: day 3, then day 7)."""
    body = (
        f"Reminder from SilicaGuard: your {tier} screening result means you "
        "should visit the hospital soon. "
        f"{HOSPITAL_INFO_EN} Show your referral message to the nurse."
    )
    ok = _send_sms(phone_number, body)
    _log_notification(worker_id, "referral_reminder", body, "sent" if ok else "failed")
    return ok


def send_referral_escalation(worker_id: int, miner_name: str, phone_number: str, tier: str) -> bool:
    """Sent to the hospital nurse (not the miner) when a referral's urgency
    deadline passes with no recorded attendance — RED: 48h, ORANGE: 14 days.
    worker_id still identifies the miner whose referral triggered this —
    the audit trail records whose clinical event caused the send, not just
    who physically received the SMS."""
    body = (
        f"ESCALATION: {tier} referral for {miner_name} ({phone_number}) has "
        "passed its urgency deadline with no recorded attendance. Please follow up."
    )
    nurse_phone = os.getenv("HOSPITAL_NURSE_PHONE")
    if not nurse_phone:
        logger.warning(
            "HOSPITAL_NURSE_PHONE not set — skipping referral escalation SMS"
        )
        _log_notification(worker_id, "referral_escalation", body, "skipped")
        return False
    ok = _send_sms(nurse_phone, body)
    _log_notification(worker_id, "referral_escalation", body, "sent" if ok else "failed")
    return ok


# --- Outreach Planner (5 August 2026) ---
# DRAFT COPY, same not-yet-signed-off caveat as everything else above.


def send_outreach_announcement(
    worker_id: int, phone_number: str, site: str, scheduled_date: str, stage: str
) -> bool:
    """stage is "3day" or "1day" — how far ahead of the visit this
    announcement is. Sent to every worker previously registered at `site`."""
    when = "in 3 days" if stage == "3day" else "tomorrow"
    body = (
        f"SilicaGuard screening at {site} {when} ({scheduled_date}). "
        "Come for your free lung health check and education session."
    )
    ok = _send_sms(phone_number, body)
    template = f"outreach_announcement_{stage}"
    _log_notification(worker_id, template, body, "sent" if ok else "failed")
    return ok
