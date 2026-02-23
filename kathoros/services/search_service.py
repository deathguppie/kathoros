"""
SearchService — cross-project FTS search.

Must be called from a background thread (FTS queries must not run on the UI thread).
Opens non-active project DBs read-only. Never migrates foreign DBs.
"""
from __future__ import annotations

import logging
from pathlib import Path

from kathoros.core.constants import PROJECT_DB_NAME
from kathoros.db.connection import open_project_db_readonly

_log = logging.getLogger("kathoros.services.search_service")

# Safe FTS5 characters — anything else is stripped before passing to MATCH
_FTS_SAFE = set("abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
_SNIPPET_LEN = 120


def _sanitize_fts_query(query: str) -> str:
    """Strip characters that are unsafe in an FTS5 MATCH expression."""
    return "".join(c for c in query if c in _FTS_SAFE).strip()


def _snippet(text: str | None) -> str:
    if not text:
        return ""
    t = text.replace("\n", " ").strip()
    return t[:_SNIPPET_LEN] + ("…" if len(t) > _SNIPPET_LEN else "")


def search_current_project(
    conn,
    query: str,
    limit: int = 100,
    project_name: str = "",
) -> list[dict]:
    """
    Run FTS on the already-open project connection.
    Must be called from a background thread.
    """
    safe_q = _sanitize_fts_query(query)
    if not safe_q:
        return []
    try:
        rows = conn.execute(
            """
            SELECT o.id, o.name, o.type, o.status, o.content, o.tags
            FROM objects o
            JOIN objects_fts f ON o.id = f.rowid
            WHERE objects_fts MATCH ?
            ORDER BY bm25(objects_fts)
            LIMIT ?
            """,
            (safe_q, limit),
        ).fetchall()
        return [
            {
                "project": project_name,
                "id": r["id"],
                "name": r["name"] or "",
                "type": r["type"] or "",
                "status": r["status"] or "",
                "snippet": _snippet(r["content"]),
            }
            for r in rows
        ]
    except Exception as exc:
        _log.warning("FTS query failed on %s: %s", project_name, exc)
        return []


def search_all_projects(
    projects_dir: Path,
    query: str,
    limit_per_project: int = 50,
) -> list[dict]:
    """
    Run FTS across every project found in projects_dir.
    Opens each DB read-only. Must be called from a background thread.
    """
    safe_q = _sanitize_fts_query(query)
    if not safe_q:
        return []

    results: list[dict] = []
    if not projects_dir.exists():
        return results

    for d in sorted(projects_dir.iterdir()):
        db_path = d / PROJECT_DB_NAME
        if not d.is_dir() or not db_path.exists():
            continue
        try:
            conn = open_project_db_readonly(db_path)
            try:
                # Read project name from DB
                row = conn.execute(
                    "SELECT name FROM projects ORDER BY id LIMIT 1"
                ).fetchone()
                proj_name = row["name"] if row else d.name
                hits = search_current_project(conn, safe_q, limit_per_project, proj_name)
                results.extend(hits)
            finally:
                conn.close()
        except Exception as exc:
            _log.warning("could not search project %s: %s", d.name, exc)

    return results
