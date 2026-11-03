# Data governance, security and ethics

> Derived from `docs/master/MASTER_REFERENCE.md` §14 and §16 (Master Reference v1.0, September 2026). The master document wins on any conflict. The team is not legally qualified; the specifics must be confirmed by a lawyer and directly with the relevant authorities. **Built** = true today; **Planned** = specified, not yet in place. First audited 18 September 2026 against the prototype; **re-audited 1 November 2026** after Phase One's backend rebuild, so the markers in this file describe the code as it stands rather than as it stood in September.

The standard applied: the system holds sensitive health data about a vulnerable population, and it is built as though a breach would be both a legal event and a personal catastrophe for the people in it, because it would be.

## Legal obligations — all Planned, several before the first real record

- Zimbabwe's **Cyber and Data Protection Act** treats health data as sensitive personal information, requires data controllers to register with the data protection authority, and requires a data protection officer. Assume this must be complete before the first real record.
- **Research ethics approval** from the Medical Research Council of Zimbabwe before screening real people under a protocol. The submission needs the instrument at a specific version, consent documents in all three languages, data flows, retention period and withdrawal mechanism.
- **Medical device classification** with the Medicines Control Authority of Zimbabwe requires a formal determination. The system is designed to sit outside device classification; obtaining the determination is a pre-pilot checklist item. **It is never described as settled.**
- **Ministry of Health and Child Care clearance** at national and district level before any deployment.

## Consent design — Built, except the worker-facing opt-out

Consent is layered, recorded as data, and separated into distinct permissions rather than bundled.

| Permission | Scope | Notes |
|---|---|---|
| Screening and referral | The core service: screening, tier, referral, and the messages required to deliver that. | Required to proceed. |
| Longitudinal record | Retention for comparison at future screenings. | Separable — a worker may accept screening and decline retention. |
| Contact by message | Result messages, reminders, escalation. | Required for follow-through. Distinct from education broadcast. |
| Education broadcast | Unsolicited health education messaging. | Separate consent with a working, permanent opt-out. |
| Research and national statistics | De-identified data for validation, research, aggregate reporting. | Separate and refusable without losing the service. |
| Employer disclosure | Any disclosure of individual results to an employer or programme sponsor. | **Future phase only.** Separate, specific, refusable. Never bundled. |

For USSD, consent is a short statement in spoken register followed by an explicit keypress, recorded with a timestamp and the version of the consent text displayed. Consent text is versioned content like every other patient-facing string.

**Built, as of 1 November 2026.** `consent_texts` and `consent_records` (migration `0004`, uniqueness in `0008`), `backend/services/consent.py`, `backend/routers/consents.py`. Three properties are enforced in code and tested:

- **Absence is never consent.** A permission nobody recorded reads as not granted. No default, no inheritance from a related permission, and no grant implied by a programme — an employer-funded cohort does not consent on a worker's behalf.
- **A record must name the wording.** `consent_text_id` is required and must name an *approved* text, because a row saying "agreed" with nothing attached is not evidence. The wording itself is a message code in the content store, so consent text goes through the same review, the same three languages and the same GSM-7 checks as every other patient-facing string.
- **A withdrawal is recorded, never a deletion.** The original row is kept and stamped, so "granted, then withdrawn on this date" stays distinguishable from "never granted".

`employer_disclosure` **cannot be granted at all** — `record()` refuses it, so the boundary exists in code before any commercial pressure exists to blur it. A refusal may still be recorded, because a refusal is a real answer. `may_disclose_to_employer()` is written as a real per-person lookup rather than a hardcoded `False`, so the day a formal-sector module exists the check is already in the code path.

**Consent capture does not work until the Clinical Lead approves a consent text.** That is correct sequencing rather than a gap: nobody is asked to agree to unreviewed wording, and `GET /api/v2/consents/texts/{code}` returns `404` until one is approved.

**Planned — the worker-facing opt-out, and the two channels.** `POST /api/v2/consents/withdraw` requires a token, so withdrawal is staff-operated today. A worker's own withdrawal should not need one, but an open endpoint keyed on a person id would let anyone stop anyone's referral reminders — a harm to the person it pretends to serve. The worker-facing route is the USSD and SMS opt-out, reaching the same service function server-side through the gateway, and it lands with item 1.9 alongside the USSD consent keypress screen. Until then §14.2's "working and permanent opt out" is not finished.

