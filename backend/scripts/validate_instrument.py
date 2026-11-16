"""Validate clinical instrument specification files.

Master Reference v1.0 §8.3 (instrument and rules as versioned data), §12
(the instrument) and Appendix A (the template). Run by CI on every pull
request that touches `clinical/`, and locally before opening one:

    cd backend
    ./venv/Scripts/python.exe scripts/validate_instrument.py
    ./venv/Scripts/python.exe scripts/validate_instrument.py ../clinical/examples/TEST-INSTRUMENT.yaml

Two layers. The JSON Schema (`clinical/instrument.schema.json`) checks shape:
required fields, patterns, the closed predicate grammar. This script checks
the things a schema cannot express — that every code a rule references exists,
that scores name real answer values, that an approved version is internally
complete, and that a safety rule cannot lower a tier.

Exit code 0 means every file is valid. Non-zero prints every problem found
rather than stopping at the first, because a clinician fixing a specification
should see the whole list once.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
CLINICAL = REPO / "clinical"
SCHEMA_PATH = CLINICAL / "instrument.schema.json"

# Tier order, lowest first. A safety rule may raise a tier and never lower
# one (§4.3, §9.1), and this is the ordering that claim is checked against.
TIER_ORDER = ["GREEN", "YELLOW", "ORANGE", "RED"]

# The channels that exist. Read from the schema's own enum below when it
# loads, so this literal is only the fallback for a run without the schema
# file -- the authority is `clinical/instrument.schema.json`, and the runtime
# copy is `services.rules_engine.CHANNELS`. This script imports nothing from
# `backend/` on purpose: it validates `clinical/` and must run wherever those
# files are, with yaml and jsonschema and nothing else.
CHANNELS = ["app", "ussd"]


def _schema_channels(schema: dict | None) -> list[str]:
    """The `channels` enum from the schema, or the fallback above."""
    try:
        enum = schema["$defs"]["question"]["properties"]["channels"]["items"]["enum"]
        return list(enum) if enum else list(CHANNELS)
    except (TypeError, KeyError):
        return list(CHANNELS)


def _fail(problems: list[str], where: str, message: str) -> None:
    problems.append(f"{where}: {message}")


def _walk_predicate(node, path: str):
    """Yield (path, node) for every predicate node, depth first."""
    yield path, node
    if not isinstance(node, dict):
        return
    for key in ("all", "any"):
        for i, child in enumerate(node.get(key) or []):
            yield from _walk_predicate(child, f"{path}.{key}[{i}]")
    if "not" in node:
        yield from _walk_predicate(node["not"], f"{path}.not")


def _referenced_codes(predicate, path: str):
    """Question codes and condition codes a predicate depends on."""
    questions: set[str] = set()
    conditions: set[str] = set()
    for _, node in _walk_predicate(predicate, path):
        if not isinstance(node, dict):
            continue
        if "answer" in node:
            questions.add(node["answer"])
        if "unknown" in node:
            questions.add(node["unknown"])
        if "score" in node and isinstance(node["score"], str):
            conditions.add(node["score"])
        if "count" in node and isinstance(node["count"], dict):
            questions.update(node["count"].get("codes") or [])
    return questions, conditions


def _answer_values(question: dict) -> set[str]:
    if question.get("response_type") == "integer_banded":
        return {b["value"] for b in question.get("bands") or []}
    return {o["value"] for o in question.get("options") or []}


def _label(path: Path) -> str:
    """Repo-relative path where possible, absolute otherwise. A file outside
    the repository is a normal case: the test suite validates deliberately
    broken copies from a temporary directory."""
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def _dates_to_strings(value):
    """YAML parses an unquoted `2026-11-01` as a `datetime.date`; JSON Schema's
    `format: date` describes a *string*. Normalising here rather than
    demanding quotes in the file is the right way round: the YAML date type is
    a feature, the schema's spelling of it is an implementation detail, and
    the Clinical Lead should not have to know which.

    Found by rehearsing the full load mechanism end to end -- it would
    otherwise have surfaced as a confusing schema error on the first real
    instrument submission.
    """
    if isinstance(value, dict):
        return {k: _dates_to_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_dates_to_strings(v) for v in value]
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def validate_file(path: Path, schema: dict | None) -> list[str]:
    problems: list[str] = []
    rel = _label(path)

    try:
        doc = _dates_to_strings(yaml.safe_load(path.read_text(encoding="utf-8")))
    except yaml.YAMLError as exc:
        return [f"{rel}: not valid YAML — {exc}"]
    if not isinstance(doc, dict):
        return [f"{rel}: top level must be a mapping"]

    # ---- layer one: shape, via JSON Schema -------------------------------
    if schema is not None:
        try:
            import jsonschema
        except ImportError:  # pragma: no cover - reported once by main()
            pass
        else:
            validator = jsonschema.Draft202012Validator(schema)
            for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.path)):
                loc = "/".join(str(p) for p in err.path) or "(root)"
                _fail(problems, rel, f"schema: {loc}: {err.message}")

    # ---- layer two: internal consistency ---------------------------------
    questions = {q["code"]: q for q in doc.get("questions") or [] if isinstance(q, dict)}
    conditions = set(doc.get("conditions") or [])
    block_codes = {b["code"] for b in doc.get("blocks") or [] if isinstance(b, dict)}

    dupes = [c for c in (q.get("code") for q in doc.get("questions") or []) if c and
             [x.get("code") for x in doc["questions"]].count(c) > 1]
    for code in sorted(set(dupes)):
        _fail(problems, rel, f"question code {code} appears more than once")

    for code, q in questions.items():
        where = f"{rel} question {code}"
        if q.get("block") not in block_codes:
            _fail(problems, rel, f"question {code} is in block {q.get('block')!r}, which is not declared")

        values = _answer_values(q)
        rtype = q.get("response_type")
        if rtype == "integer_banded":
            if q.get("options"):
                _fail(problems, rel, f"question {code} is integer_banded and must use bands, not options")
            bands = q.get("bands") or []
            froms = [b.get("from") for b in bands]
            if froms != sorted(froms):
                _fail(problems, rel, f"question {code} bands must be in ascending order of 'from'")
        elif not q.get("options"):
            _fail(problems, rel, f"question {code} has response_type {rtype} and needs options")
        if q.get("bands") and rtype != "integer_banded":
            _fail(problems, rel, f"question {code} has bands but response_type is {rtype}")

        # Scores must name a declared condition and a real answer value.
        for s in q.get("scores") or []:
            if s.get("condition") not in conditions:
                _fail(problems, where, f"score names undeclared condition {s.get('condition')!r}")
            if s.get("value") not in values:
                _fail(problems, where, f"score names answer value {s.get('value')!r}, which this question does not offer")

        # An explicit unknown option is what makes the `unknown` predicate
        # meaningful (§12.2 item 10).
        if rtype in ("single_select", "multi_select"):
            unknowns = [o for o in q.get("options") or [] if o.get("is_unknown")]
            if len(unknowns) > 1:
                _fail(problems, where, "more than one option is marked is_unknown")

        if q.get("branching"):
            qs, cs = _referenced_codes(q["branching"], f"{where} branching")
            for ref in sorted(qs):
                if ref not in questions:
                    _fail(problems, where, f"branching references unknown question {ref}")
                elif ref == code:
                    _fail(problems, where, "branching references the question itself")
            for ref in sorted(cs):
                if ref not in conditions:
                    _fail(problems, where, f"branching references undeclared condition {ref}")

    # Rules may only reference codes that exist, and every answer value a rule
    # tests must be one the question actually offers — a typo here silently
    # produces a rule that can never fire.
    for kind in ("tier_rules", "safety_rules"):
        for i, rule in enumerate(doc.get(kind) or []):
            if not isinstance(rule, dict) or "predicate" not in rule:
                continue
            ident = rule.get("code") or f"{rule.get('condition', 'all')}/{rule.get('tier') or rule.get('forces_tier')}"
            where = f"{rel} {kind}[{i}] ({ident})"
            qs, cs = _referenced_codes(rule["predicate"], where)
            for ref in sorted(qs):
                if ref not in questions:
                    _fail(problems, where, f"references unknown question {ref}")
            for ref in sorted(cs):
                if ref not in conditions:
                    _fail(problems, where, f"references undeclared condition {ref}")
            if rule.get("condition") and rule["condition"] not in conditions:
                _fail(problems, where, f"names undeclared condition {rule['condition']!r}")
            for _, node in _walk_predicate(rule["predicate"], where):
                if isinstance(node, dict) and "answer" in node and node["answer"] in questions:
                    offered = _answer_values(questions[node["answer"]])
                    for v in node.get("in") or []:
                        if v not in offered:
                            _fail(problems, where, f"tests {node['answer']} == {v!r}, which that question does not offer")

    # ---- channel equivalence, at authoring time --------------------------
    # A rule may only reference a question every channel asks. Both failure
    # modes are silent and they are opposite, which is why the message names
    # which one the author has:
    #
    #   `unknown: Q` on a question this channel never asks fires on EVERY
    #   session on that channel, because the engine derives `unknown` from
    #   "no answer recorded" and a question that was never asked has none.
    #   Direction-safe -- it raises a tier -- and operationally useless: every
    #   USSD screening would come out ORANGE and nobody would notice until a
    #   field pilot.
    #
    #   `answer`/`score`/`count` on one this channel never asks can never
    #   match on that channel, so the rule is quietly absent there and the
    #   tier is under-reported. That one is NOT direction-safe.
    #
    # Either way the two channels classify the same worker differently, which
    # principle 4 forbids. The fix is the Clinical Lead's: widen the
    # question's `channels`, or drop the rule. The grammar has no way to scope
    # a rule to a channel, deliberately -- a channel-specific clinical rule is
    # a second instrument wearing one version number.
    all_channels = set(_schema_channels(schema))
    channel_limited = {
        code: set(q["channels"]) for code, q in questions.items()
        if q.get("channels") is not None
    }
    if channel_limited:
        for kind in ("tier_rules", "safety_rules"):
            for i, rule in enumerate(doc.get(kind) or []):
                if not isinstance(rule, dict) or "predicate" not in rule:
                    continue
                ident = rule.get("code") or f"{rule.get('condition', 'all')}/{rule.get('tier') or rule.get('forces_tier')}"
                where = f"{rel} {kind}[{i}] ({ident})"
                for _, node in _walk_predicate(rule["predicate"], where):
                    if not isinstance(node, dict):
                        continue
                    for key in ("unknown", "answer"):
                        ref = node.get(key)
                        if not isinstance(ref, str) or ref not in channel_limited:
                            continue
                        absent = sorted(all_channels - channel_limited[ref])
                        if not absent:
                            continue
                        consequence = (
                            f"so this rule fires on EVERY {'/'.join(absent)} "
                            f"session, because a question that was never asked "
                            f"has no answer"
                            if key == "unknown" else
                            f"so this rule can never match on "
                            f"{'/'.join(absent)} and the tier is under-reported "
                            f"there"
                        )
                        _fail(problems, where,
                              f"references question {ref}, which is not asked on "
                              f"{'/'.join(absent)} — {consequence}. Widen {ref}'s "
                              f"channels or drop the rule; the two channels must "
                              f"classify the same worker identically.")
        # The same trap one level down: a question asked on every channel whose
        # branching depends on one that is not. The branch is then unreachable
        # on that channel, so the question is silently never asked there.
        for code, q in questions.items():
            if not q.get("branching") or code in channel_limited:
                continue
            refs, _ = _referenced_codes(q["branching"], f"{rel} question {code} branching")
            for ref in sorted(refs):
                if ref not in channel_limited:
                    continue
                absent = sorted(all_channels - channel_limited[ref])
                if absent:
                    _fail(problems, f"{rel} question {code}",
                          f"is asked on every channel but its branching depends "
                          f"on {ref}, which is not asked on {'/'.join(absent)}, "
                          f"so {code} can never be reached there. Either limit "
                          f"{code} to the same channels as {ref} or branch on a "
                          f"question every channel asks.")

    # Every condition needs a reachable baseline, or a screening can produce
    # no tier at all for it.
    for cond in sorted(conditions):
        tiers = {r.get("tier") for r in doc.get("tier_rules") or [] if r.get("condition") == cond}
        if not tiers:
            _fail(problems, rel, f"condition {cond} has no tier rules")
        elif "GREEN" not in tiers:
            _fail(problems, rel, f"condition {cond} has no GREEN rule, so a low-risk screening would fall through to no tier")

    # Intervals must cover every condition and tier: a tier with no stated
    # re-screen interval or referral window is one of the gaps §12.2 names.
    declared = {(i.get("condition"), i.get("tier")) for i in doc.get("intervals") or []}
    for cond in sorted(conditions):
        for tier in TIER_ORDER:
            if (cond, tier) not in declared:
                _fail(problems, rel, f"intervals missing for condition {cond}, tier {tier}")
    for i, interval in enumerate(doc.get("intervals") or []):
        tier = interval.get("tier")
        if tier in ("ORANGE", "RED") and not interval.get("referral_window_hours"):
            _fail(problems, f"{rel} intervals[{i}]",
                  f"tier {tier} generates a referral and needs referral_window_hours")

    # An approved version is what a result row points at forever.
    if doc.get("status") == "approved":
        for q in questions.values():
            if not (q.get("citation") or "").strip():
                _fail(problems, rel, f"approved version: question {q['code']} has no citation")
        if not doc.get("limitations"):
            _fail(problems, rel, "approved version: limitations must state what the instrument does not detect")

    return problems


def main(argv: list[str]) -> int:
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

    if argv:
        paths = [Path(a).resolve() for a in argv]
    else:
        paths = sorted(CLINICAL.rglob("*.yaml")) + sorted(CLINICAL.rglob("*.yml"))
        paths = [p for p in paths if not p.name.endswith(".fixtures.yaml")]

    if not paths:
        print("No instrument files found. clinical/instruments/ is empty until the "
              "Clinical Lead delivers instrument version one (Master Reference 12.5).")
        return 0

    problems: list[str] = []
    for path in paths:
        problems.extend(validate_file(path, schema))

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
