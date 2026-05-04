"""
migrate_proctoring.py
---------------------
Add proctoring columns to the existing 'sessions' table.
Safe to run multiple times — checks if columns exist before adding.
 
Fix log:
  - Validate DATABASE_URL is a SQLite URL before stripping prefix;
    raise clearly for Postgres/MySQL instead of silently using a bad path.
  - Added paste_attempt_count + devtools_attempt_count as denormalized
    columns (mirrors the risk-score weights tracked in proctoring.py).
"""
 
import sqlite3
import os
import sys
 
 
_RAW_DB_URL = os.getenv("DATABASE_URL", "sqlite:///./psysense.db")
 
_SQLITE_PREFIX = "sqlite:///"
 
def _resolve_db_path(url: str) -> str:
    """
    Extract the filesystem path from a SQLite SQLAlchemy URL.
    Raises ValueError for non-SQLite URLs so the error is obvious
    instead of producing a garbage path.
    """
    if not url.startswith(_SQLITE_PREFIX):
        raise ValueError(
            f"migrate_proctoring.py only supports SQLite. "
            f"DATABASE_URL is '{url}'. "
            f"Run proctoring migrations through your ORM/Alembic for other databases."
        )
    return url[len(_SQLITE_PREFIX):]          # e.g. "./psysense.db" or "/abs/path.db"
 
 
DB_PATH = _resolve_db_path(_RAW_DB_URL)
 
 
def migrate():
    if not os.path.exists(DB_PATH):
        print(
            f"[migrate] Database not found at '{DB_PATH}' — "
            "it will be created automatically on next app start."
        )
        return
 
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
 
    # Snapshot existing columns
    cursor.execute("PRAGMA table_info(sessions)")
    existing_columns = {row[1] for row in cursor.fetchall()}
 
    # ── Columns to add ──────────────────────────────────────────────────
    # proctoring_json       — full JSON blob (all events + per-question breakdown)
    # proctoring_risk       — denormalised risk level for fast WHERE/ORDER BY
    # tab_switch_count      — denormalised for recruiter dashboard sorting
    # paste_attempt_count   — denormalised (weight-5 risk factor)
    # devtools_attempt_count— denormalised (weight-8 risk factor; was missing)
    new_columns = [
        ("proctoring_json",        "TEXT    DEFAULT NULL"),
        ("proctoring_risk",        "TEXT    DEFAULT 'Low'"),
        ("tab_switch_count",       "INTEGER DEFAULT 0"),
        ("paste_attempt_count",    "INTEGER DEFAULT 0"),   # FIX: was missing
        ("devtools_attempt_count", "INTEGER DEFAULT 0"),   # FIX: was missing
    ]
 
    added = 0
    for col_name, col_def in new_columns:
        if col_name not in existing_columns:
            sql = f"ALTER TABLE sessions ADD COLUMN {col_name} {col_def}"
            print(f"[migrate] Adding column: {col_name}")
            cursor.execute(sql)
            added += 1
        else:
            print(f"[migrate] Column '{col_name}' already exists — skipping.")
 
    conn.commit()
    conn.close()
 
    if added:
        print(f"[migrate] ✅ Added {added} new column(s). Existing data preserved.")
    else:
        print("[migrate] ✅ All columns already exist. Nothing to do.")
 
 
if __name__ == "__main__":
    try:
        migrate()
    except ValueError as exc:
        print(f"[migrate] ❌ {exc}", file=sys.stderr)
        sys.exit(1)