# CLAUDE.md

Read this at the start of every session. It is the shared reference for both developers on SilicaGuard. If anything here conflicts with the master reference document (`SilicaGuard_MasterDocument_Reference_v6.docx`, v6.0, "Final Showcase Edition"), the reference document wins — flag the conflict and update this file. v6.0 explicitly supersedes v5.0 and every earlier version; it is the single source of truth as of 14 August 2026.

## Project identity

SilicaGuard is an occupational lung health screening system for Zimbabwe's artisanal and small-scale mining workforce — miners covered by neither NSSA nor any existing occupational health programme (formal/enterprise mining employers already run their own; see `docs/PROGRESS_LOG.md`, 5 August, for the scope pivot). A health worker takes an Android app to a mine site, delivers a fifteen-minute group education session using illustrated cards on the phone, then screens each miner in about ten minutes with no doctor present. The system classifies each worker into one of four risk tiers, compares the result against their previous screening to detect deterioration early, and tells each miner the single most important thing he personally should change — drawn from his own answers. Where a referral is needed it routes it to the right facility with a deadline, pre-alerts that facility, and chases the worker until attendance is confirmed. Miners who miss the outreach day self-screen by dialling a USSD code from any phone, with no internet and no cost. Everyone receives their result and reminders by SMS. Hospitals see every referral and whether it was completed. Silicosis is the first module; tuberculosis is next, on the same infrastructure.

- **These dates have all now passed.** Submission was 24 August 2026, the final showcase 28 August 2026. The block below is kept as the record of what the sprint was built against, not as a live schedule — whoever picks the project up next should replace it with the current milestone rather than counting forward from 14 August.
- **Deadlines changed 14 August 2026 (master doc v6.0) — this is a harder deadline, not extra time.** The organisers' final instructions moved the real deadline earlier and added a mandatory deliverable:
  - **Submission — Monday 24 August 2026**: the final presentation deck AND a mandatory 5-minute recorded video, both due together. The video is played during the live presentation — it is the primary demonstration, not a backup.
  - **Feature freeze — Thursday 20 August 2026.** 21–23 August is video shoot/edit and deck finalisation only — no new functionality after the freeze.
  - **Final in-person showcase (Top 10) — Friday 28 August 2026.** The live prototype must still be running and stable on this date — judges may request a live demonstration, four days after submission and eight days after freeze.
  - **Build window — 14–20 August 2026** (this is the current window; today's actual date may be later — count forward from 14 August, don't assume Day 1).
- The original 11 August prototype-presentation date (below, superseded) reflected the sprint's first cycle; treat any reference to it elsewhere in this file's sprint history as historical, not current.

## Ownership boundaries

Two developers share this repo. Respect these boundaries — **never edit a file in the other person's directory without saying so first.**

| Area | Owner |
|---|---|
| `backend/` (schema, AI services, all API routes, deployment, seed scripts) | Panashe M. Chandiwana — AI & Backend Engineer |
| `mobile/` (React Native / Expo app) | Takudzwa — Mobile, Web & Design Engineer |
| `dashboard/` (React web dashboard) | Takudzwa — Mobile, Web & Design Engineer |
| `docs/`, `CLAUDE.md`, the API contract, `.env.example`, database schema | **Shared — requires agreement before changing** |

Gabriel is the team's Clinical Lead, Research & Pilot Lead — owns clinical validity, every patient-facing string's sign-off, the risk/re-screen logic, and the pilot research/stakeholder-engagement design. He doesn't own a code directory, but nothing patient-facing ships without his sign-off (see Non-negotiable rules).

Any change to the database schema or an API response shape must be announced in the shared progress log before merging — it breaks the other developer's work if it lands silently.

## Tech stack — do not suggest alternatives

