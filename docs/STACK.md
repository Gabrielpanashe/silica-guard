# Technology stack and developer guide

> Derived from `docs/master/MASTER_REFERENCE.md` §11 (Master Reference v1.0, September 2026). The master document wins on any conflict. This is the developer onboarding document; it absorbs the former `SKILL.md`. **Built** = true today; **Planned** = specified, not yet in place. First audited 18 September 2026 against the prototype; **re-audited 1 November 2026** after Phase One's backend rebuild, so the markers in this file describe the code as it stands rather than as it stood in September.

## The stack

| Layer | Technology | Owner | Policy | Today |
|---|---|---|---|---|
| Backend language | Python | Panashe | Pin the minor version in runtime configuration. Upgrades are deliberate. | Built — 3.12.3, pinned in `render.yaml` |
| Backend framework | FastAPI | Panashe | Thin routers, service layer holds logic, schemas validated. | Built |
| Data access | SQLAlchemy + Alembic | Panashe | Every schema change is a reviewed migration. No manual change to a live database, ever. | Built — three migrations |
| Database | PostgreSQL | Panashe | Managed hosting, `pool_pre_ping` because idle poolers drop connections. Sovereignty decision in `docs/SECURITY.md`. | Built — Supabase free tier, Session Pooler, port 5432 |
| Backend hosting | Managed container hosting | Panashe | **Paid tier before any demonstration or pilot.** Free-tier spin-down produces visible cold starts. | Render free tier |
| Task scheduling | In-process scheduler | Panashe | Jobs idempotent. Disabled under test. | Built — APScheduler, three jobs |
| Mobile | React Native + Expo, Android | Takudzwa | Standalone build for the field. Developer tooling is not a field dependency. | Expo Go today; EAS config added 18 Sep |
| Mobile storage | **Encrypted** local storage with an offline queue | Takudzwa | Queued clinical data on a device that can be lost in a mining compound must be encrypted. | AES-256-GCM queue, key in the Android Keystore (`expo-secure-store`) — **built, not yet verified on a device** |
| Dashboard | Static markup, vanilla script, charting and mapping libraries | Takudzwa | No build step. Deliberately simple so it cannot rot. | Built — Chart.js, Leaflet |
| Website | Single static page on free static hosting | Takudzwa | Deliberately minimal (master document §24.1). | **In progress** — draft page on `fe/website`; not deployed (no domain, email or photographs yet) |
| Messaging and USSD | Africa's Talking, REST interface | Panashe | REST rather than the vendor SDK (certificate failure on Windows). **Delivery-receipt callbacks required.** | REST built; receipts **not** captured; **sandbox endpoint** |
| Transactional email | Hosted email API | Panashe | Outbound SMTP is blocked on the hosting tier. | Built — Resend |
| Model access | Gemini, **version pinned** | Panashe | Never a moving alias. Aggregate narrative and reviewed drafting only. Deterministic fallback mandatory. | `gemini-3.1-flash-lite`; still on the clinical path (see `ARCHITECTURE.md`) |
| Diagrams | Graphviz | Panashe | Source files in the repository, regenerable. | **Planned** — `diagrams/` |
| Error monitoring | Hosted error tracking | Panashe | Required before the pilot. | **None** |
| Version control | Git, hosted remote | All | Protected `main`, review before merge. | Built |
| Testing | Pytest (backend), device testing (mobile) | Panashe, Takudzwa | Expectations below. | 189 green on `main` |
| Secrets | Environment variables in the hosting platform, never in the repository | Panashe | A secret committed once is rotated immediately. | Built |

Deliberately **not** being chosen yet: no mobile-framework migration, no microservices, no message broker, no container orchestration, no separate analytics warehouse. Each would consume weeks the team does not have; complexity is added only when a measured constraint requires it.

## Accounts, access and credentials

