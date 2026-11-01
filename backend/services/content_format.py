"""The format rules for patient-facing content: languages, channel budgets,
the GSM 03.38 alphabet, and the placeholder syntax.

Master Reference v1.0 §8.4 and the channel budgets in §13.1-13.2.

**One definition, two consumers.** `scripts/validate_content.py` applies these
rules in CI, before a string is merged; `services/content_store.py` applies
them again at load time, before a string enters the database. Both import from
here, so a message that passes the gate cannot fail the loader for a different
reason -- two implementations of septet arithmetic that disagree would be
worse than having only one of the checks.

This module has **no dependencies at all** -- not SQLAlchemy, not PyYAML, not
`jsonschema` -- which is the reason it exists rather than the constants living
in the validator script where they started. The store is request-path code and
runs in production; the validator is a development tool whose YAML and JSON
Schema dependencies are deliberately dev-only (`requirements-dev.txt`). A
runtime service importing a CLI script would have put those dependencies on
the production boot path, and the import direction was backwards besides: the
script is the tool, the rules are the thing.
"""

from __future__ import annotations

#: The three languages, from the start. §8.4: Ndebele is not optional in this
#: geography -- the Midlands is genuinely mixed and one of the country's only
#: two dedicated occupational health clinics is at Gwanda. Adding a third
#: language to an architecture that assumes two is painful; adding it to one
#: designed for many is data entry.
LANGUAGES = ("en", "sn", "nd")
LANGUAGE_NAMES = {"en": "English", "sn": "Shona", "nd": "Ndebele"}

#: GSM 03.38 basic character set. A message consisting only of these encodes as
#: seven-bit septets: 160 per segment.
GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅå_ÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
    "¿abcdefghijklmnopqrstuvwxyzäöñüà"
    "ΔΦΓΛΩΠΨΣΘΞ"
)
#: Extension set: still seven-bit, but each costs TWO septets because it is
#: sent as an escape plus the character.
GSM7_EXTENSION = set("^{}\\[~]|€")

#: Per-channel budget in septets. See content/README.md for why each is what
#: it is: `sms` is one segment and cost is per segment; `ussd` is one page
#: including the options and navigation; `app` and `clinician` are readability
#: ceilings rather than transport limits.
CHANNEL_BUDGET = {
    "sms": 160,
    "ussd": 182,
    "app": 480,
    "clinician": 480,
}

#: Characters people paste from word processors that look identical to an
#: allowed character but are not. Named explicitly so an error can suggest the
#: fix instead of only reporting a code point.
LOOKALIKES = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", " ": " ",
    "′": "'", "″": '"', "−": "-",
}


def septets(text: str) -> int:
    """Length in GSM-7 septets, or -1 if the text cannot be encoded as GSM-7.

    The -1 is not a length and must not be compared against a budget as one.
    A single character outside the alphabet forces the whole message into
    sixteen-bit encoding at 70 characters per segment instead of 160, so the
    honest answer is "this does not encode" rather than a count.
    """
    total = 0
    for ch in text:
        if ch in GSM7_BASIC:
            total += 1
        elif ch in GSM7_EXTENSION:
            total += 2
        else:
            return -1
    return total


def non_gsm7(text: str) -> list[tuple[int, str]]:
    """(index, character) for every character outside GSM-7."""
    return [
        (i, ch) for i, ch in enumerate(text)
        if ch not in GSM7_BASIC and ch not in GSM7_EXTENSION
    ]


def placeholders_in(text: str) -> set[str]:
    """Names between braces.

    Shared so that the CI gate and the loader cannot disagree about what a
    placeholder is -- a declared `{name}` that one of them does not recognise
    would pass review and then send literal braces to a worker.
    """
    out: set[str] = set()
    buf: list[str] = []
    inside = False
    for ch in text:
        if ch == "{":
            inside, buf = True, []
        elif ch == "}" and inside:
            out.add("".join(buf))
            inside = False
        elif inside:
            buf.append(ch)
    return out
