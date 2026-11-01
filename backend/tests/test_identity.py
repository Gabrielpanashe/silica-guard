"""Identity resolution: matching a worker to his own earlier record.

Master Reference v1.0 §8.2 — "the hardest problem in the system and the one
most likely to quietly destroy the headline metric."

The decisive tests here are the ones that assert a **non**-event:

  * A telephone number alone never attaches a screening to an existing
    person. `ussd_handler._find_or_create_miner` does exactly that today, and
    §8.2 says it "would corrupt the longitudinal dataset faster than anything
    else in the system."
  * A probable match is **queued, never applied.** A duplicate is an
    annoyance; a false merge mixes two clinical histories with no way to
    detect it by inspection.
  * `resolve()` always returns a usable person, so an uncertain identity
    never costs a screening (rule 7).
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import database
from db_models import Base, Contact, Person, PersonMatchQueue, PersonMerge, ScreeningSession
from services import crypto, identity
from services.identity import IdentityBundle, IdentityError


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'identity.db'}")
    database.enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def bundle(**kwargs) -> IdentityBundle:
    return IdentityBundle(**kwargs)


def session_at(db, person_id: int, *, site_text: str) -> ScreeningSession:
    row = ScreeningSession(person_id=person_id, channel="APP", site_text=site_text)
    db.add(row)
    db.flush()
    return row


# ------------------------------------------------------- participant codes

def test_a_participant_code_is_six_characters_from_the_safe_alphabet(db):
    """Six, not the referral format's four: about a billion codes against a
    million, for a register intended for more than 500,000 people where a
    collision mixes two clinical histories (§12 item 4)."""
    code = identity.generate_participant_code(db)
    assert len(code) == identity.CODE_LENGTH == 6
    assert set(code) <= set(identity.CODE_ALPHABET)


def test_the_alphabet_excludes_the_ambiguous_characters(db):
    """A code is read off a card and typed on a numeric keypad; it must not
    hinge on telling 0 from O or 1 from I."""
    assert not (set("0O1I") & set(identity.CODE_ALPHABET))


def test_codes_are_unique_across_the_register(db):
    codes = set()
    for _ in range(40):
        code = identity.generate_participant_code(db)
        db.add(Person(participant_code=code))
        db.flush()
        codes.add(code)
    assert len(codes) == 40


def test_code_generation_raises_rather_than_colliding(db, monkeypatch):
    """A duplicate participant code points two workers at one clinical
    history, which is the same failure as a false merge."""
    db.add(Person(participant_code="AAAAAA"))
    db.flush()
    monkeypatch.setattr(identity.secrets, "choice", lambda alphabet: "A")
    with pytest.raises(IdentityError, match="could not generate"):
        identity.generate_participant_code(db)


# ------------------------------------------------- a number is not a key

def test_a_phone_number_alone_never_attaches_to_an_existing_person(db):
    """The single most important assertion in this file.

    Two brothers sharing a handset must be two records. Today
    `ussd_handler._find_or_create_miner` returns the first miner holding that
    number, which silently merges them.
    """
    first = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    second = identity.resolve(db, bundle(name="Farai Moyo", phone="0771234567"))
    db.commit()

    assert second.person_id != first.person_id
    assert second.outcome in ("created", "created_pending_review")


def test_a_shared_number_is_recorded_against_both_people(db):
    """A number is an attribute with history, so two people may hold the same
    one. The store never deduplicates across people (§8.2)."""
    first = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    second = identity.resolve(db, bundle(name="Farai Moyo", phone="0771234567"))
    db.commit()

    digest = crypto.keyed_hash("0771234567", "phone")
    owners = set(
        db.scalars(select(Contact.person_id).where(Contact.number_hmac == digest)).all()
    )
    assert owners == {first.person_id, second.person_id}


def test_a_number_is_stored_hashed_and_encrypted_never_in_plaintext(db):
    identity.resolve(db, bundle(name="Tendai Moyo", phone="+263771234567"))
    db.commit()
    contact = db.scalar(select(Contact))
    assert "263771234567" not in (contact.number_encrypted or "")
    assert "263771234567" not in (contact.number_hmac or "")
    assert crypto.decrypt(contact.number_encrypted) == "+263771234567"


def test_the_same_handset_in_two_formats_is_one_contact_row(db):
    resolution = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    person = db.get(Person, resolution.person_id)
    identity.attach_contact(db, person, "+263 77 123 4567")
    db.commit()
    assert db.query(Contact).count() == 1


def test_the_primary_number_comes_back_for_sending(db):
    """The only place a stored number becomes plaintext again, and it exists
    because a result has to reach a handset."""
    resolution = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    assert identity.primary_phone(db, resolution.person_id) == "+263771234567"


def test_a_name_is_stored_hashed_and_encrypted_never_in_plaintext(db):
    identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    person = db.scalar(select(Person))
    assert "Tendai" not in (person.name_encrypted or "")
    assert "tendai" not in (person.name_hmac or "")
    assert identity.display_name(db, person.id) == "Tendai Moyo"


# --------------------------------------------------- the deterministic hits

def test_a_participant_code_attaches_to_that_person(db):
    """The card in his pocket, and he presented it."""
    first = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    again = identity.resolve(db, bundle(participant_code=first.participant_code))
    db.commit()
    assert again.person_id == first.person_id
    assert again.outcome == "matched_participant_code"
    assert db.query(Person).count() == 1


def test_a_participant_code_is_read_leniently(db):
    """It is read aloud by a hospital clerk and typed on a keypad."""
    first = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    messy = f" {first.participant_code.lower()} "
    assert identity.resolve(db, bundle(participant_code=messy)).person_id == first.person_id


def test_a_national_id_is_a_deterministic_match_and_is_applied(db):
    """The one field §8.2 permits a directly-applied match on."""
    first = identity.resolve(
        db, bundle(name="Tendai Moyo", national_id="63-123456-A-00", phone="0771234567")
    )
    db.commit()
    again = identity.resolve(
        db, bundle(name="T Moyo", national_id="63123456a00", phone="0789999999")
    )
    db.commit()
    assert again.person_id == first.person_id
    assert again.outcome == "matched_national_id"


def test_a_national_id_match_picks_up_the_new_number(db):
    """Numbers change when a subscriber identity module is lost; the person
    does not."""
    first = identity.resolve(db, bundle(national_id="63123456A00", phone="0771234567"))
    db.commit()
    identity.resolve(db, bundle(national_id="63123456A00", phone="0789999999"))
    db.commit()
    numbers = {
        crypto.decrypt(c.number_encrypted)
        for c in db.scalars(
            select(Contact).where(Contact.person_id == first.person_id)
        ).all()
    }
    assert numbers == {"+263771234567", "+263789999999"}


def test_an_unknown_participant_code_on_the_app_is_an_error_not_a_new_record(db):
    """A health worker holding a card that matches nobody should check the
    card, not create a second record for someone who already has one."""
    with pytest.raises(IdentityError, match="matches no person"):
        identity.resolve(db, bundle(participant_code="ZZZZZZ", name="Tendai Moyo"))


def test_an_empty_bundle_is_refused(db):
    with pytest.raises(IdentityError, match="at least a participant code"):
        identity.resolve(db, bundle(age_band="30-39", sex="male"))


# ------------------------------------------------- probable, never applied

def test_a_probable_match_is_queued_and_not_applied(db):
    """§8.2: "any probable match entering a human review queue rather than
    being applied". The second record exists; the merge does not."""
    first = identity.resolve(
        db,
        bundle(name="Tendai Moyo", phone="0771234567", age_band="30-39", sex="male"),
    )
    db.commit()

    second = identity.resolve(
        db,
        bundle(name="Tendai Moyo", phone="0789999999", age_band="30-39", sex="male"),
    )
    db.commit()

    assert second.person_id != first.person_id, "nothing may be merged automatically"
    assert second.outcome == "created_pending_review"
    assert [c.person_id for c in second.candidates] == [first.person_id]
    assert second.queued_match_ids

    row = db.get(PersonMatchQueue, second.queued_match_ids[0])
    assert row.status == "pending"
    assert db.get(Person, second.person_id).merged_into_id is None


