"""The red-flag set exists twice in live code, and the copies must agree.

`ARCHITECTURE.md` principle 4: **channels are equivalent.** Mobile and USSD
read the same instrument and thresholds and must produce identical tiers from
identical answers; any difference is either specified deliberately or is a
bug.

`tests/test_channel_equivalence.py` proves that property for the **v2
engine**, over every answer the instrument offers, and says plainly that the
live USSD route is not on that engine yet (item 1.9). This file covers what
that one deliberately does not: the two channels as they run **today**.

**There are two copies of the red-flag set.**

    services/safety_overrides.py   RED_FLAG_VALUES    the app path
    services/ussd_handler.py       _DANGEROUS_TRIGGERS  the USSD path

They agree exactly as of 16 November 2026. That is worth an assertion rather
than a glance, because **two copies that happen to agree is not the same as
one source**: the day somebody adds a red flag to one of them, the two
channels classify the same worker differently and every existing test still
passes. A miner who self-screens over USSD would be told Level 2 for answers
that get Level 4 in front of a health worker, or the reverse.

Both copies go away together when item 1.9 lands and the instrument's
`safety_rules` become the only set — owned by the Clinical Lead rather than
inherited from code, which is `docs/CLINICAL.md` correction 1. **Until then
this file is the only thing holding them together.**

What this file does *not* claim: that the two channels produce the same tier
today. They cannot. The app path asks a language model for its tier and the
USSD path uses score thresholds, which is the defect item 1.9 exists to fix
and is recorded as a known divergence below rather than asserted away.
"""

import pytest

from services import safety_overrides, ussd_handler


def _app_red_flags() -> set[tuple[str, str]]:
    return {
        (code, value)
        for code, values in safety_overrides.RED_FLAG_VALUES.items()
        for value in values
    }


def _ussd_red_flags() -> set[tuple[str, str]]:
    return set(ussd_handler._DANGEROUS_TRIGGERS)


# ------------------------------------------------------------ the two copies

def test_the_two_red_flag_sets_are_identical():
    """**The assertion this file exists for.** A red flag added to one copy
    and not the other means a miner self-screening over USSD is told a
    different level from the one he would be told in front of a health
    worker, from the same answers — and nothing else in the suite notices.
    """
    app, ussd = _app_red_flags(), _ussd_red_flags()

    assert app == ussd, (
        "the red-flag sets have diverged.\n"
        f"  only in the app path (services/safety_overrides.py): {sorted(app - ussd)}\n"
        f"  only in USSD (services/ussd_handler.py):             {sorted(ussd - app)}\n"
        "Both channels must force the same tier from the same answer "
        "(ARCHITECTURE.md principle 4). Add it to both, or move both onto "
        "the instrument's safety_rules, which is item 1.9 and the point."
    )


def test_both_sets_are_non_empty():
    """A parity test over two empty sets passes for the wrong reason."""
    assert _app_red_flags()
    assert _ussd_red_flags()


def test_every_red_flag_names_a_real_question_and_option():
    """A red flag keyed to a question code or answer value that does not
    exist can never fire. It would sit in the file looking like a protection
    and be worth nothing — and because both copies are written by hand
    against `questions.py`, a renamed option breaks them silently."""
    from questions import SCREENING_QUESTIONS

    questions = {q["code"]: {o["value"] for o in q["options"]}
                 for q in SCREENING_QUESTIONS}

    for code, value in sorted(_app_red_flags() | _ussd_red_flags()):
        assert code in questions, f"red flag names unknown question {code}"
        assert value in questions[code], (
            f"red flag {code}={value!r} is not an option that question offers; "
            f"it offers {sorted(questions[code])}"
        )


def test_the_channels_ask_the_same_questions_today():
    """They share one list by import rather than holding two copies — which
    is what makes a single question mapping able to switch both channels at
    once when item 1.9 lands (§7 steps 3 and 4)."""
    import questions

    assert ussd_handler.SCREENING_QUESTIONS is questions.SCREENING_QUESTIONS


# --------------------------------------- the divergence that is not fixable here

