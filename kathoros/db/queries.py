# kathoros/db/queries.py
"""
Typed query helpers for both global.db and project.db.

Rules:
  - All queries use parameterised statements — no string formatting with user data.
  - No raw args, API keys, or secrets ever stored.
  - FTS queries are provided here but must be run off the UI thread by callers.
  - All functions accept an explicit sqlite3.Connection — no global state.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional


# ---------------------------------------------------------------------------
# global.db — agents
# ---------------------------------------------------------------------------

def insert_agent(conn: sqlite3.Connection, **fields) -> int:
    """Insert an agent record. Returns new row id."""
    conn.execute(
        """
        INSERT INTO agents
            (name, alias, type, provider, endpoint, model_string,
             capability_tags, cost_tier, context_window,
             default_research_prompt, default_audit_prompt,
             trust_level, require_tool_approval, require_write_approval,
             user_notes, is_active)
        VALUES
            (:name, :alias, :type, :provider, :endpoint, :model_string,
             :capability_tags, :cost_tier, :context_window,
             :default_research_prompt, :default_audit_prompt,
             :trust_level, :require_tool_approval, :require_write_approval,
             :user_notes, :is_active)
        """,
        {
            "name": fields["name"],
            "alias": fields.get("alias"),
            "type": fields["type"],
            "provider": fields.get("provider"),
            "endpoint": fields.get("endpoint"),
            "model_string": fields.get("model_string"),
            "capability_tags": json.dumps(fields.get("capability_tags", [])),
            "cost_tier": fields.get("cost_tier"),
            "context_window": fields.get("context_window"),
            "default_research_prompt": fields.get("default_research_prompt"),
            "default_audit_prompt": fields.get("default_audit_prompt"),
            "trust_level": fields.get("trust_level", "monitored"),
            "require_tool_approval": fields.get("require_tool_approval"),
            "require_write_approval": fields.get("require_write_approval"),
            "user_notes": fields.get("user_notes"),
            "is_active": int(fields.get("is_active", True)),
        },
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def delete_agent(conn: sqlite3.Connection, agent_id: int) -> None:
    conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    conn.commit()


def get_agent(conn: sqlite3.Connection, agent_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM agents WHERE id = ?", (agent_id,)
    ).fetchone()


def list_active_agents(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM agents WHERE is_active = 1 ORDER BY name"
    ).fetchall()


def get_global_setting(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute(
        "SELECT value FROM global_settings WHERE key = ?", (key,)
    ).fetchone()
    return row[0] if row else None


def set_global_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO global_settings (key, value) VALUES (?, ?)",
        (key, value),
    )


# ---------------------------------------------------------------------------
# project.db — projects & sessions
# ---------------------------------------------------------------------------

def insert_project(conn: sqlite3.Connection, **fields) -> int:
    conn.execute(
        """
        INSERT INTO projects (name, description, research_goals, license, git_repo_path, status)
        VALUES (:name, :description, :research_goals, :license, :git_repo_path, :status)
        """,
        {
            "name": fields["name"],
            "description": fields.get("description"),
            "research_goals": fields.get("research_goals"),
            "license": fields.get("license"),
            "git_repo_path": fields.get("git_repo_path"),
            "status": fields.get("status", "active"),
        },
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_project(conn: sqlite3.Connection, project_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()


def insert_session(conn: sqlite3.Connection, project_id: int, name: str) -> int:
    conn.execute(
        "INSERT INTO sessions (project_id, name) VALUES (?, ?)",
        (project_id, name),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_session_snapshot(
    conn: sqlite3.Connection, session_id: int, snapshot_json: str
) -> None:
    """
    Write session state snapshot. Caller must have validated size via
    connection.validate_snapshot() before calling this.
    """
    conn.execute(
        """
        UPDATE sessions
        SET state_snapshot = ?, last_active = strftime('%Y-%m-%dT%H:%M:%SZ','now')
        WHERE id = ?
        """,
        (snapshot_json, session_id),
    )


# ---------------------------------------------------------------------------
# project.db — objects
# ---------------------------------------------------------------------------

def insert_object(conn: sqlite3.Connection, session_id: int, **fields) -> int:
    conn.execute(
        """
        INSERT INTO objects
            (session_id, name, type, status, content, math_expression, latex,
             tags, related_objects, depends_on, contradicts,
             source_conversation_ref, attached_files,
             researcher_notes, ai_suggested_tags)
        VALUES
            (:session_id, :name, :type, :status, :content, :math_expression, :latex,
             :tags, :related_objects, :depends_on, :contradicts,
             :source_conversation_ref, :attached_files,
             :researcher_notes, :ai_suggested_tags)
        """,
        {
            "session_id": session_id,
            "name": fields["name"],
            "type": fields["type"],
            "status": fields.get("status", "pending"),
            "content": fields.get("content"),
            "math_expression": fields.get("math_expression"),
            "latex": fields.get("latex"),
            "tags": json.dumps(fields.get("tags", [])),
            "related_objects": json.dumps(fields.get("related_objects", [])),
            "depends_on": json.dumps(fields.get("depends_on", [])),
            "contradicts": json.dumps(fields.get("contradicts", [])),
            "source_conversation_ref": fields.get("source_conversation_ref"),
            "attached_files": json.dumps(fields.get("attached_files", [])),
            "researcher_notes": fields.get("researcher_notes"),
            "ai_suggested_tags": json.dumps(fields.get("ai_suggested_tags", [])),
        },
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_object_status(
    conn: sqlite3.Connection, object_id: int, status: str
) -> None:
    conn.execute(
        """
        UPDATE objects
        SET status = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')
        WHERE id = ?
        """,
        (status, object_id),
    )


def commit_object(conn: sqlite3.Connection, object_id: int) -> None:
    conn.execute(
        """
        UPDATE objects
        SET status = 'committed',
            committed_at = strftime('%Y-%m-%dT%H:%M:%SZ','now'),
            updated_at   = strftime('%Y-%m-%dT%H:%M:%SZ','now')
        WHERE id = ?
        """,
        (object_id,),
    )


def get_objects_by_status(
    conn: sqlite3.Connection, session_id: int, status: str
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM objects WHERE session_id = ? AND status = ? ORDER BY created_at",
        (session_id, status),
    ).fetchall()


def search_objects_fts(
    conn: sqlite3.Connection, query: str, limit: int = 50
) -> list[sqlite3.Row]:
    """
    Full-text search across objects.
    Must be called from a background thread — never the UI thread.
    Returns matched objects ordered by relevance (bm25).
    """
    return conn.execute(
        """
        SELECT o.*
        FROM objects o
        JOIN objects_fts f ON o.id = f.rowid
        WHERE objects_fts MATCH ?
        ORDER BY bm25(objects_fts)
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()


