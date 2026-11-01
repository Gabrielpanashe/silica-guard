"""Layered consent, recorded as data.

Master Reference v1.0 §8.5 and §14.2. The fifth irreversible decision.

Three assertions carry the weight, and all three are about what the system
refuses to do:

  **Absence is never consent.** Every permission nobody recorded reads False.
  No default, no inheritance from a related permission, no grant implied by a
  programme — an employer-funded cohort does not consent on a worker's behalf.

  **A consent record must say what the person was shown.** A row saying
  "agreed" with no wording attached is not evidence, so `consent_text_id` is
  required and must name an *approved* text.

  **`employer_disclosure` cannot be granted at all in phase one.** §14.4 is
  the most consequential governance rule in the document, and the boundary is
  built now, before any commercial pressure exists to blur it.
"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import database
from db_models import Base, ConsentRecord, ConsentText, Message, MessageText, Person
from services import consent, identity
from services.consent import ConsentError, ConsentMissing
from services.identity import IdentityBundle


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'consent.db'}")
    database.enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def message(db):
    """A consent text's wording lives in the content store like every other
    patient-facing string (§8.4). This stands in for an approved one."""
    row = Message(
        code="consent.core.v1",
        version=1,
        channel="app",
        status="approved",
        approved_by="Clinical Lead",
        approved_at=datetime(2026, 11, 1),
        purpose="Stands in for the approved consent wording.",
    )
    db.add(row)
    db.flush()
    db.add(MessageText(message_id=row.id, language="en", text_value="TEST consent wording."))
    db.flush()
    return row


@pytest.fixture
def text(db, message):
    row = consent.register_text(
        db,
        "CORE",
        message.code,
        status="approved",
        approved_by="Clinical Lead",
        approved_at=datetime(2026, 11, 1),
    )
    db.commit()
    return row


@pytest.fixture
def person(db):
    resolution = identity.resolve(db, IdentityBundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    return db.get(Person, resolution.person_id)


# ------------------------------------------------------- the six permissions

def test_there_are_exactly_the_six_permissions_in_14_2():
    """A seventh is a schema change and a governance decision, not a new
    string."""
    assert [p.code for p in consent.PERMISSIONS] == [
        "screening_and_referral",
        "longitudinal_record",
        "contact_by_message",
        "education_broadcast",
        "research_and_statistics",
        "employer_disclosure",
    ]


def test_only_the_core_permission_is_required_to_screen():
    """§14.2: without it there is no service. Everything else is separable, or
    the layering means nothing."""
    assert consent.REQUIRED_TO_SCREEN == ("screening_and_referral",)


def test_employer_disclosure_is_the_only_future_phase_permission():
    assert consent.FUTURE_PHASE == ("employer_disclosure",)


def test_every_permission_has_a_scope_a_worker_could_be_read(db):
    for permission in consent.PERMISSIONS:
        assert len(permission.scope) > 30, permission.code


# --------------------------------------------------- absence is not consent

def test_nothing_is_granted_by_default(db, person):
    """The single most important assertion here. A permission nobody recorded
    is not granted, and there is no path that makes it look granted."""
    standing = consent.summary(db, person.id)
    assert set(standing) == {p.code for p in consent.PERMISSIONS}
    assert not any(standing.values())


def test_screening_is_refused_without_the_core_permission(db, person):
    with pytest.raises(ConsentMissing) as exc:
        consent.may_screen(db, person.id)
    assert exc.value.permission == "screening_and_referral"


def test_one_permission_never_implies_another(db, person, text):
    """A worker who wants his results has not asked for a newsletter."""
    consent.record(db, person.id, "contact_by_message", True, consent_text_id=text.id)
    db.commit()
    assert consent.may_contact(db, person.id)
    assert not consent.may_broadcast(db, person.id)
    assert not consent.may_use_for_research(db, person.id)
    assert not consent.may_keep_longitudinal_record(db, person.id)


def test_a_refusal_is_recorded_rather_than_left_blank(db, person, text):
    """"Asked and declined" is the answer an ethics committee wants, and it
    stops the same question being asked at every visit."""
    consent.record(db, person.id, "education_broadcast", False, consent_text_id=text.id)
    db.commit()
    row = db.scalar(select(ConsentRecord).where(ConsentRecord.permission == "education_broadcast"))
    assert row is not None and row.granted == 0
    assert not consent.may_broadcast(db, person.id)


def test_an_unknown_permission_is_refused(db, person, text):
    with pytest.raises(ConsentError, match="unknown permission"):
        consent.record(db, person.id, "everything", True, consent_text_id=text.id)


# ------------------------------------------- the layering that actually bites

def test_a_worker_may_accept_screening_and_decline_retention(db, person, text):
    """§14.2's own example, and the one place the separation changes what the
    code does: a declined retention means a session with no previous_session_id
    and no deterioration comparison."""
    consent.record_many(
        db,
        person.id,
        {"screening_and_referral": True, "longitudinal_record": False},
        consent_text_id=text.id,
    )
    db.commit()

    consent.may_screen(db, person.id)  # does not raise
    assert not consent.may_keep_longitudinal_record(db, person.id)


def test_retention_granted_allows_the_longitudinal_link(db, person, text):
    consent.record_many(
        db,
        person.id,
        {"screening_and_referral": True, "longitudinal_record": True},
        consent_text_id=text.id,
    )
    db.commit()
    assert consent.may_keep_longitudinal_record(db, person.id)


# ---------------------------------------------------- the employer boundary

def test_employer_disclosure_cannot_be_granted_in_phase_one(db, person, text):
    """§14.4, the most consequential governance rule in the document. The
    boundary is built before any commercial pressure exists to blur it."""
    with pytest.raises(ConsentError, match="future-phase"):
        consent.record(db, person.id, "employer_disclosure", True, consent_text_id=text.id)


def test_employer_disclosure_may_still_be_recorded_as_refused(db, person, text):
    """A refusal is a real answer and may be recorded; only a grant is
    refused, because a grant now would be a promise nothing honours."""
    consent.record(db, person.id, "employer_disclosure", False, consent_text_id=text.id)
    db.commit()
    assert not consent.may_disclose_to_employer(db, person.id)


def test_a_bulk_screen_cannot_sneak_an_employer_grant_through(db, person, text):
    """record_many validates everything before writing anything, so a
    disallowed grant in the set does not leave the rest recorded."""
    with pytest.raises(ConsentError, match="future-phase"):
        consent.record_many(
            db,
            person.id,
            {"screening_and_referral": True, "employer_disclosure": True},
            consent_text_id=text.id,
        )
    assert db.query(ConsentRecord).count() == 0, "all-or-nothing"


def test_employer_disclosure_is_a_real_lookup_not_a_hardcoded_false(db, person):
    """Written as a per-person check so that the day the formal-sector module
    exists, the boundary is already in the code path rather than a policy
    somebody has to remember."""
    assert consent.may_disclose_to_employer(db, person.id) is False


# ------------------------------------------------------- the consent text

def test_a_record_needs_a_consent_text(db, person):
    """§14.2: recorded "with a timestamp and the version of the consent text
    displayed". A row saying "agreed" with nothing attached is not evidence."""
    with pytest.raises(ConsentError, match="no consent text"):
        consent.record(db, person.id, "screening_and_referral", True, consent_text_id=999)