- **Backend**: Python FastAPI, deployed on Render free tier. **Database: PostgreSQL via Supabase in production** (master doc v6.0 Section 16.2; full SQLAlchemy ORM + Alembic migrations — see Architecture below). Local dev and the full pytest suite still run against SQLite by design — see Architecture.
- **Mobile**: React Native (Expo), `expo-sqlite`, offline-first. No Flutter.
- **Dashboard**: React + Vite + Recharts + Leaflet is the target stack; **as actually shipped, a no-build-step static HTML/CSS/vanilla-JS page** (`dashboard/`) — see SILICAGUARD.md Section 5 for why. Deployed on Render as a Static Site, not Vercel.
- **AI**: Google Gemini 2.5 Flash via the Gemini API. Claude API is the documented drop-in alternative if Anthropic billing becomes available — that's why `ANTHROPIC_API_KEY` exists in `.env.example` even though it's currently unused.
- **USSD and SMS**: Africa's Talking, called directly over `httpx` — **not** the official SDK, which fails with an SSL error on Windows in this environment.
- **No WhatsApp. No voice/IVR. No Flutter. No chest X-ray model.** These were built or considered in earlier versions (v1.0–v3.0) and were deliberately removed. Do not reintroduce them.
- **No QR code, either.** The referral card was reframed 14 August (master doc v6.0 Section 1.1): a short human-readable **referral code** (e.g. `SG-4K7Q`), sent by SMS and entered on a simple hospital web page to confirm attendance — not a scanned QR. A QR is, at most, a later convenience layer that auto-fills the same code; don't build QR generation now.

## Development commands

Backend commands only. `mobile/` has its own `mobile/CLAUDE.md` (which defers to `mobile/AGENTS.md`); `dashboard/` is a no-build-step static page. Full day-to-day procedures (add an endpoint, add a DB field, call the AI, add a screening question, the offline-flow test) live in `SKILL.md` — this is just the commands.

```
cd backend
python -m venv venv && ./venv/Scripts/activate           # first time, Windows
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env                                    # then fill in real values
uvicorn main:app --reload                                 # http://127.0.0.1:8000, docs at /docs

pytest                                                    # full suite
pytest tests/test_screening.py                            # one file
pytest tests/test_screening.py::test_name -v              # one test

./venv/Scripts/python.exe -m alembic upgrade head         # apply migrations to whatever DATABASE_URL names
./venv/Scripts/python.exe -m alembic revision --autogenerate -m "..."   # after editing db_models.py; read the generated file before committing
./venv/Scripts/python.exe scripts/seed_demo_data.py       # reproducible demo dataset, no Gemini key needed
./venv/Scripts/python.exe scripts/ussd_simulator.py       # USSD flow in the terminal
./venv/Scripts/python.exe scripts/throughput_model.py     # deck-only SimPy model; needs requirements-dev.txt, writes throughput_chart.png (gitignored)
```

With the server running, **`http://127.0.0.1:8000/ussd-simulator`** is the browser USSD simulator — a keypad page posting the exact form fields Africa's Talking sends to `/api/ussd`. That is the one to demo (master doc v6.0 Section 16.1); `scripts/ussd_simulator.py` is the older terminal equivalent of the same flow.

Two things about `DATABASE_URL` that catch people out:

- It is a **full SQLAlchemy engine URL**, not a file path — `sqlite:///./data/silicaguard.db` by default, `postgresql+psycopg://...` in production. Alembic reads the same variable straight from the environment (`alembic/env.py`), so `alembic upgrade head` always targets whatever database the app itself would connect to. Point it at the Supabase Session Pooler URL to migrate production.
- **pytest ignores it completely.** `tests/conftest.py`'s `client` fixture builds a throwaway per-test SQLite engine and monkeypatches `database.engine`, so the suite is SQLite-only by design and never exercises Postgres. Anything Postgres-specific — a migration, an FK the old SQLite schema never enforced, a pooler behaviour — has to be verified by hand against a live server.