**Still true today**: neither channel asks for consent yet, and the v1 education broadcast (`POST /api/education/broadcast`) still sends without it. The gate exists — `consent.may_broadcast()` — and cannot be wired until the v1 `miners` rows map to `persons`, which is the adapter (item 1.11). The broadcast route is Bearer-protected, so only the team can fire it, which bounds the exposure without excusing it.

## The employer boundary — the most consequential governance rule

If an employer or insurer funds screening, that organisation **never receives individual results** without separate, specific and refusable consent from the worker. It receives aggregate exposure and risk intelligence. Any individual fitness-to-work communication goes through a clinician, never through a data interface.

Built into the programme model now, before any commercial pressure exists, it is defensible to a union, a ministry and an ethics committee. It is also commercially load-bearing: it is the reason workers answer honestly rather than concealing symptoms to protect their jobs, and honest answers are what make the data worth paying for. The technical control is that programme scoping is enforced at the data-access layer, with a test that attempts cross-programme access and confirms it fails (`ARCHITECTURE.md`, the nullable programme reference).

## Data sovereignty — decision due before the pilot

Hosting is currently outside Zimbabwe (Render, Oregon; Supabase, eu-west-1), a gap relative to national policy expectations that Professor Mushiri has already flagged. Three honest options: accept and disclose it for the pilot; move to in-country hosting; or split the architecture so identifiers remain in Zimbabwe while de-identified analytics run elsewhere. Any is defensible if chosen deliberately and explained. What is not defensible is being asked and having no answer.

## Ownership of the register

A national register of workers' occupational health data should not be owned by a startup, and saying so first is what protects the project. SilicaGuard is the **operator and technical custodian**; stewardship belongs with the Ministry of Health and Child Care, with a defined governance structure and handover path. Stated in the first substantive Ministry meeting, unprompted. Detail in `docs/REGISTER.md`.

## Threat model

| Threat | Realistic scenario | Primary control | Today |
|---|---|---|---|
| Lost or stolen field device | A handset lost at a mine site with queued screenings and a pre-synced roster. | Encrypted local storage, access code, minimal retention, server-side revocation, remote wipe. | Unencrypted AsyncStorage, no PIN, no protocol. |
| Credential compromise | A reused or phished password gives access to hosting or the database. | Password manager, unique credentials, two-factor by authenticator, least privilege, no shared logins. | Personal accounts; no vault; Phase Zero. |
| Insider or over-broad access | A dashboard account sees far more than needed; an engineer queries production out of curiosity. | Role-based access scoped to site, facility or programme; read auditing; production access restricted and logged. | **Built**: seven scoped roles, deny by default, append-only read auditing that records refusals. **Still true**: the dashboard exercises only the two prototype roles until Week 22, the v1 Bearer routes check a token rather than a capability (item 1.11), and production is queried directly for diagnosis with no restriction or log on that path. |
| Data exposure through a test or demo | A staging demo sends a real message; production data copied to a laptop. | Separate credentials per environment; synthetic data outside production; prohibition on copying production data. | One environment; one credential set. |
| Message misdelivery | A result goes to a recycled number now held by a stranger. | Number verification, delivery-failure handling, reverification of dormant contacts, minimal clinical detail in text. | None; ORANGE text names an X-ray and a hospital. |
| Interception in transit | Data intercepted between device, gateway and backend. | Transport encryption everywhere, certificate validation, webhook signature verification where supported. | HTTPS on Render and Supabase; no webhook verification. |
| Public endpoint abuse | The open referral lookup is enumerated to harvest data. | Non-sequential codes from a restricted alphabet; rate limiting; lockout; minimal data returned; all lookups logged. | Codes non-sequential (built). **Every lookup logged, hit or miss (built 2 November 2026)** — a miss is an `allowed=False` row, so a walk through the code space appears as a run of refusals in `GET /api/v2/audit/refusals` rather than as nothing. No rate limiting, no lockout: Phase Two, and until they exist the log is detection without prevention. |
| Dependency compromise | A vulnerable or malicious package enters the build. | Pinned dependencies; vulnerability scanning in CI; high severity blocks merge. | Backend requirements largely unpinned; no CI. |
| Coercion or pressure to disclose | An employer, official or other party pressures the team for individual results. | The employer boundary; a documented refusal position; a governance process; consent records. | No consent records exist to point to. |
| Loss of data | Corruption, deletion, provider failure. | Automated backups, tested restores, recovery objectives, reversible migrations. | No backups configured beyond the provider default; no restore ever tested. The 6 September Supabase pause was recovered by a dashboard restore, not a backup. |

