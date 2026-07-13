import os
import sqlite3

DATABASE_URL = os.getenv("DATABASE_URL", "./data/silicaguard.db")

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
    screened_by TEXT,
    channel TEXT,
    risk_level TEXT,
    risk_confidence REAL,
    ai_explanation_shona TEXT,
    ai_explanation_english TEXT,
    ai_contributing_factors TEXT,
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

CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screening_id INTEGER REFERENCES screenings(id),
    miner_id INTEGER REFERENCES miners(id),
    hospital TEXT DEFAULT 'Kwekwe District Hospital',
    pre_alert_sent INTEGER DEFAULT 0,
    xray_completed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'PENDING',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

CREATE TABLE IF NOT EXISTS xray_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referral_id INTEGER REFERENCES referrals(id),
    miner_id INTEGER REFERENCES miners(id),
    classification TEXT,
    confidence REAL,
    heatmap_path TEXT,
    reviewed_by TEXT,
    reviewed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT,
    direction TEXT,
    message TEXT,
    language TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
