# SilicaGuard

**Screen. Track. Follow Through.**

An occupational lung health screening and referral system for Zimbabwe's artisanal and small-scale mining communities — more than 500,000 people who produce roughly three quarters of the country's gold and sit outside every occupational health and compensation system that exists. Nobody screens them, nobody tracks them, and when a donor-funded outreach campaign does reach them, the campaign ends and the tracking ends with it.

> Derived from `docs/master/MASTER_REFERENCE.md` §2, §4 and §6.1 (Master Reference v1.0, September 2026) — the single source of truth for this project. Where this file and that document disagree, the document is right.

## What it is, and what it is not

SilicaGuard takes a worker through a short structured screening, assigns a risk tier using transparent clinical rules, compares the result to that worker's own previous screening, and produces either a health message or a referral. A referral carries a named facility, a deadline, a text message to the worker, a pre-alert to the facility, a reminder cascade, and a short human-readable code that hospital staff enter on a lookup page to confirm attendance. That last step is what makes referral completion measurable rather than assumed, and referral completion is the metric this system is judged on.

**SilicaGuard is not a diagnostic tool and does not diagnose, treat or replace clinical judgement.** Hospitals diagnose silicosis, through imaging and clinical assessment. SilicaGuard decides who gets on the imaging list first and makes sure they turn up — the front end to radiology, not an alternative to it.

It does not replace Ministry of Health outreach or donor campaigns. It is the layer that keeps working after the truck leaves.

## Two entry channels, one backend

- **Mobile** — a village health worker with an Android device at a mine site. A group education session, then individual screening of roughly ten minutes each. Works entirely offline, scores locally, synchronises when a connection is available. The higher-quality data channel.
- **USSD** — a miner dialling a shortcode from any handset. No smartphone, no internet and, once reverse billing is in place, no cost. This channel is the reason SilicaGuard reaches people that every smartphone-based health tool structurally excludes.
- The **dashboard** serves coordinators, hospitals and eventually national stakeholders. A consumer of the data, not a producer.

## The four modules — and which of them use a language model

| Module | What it does | Method |
|---|---|---|
| 1. Risk Stratification Engine | Assigns a risk tier from the screening answers, with hard safety overrides that can raise a tier but never lower one. | **Deterministic clinical rules.** Today a language model still assigns the base tier on the mobile channel; moving it off the clinical path is the first Phase One task (`ARCHITECTURE.md`). |
| 2. Longitudinal Deterioration Detection | Compares the current screening against the same worker's previous one on a tracked subset of answers and escalates on worsening. | Deterministic engineering. Not artificial intelligence and never described as such. |
| 3. Referral Routing and Follow Through | Matches a facility, sets an urgency deadline, issues a referral code, pre-alerts the facility, runs the reminder cascade, escalates on non-attendance. | Deterministic engineering. Not artificial intelligence and never described as such. |
| 4. Population Health Intelligence | A narrative summary of aggregate screening activity for the dashboard, with a deterministic fallback. | Genuine language-model application, on aggregate statistics only, never on an individual clinical decision. |

Everything else — the mobile interface, the dashboard, message dispatch, the USSD decision tree, the outreach planner, the education content — is engineering.

## Risk tiers

| Tier | Internally | In messages | Meaning | Action |
|---|---|---|---|---|
| 1 | Green | Level 1 | No current symptomatic indicators | Reinforce dust control and protective equipment; routine re-screen |
| 2 | Yellow | Level 2 | Cumulative unprotected exposure or mild isolated symptoms | Targeted education; shortened re-screen interval |
| 3 | Orange | Level 3 | Core chronic symptoms present; imaging indicated | Referral with a defined window; reminder cascade |
| 4 | Red | Level 4 | Red-flag indicators; possible complicated disease or active tuberculosis | Urgent referral within 48 hours with active tracking |

Colour is never used alone. Intervals and windows are subject to clinical sign-off (`docs/CLINICAL.md`).

## Where the system stands

SilicaGuard won the Cimas Healthathon 3.0 in August 2026. What exists is a working prototype. **What does not yet exist is a system that has ever touched a real patient.**