## Controls by layer

| Layer | Control |
|---|---|
| Transport | Encryption in transit on every connection including gateway callbacks. No unencrypted endpoint in any environment. Webhook payloads verified where the provider supports signing. |
| Storage at rest | Encryption at rest. Direct identifiers separated from clinical content into distinct tables with distinct access paths. National identity numbers, if collected, stored only as a salted hash. |
| Key management | Secrets in the hosting platform's secret store and the vault. Never in the repository, a chat message or a log. A secret exposed once is rotated immediately and the exposure recorded. |
| Application | Input validation through request schemas. Parameterised queries only. Rate limiting on public endpoints. Idempotency on webhooks and synchronisation. No personal data in error messages. |
| Authorisation | Role-based least privilege. Every clinical read scoped to the requester's legitimate relationship with that record. |
| Device | Encrypted local storage, access code, minimum pre-synced data, clearing of synced records, lost-device procedure with server-side revocation. |
| Messaging | Minimal clinical detail. A message says a result requires attention and directs to a facility; it does not name a suspected disease on a handset that may be shared. |
| Audit | Append-only audit of clinical reads and writes, consent changes, merges, exports and administrative actions, retained and reviewable. |
| Backup | Automated encrypted offsite backups; restore tested before the pilot and at least once during it. A backup that has never been restored is not a backup. |
| Build and supply chain | Pinned dependencies, vulnerability scanning, secret scanning, protected `main`, review before merge. |

## Roles and permissions — Built, backend only

| Role | Can see | Cannot see |
|---|---|---|
| Village health worker | People they are screening at their assigned site, their own encounters, the pre-synced roster for that outreach. | Other sites, other workers' encounters, national data. |
| Facility user | Referrals directed to their facility; the lookup and confirmation function. | Screenings with no referral to them, other facilities' referrals, aggregate national data. |
| District coordinator | Aggregate and operational data for their district; referral ageing. | Identified records outside their district; clinical detail beyond what coordination requires. |
| National stakeholder | Aggregate views with small-cell suppression. | Any identified record. |
| Researcher | Pseudonymised extracts under an approved protocol. | Direct identifiers and the re-identification key. |
| Programme sponsor | Aggregate data for their own cohort only. | Individual results; anything outside their cohort. |
| Administrator | System configuration, instrument versions, user management. | Routine clinical browsing. Administrative access is not a licence to read records; every read audited. |
| The person screened | Their own record and referral status. | Anyone else's. |

**Built, as of 1 November 2026** — `users` and `audit_log` (migration `0010`), `backend/services/authz.py`, `backend/services/audit.py`, `backend/routers/admin.py`. Seven of the eight rows above are roles with capabilities and a scope; the eighth, **the person screened**, has no login — a worker reaches their own record through USSD and the card in their pocket, so their access is bounded by the participant code rather than by a role.

**A role plus a scope, never a role alone.** "Facility user: can see referrals directed to their facility" is not a role, it is a role *and* a facility; a village health worker covers a handful of workings, not one and not all. Creating a scoped role with no scope is **refused**, because it passes every capability check and is bounded by nothing. The scoped-query helpers narrow to **nothing** when the scope is missing, never to everything — that is the whole reason they exist instead of an inline condition.

**Deny by default.** A capability a role does not list is refused, including one that does not exist, so a new capability is invisible to every role until somebody grants it deliberately.

**Administrative access is not a licence to read records.** The administrator role holds `admin.manage`, `person.merge` and `aggregate.read` — and deliberately **not** `person.read` or `screening.read`. An administrator who needs a worker's record has to be given a clinical role as well, which is a decision somebody makes rather than a capability that arrives with the job. A test asserts it, as do twenty-one other negative tests drawn from the "cannot see" column above.

**Passwords are hashed** with `hashlib.scrypt` and a per-user salt. The prototype accounts compared plaintext from an environment variable. **`SECRET_KEY` no longer falls back to `"dev-secret"`** — that default meant a production instance missing the variable signed tokens with a value published in this repository, so anyone could mint an administrator token; it now raises at signing time.

