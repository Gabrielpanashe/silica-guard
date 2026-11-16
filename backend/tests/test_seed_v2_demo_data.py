"""Demonstration data for the version two tables.

`docs/IMPLEMENTATION_PLAN.md` item 1.12 and the Week 8 roadmap line,
"demonstration data reseeded".

Three things carry the weight:

  **The clinical layer is gated, and the gate is not dead code.** Without an
  approved instrument and an approved consent text the script seeds the
  reference and identity layer, reports what is missing, and stops. The test
  below loads the synthetic instrument and shows the layer then running — so
  the gate is a gate rather than a path nobody has walked.

  **Results are produced, never written.** Every session goes through the real
  §10.3 pipeline, so a result row's instrument version and ruleset are the
  ones that actually produced it. The v1 seeder writes pre-computed tiers,
  which is defensible for a row whose tier came from a model call and
  indefensible for a row that claims provenance.

  **Nothing clinical and nothing patient-facing is invented.** The seeder
  creates no `Message` row and no consent wording, and reads its answer
  profiles from the instrument's own regression fixtures rather than choosing
  them. A test asserts that, because "a plausible invented question set is
  the most dangerous artefact this repository could hold"
  (`clinical/README.md`) and an unapproved consent form is worse.
"""

import copy
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

import database
from services import consent, instrument_store

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND / "scripts"))

import _demo_guard  # noqa: E402
import seed_v2_demo_data as seeder  # noqa: E402

FIXTURE = BACKEND.parent / "clinical" / "examples" / "TEST-INSTRUMENT.yaml"


def _session(client):
    return next(client.app.dependency_overrides[database.get_db]())


# ------------------------------------------------- the production guard

@pytest.mark.parametrize("url", [
    "sqlite:///./data/silicaguard.db",
    "sqlite://",
    "postgresql://u:p@localhost:5432/sg",
    "postgresql://u:p@127.0.0.1:5432/sg",
    "",
])
def test_a_local_database_is_allowed(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    assert _demo_guard.refuse_unless_local("seed.py", argv=[]) == url


@pytest.mark.parametrize("url", [
    "postgresql://u:p@aws-0-eu-west-1.pooler.supabase.com:5432/postgres",
    "postgresql://u:p@db.example.net:5432/sg",
])
def test_a_remote_database_is_refused(monkeypatch, url):
    """**The assertion that matters most in this file.** There is no staging,
    so the one Supabase database is both production and the demonstration
    target, and a developer's `.env` holds its URL. Neither seeder checked
    where it was pointed before deleting every row in the tables it owns."""
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(SystemExit) as raised:
        _demo_guard.refuse_unless_local("seed_v2_demo_data.py", argv=[])
    message = str(raised.value)
    assert "REFUSED TO RUN" in message
    assert "DELETES every row" in message


def test_the_refusal_names_no_credentials(monkeypatch):
    """A refusal is printed to a terminal and pasted into chat. It must not
    carry the password out of the environment with it."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://admin:s3cr3t-pw@db.example.net:5432/sg")
    with pytest.raises(SystemExit) as raised:
        _demo_guard.refuse_unless_local("seed.py", argv=[])
    assert "s3cr3t-pw" not in str(raised.value)
    assert "admin" not in str(raised.value)


def test_the_override_is_a_phrase_not_a_flag(monkeypatch, capsys):
    """`-y` is reachable by pressing return at the wrong prompt or by leaving
    an argument in a shell history line. A phrase is not."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example.net:5432/sg")

    for nearly in (["-y"], ["--force"], ["yes"], ["YES-DELETE-ROWS-IN-THIS-DATABASE"]):
        with pytest.raises(SystemExit):
            _demo_guard.refuse_unless_local("seed.py", argv=nearly)

    assert _demo_guard.refuse_unless_local(
        "seed.py", argv=[_demo_guard.OVERRIDE_PHRASE]
    ).startswith("postgresql://")
    assert "not a local database" in capsys.readouterr().err


# ------------------------------------------- the reference and identity layer

def test_the_reference_layer_seeds_without_any_clinical_content(client):
    from db_models import Facility, Programme, Site

    db = _session(client)
    refs = seeder._seed_reference(db)

    assert len(refs["sites"]) == len(seeder.SITES)
    assert db.scalar(select(Site).where(Site.name == "Globe & Phoenix")).district == "Kwekwe"
    kinds = {p.kind for p in db.scalars(select(Programme)).all()}
    assert kinds == {"community", "employer"}, (
        "an employer cohort has to exist for §14.4's boundary to be testable"
    )
    assert db.scalars(select(Facility)).all()
    db.close()


