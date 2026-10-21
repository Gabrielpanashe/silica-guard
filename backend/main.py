import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from database import database_reachable, init_db
from routers import auth, dashboard, education, facilities, mines, outreach, referral_lookup, screening, ussd, workers
from services.db_keepalive import run_scheduled_keepalive
from services.outreach import run_scheduled_outreach
from services.referral_cascade import run_scheduled_cascade

logger = logging.getLogger("silicaguard.main")

scheduler: BackgroundScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler
    # A database that is down must not take the whole API down with it.
    # 11 September 2026: the free-tier Supabase project auto-paused after 7
    # idle days (Render had slept, so services/db_keepalive.py stopped
    # pinging it), init_db() raised here, startup never completed, and
    # Render marked the deploy `update_failed` — so there was no instance
    # serving anything at all, not even /api/health, and nothing to tell
    # anyone from outside whether the API or the database was the problem.
    # Boot degraded instead: /api/health still answers (reporting the
    # database as down) and DB-backed routes return a clean 503 from
    # database.get_db(). The service then recovers on its own the moment
    # the database comes back — no redeploy needed.
    db_ready = False
    try:
        init_db()
        db_ready = True
    except Exception:
        logger.exception(
            "init_db() failed — starting in degraded mode. /api/health will "
            "report database=down and DB-backed routes will return 503 until "
            "the database is reachable again."
        )

    # Render's free tier has no persistent disk — the SQLite file resets on
    # every redeploy and likely every sleep/wake cycle. Rather than silently
    # deploy with an empty, unseeded DB, re-run the same reproducible demo
    # dataset used locally (backend/scripts/seed_demo_data.py) on every boot
    # when this is explicitly turned on. Off by default — this wipes and
    # reseeds every table the script owns, so it must never run against a
    # real deployment carrying real screenings. Confirmed decision (6 August
    # 2026): accept ephemeral storage for the 11 August demo rather than pay
    # for a persistent disk or migrate to Postgres this close to feature
    # freeze — see CLAUDE.md's sprint status for the full reasoning.
    if os.getenv("AUTO_SEED_ON_BOOT", "false").lower() == "true":
        if not db_ready:
            logger.warning("AUTO_SEED_ON_BOOT=true but the database is unreachable — skipping seed")
        else:
            from scripts.seed_demo_data import seed

            seed()
            logger.info("AUTO_SEED_ON_BOOT=true — reseeded demo data on startup")

    # Smart Referral Router reminder/escalation cascade — an in-process
    # background job, not an external cron (Render free tier gives us no
    # cron and this needs no new infrastructure to demo). Disabled under
    # pytest via SCHEDULER_ENABLED=false (set in tests/conftest.py before
    # `import main`), so no test ever starts a background thread. Only runs
    # while this process is awake — Render's free tier sleeps after
    # inactivity, so warm the server before a demo, same as /api/health.
    if os.getenv("SCHEDULER_ENABLED", "true").lower() != "false":
        interval = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "10"))
        scheduler = BackgroundScheduler()
        scheduler.add_job(run_scheduled_cascade, "interval", minutes=interval, id="referral_cascade")
        # Outreach Planner's 3-day/1-day announcement + report-ready cadence —
        # a second job on the SAME scheduler instance/interval, not a second
        # scheduler (see services/outreach.py).
        scheduler.add_job(run_scheduled_outreach, "interval", minutes=interval, id="outreach_announcements")
        # Supabase keep-alive (Step B, 15 August 2026) — see
        # services/db_keepalive.py. A third job on the same scheduler; only
        # matters in production (a free Supabase project pauses after 7 days
        # idle) but harmless to also run locally against SQLite.
        scheduler.add_job(run_scheduled_keepalive, "interval", minutes=interval, id="db_keepalive")
        scheduler.start()
        logger.info("Referral cascade + outreach + keep-alive schedulers started (every %s min)", interval)

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None


app = FastAPI(title="SilicaGuard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(screening.router)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(ussd.router)
app.include_router(workers.router)
app.include_router(outreach.router)
app.include_router(mines.router)
app.include_router(facilities.router)
app.include_router(referral_lookup.router)
app.include_router(education.router)


@app.get("/api/health")
def health():
    # `status` stays "ok" whenever the process is serving — that is what this
    # endpoint has always meant and what warms Render's sleeping free tier
    # before a demo. `database` is additive (11 September 2026): it separates
    # "the API is down" from "the API is up but the database is unreachable",
    # which from outside looked identical during the Supabase pause.
    return {"status": "ok", "database": "up" if database_reachable() else "down"}


# USSD web simulator (14 August 2026, master doc v6.0 Section 16.1) — a
# self-contained static page (backend/static/ussd_simulator.html, no build
# step, no new dependency) that POSTs the exact same fields a real Africa's
# Talking webhook would to the existing /api/ussd route above. Served
# directly rather than mounted via StaticFiles for one file — see
# SKILL.md's "run the USSD web simulator" note.
_STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/ussd-simulator")
def ussd_simulator_page():
    return FileResponse(_STATIC_DIR / "ussd_simulator.html")
