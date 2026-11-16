"""Seed demonstration data into the version two tables.

`docs/IMPLEMENTATION_PLAN.md` item 1.12 and the Week 8 roadmap line,
"demonstration data reseeded". A separate script from `seed_demo_data.py`
rather than a rewrite of it, because the dashboard and the mobile
application still read the v1 tables until the adapter (item 1.11) lands,
and deleting their demonstration data before then would take the demo down.
The v1 seeder goes away with `drop_v1`.

**Two layers, and the second one is gated.**

  **The reference and identity layer** -- sites, programmes, facilities,
  people, contacts, exposure profiles, a queued near-duplicate pair and a
  provisional USSD caller. All structured data: no clinical content and no
  patient-facing wording anywhere in it. Always seedable.

  **The clinical layer** -- consent records, sessions, answers, per-condition
  results and referrals. Requires an approved instrument and an approved
  consent text, and **this script will not invent either**. A plausible
  invented question set is the most dangerous artefact this repository could
  hold (`clinical/README.md`), and a consent form nobody approved is worse:
  it would be indistinguishable from a reviewed one a month later.

So where the clinical layer cannot run, the script seeds the first layer,
says exactly what is missing and who owns it, and exits zero. That is not a
degraded mode; it is the honest state of the project until instrument
version one exists.

**Results are produced, never written.** Where the clinical layer does run,
every session goes through `services/screening_v2.screen()` -- the real §10.3
pipeline, with real scoring, real deterioration comparison, real safety
overrides and real provenance. The v1 seeder writes pre-computed tiers
directly, which is defensible for a v1 row whose tier came from a model
call, and indefensible here: a v2 result row records the instrument version
and ruleset that produced it, and a hand-written tier would be a row
claiming a provenance it does not have.

Usage:
    cd backend
    ./venv/Scripts/python.exe scripts/seed_v2_demo_data.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from _demo_guard import refuse_unless_local  # noqa: E402

from database import get_fresh_session, init_db  # noqa: E402
from db_models import (  # noqa: E402
    ConsentRecord,
    Contact,
    ExposureProfile,
    Facility,
    Person,
    PersonMatchQueue,
    PersonMerge,
    Programme,
    ScreeningAnswer,
    ScreeningResult,
    ScreeningSession,
    Site,
)
from services import crypto, identity, instrument_store  # noqa: E402
from services.identity import IdentityBundle  # noqa: E402

# ─────────────────────────────────────────────── the reference layer

#: Real places in the Kwekwe and Shurugwi gold belt, with districts set so a
#: district coordinator's scope means something rather than matching nothing.
SITES = [
    ("Globe & Phoenix", "Kwekwe", "Midlands", "shaft"),
    ("Sherwood Block", "Kwekwe", "Midlands", "open_cast"),
    ("Gaika", "Kwekwe", "Midlands", "shaft"),
    ("Peak Mine", "Shurugwi", "Midlands", "shaft"),
    ("Ironwood Workings", "Shurugwi", "Midlands", "alluvial"),
]

FACILITIES = [
    ("Kwekwe District Hospital", "district", "Corner Robert Mugabe / Sixth Ave"),
    ("Shurugwi District Hospital", "district", "Shurugwi town centre"),
    ("Gweru Provincial Hospital", "provincial", "Gweru"),
]

#: One community cohort and one employer cohort. The employer one exists so
#: §14.4's boundary is demonstrable rather than theoretical: a programme
#: sponsor reading the dashboard must see this cohort and no other.
PROGRAMMES = [
    ("COMMUNITY", "Community outreach", "community", "Ministry of Health", "Ministry of Health"),
    ("MINECO", "Mine Co occupational health", "employer", "Mine Co", "Mine Co"),
]

#: Names and numbers are fictional and obviously so. Age band, sex and
#: language are structured values the schema defines, not free text.
PEOPLE = [
    # name, phone, site index, age_band, sex, language, occupation, years, controls
    ("Tendai Moyo",       "0771000001", 0, "30-39", "male",   "sn", "driller",   "5-9",  "none"),
    ("Rudo Phiri",        "0771000002", 0, "40-49", "female", "sn", "panner",    "10+",  "mask_sometimes"),
    ("Kudakwashe Marecha","0771000003", 1, "20-29", "male",   "en", "loader",    "2-4",  "mask_always"),
    ("Chipo Banda",       "0771000004", 2, "50-59", "female", "nd", "crusher",    "10+",  "none"),
    ("Farai Nyathi",      "0771000005", 3, "30-39", "male",   "nd", "driller",   "5-9",  "wet_drilling"),
    ("Simba Chirwa",      "0771000006", 4, "20-29", "male",   "sn", "panner",    "0-1",  "mask_sometimes"),
    ("Tapiwa Dube",       "0771000007", 1, "40-49", "male",   "en", "blaster",   "10+",  "none"),
    ("Nyasha Mutasa",     "0771000008", 2, "30-39", "female", "sn", "sorter",    "2-4",  "mask_always"),
]

#: Deliberately close to PEOPLE[0] on name and site but a different number:
#: enough to score above the review threshold and be QUEUED, never merged.
#: §8.2 -- a probable match is a question for a human, not an action.
NEAR_DUPLICATE = ("Tendai Moyo", "0779000099", 0, "30-39", "male", "sn")

#: A USSD caller with no participant code: a provisional person, flagged
#: unverified, never attached to whoever the number was last seen with.
PROVISIONAL_PHONE = "0771000009"

TABLES_OWNED = (
    ScreeningResult, ScreeningAnswer, ScreeningSession, ConsentRecord,
    ExposureProfile, PersonMerge, PersonMatchQueue, Contact, Person,
    Programme, Site,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _clear(db) -> None:
    """Delete in dependency order so this is re-runnable from any state.

    `facilities` is deliberately NOT cleared: the v1 seeder owns that table
    and both scripts use it, so clearing it here would delete the referral
    targets the v1 demonstration depends on.
    """
    for model in TABLES_OWNED:
        db.query(model).delete()
    db.commit()


def _seed_reference(db) -> dict:
    # Each insert checks first, so calling this twice is harmless. The script
    # clears before seeding anyway, but a function that is only safe when
    # something else ran first is a trap for the next caller -- and the
    # facility block below was already written this way, so the inconsistency
    # was the bug rather than the duplicate.
    sites = {}
    for name, district, province, kind in SITES:
        row = db.query(Site).filter(Site.name == name).first()
        if row is None:
            row = Site(name=name, district=district, province=province, type=kind,
                       sector="asm_gold", curated=1)
            db.add(row)
            db.flush()
        sites[name] = row.id

    for name, level, address in FACILITIES:
        if not db.query(Facility).filter(Facility.name == name).first():
            db.add(Facility(name=name, level=level, address=address))

    programmes = {}
    for code, name, kind, payer, owner in PROGRAMMES:
        row = db.query(Programme).filter(Programme.code == code).first()
        if row is None:
            row = Programme(code=code, name=name, kind=kind, payer=payer,
                            data_owner=owner, consent_text_code="CORE")
            db.add(row)
            db.flush()
        programmes[code] = row.id

    db.commit()
    return {"sites": sites, "programmes": programmes}


def _seed_people(db, refs: dict) -> dict:
    """Resolve each person through the real identity service.

    Not inserted directly: `identity.resolve()` is what mints a participant
    code from the unambiguous alphabet, hashes the number under the keyed
    hash, encrypts the recoverable copy and queues a probable match instead
    of applying it. Inserting rows by hand would produce a database that
    looks right and exercises none of that.
    """
    site_names = [s[0] for s in SITES]
    created = []

    for name, phone, site_index, age_band, sex, language, occupation, years, controls in PEOPLE:
        site_name = site_names[site_index]
        resolution = identity.resolve(db, IdentityBundle(
            name=name, phone=phone, age_band=age_band, sex=sex,
            language=language, site_id=refs["sites"][site_name],
            site_text=site_name,
        ), channel="APP")
        db.add(ExposureProfile(
            person_id=resolution.person_id, sector="asm_gold",
            occupation=occupation, years_band=years, controls=controls,
            wet_or_dry="wet" if controls == "wet_drilling" else "dry",
            recorded_at=_utcnow(),
        ))
        created.append(resolution)
    db.commit()

    # The near-duplicate, which must be queued rather than merged.
    name, phone, site_index, age_band, sex, language = NEAR_DUPLICATE
    duplicate = identity.resolve(db, IdentityBundle(
        name=name, phone=phone, age_band=age_band, sex=sex, language=language,
        site_id=refs["sites"][site_names[site_index]], site_text=site_names[site_index],
    ), channel="APP")

    # A USSD caller with no code: provisional, and never attached to the
    # person a number was last seen with.
    provisional = identity.resolve(
        db, IdentityBundle(phone=PROVISIONAL_PHONE), channel="USSD")
    db.commit()

    return {
        "people": created,
        "duplicate": duplicate,
        "provisional": provisional,
        "queued": len(duplicate.queued_match_ids),
    }


# ─────────────────────────────────────────────── the clinical layer

def _clinical_prerequisites(db) -> tuple[dict | None, int | None, list[str]]:
    """What the clinical layer needs, and what is missing.

    Returns the active instrument, the approved consent text id, and a list of
    plain-English reasons the layer cannot run.
    """
    missing: list[str] = []

    from db_models import Instrument

    instrument = None
    approved = (
        db.query(Instrument.code)
        .filter(Instrument.status == "approved")
        .distinct()
        .all()
    )
    for (code,) in approved:
        try:
            instrument = instrument_store.read_active(db, code)
            break
        except Exception:
            continue

    if instrument is None:
        missing.append(
            "No approved instrument is loaded. Instrument version one is the "
            "Clinical Lead's deliverable (Master Reference §12.5, roadmap "
            "Week 6). Until it exists there is no question set to answer and "
            "no rules to score against -- and this script will not invent "
            "one, because a plausible invented question set is the most "
            "dangerous artefact this repository could hold."
        )

    from db_models import ConsentText

    text = (
        db.query(ConsentText)
        .filter(ConsentText.status == "approved")
        .order_by(ConsentText.version.desc())
        .first()
    )
    if text is None:
        missing.append(
            "No approved consent text exists. A consent form is patient-facing "
            "wording and needs the Clinical Lead's recorded approval before it "
            "ships (`CLAUDE.md`), so this script will not write one: a consent "
            "form nobody approved would be indistinguishable from a reviewed "
            "one a month later."
        )

    return instrument, (text.id if text else None), missing


def _seed_clinical(db, state: dict, instrument: dict, consent_text_id: int) -> dict:
    """Run real screenings through the real pipeline.

    Answer profiles are read from the instrument's own regression fixtures
    where they exist, so the demonstration distribution is the one the
    Clinical Lead stated rather than one chosen here. Nothing in this
    function decides what a tier should be.
    """
    from services import consent as consent_service
    from services import screening_v2

    code = instrument["code"]
    fixtures = _fixture_profiles(code)
    if not fixtures:
        return {"sessions": 0, "note": (
            f"{code} has no regression fixtures beside it, so there are no "
            "answer profiles to seed from. Fixtures are part of the Clinical "
            "Lead's deliverable (an expected tier is a clinical statement); "
            "see `clinical/fixtures.schema.json`."
        )}

    sessions = 0
    for index, person in enumerate(state["people"]):
        profile = fixtures[index % len(fixtures)]
        consent_service.record_many(
            db, person.person_id,
            {"screening_and_referral": True, "longitudinal_record": True,
             "contact_by_message": True},
            consent_text_id=consent_text_id, channel="APP",
            recorded_by="demo.seed",
        )
        db.commit()
        try:
            screening_v2.screen(db, screening_v2.ScreeningRequest(
                person_id=person.person_id,
                client_session_uuid=str(uuid.uuid4()),
                answers=dict(profile["answers"]),
                channel=profile.get("channel", "app").upper(),
                screened_by="sister.moyo",
                instrument_code=code,
                started_at=_utcnow() - timedelta(minutes=6),
            ))
            sessions += 1
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            print(f"  profile {profile['name']!r} did not screen: {exc}")
    return {"sessions": sessions, "note": None}


def _fixture_profiles(instrument_code: str) -> list[dict]:
    """Answer profiles from the instrument's regression fixtures, if present."""
    import yaml

    repo = BACKEND.parent
    for folder in (repo / "clinical" / "instruments", repo / "clinical" / "examples"):
        for path in sorted(folder.glob(f"{instrument_code}*.fixtures.yaml")) if folder.exists() else []:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            profiles = [
                p for p in (doc.get("profiles") or [])
                if p.get("answers") and not (p.get("expect") or {}).get("incomplete")
            ]
            if profiles:
                return profiles
    return []