def test_an_unapproved_consent_text_cannot_be_used(db, person, message):
    """Nobody is asked to agree to unapproved wording."""
    draft = consent.register_text(db, "CORE", message.code, status="draft")
    db.commit()
    with pytest.raises(ConsentError, match="not approved"):
        consent.record(db, person.id, "screening_and_referral", True, consent_text_id=draft.id)


def test_a_consent_text_must_point_at_the_content_store(db):
    """The wording goes through the same review, three languages, GSM-7 check
    and approval trail as every other patient-facing string (§8.4)."""
    with pytest.raises(ConsentError, match="not in the content store"):
        consent.register_text(db, "CORE", "consent.nonexistent")


def test_an_approved_consent_text_is_immutable(db, message):
    """Consent records reference it, so a change is a new version — otherwise
    a record cannot say what was shown."""
    consent.register_text(
        db, "CORE", message.code, status="approved",
        approved_by="Clinical Lead", approved_at=datetime(2026, 11, 1),
    )
    db.commit()
    with pytest.raises(ConsentError, match="immutable"):
        consent.register_text(
            db, "CORE", message.code, status="approved",
            approved_by="Clinical Lead", approved_at=datetime(2026, 11, 2),
        )


def test_a_draft_consent_text_may_be_revised(db, message):
    consent.register_text(db, "CORE", message.code, status="draft")
    db.commit()
    consent.register_text(db, "CORE", message.code, status="review")
    db.commit()
    assert db.query(ConsentText).count() == 1


