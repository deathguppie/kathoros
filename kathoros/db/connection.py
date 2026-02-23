# kathoros/db/connection.py
"""
Database connection management for Kathoros.

Two connection types:
  - Read-write: current project DB and global DB
  - Read-only:  cross-project DB access (enforced at connection layer)

Security rules:
  - Read-only enforced via PRAGMA query_only = ON, not just by convention.
  - API keys are never stored or read from DB.
  - Snapshot size is capped before write.
  - FTS queries must run off the UI thread (enforced by caller).
  - WAL mode enabled for all connections (better concurrency).
  - Foreign keys enforced on every connection.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

from kathoros.db.migrations import (
    GLOBAL_MIGRATIONS,
    PROJECT_MIGRATIONS,
    run_migrations,
)

_log = logging.getLogger("kathoros.db.connection")

# Snapshot size cap — hard limit, matches constants.py
_MAX_SNAPSHOT_BYTES = 1_048_576  # 1MB


def _configure_connection(conn: sqlite3.Connection) -> None:
    """Apply standard PRAGMAs to every connection."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.row_factory = sqlite3.Row


def open_global_db(path: Path, run_migrations_flag: bool = True) -> sqlite3.Connection:
    """
    Open (and optionally migrate) the global database.
    Returns a read-write connection.
    Creates the file and parent directories if they don't exist.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    _configure_connection(conn)

    if run_migrations_flag:
        applied = run_migrations(conn, GLOBAL_MIGRATIONS, db_label="global.db")
        if applied:
            _log.info(f"global.db: applied {applied} migration(s)")

    _log.debug(f"global.db opened: {path}")
    return conn


def open_project_db(path: Path, run_migrations_flag: bool = True) -> sqlite3.Connection:
    """
    Open (and optionally migrate) a project database.
    Returns a read-write connection.
    Creates the file and parent directories if they don't exist.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    _configure_connection(conn)

    if run_migrations_flag:
        applied = run_migrations(conn, PROJECT_MIGRATIONS, db_label="project.db")
        if applied:
            _log.info(f"project.db: applied {applied} migration(s)")

    _log.debug(f"project.db opened: {path}")
    return conn


def open_project_db_readonly(path: Path) -> sqlite3.Connection:
    """
    Open a project DB as strictly read-only.
    Used for cross-project queries from non-active projects.
    Enforced at connection layer via PRAGMA query_only, not just convention.
    Raises FileNotFoundError if DB does not exist (never creates).
    """
    if not path.exists():
        raise FileNotFoundError(f"Project DB not found: {path}")

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    _configure_connection(conn)
    conn.execute("PRAGMA query_only = ON")

    _log.debug(f"project.db opened read-only: {path}")
    return conn


def validate_snapshot(snapshot_json: str) -> str:
    """
    Validate a session state snapshot before writing to DB.
    Enforces size cap. Raises ValueError if oversized.
    Does not inspect content — caller is responsible for redacting secrets.
    """
    size = len(snapshot_json.encode("utf-8"))
    if size > _MAX_SNAPSHOT_BYTES:
        raise ValueError(
            f"Snapshot size {size} bytes exceeds cap {_MAX_SNAPSHOT_BYTES} bytes. "
            "Store large artifacts as files and reference by path."
        )
    return snapshot_json
