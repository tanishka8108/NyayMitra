"""SQLite access for the authentication, verification and chat tables.

Why SQLite
----------
This environment cannot run PostgreSQL (no Docker, no psql client,
port 5432 closed — see the Phase 0 inspection notes), so the new
account/chat tables live in **one** SQLite file. No second database
*system* is introduced, no existing table is duplicated or altered:
the legacy PostgreSQL dump (``lawyer_database.sql``) and the psycopg2
seam in ``connection.py`` stay exactly as they are.

Portability
-----------
``auth_schema.sql`` is plain, portable SQL (``CREATE ... IF NOT EXISTS``)
so the same statements can be applied to PostgreSQL later; the two
SQLite-isms (``INTEGER PRIMARY KEY AUTOINCREMENT`` and ``AUTOINCREMENT``
on ``messages``/``conversations``) are noted in that file.

Connection style
----------------
One connection per use, closed by the caller in a ``finally`` block —
mirrors ``database/connection.py``'s ``get_db_connection()`` pattern.
The database path is read from the environment on every call
(``NYAYMITRA_AUTH_DB``), which is what keeps tests hermetic: each test
points it at its own throwaway file.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

DB_PATH_ENV = "NYAYMITRA_AUTH_DB"

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "nyaymitra.db"

_SCHEMA_FILE = Path(__file__).resolve().parent / "auth_schema.sql"

# Applied-once bookkeeping, keyed by resolved path so tests that point
# at a fresh file each get their schema without any global reset.
_applied_paths: set[str] = set()
_schema_lock = threading.Lock()

# Optional lawyer-profile columns added in Phase 2b. SQLite has no
# "ADD COLUMN IF NOT EXISTS", so each addition is checked against
# PRAGMA table_info first — additive and safe to run on every
# existing database file (dev file included) without dropping or
# rewriting anything that is already there.
_LAWYER_PROFILE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("bar_council", "VARCHAR(200)"),
    ("years_of_experience", "INTEGER"),
    ("professional_phone_number", "VARCHAR(50)"),
    ("professional_bio", "TEXT"),
)


def get_db_path() -> str:
    """Absolute path of the SQLite file to use (env-overridable)."""
    override = os.environ.get(DB_PATH_ENV, "").strip()
    if override:
        return override
    return str(_DEFAULT_PATH)


def connect() -> sqlite3.Connection:
    """Open a connection to the auth/chat database, schema applied.

    The caller owns the returned connection and must ``close()`` it.
    """
    path = get_db_path()

    parent = Path(path).parent
    if str(parent):
        parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    _ensure_schema(path, connection)

    return connection


def _ensure_schema(path: str, connection: sqlite3.Connection) -> None:
    """Run the schema statements once per database file (idempotent)."""
    if path in _applied_paths:
        return

    with _schema_lock:
        if path in _applied_paths:
            return

        schema = _SCHEMA_FILE.read_text(encoding="utf-8")
        connection.executescript(schema)

        _ensure_lawyer_profile_columns(connection)

        # WAL is a persistent property of the file; harmless where it
        # is unsupported (it merely reports the mode back).
        try:
            connection.execute("PRAGMA journal_mode = WAL")
        except sqlite3.Error:  # pragma: no cover - platform dependent
            pass
        connection.commit()

        _applied_paths.add(path)


def _ensure_lawyer_profile_columns(connection: sqlite3.Connection) -> None:
    """Add the Phase 2b profile columns to ``lawyers`` if missing.

    Idempotent: an existing column is never touched, a missing one is
    added nullable (old rows simply read NULL). No data is rewritten.
    """
    existing = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(lawyers)")
    }

    for name, ddl in _LAWYER_PROFILE_COLUMNS:
        if name not in existing:
            connection.execute(f"ALTER TABLE lawyers ADD COLUMN {name} {ddl}")
