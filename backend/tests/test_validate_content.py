"""The content validator must actually reject strings that would cost money
or break in the field.

Master Reference v1.0 §8.4. The character-set failure in particular is
invisible in code review and silent at runtime: one curly apostrophe pasted
out of a word processor sends every copy of that message as 16-bit at 70
characters per segment instead of 160, permanently. So the gate has to be
real, and a gate that cannot fail is worse than no gate.

No clinical content is authored here or in `content/messages/example.yaml`.
The strings are the Clinical Lead's deliverable (ROADMAP.md, weeks 8 and 12).
"""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent.parent
EXAMPLE = REPO / "content" / "messages" / "example.yaml"
VALIDATOR = REPO / "backend" / "scripts" / "validate_content.py"

sys.path.insert(0, str(REPO / "backend" / "scripts"))
from validate_content import GSM7_BASIC, non_gsm7, septets  # noqa: E402


def _run(*args: str):
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args], capture_output=True, text=True
    )


def _write(tmp_path: Path, messages: list[dict], name: str = "case") -> Path:
    p = tmp_path / f"{name}.yaml"
    p.write_text(
        yaml.safe_dump({"area": "test", "messages": messages}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------- septets

def test_plain_ascii_counts_one_septet_each():
    assert septets("hello") == 5


def test_extension_characters_cost_two_septets():
    """^ { } \\ [ ] ~ | and the euro sign are seven-bit but sent as an escape
    plus the character, so a budget check that counts them as one is wrong."""
    assert septets("[") == 2
    assert septets("abc[") == 5


def test_gsm7_includes_the_accented_characters_the_alphabet_actually_has():
    for ch in "£¥èéùìòÇØøÅåÆæßÉÄÖÑÜ§¿äöñüà":
        assert ch in GSM7_BASIC, f"{ch!r} should be GSM-7 basic"


def test_curly_punctuation_is_not_gsm7():
    for ch in "‘’“”–—… ":
        assert septets(ch) == -1, f"{ch!r} (U+{ord(ch):04X}) must be rejected"


def test_non_gsm7_reports_position_and_character():
    found = non_gsm7("ok’s")
    assert found == [(2, "’")]


# ------------------------------------------------------------- the example

def test_the_example_is_valid():
    """If this fails, every negative case below is meaningless."""
    result = _run(str(EXAMPLE))
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_example_is_not_patient_facing_content():
    """It is a format illustration. Nothing in it may be sent, and no
    local-language text is invented in it."""
    doc = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    for m in doc["messages"]:
        assert m["status"] == "draft", f"{m['code']} must stay a draft"
        assert "EXAMPLE FILLER" in m["text"]["en"] or "FILLER" in m["text"]["en"]
        for lang in ("sn", "nd"):
            assert "to be authored" in m["text"][lang], (
                f"{m['code']} {lang}: local-language text must stay an explicit "
                "marker, never invented"
            )


def test_the_example_covers_every_channel():
    doc = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    channels = {m["channel"] for m in doc["messages"]}
    assert channels == {"sms", "ussd", "app", "clinician"}


# ---------------------------------------------------------- negative cases

def test_rejects_a_curly_apostrophe(tmp_path):
    p = _write(tmp_path, [{
        "code": "t.curly", "channel": "sms", "status": "draft",
        "purpose": "word-processor punctuation",
        "text": {"en": "Don’t worry"},
    }])
    r = _run(str(p))
    assert r.returncode != 0
    assert "not GSM-7" in r.stdout
    assert "16-bit" in r.stdout, "the error must explain the cost consequence"


def test_suggests_the_ascii_replacement(tmp_path):
    p = _write(tmp_path, [{
        "code": "t.dash", "channel": "sms", "status": "draft",
        "purpose": "em dash",
        "text": {"en": "ready — go"},
    }])
    r = _run(str(p))
    assert "use '-'" in r.stdout


def test_rejects_text_over_the_channel_budget(tmp_path):
    p = _write(tmp_path, [{
        "code": "t.long", "channel": "ussd", "status": "draft",
        "purpose": "over a USSD page",
        "text": {"en": "X" * 200},
    }])
    r = _run(str(p))
    assert r.returncode != 0
    assert "over a 182 budget" in r.stdout
    assert "never truncated" in r.stdout


def test_budget_is_checked_in_every_language_not_just_english(tmp_path):
    """The local-language version is usually the longest, which is the whole
    reason the check runs per language."""
    p = _write(tmp_path, [{
        "code": "t.sn_long", "channel": "sms", "status": "draft",
        "purpose": "English fits, Shona does not",
        "text": {"en": "Short", "sn": "Y" * 200, "nd": "Short"},
    }])
    r = _run(str(p))
    assert r.returncode != 0
    assert "Shona" in r.stdout


def test_rejects_approval_without_all_three_languages(tmp_path):
    p = _write(tmp_path, [{
        "code": "t.approved", "channel": "sms", "status": "approved",
        "approved_by": "Someone", "approved_at": "2026-10-21",
        "purpose": "approved too early",
        "text": {"en": "English only"},
    }])
    r = _run(str(p))
    assert r.returncode != 0
    assert "sn" in r.stdout or "Shona" in r.stdout


def test_rejects_placeholder_mismatch_from_review_onward(tmp_path):
    p = _write(tmp_path, [{
        "code": "t.placeholder", "channel": "sms", "status": "review",
        "purpose": "declared placeholder missing from one language",
        "placeholders": ["name"],
        "text": {"en": "Hello {name}", "sn": "Hello", "nd": "Hello {name}"},
    }])
    r = _run(str(p))
    assert r.returncode != 0
    assert "placeholders missing {name}" in r.stdout


def test_allows_placeholder_gaps_while_still_a_draft(tmp_path):
    """A message is authored one language at a time over weeks. A draft whose
    local-language entry is still a marker must not fail the build; approval
    is the gate."""
    p = _write(tmp_path, [{
        "code": "t.draft", "channel": "sms", "status": "draft",
        "purpose": "work in progress",
        "placeholders": ["name"],
        "text": {"en": "Hello {name}", "sn": "(Shona: to be authored)"},
    }])
    r = _run(str(p))
    assert r.returncode == 0, r.stdout


def test_rejects_an_undeclared_placeholder(tmp_path):
    p = _write(tmp_path, [{
        "code": "t.undeclared", "channel": "sms", "status": "review",
        "purpose": "placeholder used but not declared",
        "text": {"en": "Hello {name}", "sn": "Hello {name}", "nd": "Hello {name}"},
    }])
    r = _run(str(p))
    assert r.returncode != 0
    assert "undeclared {name}" in r.stdout


def test_rejects_a_duplicate_message_code(tmp_path):
    msg = {"code": "t.dupe", "channel": "sms", "status": "draft",
           "purpose": "duplicate", "text": {"en": "One"}}
    p = _write(tmp_path, [msg, dict(msg)])
    r = _run(str(p))
    assert r.returncode != 0
    assert "duplicate message code" in r.stdout


def test_accepts_a_file_outside_the_repository(tmp_path):
    p = _write(tmp_path, [{
        "code": "t.outside", "channel": "sms", "status": "draft",
        "purpose": "path handling", "text": {"en": "Fine"},
    }])
    r = _run(str(p))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Traceback" not in (r.stdout + r.stderr)


@pytest.mark.parametrize("channel,budget", [("sms", 160), ("ussd", 182), ("app", 480)])
def test_budget_boundary_is_inclusive(tmp_path, channel, budget):
    """Exactly at the budget passes; one over fails. An off-by-one here either
    rejects valid copy or lets a second segment through."""
    at = _write(tmp_path, [{"code": "t.at", "channel": channel, "status": "draft",
                            "purpose": "exactly at the budget",
                            "text": {"en": "X" * budget}}], "at")
    over = _write(tmp_path, [{"code": "t.over", "channel": channel, "status": "draft",
                              "purpose": "one septet over the budget",
                              "text": {"en": "X" * (budget + 1)}}], "over")
    assert _run(str(at)).returncode == 0
    assert _run(str(over)).returncode != 0
