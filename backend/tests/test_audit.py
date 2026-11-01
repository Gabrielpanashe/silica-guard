"""The append-only audit trail.

Master Reference v1.0 §16.3. Four properties, each with a specific failure it
prevents:

  **Append-only.** Not "nobody calls the update" — there is no update and no
  delete anywhere in the module, asserted by inspecting it. A log that can be
  edited afterwards answers nothing.

  **Refusals are recorded.** `allowed=False` rows are the ones that matter: a
  role boundary nobody can show being enforced is a boundary nobody can show
  exists.

  **No personal data in a log line.** Checked rather than trusted, because
  the rule is easy to agree with and easy to break in a hurry.

  **An audit write cannot fail a clinical write.** `record()` joins the
  caller's transaction, so a screening can never be lost because a log row
  would not fit.
"""

import ast
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import database
from db_models import AuditLog, Base
from services import audit
from services.audit import AuditError
from services.authz import Principal

MODULE = Path(__file__).resolve().parent.parent / "services" / "audit.py"


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'audit.db'}")
    database.enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def actor():
    return Principal(user_id=4, email="sister.moyo@example.org",
                     role="village_health_worker", scope={"site_ids": [3]})


# ------------------------------------------------------------- append-only

def test_the_module_has_no_update_and_no_delete():
    """**The assertion that makes "append-only" mean something.** A log with an
    edit path is a log that can be rewritten after the fact, and the whole
    point of §16.3's audit is that it cannot.

    Enforced here rather than by a database trigger for the fourth time in
    this schema: triggers are PostgreSQL-only and invisible to the SQLite unit
    suite (§16.2).
    """
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        # No assignment to an AuditLog attribute: no `row.action = ...`.
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            raise AssertionError(
                f"audit.py assigns to an attribute at line {node.lineno}; an "
                "audit row is written once and never changed"
            )
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None)
            assert name != "delete", (
                f"audit.py calls .delete() at line {node.lineno}; the log is "
                "append-only"
            )

    assert "db.add(" in source, "it must still be able to append"


def test_a_row_is_written_into_the_callers_transaction(db, actor):
    """Flushes rather than commits, so a clinical write and its audit row
    stand or fall together."""
    audit.record(db, actor, "person.read", object_type="person", object_id=7, person_id=7)
    assert db.query(AuditLog).count() == 1, "visible before commit"
    db.rollback()
    assert db.query(AuditLog).count() == 0, "and rolls back with the caller"


def test_a_committed_row_survives(db, actor):
    audit.record(db, actor, "screening.submit", object_type="session", object_id=1)
    db.commit()
    assert db.query(AuditLog).count() == 1


# -------------------------------------------------------------- what it says

def test_the_row_names_the_actor_in_terms_that_outlive_the_user(db, actor):
    """`actor_email` and `actor_role` are denormalised on purpose: a log that
    becomes unreadable when a user row changes or is deactivated is not a
    log."""
    audit.record(db, actor, "person.read", person_id=7)
    db.commit()
    row = db.scalar(select(AuditLog))
    assert row.actor_user_id == 4
    assert row.actor_email == "sister.moyo@example.org"
    assert row.actor_role == "village_health_worker"
    assert row.at is not None and row.request_id


def test_an_unknown_action_is_refused(db, actor):
    """The set is closed because an action nobody declared is an action nobody
    will think to audit."""
    with pytest.raises(AuditError, match="unknown audit action"):
        audit.record(db, actor, "person.rummage")


def test_every_declared_action_can_be_written(db, actor):
    for action in audit.ACTIONS:
        audit.record(db, actor, action)
    db.commit()
    assert db.query(AuditLog).count() == len(audit.ACTIONS)


def test_an_anonymous_actor_is_allowed(db):
    """A failed login has no principal yet, and that attempt is exactly what
    needs recording."""
    audit.record(db, None, "auth.login_failed")
    db.commit()
    row = db.scalar(select(AuditLog))
    assert row.actor_email is None and row.action == "auth.login_failed"


