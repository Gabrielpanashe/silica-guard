# SilicaGuard

An occupational lung health screening system for Zimbabwe's mining workforce. A health worker takes an Android app to a mine site, delivers a short group education session, then screens each miner in about ten minutes. The system classifies each worker into one of four risk tiers, compares the result against their previous screening to detect deterioration early, and gives each miner one personalised piece of advice drawn from his own answers. Referrals are routed, tracked and chased to a confirmed outcome. Miners who miss the outreach day can self-screen by USSD from any phone, no internet required. Built for Cimas Healthathon 3.0 — submission (deck + 5-minute video) 24 August 2026, final in-person showcase 28 August 2026 (see `CLAUDE.md` for the full timeline).

Full product context: `SILICAGUARD.md`. Working rules and ownership boundaries: `CLAUDE.md`. Day-to-day procedures (run locally, add an endpoint, seed data): `SKILL.md`. Backend API shape: `docs/API_CONTRACT.md`.

## Setup

Requires Python 3.12+. Copy `backend/.env.example` to `backend/.env` and fill in real values before running.

```
cd backend
python -m venv venv
./venv/Scripts/activate        # Windows
pip install -r requirements.txt
uvicorn main:app --reload
```

The API is now running at `http://127.0.0.1:8000`, with interactive docs at `/docs`. To populate it with demo data:

```
./venv/Scripts/python.exe scripts/seed_demo_data.py
```

Mobile (`mobile/`, React Native/Expo) and the dashboard (`dashboard/`, plain HTML/CSS/JS — see `SILICAGUARD.md` Section 5 for why not the target React/Vite stack) both exist and are live — see `CLAUDE.md` for ownership and ports of call.

## Repo layout

- `backend/` — FastAPI backend: API routes, AI risk engine, USSD/SMS integration, database (SQLite, migrating to PostgreSQL via Supabase this sprint — see `CLAUDE.md`).
- `docs/` — the API contract shared between backend and both frontends.
- `mobile/` — React Native (Expo) practitioner app.
- `dashboard/` — the web dashboard.