**The prototype accounts are self-disarming.** `hospital` and `cimas` authenticate only while the `users` table is empty. The moment a real user exists they stop working, and a token issued to one stops working with them. That is deliberately not a feature flag: a flag nobody turns off is how a prototype credential reaches production.

**The first administrator is created by `backend/scripts/create_admin.py`**, which needs database access. The prototype accounts do not hold `admin.manage`, so they cannot create one — and the two alternatives were both worse: widening them defeats the point of retiring them, and letting the route run unauthenticated while the table is empty opens a window in which whoever reaches a fresh instance first owns the system.

### The audit log

Append-only: there is no update and no delete anywhere in `services/audit.py`, and a test asserts that by inspecting the module, because a log that can be edited afterwards answers nothing. Enforced in the service layer rather than by a trigger — triggers are PostgreSQL-only and invisible to the SQLite unit suite (§16.2).

- **A refused access writes a row.** These are the rows that matter: a role boundary nobody can show being enforced is a boundary nobody can show exists. `GET /api/v2/audit/refusals` lists them.
- **"Who has read my record?" is answerable.** `GET /api/v2/audit/persons/{id}`, and reading the trail is itself audited — an audit log nobody's reads are recorded in is a log that can be mined quietly.
- **No personal data in a log line**, checked rather than trusted: a forbidden-key list rejects a name, a number, an answer or a password in `details`. A failed-login row records neither the address tried nor the password.
- **An audit write cannot fail a clinical write.** `record()` joins the caller's transaction so a screening is never lost because a log row would not fit; a refusal commits on its own session, because a refused request has no transaction to join and is never allowed to turn a clean `403` into a `500`.

**Planned**: the dashboard exercises only the prototype roles until the Week 22 rebuild, so the negative tests are what protect the boundary in the meantime (`docs/IMPLEMENTATION_PLAN.md` §12 item 13). The v1 Bearer routes still use the plain token dependency rather than a capability, and move across with the adapter (item 1.11). Rate limiting and lockout on the login and the public lookup remain Phase Three.

**Built 2 November 2026 — the four unauthenticated referral-code routes are audited.** `GET /api/referrals/lookup/{code}`, `POST /api/referrals/lookup/{code}/confirm-attendance`, `GET /api/v2/referrals/{code}` and `POST /api/v2/referrals/{code}/close` were the only clinical surfaces escaping §16.3's audit, and they escape it from the most exposed position in the system: no login, by design, because hospital staff have no dashboard account. Each records a row on a hit and an `allowed=False` row on a miss or a refused write.

Three decisions in it:

- **The actor is a sentinel, not an absent principal.** `audit.FACILITY_LOOKUP` records `actor_role: "facility_lookup_unauthenticated"`. A NULL actor must mean one thing — left empty, an unauthenticated facility caller would be indistinguishable from a route that forgot to pass its principal, and "who read this worker's record?" must be answerable with *something*. The role is deliberately absent from `authz.ROLES`, holds no capability, and `require()` can never produce it: it is a log label, not an account.
- **A read that cannot be recorded does not happen.** On this surface the audit row is load-bearing, which is the opposite of the rule everywhere else, and the difference is what silence costs: a screening lost because a message failed is a worker who was screened and never told, so the recording is what is worth saving; a lookup served without a log is a read of a name and a telephone number that nobody can account for afterwards. A failure on the *miss* path still returns a clean 404, because an attacker must not be able to tell the log is broken by watching status codes.
- **`object_id` is capped at 64 characters.** It records the code that was *attempted*, so an arbitrary string from the request path reaches the table.

**And `POST /api/v2/screenings` recorded nothing**, which was the largest gap of the set: the deterministic cascade is the clinical act this whole system exists to perform, and §16.3 is an audit of clinical reads *and writes*. It now writes a row per submission naming the session, person, channel, tier, conditions, referrals and instrument version — never an answer, a name or a number. A replay writes nothing, matching the clinical behaviour; an incomplete session writes an `allowed=False` row naming the missing questions. The actor is a second sentinel, `audit.UNAUTHENTICATED_DEVICE`, because the handset has no login.

