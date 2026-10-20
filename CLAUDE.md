# CLAUDE.md

Operating guidance for AI-assisted development sessions on SilicaGuard. Read this first, then the files it points to. It is deliberately short: the substance lives in the documentation set derived from the master document, and this file exists so a session knows where to look and which rules are not negotiable.

## Source of truth

`SilicaGuard_Master_Reference_and_Roadmap.docx` (v1.0, September 2026) is the single source of truth — problem statement, evidence, architecture, clinical instrument, security model, roadmap, operating disciplines. `docs/master/MASTER_REFERENCE.md` is its rendered copy (regenerate, never edit). It explicitly supersedes every earlier reference document, including v6.0 "Final Showcase Edition".

**Where the repository and the master document disagree, the document is right and the repository is out of date — unless the document describes something as planned rather than built.** The documentation set marks every claim **Built** or **Planned** for exactly this reason. Do not describe a planned thing as built, in code comments, docs, UI copy or a demo.

Read in this order for any non-trivial task: `README.md` → `ARCHITECTURE.md` → `ROADMAP.md` → the `docs/*.md` file for your area → `docs/API_CONTRACT.md` if you touch a request or response.

| File | Derived from | Holds |
|---|---|---|
| `README.md` | §2, §4, §6.1 | What it is, positioning, the two channels, the four modules with the honest method column, current state |
| `ROADMAP.md` | §21.4, §22 | Phases, exit criteria, critical path, individual deadlines. **Current phase: Zero.** |
| `ARCHITECTURE.md` | §8, §9, §10 | The five irreversible decisions, the classification decision, the seven principles, pipeline, data model, environments, NFRs — each against what the code does today |
| `docs/STACK.md` | §11 | Stack, accounts, repo layout, branching, definition of done, testing, CI gates, local setup, procedures |
| `docs/CLINICAL.md` | §12, App. A | The instrument. **Owner: Gabriel.** |
| `docs/CHANNELS.md` | §13 | USSD, messaging, devices, dashboard |
| `docs/SECURITY.md` | §14, §16 | Consent, threat model, controls, roles, incident response, pre-pilot checklist |
| `docs/REGISTER.md` | §15 | The national register |
| `docs/VALIDATION.md` | §7, §17 | External evidence, realistic performance, research partners |
| `docs/FIGURES.md` | App. B | **The only permitted source of numbers, anywhere.** |
| `CONTRIBUTING.md` | §2.5, §21.3 | The five disciplines, working practices, ownership, decision rights |
| `docs/API_CONTRACT.md` | — | v1 request/response shapes (LIVE/TARGET markers) |
| `docs/PROGRESS_LOG.md` | — | Dated, append-only build history. Announce schema/API changes here before merging. |

## What SilicaGuard is, in one paragraph

An occupational lung health screening and referral system for Zimbabwe's artisanal and small-scale miners. A village health worker screens on site with an offline Android app; a miner who misses the visit self-screens over USSD from any handset. Both produce the same risk tier from the same clinical rules. Tier 3/4 results generate a referral to a real facility with a deadline, a pre-alert, a reminder cascade and a short referral code that hospital staff enter to confirm attendance — which is what makes referral completion measurable, and referral completion is the metric the system is judged on. **It does not diagnose.** Silicosis and artisanal mining are the first cell of a grid designed to grow along three independent axes: condition, sector, and who administers and pays.

## Where we are

**Phase Zero — Foundation**, week one beginning Monday 21 September 2026. The Healthathon prototype (won, August 2026) is a working system that has never touched a real patient. The database holds only demonstration data, no consent has been taken, nothing is under a data-protection obligation. **This is the last moment when the expensive decisions are still cheap** — the roadmap does the irreversible things first (`ARCHITECTURE.md`, the five decisions) and defers everything reversible. No feature work until those five are addressed.

Three things start immediately regardless of phase because their lead times are longest: the USSD shortcode process, the ethics submission preparation, and the founders agreement with company registration. **Gabriel is on the critical path** — the instrument gates the ethics submission, which gates the pilot.

## Rules that are not negotiable

From the master document. If one seems wrong, say so and raise it — never quietly deviate.

**The five operating disciplines** (`CONTRIBUTING.md`): no unconfirmed figure stated as fact; no partnership claimed that is not formally confirmed; precise about what is AI and what is engineering; name gaps before being asked; artisanal scope unless the whole team records otherwise.

**The seven architectural principles** (`ARCHITECTURE.md`): the clinical path is deterministic — no model between answers and a tier, any channel, online or offline; offline is the normal case; clinical logic is data, not code; channels are equivalent; every clinical output is traceable to an instrument and rule version; fail toward recording, never toward silence; identity separated from clinical content.

**Specific rules that follow:**
- Hard safety overrides live in Python, run last, and can raise a tier but never lower one. The model can never downgrade a RED.
- No language-model call inside a USSD session. Under 3 s per turn, hard ceiling well under 10 s.
- A completed screening is never discarded. Answers are persisted before scoring. A messaging failure is recorded and retried, never a lost screening.
- **No runtime machine translation of anything a worker reads or hears.** Every patient-facing string is human-authored, clinically reviewed, versioned, stored against a message code with one row per language (English, Shona, Ndebele), and passes the GSM 7-bit check. Model-generated free text never reaches a patient-facing surface. This holds regardless of what the code happens to do today and will be enforced by a test.
- Every patient-facing string and every clinical constant requires Gabriel's recorded approval on the pull request before it ships. Nobody may override a clinical decision.
- Every result row records instrument version, ruleset version, method and whether an override fired.
- Telephone number is never an identity key. Merges are never automatic and always reversible.
- Consent is layered, recorded as data, and exists before the first real record.
- An employer or programme sponsor never receives individual results without separate, specific, refusable consent.
- Production data is never copied to staging or a developer machine. Demonstrations run against staging.
- Secrets never enter the repository. No personal data in a log line.
- The word *silicosis* may appear in the database as a value, never as a column name.

