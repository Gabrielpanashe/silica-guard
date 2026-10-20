# Technology stack and developer guide

> Derived from `docs/master/MASTER_REFERENCE.md` §11 (Master Reference v1.0, September 2026). The master document wins on any conflict. This is the developer onboarding document; it absorbs the former `SKILL.md`. **Built** = true today (audited 18 September 2026); **Planned** = specified, not yet in place.

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
| Mobile storage | **Encrypted** local storage with an offline queue | Takudzwa | Queued clinical data on a device that can be lost in a mining compound must be encrypted. | AsyncStorage queue, **unencrypted** |
| Dashboard | Static markup, vanilla script, charting and mapping libraries | Takudzwa | No build step. Deliberately simple so it cannot rot. | Built — Chart.js, Leaflet |
| Website | Single static page on free static hosting | Takudzwa | Deliberately minimal (master document §24.1). | **Planned** — Phase Zero, week 1 |
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
| `website/` | The single-page public site. | **Planned** |
| `clinical/` | Instrument specifications by version, as reviewable source, plus the migration that loads each version. Owned by Gabriel. | **Planned** |
| `content/` | Patient-facing strings by message code and language, with the character-set validator applied in CI. | **Planned** |
| `diagrams/` | Diagram source files, regenerated rather than hand-edited. | Placeholder only |
| `docs/` | The documentation set mapped in Appendix D of the master document. | Built (this pass) |

## Branching and release

See `CONTRIBUTING.md`. In brief: short-lived branches, protected `main`, reviewed pull requests for everyone, Gabriel's recorded approval on anything clinical, staging on merge, production from a tag. **Today** there is one environment, auto-deployed from `main` — the staging/production split is Phase One.

## Configuration and secrets

- All configuration is environment-based. No environment-specific values in code.
- `backend/.env.example` lists every required variable with a description. Real values never enter the repository.
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
| Integration | Full screening through the API on both channels, referral creation, code lookup, attendance confirmation, consent capture. | Panashe | Built except consent |
| Channel equivalence | The same answers through both channels must produce identical tiers. Automated, because the team claims it publicly. | Panashe | **Planned** — would fail today |
| Content validation | Every patient-facing string in every language passes the character-set check and fits its channel budget. | CI | **Planned** |
| Device testing | Full screening on the floor handset, in airplane mode, with synchronisation afterwards. | Takudzwa | **Never yet performed** |
| Field usability | Observed sessions with a health worker and a volunteer, timed. | All three, before the pilot | Planned |
| Message delivery | Real messages to real handsets on each network, receipts confirmed. | Panashe | **Never yet confirmed** — sandbox acceptance only |

The pytest suite is SQLite-only by architecture: `backend/tests/conftest.py` builds a throwaway per-test SQLite engine and ignores `DATABASE_URL`. Anything Postgres-specific is verified by hand against a live server. Notifications and email are auto-mocked in every test.

## Continuous integration gates

A pull request cannot merge unless every gate passes. **None of these exists today** — there is no CI configuration in the repository. Adding them is Phase Zero security work (`docs/SECURITY.md`).

- Full test suite green.
- Character-set validator on all content strings in all languages.
- Channel budget: every USSD question, with options and navigation, fits the page limit in every language.
- Migration check: migrations apply cleanly to an empty database and to a copy of the staging schema.
- Secret scan.
- Dependency vulnerability scan; high severity blocks the merge.
- Instrument regression suite green.
- *(Team addition, 18 September 2026)* A test asserting that no model-produced string is ever written to a patient-facing field.

## Local setup

```
git clone <remote> && cd silicaguard
cd backend
python -m venv venv && ./venv/Scripts/activate           # Windows
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env                                    # fill from the vault; never production values
uvicorn main:app --reload                                 # http://127.0.0.1:8000, Swagger at /docs

pytest                                                    # full suite
pytest tests/test_screening.py                            # one file
pytest tests/test_screening.py::test_name -v              # one test

./venv/Scripts/python.exe -m alembic upgrade head         # apply migrations to whatever DATABASE_URL names
./venv/Scripts/python.exe -m alembic revision --autogenerate -m "..."   # after editing db_models.py; read it before committing
./venv/Scripts/python.exe scripts/seed_demo_data.py       # reproducible synthetic dataset, no model key needed
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
