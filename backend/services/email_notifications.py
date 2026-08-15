"""
Sends a real email pre-alert for ORANGE/RED referrals — a demo-only channel
alongside the existing SMS hospital pre-alert (services/notifications.py's
send_hospital_prealert). Added 10 August 2026 the night before the demo, so
a judge watching a live screening sees an actual email land, not a
simulated log line.

12 August: switched from Gmail SMTP (smtplib) to Resend's HTTP API,
called directly with httpx — same reasoning as services/notifications.py's
choice to call Africa's Talking's REST API directly rather than use SMTP-
adjacent protocols: Render's free tier blocks outbound SMTP entirely
(confirmed live — every smtplib attempt failed with `OSError: [Errno 101]
Network is unreachable`, a routing-level block on port 587, not an auth
problem). Resend is plain HTTPS, same as every other outbound call this
backend already makes (Gemini, Africa's Talking), so it isn't subject to
that restriction.

Without domain verification, Resend only allows sending FROM their shared
`onboarding@resend.dev` address and TO the email the API key's account was
created with — exactly this project's setup (EMAIL_TO is the personal
Gmail standing in for a hospital inbox, same account used to sign up for
Resend). RESEND_API_KEY is required; RESEND_FROM_EMAIL/EMAIL_TO are
overridable once a real domain is verified later.

Failures are logged, not raised — same non-negotiable pattern as SMS: a
notification failing must never break the referral/screening transaction
that triggered it (services/notifications.py's module docstring states
this explicitly; the same contract applies here).
"""

import logging
import os
from typing import List, Optional

import httpx

from services.notifications import _log_notification

logger = logging.getLogger("silicaguard.email")

_RESEND_URL = "https://api.resend.com/emails"
_DEFAULT_FROM = "SilicaGuard <onboarding@resend.dev>"
_TIMEOUT_SECONDS = 10


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
    """Returns True only if the Resend API call actually succeeded,
    mirroring send_hospital_prealert's contract — a caller could gate
    referral state on this the same way if a future version wants email-
    specific tracking. Called from services/referrals.
    create_referral_and_notify, same ORANGE/RED-only gate as everything
    else there."""
    api_key = os.getenv("RESEND_API_KEY")
    sender = os.getenv("RESEND_FROM_EMAIL", _DEFAULT_FROM)
    recipient = os.getenv("EMAIL_TO") or os.getenv("EMAIL_ADDRESS")

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

    if not api_key or not recipient:
        logger.warning(
            "RESEND_API_KEY/EMAIL_TO (or EMAIL_ADDRESS) not set — skipping referral alert email"
        )
        _log_notification(worker_id, "referral_email", body, "skipped", channel="email")
        return False

    try:
        response = httpx.post(
            _RESEND_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": sender,
                "to": [recipient],
                "subject": subject,
                "text": body,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        logger.info("Referral alert email sent via Resend: %s", response.text)
        _log_notification(worker_id, "referral_email", body, "sent", channel="email")
        return True
    except Exception:
        logger.exception("Failed to send referral alert email (worker_id=%s)", worker_id)
        _log_notification(worker_id, "referral_email", body, "failed", channel="email")
        return False