To run the other two halves (Takudzwa's — read Ownership boundaries before editing anything in them):

```
cd mobile && npm install && npx expo start   # BASE_URL in src/services/api.js points at the deployed backend by default
npx serve dashboard                          # or open dashboard/index.html directly; dashboard/lookup.html is the hospital referral-code page
```

No linter/formatter is configured in `requirements-dev.txt` — don't invent a lint command.

## Architecture

**Updated 15–16 August 2026** — the SQLAlchemy ORM migration's Step A landed 15 August (every router/service described below uses the ORM, not raw SQL); Step B landed 16 August — production now runs on Postgres via Supabase, with Alembic tracking the schema (`docs/PROGRESS_LOG.md`, 15–16 August, has both in full).

Backend is thin-router/fat-service. `routers/<area>.py` parses the HTTP request and calls into `services/<area>.py`, which holds the actual logic; `models.py` has the Pydantic request/response schemas; `db_models.py` holds the SQLAlchemy declarative models (one class per table, schema-preserving vs. the old raw-SQL shape); `database.py` holds the engine/`Session` setup — routes take a `Session` via `Depends(get_db)`, background jobs and audit writes that need their own session outside a request use `get_fresh_session()` instead (see its docstring for why `SessionLocal()` directly would be wrong in a few specific cases). A `get_connection()` shim still exists, returning a real `sqlite3.Connection` — no production code calls it anymore, only a handful of test fixtures doing convenience DB assertions; it raises loudly if ever called with `DATABASE_URL` pointed at Postgres (which now happens in production, but never in pytest — tests always run against per-test throwaway SQLite regardless of the deployed DATABASE_URL). Deleting it entirely means rewriting ~9 test files' assertion helpers onto the ORM/`Session` — real cleanup, deliberately deferred rather than blocking Step B. Alembic is wired up (`backend/alembic/`, `alembic.ini`) — `alembic/env.py` reads `DATABASE_URL` straight from the environment (bypassing `configparser`'s interpolation, which chokes on a `%`-containing percent-encoded password) so `alembic upgrade head` always targets the same database the app would connect to. `main.py` registers routers and owns the three APScheduler jobs (`services.referral_cascade.run_scheduled_cascade`, `services.outreach.run_scheduled_outreach`, `services.db_keepalive.run_scheduled_keepalive`) on one lifespan-scoped `BackgroundScheduler` — forced off under pytest (`SCHEDULER_ENABLED=false` in `tests/conftest.py`) so no test starts a background thread.