**One route where a failed audit write must not fail the request.** `audit.record_best_effort()` is used by the screening submit alone: the screening is already committed when the row is written, and §10.3's "a completed screening is never discarded" decides it — the worker gets his tier, the failure is logged at ERROR. This is the **opposite** of the rule for a read, where refusing is right because nothing is lost by refusing and an unaudited read of an identified record is precisely what §16.3 forbids. Both directions are tested, so neither can be adopted for the other case by accident.

**This is detection, not prevention, and it is not free**: an unauthenticated caller can grow the audit table one row per attempt. The rate limit is what bounds it. Recorded so the trade-off is deliberate rather than discovered.

## De-identification and analysis — Planned

All analysis, dashboards and reporting run against a de-identified view by default. Direct identifiers are removed, not masked, and the re-identification key held separately under the governance process. Small-cell suppression on every aggregate output, thresholds set in advance. Site-level reporting considered carefully: a small workings with few workers is close to identifying and may need grouping upward. **Today**: every dashboard number is computed on the identified tables.

## Incident response — Planned, written before it is needed

1. **Detect and contain.** Revoke the affected credential or device access immediately. Containment before investigation.
2. **Assess.** What data, how many people, identified or not, still exposed?
3. **Record.** A written incident log started at the moment of detection.
4. **Notify.** The data protection authority and affected individuals as the law requires, through district and facility structures where direct contact is not practical.
5. **Remediate.** Fix the cause, verify the fix.
6. **Review.** A blameless written review within two weeks, changes tracked to completion.

Incident owner: the team leader, unless the incident concerns his access, in which case the mobile engineer. Authority and ethics-committee contact details recorded before the pilot.

## Security roadmap

| Phase | Security work |
|---|---|
| Zero | Password manager and two-factor across all accounts. Secret scanning and dependency scanning in CI. Separate credentials per environment. Written lost-device procedure. |
| One | Identifier/clinical separation in the new schema. Encryption at rest. Hashed national identity numbers. Consent records. Role model implemented. Audit logging of clinical reads and writes. |
| Two | Device encryption and access code. Rate limiting and lockout on the public lookup. Message content minimisation. Backup automation and a tested restore. |
| Three | Data-controller registration complete. Sovereignty decision implemented. Independent security review if a partner or budget allows. Incident response rehearsed. Pre-pilot checklist signed. |
| Pilot and beyond | Periodic access review, audit review, restore testing, dependency updates, threat-model review on any material architecture change. |

## Pre-pilot security checklist

No real screening takes place until every item is true and the list has been signed and dated.

- [ ] Data-controller registration complete and a data protection officer named.
- [ ] Ethics approval granted, with the approved consent texts loaded as versioned content.
- [ ] Encryption in transit and at rest verified, not assumed.
- [ ] Identifiers separated from clinical content; identity numbers hashed.
- [ ] Role-based access implemented and tested by attempting access that should fail.
- [ ] Audit logging active for clinical reads, writes, merges, exports and consent changes.
- [ ] Backups automated and a restore successfully tested end to end.
- [ ] Device encryption, access code and lost-device procedure in place; health workers trained on it.
- [ ] Staging and production fully separated; no possibility of a test message reaching a real person.
- [ ] Public lookup rate-limited and monitored.
- [ ] Incident response plan written, owner named, authority contacts recorded.
- [ ] No production data on any personal device or personal account.

Signed: ______________________ Date: ____________

## Identifier storage and key handling — Built, with one gap named

> Implements the "Storage at rest" and "Key management" rows above, and `docs/IMPLEMENTATION_PLAN.md` §12 item 11. Code: `backend/services/crypto.py`.

### Two columns for one value

Every direct identifier is stored twice: a **keyed hash** for equality lookup and an **encrypted value** for use.

| Value | Hash column | Encrypted column | Why both |
|---|---|---|---|
| Telephone number | `contacts.number_hmac` (indexed) | `contacts.number_encrypted` | A number must be *found* — the USSD webhook arrives with a caller number — and also *sent to*. |
| Name | `persons.name_hmac` (indexed) | `persons.name_encrypted` | Exact-match candidate lookup without a plaintext index; a health worker and a referral letter need the name back. |
| National identity number | `persons.national_id_hash` (indexed) | **none** | §16.2: stored only as a hash. It is used for matching and never displayed, so there is nothing to recover. |

An encrypted column cannot be indexed for equality and a hash cannot be reversed, so one alone cannot do both jobs.

