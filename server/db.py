"""SQLite connection handling.

One database file, one process, single user -- so a connection per request is
plenty. WAL keeps note writes from blocking reads.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("CONCORDANCE_DB", ROOT / "data" / "concordance.db"))


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise RuntimeError(
            f"database not found at {DB_PATH}\n"
            "run: python etl/fetch_sources.py && python etl/build_db.py"
        )
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    return con
