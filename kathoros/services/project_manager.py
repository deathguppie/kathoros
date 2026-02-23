"""
ProjectManager — owns DB connections, project paths, and session lifecycle.
Single instance per application run.
UI never touches DB connections directly — always through ProjectManager.
"""
from __future__ import annotations
import logging
import shutil
import sqlite3
from pathlib import Path
from typing import Optional
from kathoros.core.constants import GLOBAL_DB_NAME, PROJECT_DB_NAME
from kathoros.db.connection import open_global_db, open_project_db, open_project_db_readonly
from kathoros.db import queries
from kathoros.services.session_service import SessionService
from kathoros.services.global_service import GlobalService

_log = logging.getLogger("kathoros.services.project_manager")

KATHOROS_DIR = Path.home() / ".kathoros"
PROJECTS_DIR = KATHOROS_DIR / "projects"


class ProjectManager:
    """
    Owns global.db and current project.db connections.
    One instance per application run.
    """

    def __init__(self) -> None:
        self._global_conn: Optional[sqlite3.Connection] = None
        self._global_service: Optional[GlobalService] = None
        self._project_conn: Optional[sqlite3.Connection] = None
        self._current_project_id: Optional[int] = None
        self._current_project_name: Optional[str] = None
        self._current_session_id: Optional[int] = None
        self._session_service: Optional[SessionService] = None

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def open_global(self) -> None:
        """Open global.db, running migrations if needed."""
        path = KATHOROS_DIR / GLOBAL_DB_NAME
        self._global_conn = open_global_db(path)
        self._global_service = GlobalService(self._global_conn)
        _log.info("global.db opened at %s", path)

    # ------------------------------------------------------------------
    # Project lifecycle
    # ------------------------------------------------------------------

    def list_projects(self, include_archived: bool = False) -> list[dict]:
        """Return enriched project metadata from each project's DB."""
        if not PROJECTS_DIR.exists():
            return []
        projects = []
        for d in sorted(PROJECTS_DIR.iterdir()):
            db_path = d / PROJECT_DB_NAME
            if not d.is_dir() or not db_path.exists():
                continue
            try:
                conn = open_project_db_readonly(db_path)
                try:
                    row = conn.execute(
                        "SELECT name, description, status FROM projects ORDER BY id LIMIT 1"
                    ).fetchone()
                    if row is None:
                        continue
                    status = row["status"] or "active"
                    if status == "archived" and not include_archived:
                        continue
                    obj_count = conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
                    sess_row = conn.execute(
                        "SELECT COUNT(*) as cnt, MAX(last_active) as last_active FROM sessions"
                    ).fetchone()
                    projects.append({
                        "name": row["name"],
                        "path": str(d),
                        "description": row["description"] or "",
                        "status": status,
                        "object_count": obj_count,
                        "session_count": sess_row["cnt"],
                        "last_active": sess_row["last_active"] or "",
                    })
                finally:
                    conn.close()
            except Exception as exc:
                _log.warning("could not read project metadata for %s: %s", d.name, exc)
        return projects

    def create_project(self, name: str, description: str = "") -> dict:
        """
        Create a new project directory and database.
        Returns project info dict.
        """
        safe_name = _safe_dirname(name)
        project_dir = PROJECTS_DIR / safe_name
        project_dir.mkdir(parents=True, exist_ok=False)

        # subdirectories per file system spec
        for sub in ("repo", "docs", "artifacts", "manifests", "exports"):
            (project_dir / sub).mkdir(exist_ok=True)

        db_path = project_dir / PROJECT_DB_NAME
        conn = open_project_db(db_path)

        project_id = queries.insert_project(
            conn, name=name, description=description, status="active"
        )
        conn.commit()
        _log.info("project created: %s (id=%d)", name, project_id)

        self._project_conn = conn
        self._current_project_id = project_id
        self._current_project_name = name
        self._open_session(name="Session 1")

        return {"name": name, "path": str(project_dir), "project_id": project_id}

    def open_project(self, name: str) -> dict:
        """
        Open an existing project by directory name.
        Returns project info dict.
        """
        project_dir = PROJECTS_DIR / name
        db_path = project_dir / PROJECT_DB_NAME

        if not db_path.exists():
            raise FileNotFoundError(f"Project DB not found: {db_path}")

        if self._project_conn:
            self._project_conn.close()

        self._project_conn = open_project_db(db_path)
        row = self._project_conn.execute(
            "SELECT * FROM projects ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            raise ValueError(f"No project record found in {db_path}")

        self._current_project_id = row["id"]
        self._current_project_name = row["name"]
        _log.info("project opened: %s", name)

        self._resume_or_create_session()
        return {"name": row["name"], "path": str(project_dir),
                "project_id": row["id"]}

    def delete_project(self, name: str) -> None:
        """Permanently delete a project directory. Cannot delete the open project."""
        if name == self._current_project_name:
            raise ValueError("Cannot delete the currently open project.")
        project_dir = PROJECTS_DIR / _safe_dirname(name)
        if not project_dir.exists():
            raise FileNotFoundError(f"Project directory not found: {project_dir}")
        shutil.rmtree(project_dir)
        _log.info("project deleted: %s", name)

    def archive_project(self, name: str) -> None:
        """Set project status to 'archived'. Cannot archive the open project."""
        if name == self._current_project_name:
            raise ValueError("Cannot archive the currently open project.")
        db_path = PROJECTS_DIR / _safe_dirname(name) / PROJECT_DB_NAME
        if not db_path.exists():
            raise FileNotFoundError(f"Project DB not found: {db_path}")
        conn = open_project_db(db_path, run_migrations_flag=False)
        try:
            conn.execute(
                "UPDATE projects SET status = 'archived', "
                "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE 1"
            )
            conn.commit()
            _log.info("project archived: %s", name)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    def _open_session(self, name: str) -> None:
        """Create a new session record and initialise SessionService."""
        session_id = queries.insert_session(
            self._project_conn, self._current_project_id, name
        )
        self._project_conn.commit()
        self._current_session_id = session_id
        self._session_service = SessionService(self._project_conn, session_id)
        _log.info("session started: id=%d", session_id)

    def _resume_or_create_session(self) -> None:
        """Resume most recent session or create first one."""
        row = queries.get_last_session(self._project_conn, self._current_project_id)
        if row:
            self._current_session_id = row["id"]
            self._session_service = SessionService(self._project_conn, row["id"])
            _log.info("session resumed: id=%d", row["id"])
        else:
            self._open_session("Session 1")

    def get_effective_settings(self) -> dict[str, str]:
        """
        Merge global defaults + project overrides.
        Project settings win. Returns empty dict if no global DB open.
        """
        effective: dict[str, str] = {}
        if self._global_service:
            effective.update(self._global_service.get_all_settings())
        if self._project_conn:
            project_overrides = queries.get_all_project_settings(self._project_conn)
            effective.update(project_overrides)
        return effective

    def get_project_settings(self) -> dict[str, str]:
        """Return only project-level overrides (not merged with global)."""
        if self._project_conn is None:
            return {}
        return queries.get_all_project_settings(self._project_conn)

    def set_project_settings(self, settings: dict) -> None:
        """Write project-level overrides. No effect if no project is open."""
        if self._project_conn is None:
            return
        for key, value in settings.items():
            queries.set_project_setting(self._project_conn, key, str(value))
        self._project_conn.commit()
        _log.info("project settings updated: %d key(s)", len(settings))

    def list_notes(self) -> list[dict]:
        if self._project_conn is None:
            return []
        from kathoros.db import queries as _q
        rows = _q.list_notes(self._project_conn)
        return [dict(r) for r in rows]

    def create_note(self, title: str = "Untitled", content: str = "", fmt: str = "markdown") -> dict:
        from kathoros.db import queries as _q
        note_id = _q.insert_note(self._project_conn, title, content, fmt)
        row = _q.get_note(self._project_conn, note_id)
        return dict(row)

    def save_note(self, note_id: int, title: str, content: str, fmt: str) -> None:
        from kathoros.db import queries as _q
        _q.update_note(self._project_conn, note_id, title, content, fmt)

    def delete_note(self, note_id: int) -> None:
        from kathoros.db import queries as _q
        _q.delete_note(self._project_conn, note_id)

    def list_committed_objects(self) -> list[dict]:
        if self._project_conn is None:
            return []
        from kathoros.db import queries as _q
        rows = _q.list_all_committed_objects(self._project_conn)
        return [dict(r) for r in rows]

    def save_state(self, snapshot: dict) -> None:
        if self._session_service:
            self._session_service.save_snapshot(snapshot)


    @property
    def global_service(self) -> Optional[GlobalService]:
        return self._global_service

    @property
    def session_service(self) -> Optional[SessionService]:
        return self._session_service

    @property
    def project_name(self) -> Optional[str]:
        return self._current_project_name

    @property
    def project_root(self) -> Optional[Path]:
        if self._current_project_name is None:
            return None
        return PROJECTS_DIR / _safe_dirname(self._current_project_name)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._project_conn:
            self._project_conn.close()
        if self._global_conn:
            self._global_conn.close()
        _log.info("ProjectManager closed")


def _safe_dirname(name: str) -> str:
    """Convert project name to safe directory name."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name).strip("_")
