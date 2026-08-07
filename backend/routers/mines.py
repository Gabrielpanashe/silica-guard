import sqlite3

from fastapi import APIRouter, HTTPException

from database import get_connection
from models import MineCreate, MineOut

router = APIRouter(prefix="/api", tags=["mines"])

# Unauthenticated, same deliberate precedent as POST /api/workers and
# POST /api/screen — a VHW in the field selecting (or adding) the mine
# they're screening at has no dashboard login. Powers the mobile app's
# outreach-site dropdown (7 August 2026), replacing the hardcoded
# "Globe & Phoenix Mine" default that was baked directly into the UI.


@router.get("/mines", response_model=list[MineOut])
def list_mines():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM mines ORDER BY district, name"
        ).fetchall()
        return [MineOut(**dict(row)) for row in rows]
    finally:
        conn.close()


@router.post("/mines", response_model=MineOut, status_code=201)
def create_mine(payload: MineCreate):
    """For the case where a VHW's site genuinely isn't in the seeded list —
    lets the dropdown grow rather than forcing a hardcoded set. Deliberately
    not a foreign key target for miners.mine_site/outreach_visits.site (both
    stay free TEXT) — a full migration tying those to mines.id is a bigger,
    riskier change than the freeze deadline allows; this table is a curated
    suggestion list for the UI, not yet a hard constraint."""
    conn = get_connection()
    try:
        try:
            cur = conn.execute(
                "INSERT INTO mines (name, district, province) VALUES (?, ?, ?)",
                (payload.name, payload.district, payload.province),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Mine already registered")
        row = conn.execute("SELECT * FROM mines WHERE id = ?", (cur.lastrowid,)).fetchone()
        return MineOut(**dict(row))
    finally:
        conn.close()