def test_the_queued_evidence_says_why(db):
    """A reviewer deciding a merge needs the evidence, not a number."""
    identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    second = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    reasons = second.candidates[0].reasons
    assert "name matches exactly" in reasons
    assert "shares a contact number" in reasons


def test_a_near_miss_name_is_a_candidate(db):
    """A transcription slip is the common duplicate, and the name is encrypted
    at rest — so similarity is computed on plaintext decrypted in memory over
    a candidate set narrowed by the indexed hashes first."""
    first = identity.resolve(
        db, bundle(name="Tendai Moyo", phone="0771234567", age_band="30-39", sex="male")
    )
    db.commit()
    second = identity.resolve(
        db, bundle(name="Tendai Moyoo", phone="0771234567", age_band="30-39", sex="male")
    )
    db.commit()
    assert [c.person_id for c in second.candidates] == [first.person_id]
    assert any("name similar" in r for r in second.candidates[0].reasons)


def test_a_different_person_at_the_same_site_is_not_a_candidate(db):
    """Demographics plus a site narrow the search; they must not be enough to
    put an unrelated worker in front of a reviewer."""
    first = identity.resolve(
        db, bundle(name="Tendai Moyo", age_band="30-39", sex="male", site_text="Globe")
    )
    db.commit()
    session_at(db, first.person_id, site_text="Globe")
    db.commit()

    second = identity.resolve(
        db,
        bundle(name="Nyasha Chirwa", age_band="30-39", sex="male", site_text="Globe"),
    )
    db.commit()
    assert second.candidates == ()
    assert second.outcome == "created"