Every service needs an account, an owner and a recovery path. **Nothing is registered to a personal address.** All credentials live in the shared password-manager vault and nowhere else, never in a chat message. No service is ever registered to an individual's personal account.

| Service | Registered to | Access held by | Notes |
|---|---|---|---|
| Domain registrar | SilicaGuard email | Panashe; Takudzwa as recovery | Renewal date recorded. |
| Email | Dedicated SilicaGuard address | Panashe primary; Takudzwa recovery | The root of every other account. Two-factor by authenticator app (not SMS — number recycling and SIM swap are real risks), recovery codes offline. |
| Code hosting | SilicaGuard email | All three | Protected `main`. Clinical content changes require Gabriel's approval on the pull request. |
| Backend and database hosting | SilicaGuard email | Panashe; Takudzwa able to recover | Billing alerts enabled. |
| Messaging gateway | SilicaGuard email | Panashe | Production account requires business verification. Sender-ID registration is separate and slow. |
| Model API | SilicaGuard email | Panashe | Usage caps set. |
| Error monitoring | SilicaGuard email | Panashe and Takudzwa | Alerts to a channel both engineers see. |
| Password manager | SilicaGuard email | All three | Shared vault, individual accounts. |
| Social and website hosting | SilicaGuard email | Panashe; Takudzwa as second administrator | Two administrators wherever the platform allows. |

**Today**: accounts are on personal addresses; the password manager and dedicated email are Phase Zero, week 1 (`ROADMAP.md`). `RENDER_API_KEY`, `GEMINI_API_KEY`, `AT_API_KEY`, `RESEND_API_KEY` and the Supabase `DATABASE_URL` are set on the Render service and in local `.env` files.

## Repository structure

| Path | Contents | Today |
|---|---|---|
| `backend/` | API application: routers, services, models, migrations, prompts, scripts, tests. | Built |
| `backend/services/` | All clinical and business logic. | Built |
| `backend/alembic/` | Migrations — the only mechanism by which a schema changes. | Built |
| `backend/tests/` | Test suite mirroring the service structure. | Built — 19 files |
| `mobile/` | React Native application: screens, components, context, services including the offline queue. | Built |
| `dashboard/` | Static dashboard and the open referral-lookup page. | Built |
| `website/` | The single-page public site. | **In progress** — draft, not deployed |
| `clinical/` | Instrument specifications by version, as reviewable source, plus the migration that loads each version. Owned by Gabriel. | **Planned** |
| `content/` | Patient-facing strings by message code and language, with the character-set validator applied in CI. | **Planned** |
| `diagrams/` | Diagram source files, regenerated rather than hand-edited. | Placeholder only |
| `docs/` | The documentation set mapped in Appendix D of the master document. | Built (this pass) |

## Branching and release

See `CONTRIBUTING.md`. In brief: short-lived branches, protected `main`, reviewed pull requests for everyone, Gabriel's recorded approval on anything clinical, staging on merge, production from a tag. **Today** there is one environment, auto-deployed from `main` — the staging/production split is Phase One.

## Configuration and secrets

- All configuration is environment-based. No environment-specific values in code.
- `backend/.env.example` lists every required variable with a description. Real values never enter the repository — and neither do working development ones for `IDENTITY_HMAC_KEY` or `CONTACT_ENCRYPTION_KEY`: a key committed to an example file is indistinguishable from a real one to the secret scanner, so those two are named with no value and you generate your own (`docs/SECURITY.md`).
- Secrets live in the hosting platform and the vault, nowhere else.
- **Model and gateway credentials are separate per environment**, so staging can never send a real message to a real person. A test run that sends a silicosis referral message to a real number is a data breach and a distressing event. *(Planned — one credential set today.)*
- `render.yaml` **does not govern the live backend service** — it was created through Render's REST API and never Blueprint-synced. Environment variables are set on the service itself. Treat the file as documented intent until it is wired up as a real Blueprint.

## Coding standards and definition of done

