import os
import sqlite3

DATABASE_URL = os.getenv("DATABASE_URL", "./data/silicaguard.db")

# v4.0 four-tier schema (see CLAUDE.md, SILICAGUARD.md Section 7). There is no
# migration framework yet — CREATE TABLE IF NOT EXISTS will not alter a table
# that already exists under the old 3-tier shape. Delete the local .db file
# and re-run init_db()/seed_demo_data.py to pick up this schema, per the
# "How to add or change a database field" procedure in SKILL.md.
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
    deadline DATETIME,
    pre_alert_sent INTEGER DEFAULT 0,
    status TEXT DEFAULT 'open'
        CHECK (status IN ('open', 'pre_alerted', 'reminded', 'attended', 'closed', 'escalated')),
    attended_at DATETIME,
    closed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS employers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contact TEXT,
    subscription_tier TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_id INTEGER REFERENCES employers(id),
    site TEXT,
    job_roles TEXT,
    start_date DATE,
    end_date DATE,
    target_count INTEGER
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


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