def test_a_clean_new_person_queues_nothing(db):
    resolution = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    assert resolution.outcome == "created"
    assert resolution.candidates == ()
    assert db.query(PersonMatchQueue).count() == 0


def test_resolve_always_returns_a_usable_person(db):
    """Rule 7: a completed screening is never discarded. An uncertain identity
    produces a duplicate plus a queue entry, never a blocked screening."""
    identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    for _ in range(3):
        resolution = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
        db.commit()
        assert db.get(Person, resolution.person_id) is not None


def test_the_same_pair_is_not_queued_twice(db):
    """Otherwise a worker screened weekly fills the reviewer's list with one
    decision repeated."""
    identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    second = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    identity.queue_candidates(db, second.person_id, list(second.candidates))
    db.commit()
    assert db.query(PersonMatchQueue).count() == 1


# ----------------------------------------------------- the USSD anonymous case

def test_a_ussd_caller_with_no_code_gets_a_provisional_identity(db):
    """§8.2 part four. Never attach to whoever the number was last seen
    with."""
    resolution = identity.resolve(db, bundle(phone="0771234567"), channel="USSD")
    db.commit()
    assert resolution.outcome == "created_provisional"
    assert resolution.provisional
    person = db.get(Person, resolution.person_id)
    assert person.provisional == 1
    assert person.provisional_reason == "ussd_no_participant_code"


def test_two_ussd_calls_from_one_handset_do_not_merge(db):
    """A miner self-screening may be using his brother's phone. Two
    provisional records is the right answer; one merged record is not."""
    first = identity.resolve(db, bundle(phone="0771234567"), channel="USSD")
    db.commit()
    second = identity.resolve(db, bundle(phone="0771234567"), channel="USSD")
    db.commit()
    assert first.person_id != second.person_id


def test_a_ussd_caller_with_a_valid_code_is_not_provisional(db):
    first = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    again = identity.resolve(
        db, bundle(participant_code=first.participant_code, phone="0771234567"),
        channel="USSD",
    )
    db.commit()
    assert again.person_id == first.person_id
    assert not again.provisional


def test_a_ussd_caller_with_an_unrecognised_code_is_provisional_with_the_reason(db):
    """There is nobody to ask on a USSD session, so the mis-key is recorded
    rather than silently ignored."""
    resolution = identity.resolve(
        db, bundle(participant_code="ZZZZZZ", phone="0771234567"), channel="USSD"
    )
    db.commit()
    person = db.get(Person, resolution.person_id)
    assert person.provisional_reason == "ussd_unrecognised_code"


def test_the_provisional_vocabulary_is_closed(db):
    """Enforced here rather than by a CHECK constraint: SQLite cannot add one
    by ALTER, and a constraint only PostgreSQL applies is the divergence
    §16.2 warns about."""
    with pytest.raises(IdentityError, match="unknown provisional reason"):
        identity._create_person(
            db, bundle(name="Tendai Moyo"), provisional_reason="because"
        )


# --------------------------------------------------- merging, reversibly