**Locked scope**: no formal or enterprise mining in phase one; no chest X-ray or imaging analysis; no WhatsApp; no QR codes; no voice/IVR; no mercury module. Do not reintroduce any of them.

## Ownership

Two engineers and a clinical lead share this repository. **Never edit a file in someone else's area without saying so first.**

| Area | Owner |
|---|---|
| `backend/` — schema, clinical engine, routers, services, migrations, security, deployment | Panashe |
| `mobile/`, `dashboard/`, `website/` | Takudzwa |
| `clinical/`, `content/` (planned), and until they exist every clinical constant and patient-facing string wherever it lives | Gabriel — sign-off, not code |
| `docs/`, `README.md`, `ROADMAP.md`, `ARCHITECTURE.md`, this file, `docs/API_CONTRACT.md`, `.env.example` | Shared — agreement before changing |

Decision rights, in full, in `CONTRIBUTING.md`. Scope changes need all three, recorded in the master document.

## Tech stack — do not suggest alternatives

Python/FastAPI, SQLAlchemy + Alembic, PostgreSQL (Supabase in production, SQLite locally and under pytest), APScheduler in-process, React Native/Expo for Android, a static vanilla-JS dashboard, Africa's Talking over REST (never their SDK — certificate failure on Windows), Resend for email, Gemini **pinned to `gemini-3.1-flash-lite`** for the aggregate narrative and reviewed drafting only. Deliberately not chosen: framework migrations, microservices, message brokers, orchestration, analytics warehouses. Full table with owners and current state in `docs/STACK.md`.

## Commands

`docs/STACK.md` has the full local setup and every day-to-day procedure. The essentials:

```
cd backend
python -m venv venv && ./venv/Scripts/activate
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env
uvicorn main:app --reload                                 # http://127.0.0.1:8000, /docs
pytest                                                    # SQLite-only by design; ignores DATABASE_URL
./venv/Scripts/python.exe -m alembic upgrade head         # targets whatever DATABASE_URL names
./venv/Scripts/python.exe scripts/seed_demo_data.py
```

`http://127.0.0.1:8000/ussd-simulator` is the browser USSD simulator. Mobile: `cd mobile && npm install && npx expo start` (`mobile/CLAUDE.md` → `mobile/AGENTS.md`). Dashboard: open `dashboard/index.html`. No linter or formatter is configured — don't invent one.

## Architecture today, in three sentences

Thin routers (`backend/routers/`) delegate to services (`backend/services/`); `db_models.py` holds the ORM, `models.py` the Pydantic schemas, `database.py` the engine and `get_db`/`get_fresh_session`. `POST /api/screen` persists answers first, calls Gemini for a base tier, runs deterioration then safety overrides, selects template-bound advice and Shona text, creates a referral for ORANGE/RED, sends SMS. The rebuild replaces the Gemini step with the deterministic cascade, adds identity/consent/instrument-version steps before it and result rows after it — `ARCHITECTURE.md` has the target pipeline and, per decision, exactly what today's code does instead and which files it touches.

## API surface

Ten routers, one auth boundary that is deliberate but not guessable from the paths. `docs/API_CONTRACT.md` holds the shapes; this is the map.

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

The unauthenticated set is deliberate: the VHW app never logs in, so the screening path and the hospital lookup page work without a token. The role model that replaces the two flat `hospital`/`cimas` accounts is in `docs/SECURITY.md`.

## Deployment

Backend `https://silicaguard-backend.onrender.com` (Render free tier, auto-deploys from `main`); dashboard `https://silicaguard-dashboard.onrender.com` (Render Static Site, tracking `main`); Supabase Postgres on the Session Pooler, port 5432 — not Direct (IPv6-only) and not the Transaction pooler. **There is no staging**; this one service is production and the demo target, which `ARCHITECTURE.md` lists as a Phase One correction.

- **`render.yaml` does not govern the live backend service.** It was created through Render's REST API and never Blueprint-synced; editing the file does nothing. Env vars are set on the service.
- **The free tier sleeps** (30–50 s wake). The free Supabase project pauses after 7 idle days — it did so on 6 September and took the API down entirely because startup called `init_db()` unconditionally; `be/survive-db-outage` (unmerged) makes boot survive that. Paid tiers before any demonstration or pilot.
- `AUTO_SEED_ON_BOOT` is `false` in production. Postgres is persistent.

## Working in this repository

- Pull `main` before starting. Short-lived branches: `be/`, `fe/`, `docs/`, `clinical/`. Reviewed PR into protected `main`, including for area owners.
- Announce any schema or API-response-shape change in `docs/PROGRESS_LOG.md` before merging. Update `docs/API_CONTRACT.md` in the same PR.
- Update the relevant `docs/` file in the same PR as the change. Append to `docs/PROGRESS_LOG.md` at the end of a session; never grow this file chronologically.
- Definition of done is the checklist in `docs/STACK.md`. Read it before opening a PR.
- Do not spawn subagents, build artifacts or add tooling unless asked.