def test_people_go_through_the_real_identity_service(client):
    """Not inserted by hand: `identity.resolve()` is what mints a participant
    code, keyed-hashes the number and encrypts the recoverable copy. Rows
    written directly would produce a database that looks right and exercises
    none of that."""
    from db_models import Contact, Person

    db = _session(client)
    refs = seeder._seed_reference(db)
    state = seeder._seed_people(db, refs)

    people = db.scalars(select(Person)).all()
    assert len(people) == len(seeder.PEOPLE) + 2, "plus the near-duplicate and the USSD caller"
    assert all(p.participant_code for p in people)
    assert len({p.participant_code for p in people}) == len(people)

    for contact in db.scalars(select(Contact)).all():
        assert contact.number_hmac and contact.number_encrypted
        assert "0771" not in (contact.number_hmac or ""), "the hash is not the number"
    db.close()


def test_the_near_duplicate_is_queued_and_never_merged(client):
    """§8.2: a probable match is a question for a human, not an action. The
    demonstration data has to contain one, or the review queue is an empty
    screen nobody has seen working."""
    from db_models import PersonMatchQueue, PersonMerge

    db = _session(client)
    state = seeder._seed_people(db, seeder._seed_reference(db))

    queued = db.scalars(select(PersonMatchQueue)).all()
    assert len(queued) >= 1
    assert all(q.status == "pending" for q in queued)
    assert db.scalars(select(PersonMerge)).all() == [], "nothing is merged automatically"
    db.close()


def test_the_ussd_caller_is_provisional(client):
    """A caller with no participant code gets a record flagged unverified,
    never an attachment to whoever the number was last seen with."""
    from db_models import Person

    db = _session(client)
    state = seeder._seed_people(db, seeder._seed_reference(db))
    person = db.get(Person, state["provisional"].person_id)
    assert person.provisional
    db.close()


def test_seeding_twice_leaves_the_same_state(client):
    """Re-runnable from any state, so a demonstration can be reset."""
    from db_models import Person, Site

    from sqlalchemy import func

    db = _session(client)
    refs = seeder._seed_reference(db)
    seeder._seed_people(db, refs)
    seeder._clear(db)
    refs = seeder._seed_reference(db)
    seeder._seed_people(db, refs)

    assert db.scalar(select(func.count()).select_from(Site)) == len(seeder.SITES)
    assert db.scalar(select(func.count()).select_from(Person)) == len(seeder.PEOPLE) + 2

    # And calling the reference seeding again, without a clear, is harmless.
    seeder._seed_reference(db)
    assert db.scalar(select(func.count()).select_from(Site)) == len(seeder.SITES)
    db.close()


# ------------------------------------------------------- the clinical gate

def test_without_an_instrument_the_clinical_layer_refuses_and_says_why(client):
    db = _session(client)
    instrument, text_id, missing = seeder._clinical_prerequisites(db)

    assert instrument is None and text_id is None
    assert len(missing) == 2
    joined = " ".join(missing)
    assert "instrument version one" in joined.lower()
    assert "consent" in joined.lower()
    assert "will not invent" in joined, "the refusal has to say why, not just that"
    db.close()


def test_with_the_prerequisites_the_clinical_layer_runs(client):
    """**The gate is a gate, not a path nobody has walked.** Loads the
    synthetic instrument and its fixtures and shows sessions and results being
    produced — against `TEST-INSTRUMENT`, which exists for exactly this and
    carries question codes that mean nothing."""
    from db_models import Message, MessageText, ScreeningResult, ScreeningSession

    db = _session(client)
    doc = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    approved = copy.deepcopy(doc)
    approved.update(status="approved", approved_by="Clinical Lead",
                    approved_at="2026-11-01")
    instrument_store.load(db, approved)

    message = Message(code="consent.core.v1", version=1, channel="app",
                      status="approved", approved_by="Clinical Lead",
                      approved_at=datetime(2026, 11, 1), purpose="Test wording.")
    db.add(message)
    db.flush()
    db.add(MessageText(message_id=message.id, language="en", text_value="TEST."))
    consent.register_text(db, "CORE", message.code, status="approved",
                          approved_by="Clinical Lead",
                          approved_at=datetime(2026, 11, 1))
    from db_models import Facility

    db.add(Facility(name="Test District Hospital", level="district"))
    db.commit()

    refs = seeder._seed_reference(db)
    state = seeder._seed_people(db, refs)
    instrument, text_id, missing = seeder._clinical_prerequisites(db)
    assert missing == [], missing

    outcome = seeder._seed_clinical(db, state, instrument, text_id)
    assert outcome["sessions"] >= 1, outcome

    sessions = db.scalars(select(ScreeningSession)).all()
    results = db.scalars(select(ScreeningResult)).all()
    assert sessions and results
    db.close()