A change is done when all of the following are true. This is the review checklist.

- Logic sits in the service layer, not in a router or a screen.
- No clinical constant is hardcoded. Questions, scores, thresholds and overrides come from the versioned tables.
- No patient-facing string is hardcoded or generated at runtime. It comes from the content store, in the person's language, reviewed.
- Tests accompany the change, including a failure case.
- Any schema change is an Alembic migration run forward and backward successfully.
- Anything touching the clinical path records its provenance: instrument version, rule version, method.
- The change behaves correctly offline, or is explicitly documented as online-only with a reason.
- Errors are handled so that a screening is never lost; failures are recorded, not swallowed.
- No personally identifying data appears in a log line.
- The relevant file under `docs/` is updated in the same pull request.

Conventions carried over: `snake_case` JSON keys; timestamps stored in UTC (the wire format is currently `"YYYY-MM-DD HH:MM:SS"` via `database.format_datetime()` — moving to full ISO 8601 is an announced change, not a silent one); every AI call's input and output persisted together for audit.

## Testing strategy

| Level | Covers | Owner | Today |
|---|---|---|---|
| Unit | Scoring, tier assignment, deterioration, overrides, facility matching, code generation, cascade decisions — pure functions with injected time. | Panashe | Built for the current code |
| Instrument regression | A fixed set of answer profiles with expected tiers, run against every instrument version, so a clinical change that moves an unrelated tier is caught. | Panashe, expected values signed off by Gabriel | **Planned** |
| Integration | Full screening through the API on both channels, referral creation, code lookup, attendance confirmation, consent capture. | Panashe | Built for v1, and for the v2 pipeline including consent; the USSD channel is still on its own thresholds (item 1.9) |
| Channel equivalence | The same answers through both channels must produce identical tiers. Automated, because the team claims it publicly. | Panashe | **Planned** — would fail today |
| Content validation | Every patient-facing string in every language passes the character-set check and fits its channel budget. | CI | **Built** — and enforced again at load time, so a string entering the database is checked even when no pull request touched `content/` |
| Device testing | Full screening on the floor handset, in airplane mode, with synchronisation afterwards. | Takudzwa | **Never yet performed** |
| Field usability | Observed sessions with a health worker and a volunteer, timed. | All three, before the pilot | Planned |
| Message delivery | Real messages to real handsets on each network, receipts confirmed. | Panashe | **Never yet confirmed** — sandbox acceptance only |

The pytest suite is SQLite-only by architecture: `backend/tests/conftest.py` builds a throwaway per-test SQLite engine and ignores `DATABASE_URL`. Anything Postgres-specific is verified by hand against a live server. Notifications and email are auto-mocked in every test.

## Continuous integration gates

