import json
import logging
import os
import re
import time
from pathlib import Path
from typing import List

from google import genai
from google.genai import types

from models import ScreeningAnswerIn

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "risk_engine_prompt.txt"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")

MODEL = "gemini-flash-latest"

logger = logging.getLogger("silicaguard.ai_risk_engine")

# 23 August 2026 — found live, via Render's own request logs, that
# POST /api/screen's 502s were caused by Gemini itself returning a genuine
# "503 Service Unavailable" for gemini-flash-latest, not a code bug, bad
# key, or network problem (a request against the same key from a different
# network succeeded on the very next attempt). A 503 from Gemini is
# Google's own "model temporarily overloaded, try again" signal, not a
# hard failure — a short retry-with-backoff resolves most of these without
# ever surfacing a 502 to the miner at all. Against the APP path's no hard
# deadline (unlike the USSD path's true 10-second limit, which never calls
# this function at all).
#
# _REQUEST_TIMEOUT_MS caps each individual attempt — added after a live
# test showed a "successful" retry taking 83 seconds end-to-end with no
# per-call timeout set at all (the SDK's own default was left to whatever
# it is, observed to be very generous), which is a bad experience even
# when it does eventually work. 3 attempts x 12s worst case + backoff
# bounds the whole function to roughly 38s worst case instead of however
# long an unbounded hang could take.
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (0.5, 1.5)
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


def _format_answers(answers: List[ScreeningAnswerIn]) -> str:
    lines = [
        f"- {a.question_code}: value={a.answer_value}, score={a.answer_score}"
        for a in answers
    ]
    return "\n".join(lines)


def _extract_json(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(text)


def assess_risk(answers: List[ScreeningAnswerIn]) -> dict:
    user_message = (
        "Here are the 10 screening answers for a miner:\n\n"
        f"{_format_answers(answers)}\n\n"
        "Classify this miner's silicosis risk per the rules above. "
        "Respond ONLY with the JSON object described in OUTPUT FORMAT."
    )

    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = _client().models.generate_content(
                model=MODEL,
                contents=user_message,
                config={"system_instruction": SYSTEM_PROMPT},
            )
            return _extract_json(response.text)
        except Exception as e:
            last_error = e
            if attempt < _MAX_ATTEMPTS - 1:
                logger.warning(
                    "Gemini call failed (attempt %d/%d): %s — retrying",
                    attempt + 1, _MAX_ATTEMPTS, e,
                )
                time.sleep(_BACKOFF_SECONDS[attempt])

    raise last_error