def test_every_seeded_result_carries_real_provenance(client):
    """The reason results are produced rather than written: a v2 result row
    records the instrument version and ruleset that classified it, and a
    hand-written tier would be a row claiming a provenance it does not have."""
    from db_models import Facility, Message, MessageText, ScreeningResult

    db = _session(client)
    doc = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    approved = copy.deepcopy(doc)
    approved.update(status="approved", approved_by="Clinical Lead",
                    approved_at="2026-11-01")
    instrument_store.load(db, approved)
    message = Message(code="consent.core.v1", version=1, channel="app",
                      status="approved", approved_by="Clinical Lead",
                      approved_at=datetime(2026, 11, 1), purpose="Test wording.")
    db.add(message)
    db.flush()
    db.add(MessageText(message_id=message.id, language="en", text_value="TEST."))
    consent.register_text(db, "CORE", message.code, status="approved",
                          approved_by="Clinical Lead",
                          approved_at=datetime(2026, 11, 1))
    db.add(Facility(name="Test District Hospital", level="district"))
    db.commit()

    refs = seeder._seed_reference(db)
    state = seeder._seed_people(db, refs)
    instrument, text_id, _ = seeder._clinical_prerequisites(db)
    seeder._seed_clinical(db, state, instrument, text_id)

    rows = db.scalars(select(ScreeningResult)).all()
    assert rows
    for row in rows:
        assert row.instrument_code == instrument["code"]
        assert row.instrument_version == instrument["version"]
        assert row.ruleset_version
        assert row.method == "deterministic_rules"
        assert row.tier in ("GREEN", "YELLOW", "ORANGE", "RED")
    db.close()


# --------------------------------------------- what the seeder may not invent

def test_the_seeder_writes_no_patient_facing_wording(client):
    """A consent form and a question label are patient-facing strings, and
    every one needs the Clinical Lead's recorded approval before it ships. A
    seeder that wrote them would produce wording indistinguishable from
    reviewed wording a month later."""
    from db_models import ConsentText, Message, MessageText

    db = _session(client)
    refs = seeder._seed_reference(db)
    seeder._seed_people(db, refs)

    assert db.scalars(select(Message)).all() == []
    assert db.scalars(select(MessageText)).all() == []
    assert db.scalars(select(ConsentText)).all() == []
    db.close()


def test_no_clinical_content_appears_in_the_seeder_source():
    """The source is checked as well as the behaviour: a question code or an
    answer value written here would be invented clinical content, whatever it
    did at runtime. Answer profiles come from the instrument's own fixtures."""
    source = (BACKEND / "scripts" / "seed_v2_demo_data.py").read_text(encoding="utf-8")

    assert "tier_rules" not in source
    assert "safety_rules" not in source
    assert "forces_tier" not in source
    for tier in ("GREEN", "YELLOW", "ORANGE", "RED"):
        assert f'"{tier}"' not in source, (
            f"{tier} is written in the seeder; tiers must come from the engine"
        )
    assert "_fixture_profiles" in source, "profiles are read, not chosen"


def test_the_exposure_values_are_structured_not_prose():
    """Exposure profile fields are schema values the register defines, not
    sentences someone wrote: `years_band`, `controls` and `occupation` are
    what the national register aggregates on."""
    for entry in seeder.PEOPLE:
        occupation, years, controls = entry[6], entry[7], entry[8]
        for value in (occupation, years, controls):
            assert value == value.lower() and " " not in value, value


def test_both_seeders_call_the_guard_before_deleting():
    """Structural, because behavioural cannot reach it: importing either
    script builds the database engine at module level, so on a machine
    without the Postgres driver the import fails before `seed()` runs.

    What this asserts is that the call is present and that it comes **first**
    -- a check that runs after the deletes has already done the damage it was
    checking for.
    """
    import ast

    for name in ("seed_demo_data.py", "seed_v2_demo_data.py"):
        tree = ast.parse((BACKEND / "scripts" / name).read_text(encoding="utf-8"))
        seed_fn = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "seed"
        )

        body = list(seed_fn.body)
        if (isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            body = body[1:]          # skip the docstring

        first_call = next(
            (n.func.id for n in ast.walk(body[0])
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)),
            None,
        )
        assert first_call == "refuse_unless_local", (
            f"{name}'s first action is {first_call!r}, not the guard -- this "
            "script deletes every row in the tables it owns"
        )