A pull request cannot merge unless every gate passes. **Seven jobs, all built** — `.github/workflows/ci.yml`, first landed 21 October 2026 (PR #29) and completed 1 November. **Only four are required status checks on protected `main`** — Test suite, Migrations, Secret scan and Dependency vulnerability scan, as set on 21 October. Clinical specifications, Content strings and Instrument regression suite run on every pull request but **do not block a merge**, which means a pull request with a broken instrument or an over-budget string can currently merge with a red tick beside it.

Adding them is a repository settings change and has to be **sequenced after the current stack merges**: a required check that a pull request has never run makes that pull request unmergeable, and the branches queued behind item 1.13 predate the regression job. So the order is: merge the stack, then add the three.

| Job | What it gates | State |
|---|---|---|
| Test suite | pytest on SQLite, Python pinned to 3.12.3 to match `render.yaml`. Includes the no-model-string rule below. | Built |
| Migrations forward and backward (PostgreSQL) | `upgrade head` on an empty PostgreSQL 16 → `downgrade base` → `upgrade head`, then an autogenerate drift check asserting `db_models.py` and `alembic/versions/` have not diverged. | Built |
| Clinical specifications | `scripts/validate_instrument.py` over `clinical/` — shape, the closed predicate grammar, mandatory citations. | Built |
| Content strings | `scripts/validate_content.py` — GSM 03.38 character set, channel budget **in every language**, placeholder parity, three languages before approval. | Built |
| Instrument regression suite | `scripts/validate_fixtures.py` plus `tests/test_instrument_regression.py`: fixed answer profiles with the Clinical Lead's expected tier for each, run against every instrument version. **The gate that makes a clinical change visible.** | Built 1 November; running against the synthetic fixture until instrument version one lands |
| Secret scan | gitleaks over the pull request's whole commit range. | Built |
| Dependency vulnerability scan | `pip-audit --strict`; two advisories suppressed individually with written reasoning, both because no fix version exists. | Built |

Two gates the master document does not list but the same reasoning requires:

- **Channel equivalence** — identical answers through both channels must produce identical result rows. **Planned, and would fail today**: `POST /api/ussd` still runs its own thresholds, so there is nothing to compare the v2 route against. Item 1.9.
- **No model-produced string on a patient-facing field** *(team addition, 18 September 2026)* — **built**, as `tests/test_content_runtime_rule.py` inside the test suite rather than its own job. It asserts on the import graph rather than on behaviour, because a behavioural test catches only the path somebody thought to exercise.

Two things worth knowing about the gates themselves:

- **Every gate was verified against deliberately broken input before being trusted**, including proving the drift check fails on an added probe column, the regression suite fails on a moved threshold, and the append-only audit assertion fails on an added edit path. A gate that cannot fail is worse than no gate, because it reads as coverage.
- **The secret scan scans the whole pull-request range**, not just the tip. A secret committed once and removed later still fails, which is correct — and cost one branch a rewrite (PR #40 → #41).

## Local setup

```
git clone <remote> && cd silicaguard
cd backend
python -m venv venv && ./venv/Scripts/activate           # Windows
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env                                    # fill from the vault; never production values

# Identity keys (§16.2): .env.example names them and carries no values, so
# generate your own. Without them /api/v2/persons/* returns a clean 503 and
# every v1 route still works — fine until you touch identity.
python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"   # IDENTITY_HMAC_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # CONTACT_ENCRYPTION_KEY

uvicorn main:app --reload                                 # http://127.0.0.1:8000, Swagger at /docs

pytest                                                    # full suite
pytest tests/test_screening.py                            # one file
pytest tests/test_screening.py::test_name -v              # one test

./venv/Scripts/python.exe -m alembic upgrade head         # apply migrations to whatever DATABASE_URL names
./venv/Scripts/python.exe -m alembic revision --autogenerate -m "..."   # after editing db_models.py; read it before committing
./venv/Scripts/python.exe scripts/seed_demo_data.py       # reproducible synthetic dataset, no model key needed
./venv/Scripts/python.exe scripts/create_admin.py you@example.org   # the first administrator; RETIRES the two prototype accounts
./venv/Scripts/python.exe scripts/ussd_simulator.py       # USSD flow in the terminal
./venv/Scripts/python.exe scripts/throughput_model.py     # deck-only queueing model (simpy, matplotlib); output gitignored
```

- `DATABASE_URL` is a full SQLAlchemy URL: `sqlite:///./data/silicaguard.db` by default, `postgresql+psycopg://...` in production. Alembic reads the same variable directly (`alembic/env.py`), so `upgrade head` targets whatever the app would connect to.
- With the server running, `http://127.0.0.1:8000/ussd-simulator` is the browser USSD simulator — it posts the exact fields Africa's Talking sends to `/api/ussd`.
- Mobile: `cd mobile && npm install && npx expo start`. `BASE_URL` in `mobile/src/services/api.js` points at the deployed backend; point it at `http://127.0.0.1:8000` for local work. Run on a physical device wherever possible.
- Dashboard: open `dashboard/index.html` or `npx serve dashboard`. `dashboard/lookup.html` is the hospital referral-code page.
- The master document specifies a local PostgreSQL instance for development; today local development runs on SQLite. Both are acceptable until the schema rebuild, after which local PostgreSQL is preferred so migrations are exercised on the production engine.

## Day-to-day procedures

**Add an endpoint**: thin route in `backend/routers/<area>.py` → logic in `backend/services/<area>.py` → Pydantic schema in `backend/models.py` (`snake_case`) → register in `main.py` → `HTTPException` with a real status and `detail` → update `docs/API_CONTRACT.md` before merging; the other developer builds against that document, not your Python.

**Add or change a database field**: edit `backend/db_models.py` → `alembic revision --autogenerate` → **read the generated migration** → `alembic upgrade head` locally, then against the target database in the same sitting → update `scripts/seed_demo_data.py` → update `docs/API_CONTRACT.md` if exposed → announce in `docs/PROGRESS_LOG.md` before merging.

**Call the model**: prompt in `backend/prompts/<name>.txt`, loaded once; strict JSON output with fence-stripping (`_extract_json()` in `ai_risk_engine.py`); persist input and output together; **never on the clinical path** — the model may enrich, explain or flag, never decide (`ARCHITECTURE.md`). The current `assess_risk()` call in `routers/screening.py` is the thing being removed from the tier decision, not the pattern to copy.

**Change a screening question**: today `backend/questions.py` and `mobile/src/screens/QuestionScreen.js` carry separate copies keyed by `question_code`, and the USSD tree and mobile scorer carry their own thresholds — a change on one side silently breaks scoring on the other. This is exactly why the instrument becomes versioned data in Phase One. Until then, change all copies together and get Gabriel's sign-off first.

**Test the offline flow**: airplane mode → three full screenings → reconnect → return to Home (triggers sync) → verify all three on the backend, not just in the app's UI. Nobody has run this yet.

### Recovering a half-migrated database

**Precondition — check this first, because the procedure is wrong for any other state.** This applies when `alembic_version` is *behind* while `Base.metadata.create_all()` has already created the newer **tables**. That is what a deploy produces when the start command does not run migrations: `create_all()` creates a missing table and can never add a missing column to a table that already exists.

Confirm it before doing anything:

```
curl -s https://silicaguard-backend.onrender.com/api/health?recheck=1
```

`schema: "drifted"` with `schema_missing` naming columns on tables that already exist is this state. A missing *whole table* is a different problem and needs a plain `alembic upgrade head`.

**`alembic upgrade head` on its own fails here**, and verified failing: it tries to run the migration that creates the tables `create_all()` already made, and stops at `DuplicateTable: relation "consent_texts" already exists` with nothing applied.

The sequence below was rehearsed against real PostgreSQL 16 by reproducing the state exactly — migrate to `f5bebe94f599`, boot the application so `create_all()` runs, then repair — and verified by `database.missing_schema()` reporting nothing, Alembic's own autogenerate check reporting no drift, and the two broken routes answering again.

```
cd backend

# 1. Tell Alembic what create_all() already built. True for every table it
#    created from the current models, which is what migrations 0004-0008
#    build up to. Nothing is written to the schema by a stamp.
./venv/Scripts/python.exe -m alembic stamp 0008_consent_text_uniqueness

# 2. The only migration whose work is genuinely missing: 0009 adds columns to
#    `referrals` and `screening_answers`, which PRE-EXISTED, so create_all()
#    left them alone. This is the step that actually repairs anything.
./venv/Scripts/python.exe -m alembic upgrade 0009_v2_referrals

# 3. 0010 creates `audit_log` and `users`, which create_all() already made.
./venv/Scripts/python.exe -m alembic stamp head

# 4. Prove it, rather than assume it. THIS IS A LOOP CONDITION, not a
#    formality: if it reports operations, go back to step 1 with the
#    earliest revision that produces them and repeat.
./venv/Scripts/python.exe -m alembic check          # expect: no new upgrade operations
curl -s ".../api/health?recheck=1"                   # expect: schema: "ok"
```

**Expect more than one pass, and never skip step 4.** The drift can be layered, because each deploy's `create_all()` froze whatever the models looked like *at that moment*. Running this against production on 2 November took two passes: the first repaired `referrals` and `screening_answers`, and `alembic check` then revealed that `persons` was missing migration `0007`'s four columns and `consent_texts` its two indexes — because those two tables had been created by an **earlier** deploy, when the models did not yet have them, and every later `create_all()` saw the tables already existed and left them alone.

That is the same bug one layer deeper, from two deploys rather than one, and **nothing but the drift check would have found it**: `missing_schema()` had reported clean after the first pass for the two tables it knew about, and the routes that were visibly broken had started working. The second pass stamped back to `0006`, ran `0007` and `0008`, and stamped forward again.

So the shape of the procedure is: stamp to the revision before the missing work, upgrade through it, stamp to head, check — and repeat until the check is silent.

**Why a stamp is safe in steps 1 and 3 and would not be elsewhere.** A stamp records a revision as applied without touching the schema, so it is only ever correct when the schema already matches what that revision produces. Here it does, because `create_all()` builds tables from the same models the migrations converge on — and step 4's drift check is what confirms that rather than trusting it. Stamping past a migration whose work is *not* already present would leave a database that Alembic believes is current and is not, which is strictly worse than the outage, because the next deploy would skip the repair silently.

**The alternative, and why it is not the default here.** `ARCHITECTURE.md` decision 1 and §8.1 say demonstration data is reseeded, not migrated — so dropping every table, running `alembic upgrade head` on the empty database and reseeding would give a clean migration history with no stamps in it, which is a better story for the ethics submission's data-flow description. It also destroys the demonstration rows the team has been demoing against, which had grown to real use by late September. Prefer it once staging exists (Phase Zero 0.5) and the demonstration target is not also production.

**Then fix the cause**, or this recurs on the next deploy that adds a column: the start command must be `python -m alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port $PORT`, set **on the Render service** — `render.yaml` records it but governs nothing, having been created through Render's REST API and never Blueprint-synced.

## Observability and support

- Error and crash monitoring on the backend with alerts to both engineers. *(Planned)*
- An in-application diagnostics screen: backend connectivity, last successful sync, pending record count, app version. *(Planned)*
- Structured logging with correlation identifiers and no personal data in log lines. *(Partial)*
- A dashboard view of operational health: messages sent and delivered, sessions started and completed, sync backlog, referral ageing. *(Planned)*
- A written support procedure for the pilot. *(Planned)*
- Today: `/api/health` returns `{"status": "ok"}`; a hardening branch (`be/survive-db-outage`) adds a `database: up|down` field and makes boot survive an unreachable database, after the Supabase free tier paused on 6 September and took the whole API down.

## Tools for work that is not code

| Purpose | Tool | Owner |
|---|---|---|
| Design and brand assets | Vector design tool of Takudzwa's choice; source files in shared storage. | Takudzwa |
| The master document | Word processing, versions kept. | Panashe |
| Shared storage | One cloud drive under the SilicaGuard account. | Panashe |
| Stakeholder tracker | Shared sheet, Appendix C of the master document. | Panashe |
| Task tracking | The issue tracker on the code host. | All three |
| Clinical authoring | Plain documents under version control in `clinical/`. | Gabriel |

## Recurring service costs to plan for

All currently unfunded; all belong in every budget submitted: domain renewal; backend hosting (paid tier); database hosting (paid tier, possibly much more if in-country); messaging credit at several messages per screening; **USSD shortcode setup and monthly rental per network** — the largest and least predictable; sender-ID registration per network; model API usage (capped, small); error monitoring; backup storage.
