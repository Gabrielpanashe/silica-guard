"""Who may read an identified record, and who may merge two people.

Master Reference v1.0 §16.3's "cannot see" column and §14.4.

**The hole this closes.** `backend/routers/persons.py` used the plain v1 token
dependency on every route, so until 2 November 2026:

  `GET /api/v2/persons/{code}` returned a **decrypted name and telephone
  number** to any authenticated role — including the three §16.3 refuses an
  identified record outright: a national stakeholder ("Any identified
  record"), a researcher ("Direct identifiers and the re-identification key")
  and a programme sponsor (§14.4).

  `POST /api/v2/persons/merges` let any of them **merge two people**, which
  `ARCHITECTURE.md` calls a clinical safety event belonging to one named role.
  A wrong merge joins two clinical histories and attributes one worker's
  deterioration to another.

  **And none of it was recorded.** `person.read`, `person.merge`,
  `person.unmerge` and `person.match_decide` are all declared in
  `audit.ACTIONS`; nothing wrote any of them. So `GET /api/v2/audit/persons/
  {id}` — whose docstring says "'who has read my record?' is a question a
  worker is entitled to an answer to" — answered an empty list however many
  people had read it. That is the promise this file makes true.

The role table was correct the whole time; the routes did not consult it. The
tests below are written from the table rather than from a list of roles I
chose, so a capability moved in `authz.ROLES` moves the expectation with it.
"""

import pytest
from sqlalchemy import select

import database
from services import authz, crypto

#: Every role an account can actually be created in, and whether §16.3 lets it
#: reach an identified record. The two prototype roles are excluded because
#: `create_user` refuses them -- they exist only on the env-var login path,
#: which `test_the_prototype_accounts_keep_working` covers separately.
REAL = [r for r in authz.ROLES if r.code not in authz.LEGACY_ROLES]

READERS = sorted(r.code for r in REAL if "person.read" in r.capabilities)
NON_READERS = sorted(r.code for r in REAL if "person.read" not in r.capabilities)
MERGERS = sorted(r.code for r in REAL if "person.merge" in r.capabilities)
NON_MERGERS = sorted(r.code for r in REAL if "person.merge" not in r.capabilities)

SCOPES = {
    "village_health_worker": {"site_ids": [1]},
    "facility_user": {"facility_id": 1},
    "district_coordinator": {"district": "Kwekwe"},
    "programme_sponsor": {"programme_id": 1},
}


def _session(client):
    return next(client.app.dependency_overrides[database.get_db]())


