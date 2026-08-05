import os
import sqlite3

DATABASE_URL = os.getenv("DATABASE_URL", "./data/silicaguard.db")

# v4.0 four-tier schema (see CLAUDE.md, SILICAGUARD.md Section 7). There is no
# migration framework yet — CREATE TABLE IF NOT EXISTS will not alter a table
# that already exists under the old 3-tier shape. Delete the local .db file
# and re-run init_db()/seed_demo_data.py to pick up this schema, per the
# "How to add or change a database field" procedure in SKILL.md.

# The Enterprise Occupational Health pillar (employer accounts, scheduled
# campaigns) was descoped 5 August 2026 per mentor feedback — SilicaGuard is
# artisanal-miner-only now (see SILICAGUARD.md Section 13). Explicitly drop
# these tables rather than leaving them as dead schema, the way xray_results/
# whatsapp_messages were left behind in an earlier removal. `campaigns` has
# an FK to `employers`, so it must drop first.
CLEANUP = """
DROP TABLE IF EXISTS campaigns;
DROP TABLE IF EXISTS employers;
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS miners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT UNIQUE NOT NULL,
    mine_site TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS screenings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    miner_id INTEGER REFERENCES miners(id),
    previous_screening_id INTEGER REFERENCES screenings(id),
    screened_by TEXT,
    channel TEXT,
    tier TEXT CHECK (tier IN ('GREEN', 'YELLOW', 'ORANGE', 'RED')),
    risk_confidence REAL,
    advice_line TEXT,
    ai_explanation_shona TEXT,
    ai_explanation_english TEXT,
    ai_contributing_factors TEXT,
    provisional INTEGER DEFAULT 0,
    fallback_used INTEGER DEFAULT 0,
    synced INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS screening_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screening_id INTEGER REFERENCES screenings(id),
    question_code TEXT,
    question_text TEXT,
    answer_value TEXT,
    answer_score INTEGER
);

CREATE TABLE IF NOT EXISTS facilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    level TEXT,
    address TEXT,
    phone TEXT,
    latitude REAL,
    longitude REAL
);

CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screening_id INTEGER REFERENCES screenings(id),
    miner_id INTEGER REFERENCES miners(id),
    hospital TEXT DEFAULT 'Kwekwe District Hospital',
    facility_id INTEGER REFERENCES facilities(id),
    deadline DATETIME,
    pre_alert_sent INTEGER DEFAULT 0,
    status TEXT DEFAULT 'open'
        CHECK (status IN ('open', 'pre_alerted', 'reminded', 'attended', 'closed', 'escalated')),
    reminder_stage INTEGER DEFAULT 0,
    attended_at DATETIME,
    closed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outreach_visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT NOT NULL,
    scheduled_date DATE,
    expected_headcount INTEGER,
    screened_count INTEGER DEFAULT 0,
    health_workers TEXT,
    report_generated INTEGER DEFAULT 0
);
"""


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DATABASE_URL) or ".", exist_ok=True)
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Additive columns landing on an existing `referrals` table (5 August 2026,
# Smart Referral Router — facility matching + reminder/escalation cascade).
# CREATE TABLE IF NOT EXISTS won't add these to a table that already exists
# under the old shape, so unlike most schema changes in this project (which
# just ask you to delete backend/data/silicaguard.db), these two are applied
# via ALTER TABLE so an existing local/deployed DB doesn't need deleting.
_REFERRAL_ALTERS = (
    "ALTER TABLE referrals ADD COLUMN facility_id INTEGER REFERENCES facilities(id)",
    "ALTER TABLE referrals ADD COLUMN reminder_stage INTEGER DEFAULT 0",
)


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(CLEANUP)
        conn.executescript(SCHEMA)
        for statement in _REFERRAL_ALTERS:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()
    finally:
        conn.close()