`POST /api/screen` (`routers/screening.py`) is the core request and shows the intended call order for new work in this area: persist the raw answers first (so a downstream failure never loses data) → `services/ai_risk_engine.py` (Gemini call against `prompts/risk_engine_prompt.txt`, strict-JSON parse that strips markdown fences) → `services/deterioration.py` (trajectory vs. `previous_screening_id`, can escalate the tier) → `services/safety_overrides.py` (hard red-flag rules in plain Python, applied last so the model can never downgrade a RED) → `services/advice_engine.py` / `services/explanation_shona.py` (template-bound, not model-generated free text) → `services/referrals.py` + `services/facility_matching.py` for ORANGE/RED → `services/notifications.py` (SMS, Africa's Talking REST API over `httpx`, never their SDK) and `services/email_notifications.py`. Every AI call's input and output is persisted on the `screenings` row together, for audit — this is a non-negotiable rule, not a style choice.

The `miners` table (API-facing as "worker") is the identity anchor: `phone` is unique and everything else — screenings, referrals, deterioration comparisons, outreach linkage — hangs off `miner_id`/`worker_id`. `docs/API_CONTRACT.md` is the live source of truth for request/response shapes (with LIVE vs TARGET markers per route); `SILICAGUARD.md` has the full annotated project tree (Section 6), schema (Section 7) and the four AI modules in depth (Section 10).

## API surface

Ten routers, and one auth boundary that is deliberate but not guessable from the paths. `docs/API_CONTRACT.md` holds the request/response shapes; this is the map.

| Router | Routes | Auth |
|---|---|---|
| `screening.py` | `POST /api/screen` | none |
| `ussd.py` | `POST /api/ussd` | none (Africa's Talking webhook) |
| `workers.py` | `POST /api/workers`, `GET /api/workers/{phone}` | none |
| `mines.py` | `GET`/`POST /api/mines` | none |
| `facilities.py` | `GET /api/facilities` | none |
| `referral_lookup.py` | `GET /api/referrals/lookup/{code}`, `POST /api/referrals/lookup/{code}/confirm-attendance` | none (hospital-facing) |
| `dashboard.py` | `GET /api/dashboard/today`, `POST /api/referrals/notify-email` | none |
| `dashboard.py` | `GET /api/dashboard/week`, `GET /api/referrals`, `PATCH /api/referrals/{id}`, `GET /api/miners`, `GET /api/screenings` | Bearer |
| `outreach.py` | `POST /api/outreach` | none |
| `outreach.py` | `GET /api/outreach`, `POST /api/outreach/{id}/send-now` | Bearer |
| `education.py` | `POST /api/education/broadcast` | Bearer |
| `auth.py` | `POST /api/auth/login`, `GET /api/auth/me` | login open, `/me` Bearer |
| `main.py` | `GET /api/health`, `GET /ussd-simulator` | none |

The unauthenticated set is a deliberate precedent, not an oversight: the VHW mobile app never logs in, so everything on the screening path — register a worker, screen him, read his history, list mines, load today's worklist, schedule an outreach visit — has to work without a token, as does the hospital's referral-code page. The Bearer routes are the coordinator dashboard's. Note the split inside both `dashboard.py` and `outreach.py`: one file, routes on both sides of the boundary.

## Deployment

Backend: `https://silicaguard-backend.onrender.com` (Render free tier, auto-deploys on push to `main`). Dashboard: `https://silicaguard-dashboard.onrender.com` (Render Static Site, `rootDir: dashboard`, tracking `main`). Database: Postgres via Supabase on the Session Pooler endpoint, port 5432 — not the Direct connection (IPv6-only, unreachable from Render's free tier) and not the Transaction pooler (breaks SQLAlchemy's session-level assumptions).

Three operational facts to know before touching any of it:

- **`render.yaml` does not govern the live backend service.** That service was created directly through Render's REST API on 6 August and was never Blueprint-synced to this repo, so edits to `render.yaml` have had — and still have — zero effect on what actually runs. Env vars have to be set on the service itself. Treat the file as documented intent until someone wires it up as a real Blueprint, which is a manual dashboard action.
- **The free tier sleeps** after inactivity and takes 30–50 seconds to wake. Hit `/api/health` a few minutes before any demo or rehearsal.
- **`AUTO_SEED_ON_BOOT` is `false` in production.** Postgres is persistent, so reseeding on boot would destroy real state (confirmed referral codes, live screenings). The free Supabase project also auto-pauses after 7 idle days; the only mitigation in code is `services/db_keepalive.py`'s APScheduler job, which upserts one row on the same interval as the other two jobs.

## The four AI modules — and nothing else is AI

1. **Risk Stratification Engine** — screening answers → four-tier classification, reasoning like an occupational health physician, output includes the personalised advice line.
2. **Longitudinal Deterioration Detection** — compares a re-screen against the worker's previous screening; any adverse trajectory escalates the tier one level even if absolute values wouldn't warrant it.
3. **Smart Referral Router** — sets urgency window, matches facility, composes the referral packet, schedules reminders/escalation.
4. **Population Health Intelligence** — weekly job producing site-clustering analysis and a plain-language narrative for the hospital dashboard.

Only 1 and 4 make a live Gemini call. 2 and 3 are deterministic Python — still the AI claims, but say that precisely on camera rather than implying a model is reasoning there (`docs/DEMO_GUIDE.md` has the wording).

The mobile app UI, the dashboards, SMS dispatch, Teach Mode cards, the USSD decision tree, the outreach planner and the compliance export are **not AI**. They are good software engineering. Never describe them as AI — overclaiming weakens the four real claims.

## Non-negotiable rules

Copied verbatim from the reference document's implementation map. These are not up for reinterpretation in the course of normal feature work — if one seems wrong, say so and raise it rather than quietly deviating.

- Hard red-flag overrides live in Python code, outside the model call. The model can never downgrade a RED.
- USSD handlers must respond within 10 seconds and complete a session within 180 seconds. No LLM call inside a USSD session.
- Every screening stores the AI input and output together, so any classification can be audited afterwards.
- The mobile app must complete a full screening with no connectivity and sync cleanly afterwards. Test in airplane mode before declaring done.
- Phone numbers are hashed at rest. Never store a raw phone number in an exportable table.
- Every patient-facing string requires the Clinical Lead's written sign-off before it ships.
- Every screening result must carry a personalised advice line. A result without one is incomplete.

## Coding conventions

- API responses use `snake_case` JSON keys.
- All timestamps stored in UTC, ISO 8601.
- Never hardcode secrets — always read from environment variables.
- Any change to the database schema or an API response shape must be announced in the shared log before merging.

## Git workflow

- `main` is protected and always deployable.
- Branch naming: `be/<short-description>` for backend, `fe/<short-description>` for frontend.
- Small commits, clear messages, pull request into `main`.
- Pull from `main` before starting work every day.

## Current state

A snapshot, not a log. The dated session-by-session history moved to `docs/PROGRESS_LOG.md` on 9 September 2026 — append new entries there, and **rewrite this section in place** rather than growing it. It had reached 77% of this file, and two pairs of parallel branches had already silently lost each other's edits to it.

Last verified against the tree: 9 September 2026, on `main`.

**Built and live in production.** All four AI modules; the full screening pipeline (`POST /api/screen` → Gemini risk engine → deterioration → Python safety overrides → advice line + Shona explanation → facility-matched referral → SMS); the reminder/escalation cascade and outreach announcements on APScheduler, plus on-demand `POST /api/outreach/{id}/send-now`; result SMS for all four tiers; the referral code end to end (generated on ORANGE/RED → in the miner's SMS and the hospital pre-alert → shown on the mobile referral card → confirmable at `dashboard/lookup.html` or from the app's Worklist); the USSD self-screening tree and its browser simulator at `/ussd-simulator`; Postgres via Supabase with Alembic; the coordinator dashboard (Chart.js, Leaflet facility map, referral queue, outreach planner, miners directory, activity log); the VHW mobile app with an AsyncStorage-backed offline sync queue; the SMS `notifications` audit trail; repeat-screening interval stats; `scripts/throughput_model.py` for the deck.

**Genuinely not built — do not claim these live:**

- **Teach Mode.** The master doc's six illustrated in-app cards do not exist anywhere. `POST /api/education/broadcast` (`services/education_messages.py`) is a working, deliberate stand-in that sends the same six topics as EN+Shona SMS. Present it as the SMS channel for Teach Mode, not as Teach Mode.
- **Clinical Lead sign-off on patient-facing copy.** Every advice-line template, `explanation_shona` template, SMS template, the narrative prompt and the dashboard copy are still draft. `backend/prompts/PENDING_CLINICAL_REVIEW.md` tracks the two specific discrepancies against the master doc (the YELLOW re-screen interval, the "Level 1–4" SMS/USSD wording). This is a non-negotiable rule with nothing signed against it yet.
- **Real SMS arriving on a physical handset.** Every "SMS sent" note in the progress log is an Africa's Talking *sandbox* API success — a 201 and a logged row — not confirmed delivery. Sandbox silently no-ops for any number not registered as a Simulator Number, which is a dashboard-only action on their side.
- **USSD over a real carrier network.** Sandbox and the local simulators only; no production shortcode is provisioned. The master doc's own resolution is to demo through our simulator with a real SMS leg, framed on stage as "our simulator, their SMS."
- **The airplane-mode test.** The offline queue is code-complete and wired into `ResultScreen.js`'s failure path, but the non-negotiable rule says test it in airplane mode before declaring it done, and nobody has.
- **Stakeholder engagement** (master doc Section 4.2, Gabriel's): zero conversations logged.
- **A logo or brand asset**: none anywhere in the repo.

**Open decisions, not code:** whether to put the Supabase project on Pro for the critical period (the keep-alive job is currently the only 7-day-pause mitigation); the phone-number hashing rule, reviewed below but never signed off by the team.

**Known debt worth knowing about:** `database.get_connection()` survives only for test-fixture convenience — removing it means rewriting ~9 test files' assertion helpers onto the ORM. `mobile/src/components/OutreachBanner.js` and `MinerScreeningIllustration.js` are dead. Two comments in `mobile/src/services/api.js` still describe the cascade and `ai_narrative` as unbuilt; both have been live since 5 August. `SyncPill` derives connectivity from the pending-queue count, so it cannot tell "offline with nothing queued" from "connected."

**Phone-number hashing rule, reviewed not changed**: this file's non-negotiable rule says phone numbers must be hashed at rest and never stored raw in an exportable table. `miners.phone` stays plaintext — it is the operational identity for SMS delivery, USSD caller lookup and `GET /api/workers/{phone}`, and a one-way hash breaks all three (you cannot text a hash). The rule's actual target, an *exportable* table, does not exist post-pivot: the enterprise CSV export that would have been that surface is out of scope. The recommendation is to treat the rule as binding on any future bulk-export surface specifically, rather than on the operational table. Flagged per the rule's own "if one seems wrong, say so" instruction, not decided unilaterally — it still needs the team's agreement.