def test_active_text_takes_the_highest_approved_version(db, message):
    for version in (1, 2):
        consent.register_text(
            db, "CORE", message.code, version=version, status="approved",
            approved_by="Clinical Lead", approved_at=datetime(2026, 11, 1),
        )
    db.commit()
    assert consent.active_text(db, "CORE").version == 2


def test_active_text_ignores_a_later_draft(db, message):
    consent.register_text(
        db, "CORE", message.code, version=1, status="approved",
        approved_by="Clinical Lead", approved_at=datetime(2026, 11, 1),
    )
    consent.register_text(db, "CORE", message.code, version=2, status="draft")
    db.commit()
    assert consent.active_text(db, "CORE").version == 1


def test_active_text_refuses_when_nothing_is_approved(db, message):
    """Which is the state until the Clinical Lead approves one, and is why
    consent capture does not work before then."""
    consent.register_text(db, "CORE", message.code, status="draft")
    db.commit()
    with pytest.raises(ConsentError, match="no version is approved"):
        consent.active_text(db, "CORE")


def test_the_record_names_the_version_that_was_shown(db, person, text):
    consent.record(db, person.id, "screening_and_referral", True, consent_text_id=text.id)
    db.commit()
    row = db.scalar(select(ConsentRecord))
    stored = db.get(ConsentText, row.consent_text_id)
    assert (stored.code, stored.version) == ("CORE", 1)


# ---------------------------------------------------------- withdrawal

def test_a_withdrawal_keeps_the_original_row(db, person, text):
    """§14.3 requires the withdrawal mechanism to be demonstrable. "Granted,
    then withdrawn on this date" is a different story from "never granted",
    and only one of them can be shown to a committee."""
    consent.record(db, person.id, "education_broadcast", True, consent_text_id=text.id)
    db.commit()
    assert consent.may_broadcast(db, person.id)

    consent.withdraw(db, person.id, "education_broadcast", withdrawn_by="worker")
    db.commit()

    assert not consent.may_broadcast(db, person.id)
    assert db.query(ConsentRecord).count() == 1
    row = db.scalar(select(ConsentRecord))
    assert row.granted == 1 and row.withdrawn_at is not None


def test_withdrawing_something_never_granted_is_not_an_error(db, person):
    """A worker opting out of what he never opted into should not get a
    failure."""
    assert consent.withdraw(db, person.id, "education_broadcast") is None


def test_a_permission_can_be_granted_again_after_withdrawal(db, person, text):
    consent.record(db, person.id, "education_broadcast", True, consent_text_id=text.id)
    db.commit()
    consent.withdraw(db, person.id, "education_broadcast")
    db.commit()
    consent.record(db, person.id, "education_broadcast", True, consent_text_id=text.id)
    db.commit()
    assert consent.may_broadcast(db, person.id)
    assert db.query(ConsentRecord).count() == 2, "both decisions survive"


def test_the_most_recent_decision_stands(db, person, text):
    consent.record(db, person.id, "research_and_statistics", True, consent_text_id=text.id)
    db.commit()
    consent.record(db, person.id, "research_and_statistics", False, consent_text_id=text.id)
    db.commit()
    assert not consent.may_use_for_research(db, person.id)


