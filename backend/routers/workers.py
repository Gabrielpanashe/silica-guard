import sqlite3

from fastapi import APIRouter, HTTPException

from database import get_connection
from models import WorkerCreate, WorkerDetail, WorkerOut, WorkerScreeningSummary

router = APIRouter(prefix="/api", tags=["workers"])

# Unauthenticated on purpose, same as /api/screen and the old /api/miners —
# see routers/auth.py's get_current_user docstring: these are called by
# VHWs in the field and by USSD, neither of which holds a dashboard login.
# GET /api/workers/{phone} returns clinical history (tier, advice_line) by
# phone number alone, which is a materially bigger exposure than the
# write-only POST route it sits next to — flagged in the implementation
# plan as an explicit, not-silently-inherited decision, not an oversight.


@router.post("/workers", response_model=WorkerOut)
def create_worker(worker: WorkerCreate):
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO miners (name, phone, mine_site) VALUES (?, ?, ?)",
            (worker.name, worker.phone, worker.site),
        )
        conn.commit()
        return WorkerOut(
            id=cur.lastrowid,
            name=worker.name,
            phone=worker.phone,
            site=worker.site,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Phone number already registered")
    finally:
        conn.close()


@router.get("/workers/{phone}", response_model=WorkerDetail)
def get_worker_by_phone(phone: str):
    """Look up a worker by phone and return their full screening history —
    this is what turns a visit into a re-screen (SILICAGUARD.md Section 8)."""
    conn = get_connection()
    try:
        worker_row = conn.execute(
            "SELECT id, name, phone, mine_site FROM miners WHERE phone = ?", (phone,)
        ).fetchone()
        if worker_row is None:
            raise HTTPException(status_code=404, detail="Worker not found")

        screening_rows = conn.execute(
            """SELECT id, tier, created_at, advice_line FROM screenings
               WHERE miner_id = ? ORDER BY created_at DESC, id DESC""",
            (worker_row["id"],),
        ).fetchall()

        return WorkerDetail(
            id=worker_row["id"],
            name=worker_row["name"],
            phone=worker_row["phone"],
            site=worker_row["mine_site"],
            screenings=[
                WorkerScreeningSummary(
                    id=row["id"],
                    tier=row["tier"],
                    created_at=row["created_at"],
                    advice_line=row["advice_line"],
                )
                for row in screening_rows
            ],
        )
    finally:
        conn.close()