# ---------------------------------------------------------------------------
# project.db — interactions
# ---------------------------------------------------------------------------

def insert_interaction(
    conn: sqlite3.Connection,
    session_id: int,
    agent_id: Optional[int],
    role: str,
    content: str,
    tool_invocations: Optional[list] = None,
) -> int:
    conn.execute(
        """
        INSERT INTO interactions (session_id, agent_id, role, content, tool_invocations)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            session_id,
            agent_id,
            role,
            content,
            json.dumps(tool_invocations or []),
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_session_interactions(
    conn: sqlite3.Connection, session_id: int
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM interactions WHERE session_id = ? ORDER BY timestamp",
        (session_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# project.db — tool audit log
# ---------------------------------------------------------------------------

def insert_tool_audit_log(conn: sqlite3.Connection, **fields) -> int:
    """
    Persist a RouterResult to the project tool_audit_log.
    raw_args must never be passed here — only raw_args_hash.
    """
    assert "args" not in fields, "raw args must never be stored in audit log"
    assert "raw_args" not in fields, "raw args must never be stored in audit log"
    assert len(fields.get("raw_args_hash", "")) == 64, (
        f"raw_args_hash must be 64 chars, got {len(fields.get('raw_args_hash',''))}"
    )

    conn.execute(
        """
        INSERT INTO tool_audit_log
            (request_id, agent_id, agent_name, trust_level, access_mode,
             tool_name, raw_args_hash, nonce_valid, enveloped, detected_via,
             decision, validation_ok, validation_errors, output_size,
             execution_ms, artifacts)
        VALUES
            (:request_id, :agent_id, :agent_name, :trust_level, :access_mode,
             :tool_name, :raw_args_hash, :nonce_valid, :enveloped, :detected_via,
             :decision, :validation_ok, :validation_errors, :output_size,
             :execution_ms, :artifacts)
        """,
        {
            "request_id":        fields["request_id"],
            "agent_id":          fields["agent_id"],
            "agent_name":        fields["agent_name"],
            "trust_level":       fields["trust_level"],
            "access_mode":       fields["access_mode"],
            "tool_name":         fields["tool_name"],
            "raw_args_hash":     fields["raw_args_hash"],
            "nonce_valid":       int(fields["nonce_valid"]),
            "enveloped":         int(fields["enveloped"]),
            "detected_via":      fields["detected_via"],
            "decision":          fields["decision"],
            "validation_ok":     int(fields["validation_ok"]),
            "validation_errors": json.dumps(fields.get("validation_errors", [])),
            "output_size":       fields.get("output_size", 0),
            "execution_ms":      fields.get("execution_ms", 0.0),
            "artifacts":         json.dumps(fields.get("artifacts", [])),
        },
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# ---------------------------------------------------------------------------
# SessionService additions
# ---------------------------------------------------------------------------

def list_all_committed_objects(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """All committed objects across all sessions in this project, oldest first."""
    return conn.execute(
        "SELECT * FROM objects WHERE status = 'committed' ORDER BY committed_at ASC"
    ).fetchall()


def get_last_session(
    conn: sqlite3.Connection, project_id: int
) -> Optional[sqlite3.Row]:
    """Return the most recently active session for a project, or None."""
    return conn.execute(
        "SELECT * FROM sessions WHERE project_id = ? ORDER BY last_active DESC LIMIT 1",
        (project_id,),
    ).fetchone()


def get_session_by_id(
    conn: sqlite3.Connection, session_id: int
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()


def get_object_by_id(conn: sqlite3.Connection, object_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM objects WHERE id = ?", (object_id,)
    ).fetchone()


def list_objects(
    conn: sqlite3.Connection, session_id: int, limit: int = 200, offset: int = 0
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, name, type, status, object_type, epistemic_status,
               claim_level, narrative_label, falsifiable, validation_scope,
               created_at, updated_at
        FROM objects WHERE session_id = ?
        ORDER BY created_at DESC LIMIT ? OFFSET ?
        """,
        (session_id, limit, offset),
    ).fetchall()