### Built and working

| Component | State |
|---|---|
| Backend | Python and FastAPI, ten routers, service layer separated from routing, 189 tests passing |
| Database | PostgreSQL through a managed free tier, nine tables, Alembic migrations |
| Mobile | React Native and Expo, eight screens, offline-first with a local queue |
| Dashboard | Static markup and vanilla script with charting and mapping: login, statistics, tier distribution, site breakdown, facility map, referral queue, outreach planner, miner directory, activity log |
| Referral lookup | Unauthenticated code lookup and attendance confirmation, so hospital staff can close a referral without an account |
| USSD | Working decision tree with a browser simulator |
| Messaging | Seven message senders through the gateway's REST interface, every send written to an audit table |
| Scheduler | Background jobs for the referral cascade, outreach announcements and database keep-alive |

### Not true yet

- No real patient has ever been screened. Every record is demonstration data.
- No ethics approval, no Ministry clearance, no data-controller registration.
- No USSD shortcode. No shortcode appears in any material until one is allocated.
- No confirmed message delivery to a physical handset outside the sandbox.
- No clinical sign-off on the instrument or on any patient-facing text.
- Teach Mode as designed — illustrated in-app education cards — is not built; text-message health tips are the stand-in.
- No validation of any kind: no sensitivity, no specificity, no radiological comparison.
- Phone numbers stored in plaintext; hosting outside Zimbabwe; device classification not formally determined.
- The screening produces one tier as columns, identity is keyed on phone number, and every clinical rule is hardcoded in three places — the architectural defects the current phase exists to correct (`ARCHITECTURE.md`).

## Scope decisions that are locked

No formal or enterprise mining in phase one. No chest X-ray or imaging analysis. No WhatsApp. No QR codes. No voice or IVR. No mercury toxicity module. Not reopened without an explicit, recorded, team-wide decision.

## Documentation

| File | What it holds |
|---|---|
| `docs/master/MASTER_REFERENCE.md` | The master document, rendered from the `.docx`. Source of truth. |
| `ROADMAP.md` | Phases, exit criteria, critical path, individual deadlines. Current phase: Zero. |
| `ARCHITECTURE.md` | The five irreversible decisions, the classification decision, principles, pipeline, data model. |
| `docs/STACK.md` | Stack, accounts, repository layout, branching, definition of done, testing, CI gates, local setup. |
| `docs/CLINICAL.md` | The instrument: corrections required, version two question set, sign-off record. Owner: Gabriel. |
| `docs/CHANNELS.md` | USSD, messaging, devices, dashboard constraints. |
| `docs/SECURITY.md` | Legal obligations, consent, threat model, controls, roles, incident response, pre-pilot checklist. |
| `docs/REGISTER.md` | What the national register is and is not; stewardship; data classification. |
| `docs/VALIDATION.md` | External evidence, realistic performance, validation questions, research partners. |
| `docs/FIGURES.md` | The only permitted source of numbers for any material. |
| `docs/API_CONTRACT.md` | The v1 API request/response shapes both frontends build against. |
| `docs/PROGRESS_LOG.md` | Dated, append-only build history. |
| `CONTRIBUTING.md` | The five operating disciplines, working practices, ownership, decision rights. |
| `CLAUDE.md` | Operating guidance for AI-assisted development sessions. |

## Running it

```
cd backend
python -m venv venv && ./venv/Scripts/activate           # Windows
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env                                    # fill from the vault
uvicorn main:app --reload                                 # http://127.0.0.1:8000, Swagger at /docs
pytest
./venv/Scripts/python.exe scripts/seed_demo_data.py       # synthetic demo data
```

Mobile: `cd mobile && npm install && npx expo start`. Dashboard: open `dashboard/index.html`. USSD: `http://127.0.0.1:8000/ussd-simulator`. Full setup, Alembic, environments and procedures in `docs/STACK.md`.

## Team

Panashe M. Chandiwana — Team Leader, Founder, Backend and AI Engineer. Takudzwa — Mobile, Web and Design Engineer. Gabriel — Clinical Lead. Dr S. Bopoto (Cimas) — mentor, advisory.
