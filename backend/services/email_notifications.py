"""
Sends a real email pre-alert for ORANGE/RED referrals — a demo-only channel
alongside the existing SMS hospital pre-alert (services/notifications.py's
send_hospital_prealert). Added 10 August 2026 the night before the demo, so
a judge watching a live screening sees an actual email land, not a
simulated log line.

Uses Gmail SMTP via Python's stdlib smtplib — no new dependency. Google
blocks plain-password SMTP login, so sending requires a Gmail "App
Password" (myaccount.google.com/apppasswords, needs 2-Step Verification
enabled first), read from EMAIL_APP_PASSWORD. Never hardcoded, never
logged.

For this demo, EMAIL_ADDRESS is both the sender and (by default) the
recipient — a personal Gmail standing in for a hospital's real inbox,
exactly as documented in CLAUDE.md's sprint status: "working as a hospital
email linked for now." Set EMAIL_TO separately to point at a different
address without touching this function or its caller.

Failures are logged, not raised — same non-negotiable pattern as SMS: a
notification failing must never break the referral/screening transaction
that triggered it (services/notifications.py's module docstring states
this explicitly; the same contract applies here).
"""

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import List, Optional

from services.notifications import _log_notification

logger = logging.getLogger("silicaguard.email")

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587
_SMTP_TIMEOUT_SECONDS = 10


def send_referral_alert_email(
    worker_id: int,
    miner_name: str,
    phone_number: str,
    mine_site: Optional[str],
    tier: str,
    facility_name: str,
    deadline: str,
    contributing_factors: Optional[List[str]] = None,
) -> bool:
    """Returns True only if the email actually sent, mirroring
    send_hospital_prealert's contract — a caller could gate referral state
    on this the same way if a future version wants email-specific
    tracking. Called from services/referrals.create_referral_and_notify,
    same ORANGE/RED-only gate as everything else there."""
    sender = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_APP_PASSWORD")
    recipient = os.getenv("EMAIL_TO") or sender

    factors_summary = ", ".join(contributing_factors) if contributing_factors else "N/A"
    subject = f"[SilicaGuard] {tier} referral — {miner_name} ({mine_site or 'unknown site'})"
    body = (
        f"New {tier} referral from a live SilicaGuard screening.\n\n"
        f"Miner: {miner_name}\n"
        f"Phone: {phone_number}\n"
        f"Site: {mine_site or 'unknown'}\n"
        f"Facility: {facility_name}\n"
        f"Deadline: {deadline}\n"
        f"Contributing factors: {factors_summary}\n\n"
        "— SilicaGuard Smart Referral Router (demo — standing in for a "
        "real hospital inbox integration)"
    )

    if not sender or not password:
        logger.warning(
            "EMAIL_ADDRESS/EMAIL_APP_PASSWORD not set — skipping referral alert email"
        )
        _log_notification(worker_id, "referral_email", body, "skipped", channel="email")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)

    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=_SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.starttls()
            smtp.login(sender, password)
            smtp.send_message(msg)
        _log_notification(worker_id, "referral_email", body, "sent", channel="email")
        return True
    except Exception:
        logger.exception("Failed to send referral alert email (worker_id=%s)", worker_id)
        _log_notification(worker_id, "referral_email", body, "failed", channel="email")
        return False
