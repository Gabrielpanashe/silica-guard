"""Validate instrument regression fixtures.

Master Reference v1.0 §11.7. Run by CI on every pull request, and locally
before opening one:

    cd backend
    ./venv/Scripts/python.exe scripts/validate_fixtures.py

What it enforces, and why each is a build failure rather than a review
comment:

  Shape            `clinical/fixtures.schema.json`. A malformed expectation
                   silently asserts nothing, which is worse than no fixture
                   at all because it looks like coverage.

  Pairing          Every fixture file names the instrument and version beside
                   it. A fixture pointing at the wrong version regresses the
                   wrong behaviour.

  Known codes      Every question code and answer value in a profile exists
                   in the instrument, and every condition in an expectation is
                   one the instrument assesses. A typo in a question code
                   otherwise produces an unanswered question and an
                   "incomplete" result that happens to pass.

  Approval         Fixtures that gate a release carry the Clinical Lead's name
                   and a date, because an expected tier is a clinical
                   assertion. `status: example` is exempt and gates nothing.

The behavioural half -- that each profile actually produces its expected tier
-- is `tests/test_instrument_regression.py`. This script checks the file is
sayable; that test checks it is true.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
CLINICAL = REPO / "clinical"
SCHEMA_PATH = CLINICAL / "fixtures.schema.json"
TIERS = ("GREEN", "YELLOW", "ORANGE", "RED")


def _label(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def _dates_to_strings(value):
    """YAML parses an unquoted date as a `datetime.date`; the schema's
    `format: date` describes a string. Same normalisation as the other two
    validators, and for the same reason: the YAML date type is a feature and
    the schema's spelling of it is an implementation detail."""
    if isinstance(value, dict):
        return {k: _dates_to_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_dates_to_strings(v) for v in value]
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def _answer_values(question: dict) -> set[str]:
    if question.get("response_type") == "integer_banded":
        return {b["value"] for b in question.get("bands") or []}
    return {o["value"] for o in question.get("options") or []}


def validate_file(fixtures_path: Path, schema: dict | None) -> list[str]:
    problems: list[str] = []
    where = _label(fixtures_path)

    try:
        doc = _dates_to_strings(yaml.safe_load(fixtures_path.read_text(encoding="utf-8")))
    except yaml.YAMLError as exc:
        return [f"{where}: not valid YAML: {exc}"]
    if not isinstance(doc, dict):
        return [f"{where}: expected a mapping at the top level"]

    if schema is not None:
        import jsonschema

        for error in sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(doc),
            key=lambda e: list(e.path),
        ):
            path = "/".join(str(p) for p in error.path) or "(root)"
            problems.append(f"{where}: schema: {path}: {error.message}")
        if problems:
            # Later checks assume the shape; reporting both sets of errors at
            # once produces noise that hides the real one.
            return problems

    # ── the instrument beside it ─────────────────────────────────────────
    instrument_path = fixtures_path.parent / fixtures_path.name.replace(
        ".fixtures.yaml", ".yaml"
    )
    if not instrument_path.exists():
        return problems + [
            f"{where}: no instrument file beside it "
            f"(expected {instrument_path.name})"
        ]

    instrument = _dates_to_strings(
        yaml.safe_load(instrument_path.read_text(encoding="utf-8"))
    )
    if doc.get("instrument") != instrument.get("code"):
        problems.append(
            f"{where}: names instrument {doc.get('instrument')!r} but sits "
            f"beside {instrument.get('code')!r}. A fixture file pointing at "
            "the wrong instrument regresses the wrong behaviour."
        )
    if doc.get("version") != instrument.get("version"):
        problems.append(
            f"{where}: names version {doc.get('version')} but sits beside "
            f"version {instrument.get('version')}. Fixtures are "
            "version-specific: a threshold moving is a new version, and the "
            "old fixtures describe the old version's behaviour."
        )

    # ── approval, for anything that gates a release ──────────────────────
    if doc.get("status") != "example":
        for field in ("approved_by", "approved_at"):
            if not doc.get(field):
                problems.append(
                    f"{where}: no {field}. An expected tier is a clinical "
                    "assertion, so fixtures that gate a release carry the "
                    "Clinical Lead's recorded approval (§11.4)."
                )

    # ── codes and values must exist ──────────────────────────────────────
    questions = {q["code"]: q for q in instrument.get("questions") or []}
    conditions = set(instrument.get("conditions") or [])
    safety_codes = {r["code"] for r in instrument.get("safety_rules") or []}

    for index, profile in enumerate(doc.get("profiles") or []):
        name = profile.get("name", f"profile {index}")
        for group in ("answers", "previous_answers"):
            for code, value in (profile.get(group) or {}).items():
                if code not in questions:
                    problems.append(
                        f"{where}: {name!r}: {group} names question {code!r}, "
                        "which the instrument does not define. A typo here "
                        "produces an unanswered question and an 'incomplete' "
                        "result that happens to pass."
                    )
                    continue
                allowed = _answer_values(questions[code])
                if value not in allowed:
                    problems.append(
                        f"{where}: {name!r}: {code}={value!r} is not one of "
                        f"{sorted(allowed)}"
                    )

        expect = profile.get("expect") or {}
        if expect.get("incomplete") and len(expect) > 1:
            problems.append(
                f"{where}: {name!r}: `incomplete` is mutually exclusive with "
                "every other expectation — a profile that produces no tier "
                "cannot also assert one."
            )
        for group in ("tiers", "scored_tiers", "scores"):
            for condition in (expect.get(group) or {}):
                if condition not in conditions:
                    problems.append(
                        f"{where}: {name!r}: {group} names condition "
                        f"{condition!r}, which the instrument does not assess"
                    )
        for code in expect.get("overrides") or []:
            if code not in safety_codes:
                problems.append(
                    f"{where}: {name!r}: expects safety rule {code!r}, which "
                    f"the instrument does not define. Known: {sorted(safety_codes)}"
                )
        if not expect:
            problems.append(
                f"{where}: {name!r}: no expectations at all, so it asserts "
                "nothing while looking like coverage."
            )

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)

    paths = args.paths or sorted(CLINICAL.rglob("*.fixtures.yaml"))
    if not paths:
        print(
            "No fixture files found. That is expected until instrument "
            "version one lands (item 1.4) — the synthetic example lives in "
            "clinical/examples/."
        )
        return 0

    schema = None
    try:
        import jsonschema  # noqa: F401

        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except ImportError:
        print(
            "warning: jsonschema not installed; shape checks skipped "
            "(pip install -r requirements-dev.txt)",
            file=sys.stderr,
        )

    problems: list[str] = []
    for path in paths:
        problems.extend(validate_file(path, schema))

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print(f"\n{len(problems)} problem(s) in: "
              f"{', '.join(p.name for p in paths)}", file=sys.stderr)
        return 1

    print(f"OK: {', '.join(p.name for p in paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