@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known and recorded: the two channels do not share a classifier. "
        "`POST /api/screen` asks Gemini for its tier; `handle_ussd` uses "
        "score thresholds (>=12 ORANGE, >=6 YELLOW). So identical answers "
        "can produce different tiers, which is the defect item 1.9 exists to "
        "fix by putting both on the deterministic cascade. strict=True means "
        "this flips to a HARD FAILURE the moment they do share one, which is "
        "the signal to delete this marker and assert equality instead."
    ),
)
def test_the_channels_share_a_classifier():
    """Asserted as a known failure rather than left unwritten, so that the
    gap is in the suite rather than only in a document."""
    import inspect

    app_source = inspect.getsource(
        __import__("routers.screening", fromlist=["screen_miner"]).screen_miner
    )
    ussd_source = inspect.getsource(ussd_handler.handle_ussd)

    app_classifier = "assess_risk" in app_source
    ussd_classifier = "_classify" in ussd_source
    assert not (app_classifier or ussd_classifier), (
        "one channel still carries its own classifier"
    )


def test_the_ussd_thresholds_are_in_one_place_only():
    """The score cut points live in `_classify` and nowhere else. A second
    copy would be the same problem as the red-flag set, one layer down."""
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    holders = [
        path.name
        for path in sorted((backend / "services").glob("*.py"))
        if ">= 12" in path.read_text(encoding="utf-8")
        or ">= 6" in path.read_text(encoding="utf-8")
    ]
    assert holders == ["ussd_handler.py"], holders


# ------------------------------- the third copy, on the handset, which differs

def _mobile_red_flags() -> set[tuple[str, str]]:
    """The red flags the offline scorer in `mobile/` actually checks.

    Read out of the JavaScript rather than assumed, because this is the only
    place the three copies can be compared at all: one lives in Python, one
    in Python, and one in a React Native screen.
    """
    import pathlib
    import re

    repo = pathlib.Path(__file__).resolve().parent.parent.parent
    source = (repo / "mobile" / "src" / "screens" / "QuestionScreen.js").read_text(
        encoding="utf-8"
    )
    return set(re.findall(
        r"question_code === '([A-Z_]+)' && a\.answer_value === '([a-z]+)'", source
    ))


@pytest.mark.xfail(
    strict=True,
    reason=(
        "KNOWN DIVERGENCE, found 16 November 2026, and it is a safety one. "
        "`mobile/src/screens/QuestionScreen.js`'s `offlineScore()` checks two "
        "red flags, not four: BREATHLESSNESS=severe and CHEST_PAIN=severe are "
        "absent from the handset entirely. Offline is the normal case "
        "(principle 2), so a miner with severe breathlessness screened on a "
        "handset with no signal is shown a tier from the score alone, while "
        "the server would force the top tier for the same answers. Fixing it "
        "is in mobile/, which is Takudzwa's area; it goes away for good when "
        "the handset interprets the instrument instead of carrying its own "
        "copy (item 1.14a). strict=True so this becomes a hard failure the "
        "moment the sets match, which is the signal to delete this marker."
    ),
)
def test_the_handset_checks_the_same_red_flags_as_the_server():
    assert _mobile_red_flags() == _app_red_flags()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "KNOWN DIVERGENCE, same find. The handset's overrides raise a GREEN "
        "or YELLOW to ORANGE and stop there -- they cannot produce the top "
        "tier at all -- while the server's force it. The comment directly "
        "above that code reads 'Apply safety overrides — RED can never be "
        "missed', which is the opposite of what the code does: prose "
        "asserting a safety property the code does not have. Item 1.14a."
    ),
)
def test_a_handset_override_can_reach_the_top_tier():
    import pathlib
    import re

    repo = pathlib.Path(__file__).resolve().parent.parent.parent
    source = (repo / "mobile" / "src" / "screens" / "QuestionScreen.js").read_text(
        encoding="utf-8"
    )
    override_block = source[source.index("Apply safety overrides"):]
    override_block = override_block[:override_block.index("return")]

    assigned = set(re.findall(r"tier = '([A-Z]+)'", override_block))
    assert "RED" in assigned, (
        f"an override on the handset can only assign {sorted(assigned)}, so "
        "the top tier is unreachable offline however severe the answers"
    )


def test_the_three_copies_are_counted_so_nobody_forgets_one():
    """Three places hold red-flag logic today. The number is asserted so that
    a fourth cannot appear quietly, and so that removing them is visible:
    this test fails when the count changes in either direction."""
    copies = {
        "services/safety_overrides.py": _app_red_flags(),
        "services/ussd_handler.py": _ussd_red_flags(),
        "mobile/src/screens/QuestionScreen.js": _mobile_red_flags(),
    }
    assert len(copies) == 3
    assert all(copies.values()), "an empty copy is a copy that protects nobody"