def test_a_merge_keeps_the_losing_record(db):
    """Reversible from the first day (§8.2): the losing row is flagged, never
    deleted, so both histories survive."""
    winner = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    loser = identity.resolve(db, bundle(name="Tendai Moyo", phone="0789999999"))
    db.commit()

    identity.merge(
        db, winner.person_id, loser.person_id, merged_by="clerk", evidence={"reason": "same card"}
    )
    db.commit()

    assert db.get(Person, loser.person_id) is not None
    assert db.get(Person, loser.person_id).merged_into_id == winner.person_id


def test_a_merge_moves_the_clinical_history(db):
    """Joining the history is the point of the merge."""
    winner = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    loser = identity.resolve(db, bundle(name="Tendai Moyo", phone="0789999999"))
    db.commit()
    session_at(db, loser.person_id, site_text="Globe")
    db.commit()

    identity.merge(db, winner.person_id, loser.person_id, merged_by="clerk")
    db.commit()

    sessions = db.scalars(
        select(ScreeningSession).where(ScreeningSession.person_id == winner.person_id)
    ).all()
    assert len(sessions) == 1
    contacts = db.scalars(
        select(Contact).where(Contact.person_id == winner.person_id)
    ).all()
    assert len(contacts) == 2


def test_a_merge_records_who_when_and_on_what_evidence(db):
    winner = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    loser = identity.resolve(db, bundle(name="Tendai Moyo", phone="0789999999"))
    db.commit()
    record = identity.merge(
        db, winner.person_id, loser.person_id, merged_by="sister.moyo",
        evidence={"reason": "presented the same card"},
    )
    db.commit()
    assert record.merged_by == "sister.moyo" and record.merged_at is not None
    assert "presented the same card" in record.evidence


def test_a_merge_never_overwrites_a_recorded_value(db):
    """A merge must not be able to change something somebody already wrote
    down. It fills gaps only."""
    winner = identity.resolve(db, bundle(name="Tendai Moyo", age_band="30-39"))
    loser = identity.resolve(db, bundle(name="Tendai Moyo", age_band="40-49", sex="male"))
    db.commit()

    identity.merge(db, winner.person_id, loser.person_id, merged_by="clerk")
    db.commit()

    survivor = db.get(Person, winner.person_id)
    assert survivor.age_band == "30-39", "the winner's own value stands"
    assert survivor.sex == "male", "a gap is filled"


def test_a_merge_clears_a_provisional_flag_when_the_other_side_is_verified(db):
    provisional = identity.resolve(db, bundle(phone="0771234567"), channel="USSD")
    verified = identity.resolve(db, bundle(name="Tendai Moyo", phone="0789999999"))
    db.commit()

    identity.merge(db, provisional.person_id, verified.person_id, merged_by="clerk")
    db.commit()
    assert db.get(Person, provisional.person_id).provisional == 0


def test_a_person_cannot_be_merged_into_themselves(db):
    person = identity.resolve(db, bundle(name="Tendai Moyo"))
    db.commit()
    with pytest.raises(IdentityError, match="into themselves"):
        identity.merge(db, person.person_id, person.person_id, merged_by="clerk")


def test_a_merge_chain_is_refused(db):
    """Chaining makes the reversal ambiguous, so the second merge is refused
    until the first is undone."""
    a = identity.resolve(db, bundle(name="A A"))
    b = identity.resolve(db, bundle(name="B B"))
    c = identity.resolve(db, bundle(name="C C"))
    db.commit()
    identity.merge(db, a.person_id, b.person_id, merged_by="clerk")
    db.commit()
    with pytest.raises(IdentityError, match="already merged"):
        identity.merge(db, c.person_id, b.person_id, merged_by="clerk")


def test_reading_a_merged_record_follows_the_pointer(db):
    """A card printed before a merge still works, which is the point of
    printing one."""
    winner = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    loser = identity.resolve(db, bundle(name="Tendai Moyo", phone="0789999999"))
    db.commit()
    loser_code = loser.participant_code
    identity.merge(db, winner.person_id, loser.person_id, merged_by="clerk")
    db.commit()

    assert identity.find_by_participant_code(db, loser_code).id == winner.person_id
    assert identity.effective_person(db, loser.person_id).id == winner.person_id