def insert_cross_reference(
    conn: sqlite3.Connection, source_id: int, target_id: int, reference_type: str
) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO cross_references
               (source_object_id, target_object_id, reference_type)
           VALUES (?, ?, ?)""",
        (source_id, target_id, reference_type),
    )


def delete_cross_reference(
    conn: sqlite3.Connection, source_id: int, target_id: int, reference_type: str
) -> None:
    conn.execute(
        """DELETE FROM cross_references
           WHERE source_object_id = ? AND target_object_id = ? AND reference_type = ?""",
        (source_id, target_id, reference_type),
    )


def get_edges_for_object(conn: sqlite3.Connection, object_id: int) -> list:
    from kathoros.epistemic.checker import Edge
    rows = conn.execute(
        """SELECT source_object_id, target_object_id, reference_type
           FROM cross_references
           WHERE source_object_id = ? OR target_object_id = ?""",
        (object_id, object_id),
    ).fetchall()
    return [Edge(source_id=r["source_object_id"], target_id=r["target_object_id"],
                 reference_type=r["reference_type"]) for r in rows]


def update_epistemic_status(
    conn, object_id: int, epistemic_status: str
) -> None:
    conn.execute(
        """UPDATE objects
           SET epistemic_status = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')
           WHERE id = ?""",
        (epistemic_status, object_id),
    )


def get_interactions(
    conn,
    session_id: int,
    limit: int = 500,
) -> list:
    return conn.execute(
        """
        SELECT id, session_id, agent_id, role, content, timestamp
        FROM interactions
        WHERE session_id = ?
        ORDER BY timestamp ASC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()


def list_agents(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, name, alias, type, provider, endpoint, model_string,
               capability_tags, cost_tier, context_window,
               trust_level, require_tool_approval, require_write_approval,
               user_notes, is_active, created_at, updated_at
        FROM agents
        ORDER BY name ASC
        """
    ).fetchall()


def update_agent(conn: sqlite3.Connection, agent_id: int, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = "strftime('%Y-%m-%dT%H:%M:%SZ','now')"
    set_clause = ", ".join(
        f"{k} = strftime('%Y-%m-%dT%H:%M:%SZ','now')" if k == "updated_at"
        else f"{k} = ?"
        for k in fields
    )
    values = [v for k, v in fields.items() if k != "updated_at"]
    values.append(agent_id)
    conn.execute(f"UPDATE agents SET {set_clause} WHERE id = ?", values)
    conn.commit()


def get_all_project_settings(conn: sqlite3.Connection) -> dict[str, str]:
    """Return all project-level setting overrides."""
    try:
        rows = conn.execute("SELECT key, value FROM project_settings").fetchall()
        return {row["key"]: row["value"] for row in rows}
    except Exception:
        return {}


def set_project_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO project_settings (key, value, updated_at)
        VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        """,
        (key, value),
    )


