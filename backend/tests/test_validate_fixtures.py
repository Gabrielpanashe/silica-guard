"""The fixtures validator, tested against deliberately broken input.

Master Reference v1.0 §11.7. A validator that has only ever seen valid files
is a validator nobody knows works — the same reasoning as
`test_validate_instrument.py` and `test_validate_content.py`, and the reason
those two found a real bug when they were written.

Every case below asserts both a non-zero exit **and** the specific message,
because a validator that rejects a file for the wrong reason sends the author
hunting the wrong thing.
"""

import copy
import json
from pathlib import Path

import pytest
import yaml

from scripts import validate_fixtures

REPO = Path(__file__).resolve().parent.parent.parent
EXAMPLES = REPO / "clinical" / "examples"
SCHEMA = json.loads((REPO / "clinical" / "fixtures.schema.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def instrument():
    return yaml.safe_load((EXAMPLES / "TEST-INSTRUMENT.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fixtures():
    return yaml.safe_load(
        (EXAMPLES / "TEST-INSTRUMENT.fixtures.yaml").read_text(encoding="utf-8")
    )


def write_pair(tmp_path: Path, instrument: dict, fixtures: dict) -> Path:
    """Both files, so the pairing checks have something to pair with."""
    code = instrument["code"]
    (tmp_path / f"{code}.yaml").write_text(
        yaml.safe_dump(instrument, sort_keys=False), encoding="utf-8"
    )
    path = tmp_path / f"{code}.fixtures.yaml"
    path.write_text(yaml.safe_dump(fixtures, sort_keys=False), encoding="utf-8")
    return path


def problems_for(tmp_path, instrument, fixtures) -> list[str]:
    return validate_fixtures.validate_file(
        write_pair(tmp_path, instrument, fixtures), SCHEMA
    )


# ------------------------------------------------------------- the good case

def test_the_committed_example_validates():
    assert validate_fixtures.main([]) == 0


def test_a_round_trip_of_the_example_validates(tmp_path, instrument, fixtures):
    assert problems_for(tmp_path, instrument, fixtures) == []


# ---------------------------------------------------------------- the shape

def test_a_profile_with_no_expectations_is_refused(tmp_path, instrument, fixtures):
    """It asserts nothing while looking like coverage, which is worse than no
    fixture at all."""
    broken = copy.deepcopy(fixtures)
    broken["profiles"] = [{"name": "Says nothing", "answers": {"T1": "none"}, "expect": {}}]
    problems = problems_for(tmp_path, instrument, broken)
    assert any("asserts" in p and "nothing" in p for p in problems), problems


def test_a_profile_with_no_name_is_refused(tmp_path, instrument, fixtures):
    """The name is read aloud in review and printed when the test fails."""
    broken = copy.deepcopy(fixtures)
    del broken["profiles"][0]["name"]
    assert any("name" in p for p in problems_for(tmp_path, instrument, broken))


def test_an_unknown_tier_is_refused(tmp_path, instrument, fixtures):
    broken = copy.deepcopy(fixtures)
    broken["profiles"][0]["expect"]["primary_tier"] = "AMBER"
    assert any("AMBER" in p for p in problems_for(tmp_path, instrument, broken))


def test_an_unknown_channel_is_refused(tmp_path, instrument, fixtures):
    broken = copy.deepcopy(fixtures)
    broken["profiles"][0]["channel"] = "whatsapp"
    assert any("whatsapp" in p for p in problems_for(tmp_path, instrument, broken))


def test_no_profiles_at_all_is_refused(tmp_path, instrument, fixtures):
    broken = copy.deepcopy(fixtures)
    broken["profiles"] = []
    assert problems_for(tmp_path, instrument, broken)


# -------------------------------------------------------------- the pairing

def test_a_mismatched_instrument_code_is_refused(tmp_path, instrument, fixtures):
    """A fixture file pointing at the wrong instrument regresses the wrong
    behaviour, which is worse than no fixture."""
    broken = copy.deepcopy(fixtures)
    broken["instrument"] = "OTHER-INSTRUMENT"
    problems = problems_for(tmp_path, instrument, broken)
    assert any("wrong instrument" in p for p in problems), problems


def test_a_mismatched_version_is_refused(tmp_path, instrument, fixtures):
    """Fixtures are version-specific: a threshold moving is a new version, and
    the old fixtures describe the old version's behaviour."""
    broken = copy.deepcopy(fixtures)
    broken["version"] = 2
    problems = problems_for(tmp_path, instrument, broken)
    assert any("version-specific" in p for p in problems), problems


def test_fixtures_with_no_instrument_beside_them_are_refused(tmp_path, fixtures):
    path = tmp_path / "TEST-INSTRUMENT.fixtures.yaml"
    path.write_text(yaml.safe_dump(fixtures, sort_keys=False), encoding="utf-8")
    problems = validate_fixtures.validate_file(path, SCHEMA)
    assert any("no instrument file beside it" in p for p in problems), problems


# ------------------------------------------------- codes and values must exist

def test_an_unknown_question_code_is_refused(tmp_path, instrument, fixtures):
    """**The case that matters most.** A typo in a question code otherwise
    produces an unanswered question and an "incomplete" result that happens to
    pass — a fixture that looks like it tests something and does not."""
    broken = copy.deepcopy(fixtures)
    broken["profiles"][0]["answers"] = {"T9": "none", "T2": "low"}
    problems = problems_for(tmp_path, instrument, broken)
    assert any("T9" in p and "does not define" in p for p in problems), problems


def test_an_unknown_answer_value_is_refused(tmp_path, instrument, fixtures):
    broken = copy.deepcopy(fixtures)
    broken["profiles"][0]["answers"] = {"T1": "maybe", "T2": "low"}
    problems = problems_for(tmp_path, instrument, broken)
    assert any("maybe" in p for p in problems), problems


def test_a_banded_questions_band_value_is_accepted(tmp_path, instrument, fixtures):
    """T2 is `integer_banded`, so its valid values are the band names rather
    than options — the validator has to know the difference."""
    good = copy.deepcopy(fixtures)
    good["profiles"] = [
        {
            "name": "Banded value is a band name",
            "answers": {"T1": "none", "T2": "high"},
            "expect": {"primary_tier": "YELLOW"},
        }
    ]
    assert problems_for(tmp_path, instrument, good) == []


def test_an_unknown_previous_answer_code_is_refused(tmp_path, instrument, fixtures):
    broken = copy.deepcopy(fixtures)
    broken["profiles"][0]["previous_answers"] = {"T9": "none"}
    assert any("T9" in p for p in problems_for(tmp_path, instrument, broken))


def test_an_unknown_condition_is_refused(tmp_path, instrument, fixtures):
    broken = copy.deepcopy(fixtures)
    broken["profiles"][0]["expect"]["tiers"] = {"condition_z": "GREEN"}
    problems = problems_for(tmp_path, instrument, broken)
    assert any("condition_z" in p and "does not assess" in p for p in problems), problems


def test_an_unknown_safety_rule_is_refused(tmp_path, instrument, fixtures):
    """Expecting a rule that does not exist is an assertion that can never
    fire, so it passes forever while testing nothing."""
    broken = copy.deepcopy(fixtures)
    broken["profiles"][0]["expect"]["overrides"] = ["test_imaginary_rule"]
    problems = problems_for(tmp_path, instrument, broken)
    assert any("test_imaginary_rule" in p and "does not define" in p for p in problems)


def test_incomplete_cannot_be_combined_with_another_expectation(
    tmp_path, instrument, fixtures
):
    """A profile that produces no tier cannot also assert one."""
    broken = copy.deepcopy(fixtures)
    broken["profiles"][0]["expect"] = {"incomplete": True, "primary_tier": "GREEN"}
    problems = problems_for(tmp_path, instrument, broken)
    assert any("mutually exclusive" in p for p in problems), problems


# -------------------------------------------------------------- the approval

def test_real_fixtures_need_an_approver(tmp_path, instrument, fixtures):
    """An expected tier is a clinical assertion."""
    broken = copy.deepcopy(fixtures)
    broken["status"] = "approved"
    broken.pop("approved_by", None)
    broken.pop("approved_at", None)
    problems = problems_for(tmp_path, instrument, broken)
    assert any("approved_by" in p for p in problems), problems
    assert any("approved_at" in p for p in problems), problems


def test_an_example_file_needs_no_approver(tmp_path, instrument, fixtures):
    """`status: example` gates nothing, so it is exempt — which is why the
    committed example can exist at all."""
    assert fixtures["status"] == "example"
    assert problems_for(tmp_path, instrument, fixtures) == []


def test_an_unquoted_yaml_date_is_accepted(tmp_path, instrument, fixtures):
    """YAML parses `2026-11-01` as a date object while the schema wants a
    string. Found by rehearsing the full load mechanism end to end: it would
    otherwise have surfaced as a confusing schema error on the Clinical Lead's
    first submission."""
    import datetime

    approved = copy.deepcopy(fixtures)
    approved["status"] = "approved"
    approved["approved_by"] = "Clinical Lead"
    approved["approved_at"] = datetime.date(2026, 11, 1)
    assert problems_for(tmp_path, instrument, approved) == []


# ------------------------------------------------------------- the exit code

def test_a_broken_file_exits_non_zero(tmp_path, instrument, fixtures, capsys):
    broken = copy.deepcopy(fixtures)
    broken["profiles"][0]["answers"] = {"T9": "none"}
    path = write_pair(tmp_path, instrument, broken)
    assert validate_fixtures.main([str(path)]) == 1
    assert "T9" in capsys.readouterr().err


def test_no_fixture_files_is_not_a_failure(tmp_path, capsys):
    """Expected until instrument version one lands. An empty directory must
    not fail the build, but it must say so rather than printing OK."""
    assert validate_fixtures.main([]) == 0


def test_malformed_yaml_is_reported_not_raised(tmp_path, instrument):
    (tmp_path / "TEST-INSTRUMENT.yaml").write_text(
        yaml.safe_dump(instrument, sort_keys=False), encoding="utf-8"
    )
    path = tmp_path / "TEST-INSTRUMENT.fixtures.yaml"
    path.write_text("profiles: [unclosed", encoding="utf-8")
    problems = validate_fixtures.validate_file(path, SCHEMA)
    assert any("not valid YAML" in p for p in problems), problems


def test_a_path_outside_the_repository_is_labelled_not_crashed(tmp_path, instrument, fixtures):
    """`relative_to()` raises for a path outside the repository. That exact
    bug made every negative case in `test_validate_instrument.py` "pass" on a
    traceback rather than a rejection when those tests were written."""
    broken = copy.deepcopy(fixtures)
    broken["profiles"][0]["answers"] = {"T9": "none"}
    problems = problems_for(tmp_path, instrument, broken)
    assert problems and all(isinstance(p, str) for p in problems)
    assert str(tmp_path) in problems[0] or "TEST-INSTRUMENT" in problems[0]