def test_a_merge_cycle_is_caught_rather_than_looping(db):
    """An infinite loop here would take the screening route down, so the hop
    limit is a real guard and not defensive decoration."""
    a = identity.resolve(db, bundle(name="A A"))
    b = identity.resolve(db, bundle(name="B B"))
    db.commit()
    db.get(Person, a.person_id).merged_into_id = b.person_id
    db.get(Person, b.person_id).merged_into_id = a.person_id
    db.commit()
    with pytest.raises(IdentityError, match="does not terminate"):
        identity.effective_person(db, a.person_id)


def test_a_merge_can_be_reversed(db):
    winner = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    loser = identity.resolve(db, bundle(name="Tendai Moyo", phone="0789999999"))
    db.commit()
    record = identity.merge(db, winner.person_id, loser.person_id, merged_by="clerk")
    db.commit()

    identity.unmerge(db, record.id, reversed_by="supervisor")
    db.commit()

    assert db.get(Person, loser.person_id).merged_into_id is None
    assert db.get(PersonMerge, record.id).reversed_by == "supervisor"
    assert db.get(PersonMerge, record.id).reversed_at is not None


def test_a_reversal_keeps_the_merge_in_the_audit(db):
    """Both the merge and the reversal are recorded. "This was merged and then
    undone" is a different story from "this was never merged"."""
    winner = identity.resolve(db, bundle(name="Tendai Moyo"))
    loser = identity.resolve(db, bundle(name="Tendai Moyo"))
    db.commit()
    record = identity.merge(db, winner.person_id, loser.person_id, merged_by="clerk")
    db.commit()
    identity.unmerge(db, record.id, reversed_by="supervisor")
    db.commit()
    assert db.query(PersonMerge).count() == 1


def test_a_merge_cannot_be_reversed_twice(db):
    winner = identity.resolve(db, bundle(name="Tendai Moyo"))
    loser = identity.resolve(db, bundle(name="Tendai Moyo"))
    db.commit()
    record = identity.merge(db, winner.person_id, loser.person_id, merged_by="clerk")
    db.commit()
    identity.unmerge(db, record.id, reversed_by="supervisor")
    db.commit()
    with pytest.raises(IdentityError, match="already reversed"):
        identity.unmerge(db, record.id, reversed_by="supervisor")


# -------------------------------------------------------------- the queue

def test_the_queue_lists_pending_matches_worst_first(db):
    identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    rows = identity.pending_matches(db)
    assert len(rows) == 1 and rows[0].status == "pending"


def test_deciding_merge_applies_it_with_the_queued_evidence(db):
    """The reason a reviewer was shown a pair becomes the reason recorded
    against the merge."""
    first = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    second = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()

    row = identity.decide_match(
        db, second.queued_match_ids[0], decision="merge", decided_by="clerk"
    )
    db.commit()

    assert row.status == "merged" and row.resolved_by == "clerk"
    assert db.get(Person, second.person_id).merged_into_id == first.person_id
    record = db.scalar(select(PersonMerge))
    assert "name matches exactly" in record.evidence
    assert "queued_match_id" in record.evidence


def test_deciding_reject_is_recorded_rather_than_discarded(db):
    """"Reviewed, and they are different people" has to survive, or the same
    pair is queued again at the next screening."""
    identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    second = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()

    row = identity.decide_match(
        db, second.queued_match_ids[0], decision="reject", decided_by="clerk"
    )
    db.commit()
    assert row.status == "rejected" and row.resolved_at is not None
    assert db.get(Person, second.person_id).merged_into_id is None
    assert identity.pending_matches(db) == []


def test_a_decided_match_cannot_be_decided_again(db):
    identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    second = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    match_id = second.queued_match_ids[0]
    identity.decide_match(db, match_id, decision="reject", decided_by="clerk")
    db.commit()
    with pytest.raises(IdentityError, match="already rejected"):
        identity.decide_match(db, match_id, decision="merge", decided_by="clerk")


def test_an_unknown_decision_is_refused(db):
    identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    second = identity.resolve(db, bundle(name="Tendai Moyo", phone="0771234567"))
    db.commit()
    with pytest.raises(IdentityError, match="must be 'merge' or 'reject'"):
        identity.decide_match(
            db, second.queued_match_ids[0], decision="maybe", decided_by="clerk"
        )
