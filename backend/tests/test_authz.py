"""Roles, scopes and password hashing.

Master Reference v1.0 §16.3. **The tests that matter here are the negative
ones.** Every row in §16.3's table has a "cannot see" column, and a role
defined only by what it may do is a role nobody can test. §10's Phase One
requirement is explicit: "negative tests for each role attempting access that
must fail".

Three properties:

  **Deny by default.** A capability a role does not list is refused, including
  one that does not exist. A new capability is therefore invisible to every
  role until somebody grants it deliberately.

  **A role plus a scope, never a role alone.** A facility user with no
  facility passes every capability check and is bounded by nothing, so
  creating one is refused.

  **A missing scope narrows to nothing, never to everything.** That is the
  whole reason the scoped-query helpers exist instead of an inline `if`.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import database
from db_models import Base, Facility, Person, Programme, Referral, User
from services import authz
from services.authz import AuthzError, Principal


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'authz.db'}")
    database.enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def principal(role: str, **scope) -> Principal:
    return Principal(user_id=1, email=f"{role}@example.org", role=role, scope=scope)


# ------------------------------------------------------------ the role table

def test_the_seven_logged_in_roles_match_16_3():
    """§16.3's table has eight rows; the eighth is the person screened, who
    has no login and reaches their own record through USSD and the card in
    their pocket."""
    assert set(authz.SPECIFIED_ROLES) == {
        "village_health_worker",
        "facility_user",
        "district_coordinator",
        "national_stakeholder",
        "researcher",
        "programme_sponsor",
        "administrator",
    }


def test_every_role_records_what_it_cannot_see():
    """The "cannot see" column is the sentence a negative test is written
    from, so it lives in code rather than only in the document."""
    for role in authz.ROLES:
        assert role.cannot, role.code
        assert len(role.cannot) > 15, role.code


def test_every_capability_is_held_by_at_least_one_role():
    """A capability no role holds is dead code pretending to be a
    permission."""
    held = set().union(*(r.capabilities for r in authz.ROLES))
    assert set(authz.CAPABILITIES) - held == set()


def test_the_prototype_roles_are_marked_and_not_a_target_state():
    assert authz.LEGACY_ROLES == ("hospital", "cimas")
    for code in authz.LEGACY_ROLES:
        assert code not in authz.SPECIFIED_ROLES


# ------------------------------------------------------------ deny by default

def test_an_unknown_capability_is_refused():
    assert principal("administrator").allows("nonsense") is False


def test_an_unknown_role_holds_nothing():
    assert principal("wizard").allows("aggregate.read") is False


def test_a_deactivated_principal_holds_nothing():
    p = Principal(user_id=1, email="a@b.c", role="administrator", scope={}, active=False)
    assert p.allows("admin.manage") is False


# -------------------------------------- the negative tests §16.3 asks for

@pytest.mark.parametrize(
    "role,capability",
    [
        # National stakeholder: "Any identified record."
        ("national_stakeholder", "person.read"),
        ("national_stakeholder", "screening.read"),
        ("national_stakeholder", "referral.read"),
        # Researcher: "Direct identifiers and the re-identification key."
        ("researcher", "person.read"),
        ("researcher", "screening.read"),
        # Programme sponsor: "Individual results; anything outside their
        # cohort." §14.4 is the most consequential governance rule here.
        ("programme_sponsor", "person.read"),
        ("programme_sponsor", "screening.read"),
        ("programme_sponsor", "referral.read"),
        # Administrator: "Administrative access is not a licence to read
        # records." An administrator needing a record needs a clinical role
        # too, which is a decision somebody makes.
        ("administrator", "person.read"),
        ("administrator", "screening.read"),
        # Facility user: "Screenings with no referral to them."
        ("facility_user", "screening.read"),
        ("facility_user", "aggregate.read"),
        # District coordinator: "Identified records outside their district;
        # clinical detail beyond what coordination requires."
        ("district_coordinator", "person.read"),
        ("district_coordinator", "screening.read"),
        # Village health worker: "national data".
        ("village_health_worker", "aggregate.read"),
        ("village_health_worker", "export.pseudonymised"),
        # Nobody but an administrator manages users.
        ("village_health_worker", "admin.manage"),
        ("facility_user", "admin.manage"),
        ("researcher", "admin.manage"),
        # A merge mixes two clinical histories if wrong: the narrowest
        # capability in the model.
        ("village_health_worker", "person.merge"),
        ("facility_user", "person.merge"),
    ],
)
def test_a_role_is_refused_what_16_3_says_it_cannot_see(role, capability):
    assert principal(role).allows(capability) is False, (
        f"{role} must not hold {capability}: {authz.BY_CODE[role].cannot}"
    )


@pytest.mark.parametrize(
    "role,capability",
    [
        ("village_health_worker", "screening.write"),
        ("village_health_worker", "person.read"),
        ("village_health_worker", "consent.write"),
        ("facility_user", "referral.read"),
        ("facility_user", "referral.close"),
        ("district_coordinator", "aggregate.read"),
        ("national_stakeholder", "aggregate.read"),
        ("researcher", "export.pseudonymised"),
        ("programme_sponsor", "aggregate.read"),
        ("administrator", "admin.manage"),
        ("administrator", "person.merge"),
    ],
)
def test_a_role_holds_what_16_3_says_it_can_see(role, capability):
    assert principal(role).allows(capability) is True


def test_only_an_administrator_can_merge_among_the_specified_roles():
    """A false merge is a clinical safety event that mixes two histories with
    no way to detect it by inspection (§8.2)."""
    holders = [
        r.code for r in authz.ROLES
        if "person.merge" in r.capabilities and r.code not in authz.LEGACY_ROLES
    ]
    assert holders == ["administrator"]


def test_no_role_can_read_an_identified_record_and_export_pseudonymised_data():
    """A researcher holding both would hold the re-identification key in
    practice, whatever the policy says."""
    for role in authz.ROLES:
        both = {"person.read", "export.pseudonymised"} <= role.capabilities
        assert not both, role.code


# ------------------------------------------------- a role needs its scope

@pytest.mark.parametrize(
    "role,field",
    [
        ("village_health_worker", "site_ids"),
        ("facility_user", "facility_id"),
        ("district_coordinator", "district"),
        ("programme_sponsor", "programme_id"),
    ],
)
def test_a_scoped_role_declares_its_scope_field(role, field):
    assert authz.BY_CODE[role].scope_field == field


def test_creating_a_scoped_role_without_a_scope_is_refused(db):
    """It passes every capability check and is bounded by nothing, which is
    worse than no account at all."""
    with pytest.raises(AuthzError, match="needs facility_id"):
        authz.create_user(db, "f@example.org", "password123", "facility_user")


def test_creating_a_scoped_role_with_a_scope_succeeds(db):
    db.add(Facility(name="Kwekwe District Hospital", level="district"))
    db.flush()
    facility_id = db.scalar(select(Facility.id))
    user = authz.create_user(
        db, "f@example.org", "password123", "facility_user", facility_id=facility_id
    )
    db.commit()
    assert authz.principal_for(user).scope == {"facility_id": facility_id}


def test_a_village_health_worker_carries_several_sites(db):
    """A worker covers a handful of workings, not one and not all of them."""
    user = authz.create_user(
        db, "v@example.org", "password123", "village_health_worker", site_ids=[3, 7, 9]
    )
    db.commit()
    assert authz.principal_for(user).scope == {"site_ids": [3, 7, 9]}


def test_an_unscoped_role_needs_no_scope(db):
    user = authz.create_user(db, "n@example.org", "password123", "national_stakeholder")
    db.commit()
    assert authz.principal_for(user).scope == {}


def test_a_prototype_role_cannot_be_given_to_a_new_user(db):
    """They exist only for the transition and are deleted with the v1
    adapter."""
    with pytest.raises(AuthzError, match="prototype account"):
        authz.create_user(db, "h@example.org", "password123", "hospital")


def test_an_unknown_role_is_refused(db):
    with pytest.raises(AuthzError, match="unknown role"):
        authz.create_user(db, "x@example.org", "password123", "wizard")


def test_a_duplicate_email_is_refused(db):
    authz.create_user(db, "n@example.org", "password123", "researcher")
    db.commit()
    with pytest.raises(AuthzError, match="already exists"):
        authz.create_user(db, "N@EXAMPLE.ORG", "password123", "researcher")


# ------------------------------- a missing scope narrows to nothing

def test_a_facility_scope_narrows_the_query(db):
    db.add_all([Facility(name="A", level="district"), Facility(name="B", level="district")])
    db.flush()
    a, b = db.scalars(select(Facility.id)).all()
    db.add_all([
        Referral(facility_id=a, referral_code="SG-AAAA"),
        Referral(facility_id=b, referral_code="SG-BBBB"),
    ])
    db.commit()

    scoped = authz.for_facility(
        select(Referral), Referral.facility_id, principal("facility_user", facility_id=a)
    )
    assert [r.referral_code for r in db.scalars(scoped).all()] == ["SG-AAAA"]


def test_a_facility_role_with_no_facility_sees_nothing(db):
    """**The assertion that justifies these helpers existing.** The failure
    mode of a missing scope must be an empty result, never an unfiltered
    one."""
    db.add(Facility(name="A", level="district"))
    db.flush()
    db.add(Referral(referral_code="SG-AAAA", facility_id=db.scalar(select(Facility.id))))
    db.commit()
    scoped = authz.for_facility(
        select(Referral), Referral.facility_id, principal("facility_user")
    )
    assert db.scalars(scoped).all() == []


def test_a_site_role_with_no_sites_sees_nothing(db):
    db.add(Person(participant_code="AAAAAA"))
    db.commit()
    scoped = authz.for_sites(
        select(Person), Person.id, principal("village_health_worker")
    )
    assert db.scalars(scoped).all() == []


def test_a_district_role_with_no_district_sees_nothing(db):
    db.add(Person(participant_code="AAAAAA"))
    db.commit()
    scoped = authz.for_district(
        select(Person), Person.age_band, principal("district_coordinator")
    )
    assert db.scalars(scoped).all() == []


def test_a_programme_role_with_no_programme_sees_nothing(db):
    db.add(Programme(code="P1", name="Programme one"))
    db.commit()
    scoped = authz.for_programme(
        select(Programme), Programme.id, principal("programme_sponsor")
    )
    assert db.scalars(scoped).all() == []


# ------------------------------------------------------------- passwords

def test_a_password_round_trips():
    stored = authz.hash_password("correct-horse-battery")
    assert authz.verify_password("correct-horse-battery", stored)
    assert not authz.verify_password("correct-horse-batterx", stored)


def test_the_hash_is_not_the_password():
    stored = authz.hash_password("correct-horse-battery")
    assert "correct-horse-battery" not in stored
    assert stored.startswith("scrypt$")


def test_the_same_password_hashes_differently_each_time():
    """Per-user salt: two users with the same password must not have the same
    stored value, or cracking one cracks both."""
    assert authz.hash_password("same-password") != authz.hash_password("same-password")


def test_the_parameters_travel_with_the_hash():
    """So raising them later does not invalidate existing passwords."""
    scheme, n, r, p, _salt, _hash = authz.hash_password("x" * 12).split("$")
    assert scheme == "scrypt" and int(n) >= 2 ** 14 and int(r) == 8 and int(p) == 1


def test_a_short_password_is_refused():
    with pytest.raises(AuthzError, match="at least 8"):
        authz.hash_password("short")


@pytest.mark.parametrize("stored", [None, "", "garbage", "scrypt$bad", "bcrypt$1$2$3$4$5"])
def test_a_malformed_hash_is_not_a_way_in(stored):
    """A corrupted row must fail closed rather than raise, because a raised
    exception in a login path is a different bug with the same cause."""
    assert authz.verify_password("anything", stored) is False


def test_an_empty_password_never_verifies():
    stored = authz.hash_password("correct-horse-battery")
    assert authz.verify_password("", stored) is False


# ----------------------------------------------------------- authenticate

def test_authenticate_accepts_the_right_password(db):
    authz.create_user(db, "r@example.org", "password123", "researcher")
    db.commit()
    assert authz.authenticate(db, "r@example.org", "password123") is not None


def test_authenticate_is_case_insensitive_on_email(db):
    authz.create_user(db, "r@example.org", "password123", "researcher")
    db.commit()
    assert authz.authenticate(db, "R@Example.ORG", "password123") is not None


def test_authenticate_refuses_a_deactivated_user(db):
    user = authz.create_user(db, "r@example.org", "password123", "researcher")
    db.commit()
    user.active = 0
    db.commit()
    assert authz.authenticate(db, "r@example.org", "password123") is None


def test_authenticate_refuses_an_unknown_email(db):
    assert authz.authenticate(db, "nobody@example.org", "password123") is None


# ------------------------------------------- the prototype account fuse

def test_the_prototype_accounts_are_live_while_no_user_exists(db):
    assert authz.any_user_exists(db) is False


def test_creating_a_user_retires_the_prototype_accounts(db):
    """Self-disarming rather than a flag. A flag nobody turns off is how a
    prototype credential reaches production."""
    authz.create_user(db, "admin@example.org", "password123", "administrator")
    db.commit()
    assert authz.any_user_exists(db) is True


def test_a_deactivated_user_still_counts_as_a_user(db):
    """Otherwise deactivating the last account would quietly bring the
    environment-variable credentials back to life."""
    user = authz.create_user(db, "admin@example.org", "password123", "administrator")
    db.commit()
    user.active = 0
    db.commit()
    assert authz.any_user_exists(db) is True