# ------------------------------------------------- no personal data, checked

@pytest.mark.parametrize(
    "details",
    [
        {"name": "Tendai Moyo"},
        {"phone": "+263771234567"},
        {"phone_number": "+263771234567"},
        {"national_id": "63-123456-A-00"},
        {"answers": {"T1": "some"}},
        {"password": "hunter2"},
        {"message": "Your result is ready"},
        {"Name": "Tendai Moyo"},
    ],
)
def test_personal_data_in_a_log_line_is_refused(db, actor, details):
    """`CLAUDE.md`: no personal data in a log line. Checked rather than
    trusted — the log must not become a second copy of the register."""
    with pytest.raises(AuditError, match="may not contain"):
        audit.record(db, actor, "person.read", details=details)


def test_codes_counts_and_ids_are_fine(db, actor):
    audit.record(
        db, actor, "person.read",
        person_id=7, details={"participant_code_prefix": "8N", "entries": 4,
                              "condition": "silicosis", "tier": "ORANGE"},
    )
    db.commit()
    stored = json.loads(db.scalar(select(AuditLog)).details)
    assert stored["entries"] == 4 and stored["tier"] == "ORANGE"


def test_details_are_json_text_not_a_native_column(db, actor):
    """§16.2, the same portability rule as the instrument predicates."""
    audit.record(db, actor, "person.read", details={"a": 1})
    db.commit()
    assert isinstance(db.scalar(select(AuditLog)).details, str)


# --------------------------------------------------------------- refusals

def test_a_refusal_is_recorded_as_a_row(db, actor):
    audit.record(db, actor, "person.merge", allowed=False,
                 details={"capability": "person.merge"})
    db.commit()
    row = db.scalar(select(AuditLog))
    assert row.allowed == 0


def test_refusals_can_be_listed(db, actor):
    audit.record(db, actor, "person.read", allowed=True)
    audit.record(db, actor, "person.merge", allowed=False)
    audit.record(db, actor, "admin.user_create", allowed=False)
    db.commit()
    refused = audit.refusals(db)
    assert len(refused) == 2
    assert {r.action for r in refused} == {"person.merge", "admin.user_create"}


def test_a_refusal_on_its_own_session_never_raises(monkeypatch, actor):
    """A failure to log a refusal must not turn a clean 403 into a 500 — the
    refusal itself still has to reach the caller."""
    import services.audit as module

    def explode():
        raise RuntimeError("no database")

    monkeypatch.setattr("database.get_fresh_session", explode)
    module.record_refusal(actor, "person.merge")  # must not raise


# ------------------------------------------------------------- reading it

def test_every_access_to_one_person_can_be_listed(db, actor):
    """"Who has read my record?" is a question a worker is entitled to an
    answer to."""
    audit.record(db, actor, "person.read", person_id=7)
    audit.record(db, actor, "screening.read", person_id=7)
    audit.record(db, actor, "person.read", person_id=8)
    db.commit()

    entries = audit.for_person(db, 7)
    assert len(entries) == 2
    assert {e.action for e in entries} == {"person.read", "screening.read"}


def test_rows_from_one_request_correlate(db, actor):
    rid = audit.new_request_id()
    audit.record(db, actor, "person.read", person_id=7, request_id=rid)
    audit.record(db, actor, "consent.read", person_id=7, request_id=rid)
    audit.record(db, actor, "person.read", person_id=8)
    db.commit()
    assert len(audit.for_request(db, rid)) == 2


def test_a_request_id_is_generated_when_none_is_given(db, actor):
    audit.record(db, actor, "person.read")
    db.commit()
    assert db.scalar(select(AuditLog)).request_id


def test_two_generated_request_ids_differ():
    assert audit.new_request_id() != audit.new_request_id()