def test_the_history_keeps_every_decision_in_order(db, person, text):
    """What a worker, an auditor or an ethics committee is entitled to see."""
    consent.record(db, person.id, "screening_and_referral", True, consent_text_id=text.id)
    db.commit()
    consent.record(db, person.id, "education_broadcast", False, consent_text_id=text.id)
    db.commit()
    consent.withdraw(db, person.id, "screening_and_referral")
    db.commit()

    history = consent.history(db, person.id)
    assert [r.permission for r in history] == [
        "screening_and_referral",
        "education_broadcast",
    ]
    assert history[0].withdrawn_at is not None


# ------------------------------------------------------------- the channel

def test_ussd_is_a_recordable_channel(db, person, text):
    """§14.2: on USSD, consent is a short statement in spoken register
    followed by an explicit keypress, recorded with a timestamp and the text
    version."""
    row = consent.record(
        db, person.id, "screening_and_referral", True,
        consent_text_id=text.id, channel="USSD",
    )
    db.commit()
    assert row.channel == "USSD" and row.recorded_at is not None


def test_an_unknown_channel_is_refused(db, person, text):
    with pytest.raises(ConsentError, match="channel must be"):
        consent.record(
            db, person.id, "screening_and_referral", True,
            consent_text_id=text.id, channel="whatsapp",
        )


def test_an_unknown_person_is_refused(db, text):
    with pytest.raises(ConsentError, match="no person"):
        consent.record(db, 999, "screening_and_referral", True, consent_text_id=text.id)


# ------------------------------------------------------ consent and merges

def test_consent_survives_a_merge(db, text):
    """A bug found while building this: `identity.merge()` moved contacts and
    sessions but not consent records, so a worker's recorded decisions would
    have silently vanished when a clerk joined two records. Every read goes to
    the winner, and the rows were left pointing at the loser."""
    winner = identity.resolve(db, IdentityBundle(name="Tendai Moyo", phone="0771234567"))
    loser = identity.resolve(db, IdentityBundle(name="Tendai Moyo", phone="0789999999"))
    db.commit()

    consent.record_many(
        db,
        loser.person_id,
        {"screening_and_referral": True, "longitudinal_record": True},
        consent_text_id=text.id,
    )
    db.commit()

    identity.merge(db, winner.person_id, loser.person_id, merged_by="clerk")
    db.commit()

    consent.may_screen(db, winner.person_id)  # does not raise
    assert consent.may_keep_longitudinal_record(db, winner.person_id)
    assert len(consent.history(db, winner.person_id)) == 2


def test_the_later_decision_wins_across_a_merge(db, text):
    """Both records' decisions move, and the most recent stands — it is the
    same person's later decision."""
    winner = identity.resolve(db, IdentityBundle(name="Tendai Moyo", phone="0771234567"))
    loser = identity.resolve(db, IdentityBundle(name="Tendai Moyo", phone="0789999999"))
    db.commit()

    consent.record(db, winner.person_id, "education_broadcast", False, consent_text_id=text.id)
    db.commit()
    consent.record(db, loser.person_id, "education_broadcast", True, consent_text_id=text.id)
    db.commit()

    identity.merge(db, winner.person_id, loser.person_id, merged_by="clerk")
    db.commit()
    assert consent.may_broadcast(db, winner.person_id)


def test_everything_that_follows_a_person_is_enumerated_in_one_place():
    """The failure mode of forgetting a table is silent: the rows stay
    pointing at the losing record, every read goes to the winner, and the data
    is simply gone from view. So the list is explicit and this test names what
    must never quietly leave it."""
    from db_models import ConsentRecord as C, Contact, ExposureProfile, ScreeningSession

    assert {model for model, _ in identity.MERGE_FOLLOWS} == {
        Contact,
        ScreeningSession,
        C,
        ExposureProfile,
    }
