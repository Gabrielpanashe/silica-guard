"""The instrument validator must actually reject broken specifications.

`scripts/validate_instrument.py` is a CI gate over `clinical/`, and a gate
that cannot fail is worse than no gate: it converts "unchecked" into
"checked" in everyone's head while changing nothing. So each case below
takes the synthetic example, breaks it one specific way, and asserts the
validator both fails and says why.

The fixture is `clinical/examples/TEST-INSTRUMENT.yaml`, whose question codes
are T1-T3 and mean nothing. No clinical content is invented here or there --
instrument version one is the Clinical Lead's deliverable (Master Reference
v1.0 Section 12.5).
"""

import copy
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent.parent
EXAMPLE = REPO / "clinical" / "examples" / "TEST-INSTRUMENT.yaml"
VALIDATOR = REPO / "backend" / "scripts" / "validate_instrument.py"


def _run(path: Path):
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def example():
    return yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))


def _write(tmp_path: Path, doc: dict, name: str) -> Path:
    p = tmp_path / f"{name}.yaml"
    p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return p


def test_the_example_itself_is_valid():
    """If this fails, every negative case below is meaningless."""
    result = _run(EXAMPLE)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_example_is_not_loadable_as_an_instrument(example):
    """status: example is what keeps a format illustration out of a database.
    A plausible invented question set that could be loaded is the most
    dangerous thing clinical/ could contain."""
    assert example["status"] == "example"


def test_example_exercises_every_predicate_node(example):
    """The rules engine's tests read this file. A grammar node that stops
    being represented here stops being covered."""
    blob = yaml.safe_dump(example)
    for node in ("all:", "any:", "not:", "answer:", "gte:", "lte:", "count:", "unknown:"):
        assert node in blob, f"example no longer exercises {node}"


# (name, mutation, substring the validator must print)
CASES = [
    (
        "rule_references_unknown_question",
        lambda d: d["tier_rules"][1].update({"predicate": {"answer": "T9", "in": ["some"]}}),
        "unknown question T9",
    ),
    (
        "score_names_a_value_the_question_does_not_offer",
        lambda d: d["questions"][0]["scores"].append(
            {"condition": "condition_a", "value": "nope", "score": 1}
        ),
        "does not offer",
    ),
    (
        "rule_tests_a_value_the_question_does_not_offer",
        lambda d: d["tier_rules"][3].update({"predicate": {"answer": "T1", "in": ["enormous"]}}),
        "does not offer",
    ),
    (
        "condition_has_no_green_rule",
        lambda d: d.__setitem__(
            "tier_rules",
            [r for r in d["tier_rules"]
             if not (r["condition"] == "condition_a" and r["tier"] == "GREEN")],
        ),
        "no GREEN rule",
    ),
    (
        "intervals_missing_a_tier",
        lambda d: d.__setitem__(
            "intervals",
            [i for i in d["intervals"]
             if not (i["condition"] == "condition_b" and i["tier"] == "RED")],
        ),
        "intervals missing",
    ),
    (
        "referring_tier_without_a_window",
        lambda d: [i.update({"referral_window_hours": None})
                   for i in d["intervals"] if i["tier"] == "ORANGE"],
        "needs referral_window_hours",
    ),
    (
        "approved_without_an_approver",
        lambda d: d.__setitem__("status", "approved"),
        "approved_by",
    ),
    (
        "score_names_an_undeclared_condition",
        lambda d: d["questions"][0]["scores"].append(
            {"condition": "condition_zzz", "value": "none", "score": 0}
        ),
        "undeclared condition",
    ),
    (
        "malformed_predicate_node",
        lambda d: d["tier_rules"][1].update({"predicate": {"answer": "T1"}}),
        "schema",
    ),
    (
        "question_in_an_undeclared_block",
        lambda d: d["questions"][0].update({"block": "no_such_block"}),
        "not declared",
    ),
    (
        "duplicate_question_code",
        lambda d: d["questions"].append(copy.deepcopy(d["questions"][0])),
        "more than once",
    ),
    (
        "integer_banded_question_given_options",
        lambda d: d["questions"][1].update(
            {"options": [{"value": "a", "label_message_code": "test.a"},
                         {"value": "b", "label_message_code": "test.b"}]}
        ),
        "must use bands",
    ),
    (
        "bands_out_of_order",
        lambda d: d["questions"][1].__setitem__(
            "bands", list(reversed(d["questions"][1]["bands"]))
        ),
        "ascending order",
    ),
    (
        "branching_references_itself",
        lambda d: d["questions"][0].__setitem__("branching", {"answer": "T1", "in": ["some"]}),
        "references the question itself",
    ),
]


@pytest.mark.parametrize("name,mutate,expected", CASES, ids=[c[0] for c in CASES])
def test_validator_rejects(tmp_path, example, name, mutate, expected):
    doc = copy.deepcopy(example)
    mutate(doc)
    result = _run(_write(tmp_path, doc, name))
    assert result.returncode != 0, (
        f"{name}: validator accepted a broken instrument\n{result.stdout}"
    )
    assert expected.lower() in result.stdout.lower(), (
        f"{name}: expected {expected!r} in output, got:\n{result.stdout}"
    )


def test_validator_accepts_a_file_outside_the_repository(tmp_path, example):
    """The validator takes an explicit path, and tests pass it files from a
    temporary directory. Resolving a repo-relative label must not crash on a
    path outside the repository -- it did, and every negative case above was
    silently passing on a traceback until it was fixed."""
    result = _run(_write(tmp_path, copy.deepcopy(example), "outside"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in (result.stdout + result.stderr)
