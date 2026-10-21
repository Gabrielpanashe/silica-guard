"""Validate patient-facing content files.

Master Reference v1.0 §8.4 (language, and the character-set trap) and the
channel budgets in §13.1-13.2. Run by CI on every pull request that touches
`content/`, and locally before opening one:

    cd backend
    ./venv/Scripts/python.exe scripts/validate_content.py
    ./venv/Scripts/python.exe scripts/validate_content.py --verbose

What it enforces, and why each one is a build failure rather than a review
comment:

  GSM 03.38      One character outside the seven-bit alphabet forces the whole
                 message into sixteen-bit encoding, dropping a segment from 160
                 characters to 70 and permanently multiplying the cost of every
                 send. One curly apostrophe pasted out of a word processor does
                 it. The failure is invisible in review and silent at runtime.

  Channel budget A USSD page holds roughly 182 characters including the options
                 and navigation; an SMS segment holds 160. A string that does
                 not fit is rewritten, never truncated at runtime -- so it has
                 to fail here. Checked in every language, because the local
                 language version is usually the longest.

  Languages      English, Shona and Ndebele before a message may be approved.

  Placeholders   Every language must use exactly the declared set. A
                 placeholder present in English and missing in Shona sends a
                 broken message to the people least able to query it.

Exit 0 means every file is valid. Non-zero prints every problem rather than
stopping at the first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
CONTENT = REPO / "content"
SCHEMA_PATH = CONTENT / "schema.json"

LANGUAGES = ("en", "sn", "nd")
LANGUAGE_NAMES = {"en": "English", "sn": "Shona", "nd": "Ndebele"}

# GSM 03.38 basic character set. A message consisting only of these encodes as
# seven-bit septets: 160 per segment.
GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅå_ÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
    "¿abcdefghijklmnopqrstuvwxyzäöñüà"
    "ΔΦΓΛΩΠΨΣΘΞ"
)
# Extension set: still seven-bit, but each costs TWO septets because it is sent
# as an escape plus the character.
GSM7_EXTENSION = set("^{}\\[~]|€")

# Per-channel budget in septets. See content/README.md.
CHANNEL_BUDGET = {
    "sms": 160,
    "ussd": 182,
    "app": 480,
    "clinician": 480,
}

# Characters people paste from word processors that look identical to an
# allowed character but are not. Named explicitly so the error can suggest the
# fix instead of only reporting a code point.
LOOKALIKES = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", " ": " ",
    "′": "'", "″": '"', "−": "-",
}


def septets(text: str) -> int:
    """Length in GSM-7 septets, or -1 if the text cannot be encoded as GSM-7."""
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


def _placeholders(text: str) -> set[str]:
    out, buf, inside = set(), [], False
    for ch in text:
        if ch == "{":
            inside, buf = True, []
        elif ch == "}" and inside:
            out.add("".join(buf))
            inside = False
        elif inside:
            buf.append(ch)
    return out


def _label(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def validate_file(path: Path, schema: dict | None, verbose: bool = False) -> list[str]:
    problems: list[str] = []
    rel = _label(path)

    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"{rel}: not valid YAML — {exc}"]
    if not isinstance(doc, dict):
        return [f"{rel}: top level must be a mapping"]

    if schema is not None:
        try:
            import jsonschema
        except ImportError:
            pass
        else:
            validator = jsonschema.Draft202012Validator(schema)
            for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.path)):
                loc = "/".join(str(p) for p in err.path) or "(root)"
                problems.append(f"{rel}: schema: {loc}: {err.message}")

    seen: set[str] = set()
    for message in doc.get("messages") or []:
        if not isinstance(message, dict):
            continue
        code = message.get("code", "(no code)")
        where = f"{rel} [{code}]"

        if code in seen:
            problems.append(f"{where}: duplicate message code in this file")
        seen.add(code)

        channel = message.get("channel")
        budget = message.get("max_len_override") or CHANNEL_BUDGET.get(channel, 0)
        declared = set(message.get("placeholders") or [])
        texts = message.get("text") or {}

        for lang in LANGUAGES:
            text = texts.get(lang)
            if text is None:
                continue
            name = LANGUAGE_NAMES[lang]

            bad = non_gsm7(text)
            if bad:
                detail = ", ".join(
                    f"{ch!r} at {i}"
                    + (f" (use {LOOKALIKES[ch]!r})" if ch in LOOKALIKES else f" (U+{ord(ch):04X})")
                    for i, ch in bad[:5]
                )
                more = f", and {len(bad) - 5} more" if len(bad) > 5 else ""
                problems.append(
                    f"{where} {name}: not GSM-7 — {detail}{more}. "
                    f"One such character sends the whole message as 16-bit at 70 characters "
                    f"per segment instead of 160."
                )
                continue  # a length check in septets is meaningless until it encodes

            length = septets(text)
            if budget and length > budget:
                problems.append(
                    f"{where} {name}: {length} septets over a {budget} budget for channel "
                    f"{channel!r}. Rewrite it; a string is never truncated at runtime."
                )
            elif verbose:
                print(f"  {code:<40} {name:<8} {length:>4}/{budget} septets")

            # Placeholder parity is checked from `review` onward, not on a
            # draft. A message is authored one language at a time over weeks
            # (English Week 8, Shona and Ndebele Week 12), so a draft whose
            # local-language entry is still a marker must not fail the build —
            # but a message must never reach approval with a placeholder
            # present in one language and missing in another, because that
            # sends broken text to the people least able to query it.
            used = _placeholders(text)
            if message.get("status") in ("review", "approved") and used != declared:
                missing = sorted(declared - used)
                extra = sorted(used - declared)
                bits = []
                if missing:
                    bits.append("missing " + ", ".join("{" + m + "}" for m in missing))
                if extra:
                    bits.append("undeclared " + ", ".join("{" + e + "}" for e in extra))
                problems.append(f"{where} {name}: placeholders {'; '.join(bits)}")

        if message.get("status") == "approved":
            for lang in LANGUAGES:
                if not (texts.get(lang) or "").strip():
                    problems.append(
                        f"{where}: approved but has no {LANGUAGE_NAMES[lang]} text. "
                        f"All three languages are required before approval (§8.4)."
                    )

    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paths", nargs="*", help="Files to check. Default: everything under content/.")
    parser.add_argument("--verbose", action="store_true", help="Print per-message septet counts.")
    args = parser.parse_args(argv)

    schema = None
    if SCHEMA_PATH.exists():
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    else:
        print(f"warning: {SCHEMA_PATH} not found; shape checks skipped", file=sys.stderr)

    try:
        import jsonschema  # noqa: F401
    except ImportError:
        print("warning: jsonschema not installed; shape checks skipped "
              "(pip install -r requirements-dev.txt)", file=sys.stderr)

    if args.paths:
        paths = [Path(p).resolve() for p in args.paths]
    else:
        paths = sorted((CONTENT / "messages").rglob("*.yaml")) if (CONTENT / "messages").exists() else []

    if not paths:
        print("No content files found. content/messages/ holds the example only until the "
              "Clinical Lead delivers the strings (Master Reference 12.5, ROADMAP.md weeks 8 and 12).")
        return 0

    problems: list[str] = []
    for path in paths:
        problems.extend(validate_file(path, schema, verbose=args.verbose))

    for p in problems:
        print(p)

    checked = ", ".join(p.name for p in paths)
    if problems:
        print(f"\n{len(problems)} problem(s) in: {checked}")
        return 1
    print(f"OK: {checked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
