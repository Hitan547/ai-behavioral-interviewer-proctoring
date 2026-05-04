"""
migrate_db.py
-------------
One-time migration script for PsySense V2.

Run this ONCE from your project root:
    python migrate_db.py

What it does:
  - Adds jd_id column to existing sessions table
  - Creates job_postings table (if not exists)
  - Creates candidate_profiles table (if not exists)
  - Safe to re-run — skips columns/tables that already exist
"""

import sqlite3
import os

DB_PATH = "data/psysense.db"

if not os.path.exists(DB_PATH):
    print(f"❌ Database not found at {DB_PATH}. Run the app once first to create it.")
    exit(1)

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()


# ── Helper: check if column exists ───────────────────────────────────────

def column_exists(table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def table_exists(table: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


# ── Step 1: Add jd_id to sessions ────────────────────────────────────────

if not column_exists("sessions", "jd_id"):
    cur.execute("ALTER TABLE sessions ADD COLUMN jd_id INTEGER")
    print("✅ Added jd_id column to sessions table")
else:
    print("⏭  sessions.jd_id already exists — skipped")


# ── Step 2: Create job_postings table ────────────────────────────────────

if not table_exists("job_postings"):
    cur.execute("""
        CREATE TABLE job_postings (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            title          TEXT    NOT NULL,
            jd_text        TEXT    NOT NULL,
            min_pass_score INTEGER DEFAULT 60,
            deadline       DATETIME,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            status         TEXT    DEFAULT 'Active'
        )
    """)
    print("✅ Created job_postings table")
else:
    print("⏭  job_postings table already exists — skipped")


# ── Step 3: Create candidate_profiles table ───────────────────────────────

if not table_exists("candidate_profiles"):
    cur.execute("""
        CREATE TABLE candidate_profiles (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT    NOT NULL,
            email            TEXT    NOT NULL,
            resume_text      TEXT,
            resume_filename  TEXT,
            jd_id            INTEGER NOT NULL REFERENCES job_postings(id),
            match_score      REAL,
            match_reason     TEXT,
            key_matches      TEXT,
            key_gaps         TEXT,
            username         TEXT,
            temp_password    TEXT,
            account_created  INTEGER DEFAULT 0,
            invite_sent_at   DATETIME,
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
            interview_status TEXT    DEFAULT 'Shortlisted'
        )
    """)
    print("✅ Created candidate_profiles table")
else:
    print("⏭  candidate_profiles table already exists — skipped")


# ── Commit & close ────────────────────────────────────────────────────────

conn.commit()
conn.close()

print("\n🎉 Migration complete. You can now run the app normally.")