def _login(client, role):
    """An account in `role`, with whatever scope that role requires."""
    from db_models import Facility, Programme, Site

    db = _session(client)
    if not db.scalar(select(Facility.id)):
        db.add(Facility(name="Test District Hospital", level="district"))
    if not db.scalar(select(Site.id)):
        db.add(Site(name="Globe & Phoenix", district="Kwekwe"))
    if role == "programme_sponsor" and not db.scalar(select(Programme.id)):
        db.add(Programme(code="P1", name="P", kind="employer", payer="P",
                         data_owner="P", consent_text_code="CORE"))
    db.commit()
    email = f"{role}@example.org"
    authz.create_user(db, email, "password123", role, **SCOPES.get(role, {}))
    db.commit()
    db.close()
    token = client.post("/api/auth/login", json={
        "email": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def two_people(client):
    """Two resolved people. Returns (participant_code, person_id, other_id)."""
    first = client.post("/api/v2/persons/resolve",
                        json={"name": "Tendai Moyo", "phone": "0771234567"}).json()
    second = client.post("/api/v2/persons/resolve",
                         json={"name": "Rudo Phiri", "phone": "0772345678"}).json()
    return first["participant_code"], first["person_id"], second["person_id"]


def _rows(client, action):
    from db_models import AuditLog

    db = _session(client)
    rows = list(db.scalars(
        select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)
    ).all())
    db.close()
    return rows


# -------------------------------------------------- reading a person

@pytest.mark.parametrize("role", NON_READERS)
def test_a_role_without_person_read_is_refused_an_identified_record(client, two_people, role):
    """**The assertion that closes the hole.** Includes the three roles §16.3
    refuses an identified record outright, and the district coordinator, whose
    row says "identified records outside their district" — which with no
    district on the record means not at all through this route."""
    code, _, _ = two_people
    response = client.get(f"/api/v2/persons/{code}", headers=_login(client, role))
    assert response.status_code == 403, f"{role} reached an identified record"


@pytest.mark.parametrize("role", READERS)
def test_a_role_with_person_read_still_reads_one(client, two_people, role):
    """The refusal must be the narrow one it claims to be. A village health
    worker confirming a card at the next outreach is the flow this route
    exists for, and both prototype accounts hold the capability too, so the
    dashboard's lookup keeps working."""
    code, _, _ = two_people
    response = client.get(f"/api/v2/persons/{code}", headers=_login(client, role))
    assert response.status_code == 200, f"{role} should read a person: {response.text}"
    assert response.json()["name"] == "Tendai Moyo"


def test_an_identified_read_is_recorded_against_the_person(client, two_people):
    """§16.3: every read audited — and recorded against the `person_id`, which
    is what makes "who has read this worker's record?" answerable without the
    log becoming a second copy of the register."""
    code, person_id, _ = two_people
    client.get(f"/api/v2/persons/{code}", headers=_login(client, "facility_user"))

    rows = _rows(client, "person.read")
    assert len(rows) == 1
    assert rows[0].person_id == person_id
    assert rows[0].object_id == code
    assert rows[0].actor_email == "facility_user@example.org"
    assert rows[0].allowed == 1


def test_the_worker_can_be_told_who_read_their_record(client, two_people):
    """**The promise this file makes true.** `GET /api/v2/audit/persons/{id}`
    answered an empty list before, because no read was recorded."""
    code, person_id, _ = two_people
    client.get(f"/api/v2/persons/{code}", headers=_login(client, "facility_user"))

    headers = _login(client, "village_health_worker")
    rows = client.get(f"/api/v2/audit/persons/{person_id}", headers=headers).json()
    reads = [r for r in rows if r["action"] == "person.read"]
    assert reads, "a read happened and the worker's log must show it"
    assert any(r["actor_email"] == "facility_user@example.org" for r in reads)


def test_a_refused_read_is_recorded_too(client, two_people):
    """The rows that show the boundary being enforced rather than declared."""
    code, _, _ = two_people
    client.get(f"/api/v2/persons/{code}", headers=_login(client, "researcher"))

    rows = _rows(client, "person.read")
    assert rows and rows[-1].allowed == 0
    assert rows[-1].actor_role == "researcher"


def test_an_unknown_participant_code_is_recorded_as_a_refusal(client):
    """The participant-code space is the same six-character alphabet as a
    referral code, so a walk through it is worth seeing."""
    client.get("/api/v2/persons/ZZZZZZ", headers=_login(client, "facility_user"))
    rows = _rows(client, "person.read")
    assert rows and rows[-1].allowed == 0
    assert rows[-1].object_id == "ZZZZZZ"


def test_the_match_queue_needs_person_read(client):
    for role in NON_READERS:
        response = client.get("/api/v2/persons/matches/queue", headers=_login(client, role))
        assert response.status_code == 403, role


# -------------------------------------------------- merging two people

@pytest.mark.parametrize("role", NON_MERGERS)
def test_a_role_without_person_merge_cannot_merge_two_people(client, two_people, role):
    """A merge joins two clinical histories. `ARCHITECTURE.md`: a clinical
    safety event that belongs to one named role — and that role is the
    administrator, nobody else."""
    _, winner, loser = two_people
    response = client.post("/api/v2/persons/merges", headers=_login(client, role), json={
        "winner_person_id": winner, "loser_person_id": loser,
        "merged_by": "sister.moyo", "reason": "same worker",
    })
    assert response.status_code == 403, f"{role} merged two people"


def test_the_prototype_accounts_keep_working(client, monkeypatch):
    """**The consequence to check before changing an auth boundary.** The
    dashboard logs in with one of two env-var accounts, and `hospital` holds
    `person.read` in the role table — so the identity lookup keeps working
    where it already worked. `cimas` holds it too. Neither holds
    `person.merge`, which is correct: a merge belongs to the administrator.
    """
    monkeypatch.setenv("HOSPITAL_EMAIL", "hospital@silicaguard.health")
    monkeypatch.setenv("HOSPITAL_PASSWORD", "prototype-password")

    person = client.post("/api/v2/persons/resolve",
                         json={"name": "Chipo Banda", "phone": "0774567890"}).json()
    token = client.post("/api/auth/login", json={
        "email": "hospital@silicaguard.health",
        "password": "prototype-password"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get(f"/api/v2/persons/{person['participant_code']}",
                      headers=headers).status_code == 200
    assert client.post("/api/v2/persons/merges", headers=headers, json={
        "winner_person_id": person["person_id"],
        "loser_person_id": person["person_id"],
        "merged_by": "x",
    }).status_code == 403


def test_only_the_administrator_holds_person_merge(client):
    """Stated against the table so that widening it is deliberate."""
    assert MERGERS == ["administrator"]


def test_an_administrator_can_merge_and_it_is_recorded(client, two_people):
    _, winner, loser = two_people
    headers = _login(client, "administrator")
    response = client.post("/api/v2/persons/merges", headers=headers, json={
        "winner_person_id": winner, "loser_person_id": loser,
        "merged_by": "sister.moyo", "reason": "same worker",
    })
    assert response.status_code == 200, response.text

    rows = _rows(client, "person.merge")
    assert len(rows) == 1
    assert rows[0].person_id == winner
    assert rows[0].actor_email == "administrator@example.org"


def test_the_log_records_the_account_and_the_payload_records_the_clinician(
    client, two_people
):
    """Both are needed and they are not the same thing: `merged_by` names who
    *judged* that two records are one person; the audit row names the account
    that submitted it. One answers "who decided this?", the other "who did
    it?"."""
    _, winner, loser = two_people
    headers = _login(client, "administrator")
    body = client.post("/api/v2/persons/merges", headers=headers, json={
        "winner_person_id": winner, "loser_person_id": loser,
        "merged_by": "sister.moyo", "reason": "same worker",
    }).json()

    assert body["merged_by"] == "sister.moyo"
    row = _rows(client, "person.merge")[0]
    assert row.actor_email == "administrator@example.org"
    assert "sister.moyo" in (row.details or ""), "the decision is in the row too"


def test_reversing_a_merge_needs_the_same_capability_and_is_recorded(client, two_people):
    """"Merges are never automatic and always reversible" (`CLAUDE.md`), and a
    reversal is as much a clinical event as the merge."""
    _, winner, loser = two_people
    headers = _login(client, "administrator")
    merge = client.post("/api/v2/persons/merges", headers=headers, json={
        "winner_person_id": winner, "loser_person_id": loser,
        "merged_by": "sister.moyo",
    }).json()

    assert client.delete(
        f"/api/v2/persons/merges/{merge['merge_id']}?reversed_by=sister.moyo"
    ).status_code == 401, "no token at all"

    refused = client.delete(
        f"/api/v2/persons/merges/{merge['merge_id']}?reversed_by=sister.moyo",
        headers=_login(client, "researcher"),
    )
    assert refused.status_code == 403

    ok = client.delete(
        f"/api/v2/persons/merges/{merge['merge_id']}?reversed_by=sister.moyo",
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    rows = _rows(client, "person.unmerge")
    assert len(rows) == 1 and rows[0].allowed == 1


def test_deciding_a_queued_match_needs_person_merge(client, two_people):
    """Applying a queued decision joins two histories, which is the same act
    as a merge whatever the route is called."""
    response = client.post("/api/v2/persons/matches/1",
                           headers=_login(client, "village_health_worker"),
                           json={"decision": "merge", "decided_by": "sister.moyo"})
    assert response.status_code == 403


# ---------------------------------------------- what the routes still allow

def test_resolve_stays_open_because_the_field_app_has_no_login(client):
    """The deliberate exception, and the reason the identity *lookup* cannot
    simply be opened to match it: resolve takes a bundle and returns a code,
    while the lookup turns a code into a name, and a six-character code space
    is walkable."""
    response = client.post("/api/v2/persons/resolve",
                           json={"name": "Chipo Banda", "phone": "0774567890"})
    assert response.status_code == 200
    assert "name" not in response.json() or response.json().get("name") is None


def test_no_v2_router_uses_the_v1_token_dependency():
    """The regression guard, and the one that would have caught this.

    `get_current_user` returns a dict and checks only that a token parses, so
    a route using it is a route with no boundary — which is exactly how this
    hole existed for two days while the role model sat beside it.

    The **v1** routers are excluded, and that is not an exemption I am
    granting: `docs/SECURITY.md` records that they move onto capabilities with
    the adapter (item 1.11), so they are a deferred decision rather than an
    oversight. Every `/api/v2` router must already be across.
    """
    import ast
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    v1 = {"dashboard.py", "education.py", "outreach.py", "auth.py"}

    def _serves_v2(tree) -> bool:
        """True if this module declares an `/api/v2` prefix or route path.

        Read from the AST rather than by searching the text: a comment
        mentioning a v2 route is not a v2 route. The first version of this
        test substring-matched both halves and went green on every branch
        individually, then failed once two branches merged — because one
        added a comment naming `get_current_user` and the other added a
        comment naming `/api/v2/audit/refusals`, in a file that serves
        neither.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        if str(kw.value.value).startswith("/api/v2"):
                            return True
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                # A decorator path, which is relative to the prefix -- so only
                # an absolute v2 path counts here.
                if node.value.startswith("/api/v2"):
                    parent_is_decorator = True  # cheap: any such literal
                    if parent_is_decorator:
                        return True
        return False

    def _uses_the_v1_dependency(tree) -> bool:
        """True if `get_current_user` is referenced as code.

        A string or comment mentioning it is not a use of it, and
        `auth.get_current_user` is, which a search for the bare name in an
        import line would miss.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "get_current_user":
                return True
            if isinstance(node, ast.Attribute) and node.attr == "get_current_user":
                return True
            if isinstance(node, ast.ImportFrom):
                if any(a.name == "get_current_user" for a in node.names):
                    return True
        return False

    offenders = []
    for path in sorted((backend / "routers").glob("*.py")):
        if path.name in v1:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _serves_v2(tree) and _uses_the_v1_dependency(tree):
            offenders.append(path.name)

    assert not offenders, (
        f"{offenders} serve v2 routes on the plain token dependency; use "
        "require(capability) so the role table is actually consulted"
    )


def test_reading_a_workers_consent_position_needs_consent_read(client, two_people):
    """Found by the same sweep. §16.3 gives `consent.read` to the village
    health worker alone — they are who has to know whether the worker in front
    of them agreed to be screened — and this route was on the plain token
    dependency too."""
    code, _, _ = two_people

    for role in sorted(r.code for r in REAL if "consent.read" not in r.capabilities):
        response = client.get(f"/api/v2/persons/{code}/consents",
                              headers=_login(client, role))
        assert response.status_code == 403, role


def test_withdrawing_consent_needs_consent_write_and_is_recorded(client, two_people):
    """§14.3 requires the withdrawal mechanism to be demonstrable, which means
    a withdrawal has to be as recoverable from the log as a grant: "granted,
    then withdrawn on this date" is a different story from "never granted"."""
    _, person_id, _ = two_people

    refused = client.post("/api/v2/consents/withdraw",
                          headers=_login(client, "researcher"),
                          json={"person_id": person_id,
                                "permission": "screening_and_referral",
                                "withdrawn_by": "sister.moyo"})
    assert refused.status_code == 403

    allowed = client.post("/api/v2/consents/withdraw",
                          headers=_login(client, "village_health_worker"),
                          json={"person_id": person_id,
                                "permission": "screening_and_referral",
                                "withdrawn_by": "sister.moyo"})
    assert allowed.status_code == 200, allowed.text

    rows = _rows(client, "consent.withdraw")
    assert rows and rows[-1].person_id == person_id and rows[-1].allowed == 1


def test_every_declared_person_action_is_now_written_somewhere():
    """`audit.ACTIONS` is a closed set so the log can be queried rather than
    grepped. An action declared and never written is a promise nobody keeps —
    which is what `person.unmerge` and `person.match_decide` were."""
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    written = "".join(
        path.read_text(encoding="utf-8")
        for path in list((backend / "routers").glob("*.py"))
        + list((backend / "services").glob("*.py"))
        if path.name != "audit.py"
    )
    for action in ("person.read", "person.merge", "person.unmerge",
                   "person.match_decide"):
        assert f'"{action}"' in written, f"{action} is declared and written nowhere"