### Three decisions worth stating plainly

**A keyed hash, not a per-row salt.** The textbook answer for storing an identifier is a random salt per row, and it is the wrong answer here: a per-row salt makes two records holding the same national identity number hash differently, which destroys the one deterministic match §8.2 relies on. The key *is* the salt, it is the same for every row, and it lives in the platform secret store rather than in the database. This protects against disclosure of the database; it does **not** protect against disclosure of the database and the key together. That is the trade-off, and it is accepted rather than assumed.

**Domain separation.** Every digest is computed over `purpose + ":" + value`, with `purpose` from a closed set. Without it, a number typed into the national-identity field would produce the same digest as the same number typed into the phone field, and the system would merge two people — the clinical safety event §8.2 names.

**Authenticated encryption.** Fernet (AES-128-CBC with an HMAC-SHA256 tag), so a tampered column fails to decrypt rather than returning different plaintext. That matters for a telephone number a result message is about to be sent to: silently delivering a worker's result to a different handset is a disclosure, not a glitch.

### Keys

| Variable | Holds | Generate |
|---|---|---|
| `IDENTITY_HMAC_KEY` | The HMAC key for every lookup digest | `python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` |
| `CONTACT_ENCRYPTION_KEY` | The Fernet key for every recoverable value | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

Set on the hosting platform, never in the repository. **`.env.example` names both variables and carries no values**, and that is a deliberate reversal: it first shipped with working development keys so a fresh checkout would run, gitleaks flagged both, and the gate was right — a working key in a public example file is indistinguishable from a real one, to the scanner and to a reader. Allowlisting that file would have been the worst exception in the repository, because it is exactly where a real secret gets pasted by accident. A checkout without keys gets a clean `503` from `/api/v2/persons/*` naming the missing variable; every v1 route is unaffected. Two tests keep it that way, one of them asserting that the suite derives its own keys from readable ASCII rather than committing a high-entropy literal anywhere.

**There is deliberately no fallback.** A missing key raises, and the HTTP layer turns that into a retryable `503` rather than saving an unprotected record. `routers/auth.py:29` falls back to `"dev-secret"` when `SECRET_KEY` is unset; that pattern is **not** copied here, because a production instance quietly hashing national identity numbers under a guessable default produces a column that looks protected, is not, and cannot be fixed afterwards — the plaintext is gone.

### Rotation — Planned, and required before the first real record

**Changing either key orphans existing data.** Every hash stops matching and every encrypted value stops decrypting. There is no partial failure: the register simply stops recognising anybody.

Rotation is therefore a migration, not an edit, and the procedure below must be written as a runnable script and tested on staging before any real record exists. Until that script exists, **a key exposure is an incident with no clean recovery**, which is the honest statement of where this stands.

1. Set the new key alongside the old one (`IDENTITY_HMAC_KEY_NEXT`, `CONTACT_ENCRYPTION_KEY_NEXT`).
2. Decrypt with the old key and re-encrypt with the new one, row by row, in a transaction per batch; recompute every digest with the new HMAC key in the same batch. Hashes and ciphertext must move together or a row becomes unfindable.
3. Verify a sample end to end — a participant code lookup, a USSD caller-number lookup, and one outbound message to a test handset.
4. Promote the new keys and remove the old ones. Record the rotation, its reason and its date.

Steps 2 and 3 need the whole table, so plan it for a quiet window and expect the API to be read-only while it runs.

## Phone-number storage — documented tradeoff, expiring

`miners.phone` is stored in plaintext because it is the operational identity for SMS delivery, USSD caller lookup and `GET /api/workers/{phone}`, and a one-way hash breaks all three. This was an acceptable prototype tradeoff and **ceases to be acceptable the moment real patient data exists**.

**The replacement is built** — `contacts`, hashed and encrypted, separated from clinical content (see the section above, and `ARCHITECTURE.md` decisions 1 and 2) — **and the v1 column is still there and still in use.** `routers/ussd.py`, `GET /api/workers/{phone}` and the mobile application's `resolveMinerId()` all still read it, and `miners` is dropped by migration `0009` once the v1 adapter is deleted (`docs/IMPLEMENTATION_PLAN.md` §4). Until then both forms exist, which is the transition working as designed and not a reason to relax the expiry: **no real record before `miners` is gone.**