def get_all_settings(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM global_settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


# ---------------------------------------------------------------------------
# project.db — audit sessions, results, conflict rulings
# ---------------------------------------------------------------------------

def insert_audit_session(conn, artifact_id, artifact_type, execution_mode,
                         agent_order, scope="current") -> int:
    conn.execute("""
        INSERT INTO audit_sessions
            (artifact_id, artifact_type, execution_mode, agent_order, cross_project_scope)
        VALUES (:artifact_id, :artifact_type, :execution_mode, :agent_order, :scope)
    """, {"artifact_id": artifact_id, "artifact_type": artifact_type,
          "execution_mode": execution_mode, "agent_order": json.dumps(agent_order),
          "scope": scope})
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def complete_audit_session(conn, audit_session_id, final_decision,
                           researcher_notes, completed_at) -> None:
    conn.execute("""
        UPDATE audit_sessions
        SET final_decision=:decision, researcher_notes=:notes, completed_at=:ts
        WHERE id=:id
    """, {"decision": final_decision, "notes": researcher_notes,
          "ts": completed_at, "id": audit_session_id})


def insert_audit_result(conn, audit_session_id, agent_id) -> int:
    conn.execute("""
        INSERT INTO audit_results (audit_session_id, agent_id)
        VALUES (:session_id, :agent_id)
    """, {"session_id": audit_session_id, "agent_id": agent_id})
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_audit_result_output(conn, audit_result_id, verbose_output, findings="") -> None:
    conn.execute("""
        UPDATE audit_results SET verbose_output=:out, findings=:findings
        WHERE id=:id
    """, {"out": verbose_output, "findings": findings, "id": audit_result_id})


def insert_conflict_ruling(conn, audit_session_id, conflict_description) -> int:
    conn.execute("""
        INSERT INTO conflict_rulings (audit_session_id, conflict_description)
        VALUES (:session_id, :desc)
    """, {"session_id": audit_session_id, "desc": conflict_description})
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_conflict_ruling(conn, ruling_id, researcher_ruling, ruled_at) -> None:
    conn.execute("""
        UPDATE conflict_rulings SET researcher_ruling=:ruling, ruled_at=:ts
        WHERE id=:id
    """, {"ruling": researcher_ruling, "ts": ruled_at, "id": ruling_id})


def get_conflict_rulings(conn, audit_session_id) -> list:
    return conn.execute("""
        SELECT * FROM conflict_rulings WHERE audit_session_id=?
    """, (audit_session_id,)).fetchall()


# ---------------------------------------------------------------------------
# project.db — object editing
# ---------------------------------------------------------------------------

_OBJECT_EDITABLE = {"name", "type", "content", "math_expression",
                    "latex", "tags", "researcher_notes"}


def update_object(conn: sqlite3.Connection, object_id: int, **fields) -> None:
    safe = {k: v for k, v in fields.items() if k in _OBJECT_EDITABLE}
    if not safe:
        return
    set_parts = [f"{k} = ?" for k in safe]
    set_parts.append("updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')")
    values = list(safe.values()) + [object_id]
    conn.execute(
        f"UPDATE objects SET {', '.join(set_parts)} WHERE id = ?", values
    )


# ── Notes ─────────────────────────────────────────────────────────────

def list_notes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, title, format, tags, created_at, updated_at FROM notes ORDER BY updated_at DESC"
    ).fetchall()


def get_note(conn: sqlite3.Connection, note_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT id, title, content, format, tags, created_at, updated_at FROM notes WHERE id = ?",
        (note_id,)
    ).fetchone()


def insert_note(conn: sqlite3.Connection, title: str, content: str, fmt: str) -> int:
    conn.execute(
        "INSERT INTO notes (title, content, format) VALUES (?, ?, ?)",
        (title, content, fmt),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_note(conn: sqlite3.Connection, note_id: int, title: str, content: str, fmt: str) -> None:
    conn.execute(
        """UPDATE notes SET title = ?, content = ?, format = ?,
           updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id = ?""",
        (title, content, fmt, note_id),
    )
    conn.commit()


def delete_note(conn: sqlite3.Connection, note_id: int) -> None:
    conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    conn.commit()

