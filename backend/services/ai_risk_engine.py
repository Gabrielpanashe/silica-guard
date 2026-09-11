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

# 23 August 2026 — root-caused live, not guessed: "gemini-flash-latest" is a
# MOVING ALIAS, and Google had silently repointed it at a brand-new model
# generation (Gemini 3.x was already in this project's model catalog,
# alongside 3.1/3.5/3.6/3.7) — freshly-released models are exactly what
# gets 503'd/queued under load before Google finishes scaling capacity for
# them. Confirmed directly: gemini-3.6-flash (Google's own suggested
# replacement once even gemini-2.5-flash came back 404 "no longer
# available to new users") returned successfully every time but with
# wildly inconsistent latency — 1.8s, 10.3s, 12.1s, 29.1s, 61.8s, 101.9s
# across 6 back-to-back calls — worse for a live demo than an occasional
# clean 503, since it never fails fast, it just hangs unpredictably.
#
# gemini-3.1-flash-lite tested consistently fast (~1-2s, zero retries
# needed across 6 calls) AND produced clinically consistent judgments
# matching what the flagship model concluded independently on the same
# two test cases (a heavy-exposure/mild-symptom scenario → ORANGE both
# times; a low-exposure/asymptomatic scenario → GREEN both times, high
# confidence). Pinned to this specific version, not another "-latest"
# alias, so this can't silently repoint at an unstable model again —
# revisit deliberately, not by surprise.
MODEL = "gemini-3.1-flash-lite"

logger = logging.getLogger("silicaguard.ai_risk_engine")

# Retry-with-backoff for whatever transient failures remain (a 503, a
# brief network blip) — cheap insurance now that MODEL itself is the
# primary fix, not the main mitigation it was before pinning away from
# the unstable "-latest" alias.
#
# _REQUEST_TIMEOUT_MS caps each individual attempt — added after a live
# test against the old alias showed a "successful" retry taking 83
# seconds end-to-end with no per-call timeout set at all (the SDK's own
# default was left to whatever it is, observed to be very generous).
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
