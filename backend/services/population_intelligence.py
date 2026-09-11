"""Population Health Intelligence — SILICAGUARD.md Section 10, AI module 4:
"a scheduled weekly job reads the preceding period's screening/referral/
attendance data, identifies site-level risk clustering, and produces a
short plain-language narrative for the dashboard."

Follows services/ai_risk_engine.py's exact pattern (own lazily-constructed
genai.Client, prompt loaded once at import time, same model). Unlike the
risk engine, this is *not* JSON output — the whole response is the
narrative text, since there's nothing structured to extract.

This narrative is for a professional dashboard audience (hospital/district
health staff), not a patient — the same category as the risk engine's
explanation_english, which is also free-form AI text today. CLAUDE.md's
"no AI output reaches a patient as free-form text" governance rule is
about patient-facing content specifically and doesn't apply here.

Wrapped in try/except -> a deterministic fallback string, so
GET /api/dashboard/week can never 500 because Gemini is slow/down/rate
limited — a dashboard should degrade gracefully, not break.
"""

import os
from pathlib import Path

from google import genai
from google.genai import types

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "population_narrative_prompt.txt"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")

# 23 August 2026 — same fix as services/ai_risk_engine.py's MODEL, same
# reasoning (see that file's comment for the full investigation):
# "gemini-flash-latest" is a moving alias that had drifted onto an
# unstable, freshly-released model generation. Pinned to the same tested,
# fast, reliable version rather than another alias.
MODEL = "gemini-3.1-flash-lite"
_REQUEST_TIMEOUT_MS = 12_000

_client_instance: genai.Client | None = None


def _client() -> genai.Client:
    global _client_instance
    if _client_instance is None:
        _client_instance = genai.Client(
            api_key=os.getenv("GEMINI_API_KEY"),
            http_options=types.HttpOptions(timeout=_REQUEST_TIMEOUT_MS),
        )
    return _client_instance


def _fallback_narrative(
    total_screened: int,
    high_risk_count: int,
    referral_completion_rate: float,
    site_breakdown: list,
) -> str:
    """Deterministic, no AI call — used when the live Gemini call fails."""
    top_site = max(site_breakdown, key=lambda s: s["count"])["mine_site"] if site_breakdown else "no site data"
    return (
        f"{total_screened} workers screened this period, {high_risk_count} at ORANGE/RED risk "
        f"(referral completion {referral_completion_rate:.0%}). Most screening activity at {top_site}. "
        "(Automated narrative unavailable this week — AI service could not be reached.)"
    )


def generate_weekly_narrative(
    total_screened: int,
    high_risk_count: int,
    referral_completion_rate: float,
    tier_distribution: dict,
    site_breakdown: list,
) -> str:
    user_message = (
        f"total_screened: {total_screened}\n"
        f"high_risk_count (ORANGE+RED): {high_risk_count}\n"
        f"referral_completion_rate: {referral_completion_rate:.2f}\n"
        f"tier_distribution: {tier_distribution}\n"
        f"site_breakdown: {site_breakdown}\n\n"
        "Write this week's narrative per the rules above."
    )
    try:
        response = _client().models.generate_content(
            model=MODEL,
            contents=user_message,
            config={"system_instruction": SYSTEM_PROMPT},
        )
        text = response.text.strip()
        if not text:
            raise ValueError("empty response from Gemini")
        return text
    except Exception:
        return _fallback_narrative(
            total_screened, high_risk_count, referral_completion_rate, site_breakdown
        )