# ─────────────────────────────────────────────────────────── entry point

def seed() -> None:
    refuse_unless_local("seed_v2_demo_data.py")

    if not crypto.keys_configured():
        raise SystemExit(
            "\nIDENTITY_HMAC_KEY and CONTACT_ENCRYPTION_KEY are not set, so no "
            "person can be created: a telephone number is stored as a keyed "
            "hash plus an encrypted copy, never in the clear.\n\n"
            "Generate a pair for local use:\n\n"
            "    python -c \"import base64,os;print('IDENTITY_HMAC_KEY='+base64.urlsafe_b64encode(os.urandom(32)).decode())\"\n"
            "    python -c \"from cryptography.fernet import Fernet;print('CONTACT_ENCRYPTION_KEY='+Fernet.generate_key().decode())\"\n\n"
            "Put them in backend/.env. Keys generated locally are for local "
            "data only -- the production pair lives on the service and in the "
            "password manager, and losing it makes real data unrecoverable.\n"
        )

    init_db()
    db = get_fresh_session()
    try:
        _clear(db)
        refs = _seed_reference(db)
        state = _seed_people(db, refs)

        instrument, consent_text_id, missing = _clinical_prerequisites(db)
        clinical = {"sessions": 0, "note": None}
        if not missing:
            clinical = _seed_clinical(db, state, instrument, consent_text_id)

        people = db.query(Person).count()
        contacts = db.query(Contact).count()
        queued = db.query(PersonMatchQueue).count()
        results = db.query(ScreeningResult).count()

        print("\nReference and identity layer")
        print(f"  sites              {len(refs['sites'])}")
        print(f"  programmes         {len(refs['programmes'])} (one community, one employer)")
        print(f"  facilities         {db.query(Facility).count()} (shared with the v1 seeder, not cleared)")
        print(f"  people             {people}")
        print(f"  contacts           {contacts} (number hashed and encrypted, never in the clear)")
        print(f"  exposure profiles  {db.query(ExposureProfile).count()}")
        print(f"  queued matches     {queued} (probable, awaiting a human -- never applied)")
        print(f"  provisional person 1 (USSD caller with no participant code)")

        print("\nClinical layer")
        if missing:
            print(f"  NOT SEEDED -- {len(missing)} prerequisite(s) missing:\n")
            for reason in missing:
                print(f"    - {reason}\n")
            print("  Everything above is seeded and usable. Sessions, results and")
            print("  referrals arrive with instrument version one.")
        else:
            print(f"  sessions           {clinical['sessions']}")
            print(f"  results            {results} (produced by the §10.3 pipeline, not written)")
            if clinical["note"]:
                print(f"  note: {clinical['note']}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
