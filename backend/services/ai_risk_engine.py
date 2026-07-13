import json
import os
import re
from pathlib import Path
from typing import List

from google import genai

from models import ScreeningAnswerIn

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "risk_engine_prompt.txt"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")

MODEL = "gemini-flash-latest"

_client_instance: genai.Client | None = None


def _client() -> genai.Client:
    global _client_instance
    if _client_instance is None:
        _client_instance = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
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

    response = _client().models.generate_content(
        model=MODEL,
        contents=user_message,
        config={"system_instruction": SYSTEM_PROMPT},
    )

    return _extract_json(response.text)
