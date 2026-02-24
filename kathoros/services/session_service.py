"""
SessionService — the only supported entrypoint between UI and DB.
UI must never import db.queries directly.
No router calls (INV-1). No approval logic (INV-15).
"""
from __future__ import annotations
import logging
import sqlite3
import secrets
from typing import Optional
from kathoros.db import queries
from kathoros.epistemic.checker import CheckResult, Edge, EpistemicChecker, ObjectNode

_log = logging.getLogger("kathoros.services.session_service")


class SessionService:
    def __init__(self, project_conn: sqlite3.Connection, session_id: int) -> None:
        self._conn = project_conn
        self._session_id = session_id
        self.session_nonce = secrets.token_hex(16)
        self._checker = EpistemicChecker()

    def get_object(self, object_id: int) -> Optional[dict]:
        row = queries.get_object_by_id(self._conn, object_id)
        return dict(row) if row else None

    def list_objects(self, limit: int = 200, offset: int = 0) -> list[dict]:
        rows = queries.list_objects(self._conn, self._session_id, limit, offset)
        return [dict(r) for r in rows]

    def set_object_status(self, object_id: int, new_status: str, note: Optional[str] = None) -> dict:
        row = queries.get_object_by_id(self._conn, object_id)
        if row is None:
            return {"ok": False, "object_id": object_id, "new_status": new_status,
                    "integrity": None, "error": "object not found"}
        target = _build_node(row)
        all_nodes = self._fetch_all_nodes()
        all_edges = self._fetch_edges(object_id)
        result = self._checker.check(target, all_nodes, all_edges, proposed_status=new_status)
        if not result.ok:
            messages = [f"{v.code}: {v.message}" for v in result.blocks]
            return {"ok": False, "object_id": object_id, "new_status": new_status,
                    "integrity": _serialize_result(result), "error": "; ".join(messages)}
        queries.update_epistemic_status(self._conn, object_id, new_status)
        self._conn.commit()
        return {"ok": True, "object_id": object_id, "new_status": new_status,
                "integrity": _serialize_result(result) if result.warns else None, "error": None}

    def update_object(self, object_id: int, **fields) -> dict:
        import json
        if "tags" in fields and isinstance(fields["tags"], list):
            fields["tags"] = json.dumps(fields["tags"])
        if "depends_on" in fields and isinstance(fields["depends_on"], list):
            fields["depends_on"] = json.dumps(fields["depends_on"])
        queries.update_object(self._conn, object_id, **fields)
        self._conn.commit()
        return {"ok": True, "object_id": object_id}

    def commit_object(self, object_id: int) -> dict:
        result = self.set_object_status(object_id, "committed")
        if result["ok"]:
            queries.commit_object(self._conn, object_id)
            self._conn.commit()
        return result

    def add_reference(self, source_id: int, target_id: int, reference_type: str) -> dict:
        try:
            queries.insert_cross_reference(self._conn, source_id, target_id, reference_type)
            self._conn.commit()
            return {"ok": True, "error": None}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def remove_reference(self, source_id: int, target_id: int, reference_type: str) -> dict:
        try:
            queries.delete_cross_reference(self._conn, source_id, target_id, reference_type)
            self._conn.commit()
            return {"ok": True, "error": None}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def log_interaction(self, agent_id, role, content, tool_invocations=None) -> int:
        row_id = queries.insert_interaction(
            self._conn, self._session_id, agent_id, role, content, tool_invocations)
        self._conn.commit()
        return row_id

    def create_audit_session(self, artifact_id: int, artifact_type: str,
                             execution_mode: str, agent_ids: list,
                             scope: str = "current") -> int:
        audit_id = queries.insert_audit_session(
            self._conn, artifact_id, artifact_type, execution_mode, agent_ids, scope)
        self._conn.commit()
        return audit_id

    def start_audit_result(self, audit_session_id: int, agent_id: int) -> int:
        result_id = queries.insert_audit_result(self._conn, audit_session_id, agent_id)
        self._conn.commit()
        return result_id

    def finish_audit_result(self, audit_result_id: int, verbose_output: str,
                            findings: str = "") -> None:
        queries.update_audit_result_output(self._conn, audit_result_id, verbose_output, findings)
        self._conn.commit()

    def add_conflict(self, audit_session_id: int, description: str) -> int:
        ruling_id = queries.insert_conflict_ruling(self._conn, audit_session_id, description)
        self._conn.commit()
        return ruling_id

    def complete_audit(self, audit_session_id: int, final_decision,
                       researcher_notes: str) -> None:
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        queries.complete_audit_session(
            self._conn, audit_session_id, final_decision, researcher_notes, ts)
        self._conn.commit()

    def _fetch_all_nodes(self) -> list:
        rows = queries.list_objects(self._conn, self._session_id, limit=10000, offset=0)
        return [_build_node(r) for r in rows]

    def _fetch_edges(self, object_id: int) -> list:
        return queries.get_edges_for_object(self._conn, object_id)


    def save_snapshot(self, snapshot: dict) -> None:
        import json
        from kathoros.core.constants import MAX_SNAPSHOT_SIZE_BYTES
        data = json.dumps(snapshot, separators=(",", ":"))
        if len(data.encode("utf-8")) > MAX_SNAPSHOT_SIZE_BYTES:
            _log.warning("snapshot exceeds size cap — not saved")
            return
        queries.update_session_snapshot(self._conn, self._session_id, data)
        self._conn.commit()

    def get_snapshot(self) -> dict:
        import json
        row = queries.get_session_by_id(self._conn, self._session_id)
        if row and row["state_snapshot"]:
            try:
                return json.loads(row["state_snapshot"])
            except (json.JSONDecodeError, ValueError):
                _log.warning("corrupt state_snapshot — ignoring")
        return {}

    def get_interactions(self, limit: int = 500) -> list[dict]:
        rows = queries.get_interactions(self._conn, self._session_id, limit)
        return [dict(r) for r in rows]

    def insert_objects(self, objects: list[dict]) -> int:
        import logging
        from kathoros.agents.import_parser import detect_batch_cycles
        _log = logging.getLogger("kathoros.services.session_service")
        count = 0
        name_to_id: dict[str, int] = {}

        # Pre-flight: reject the entire batch if any circular dependency exists.
        # Circular depends_on in a physics ontology signals conceptual smuggling —
        # neither object can be independently grounded. Hard error, no partial insert.
        cycles = detect_batch_cycles(objects)
        if cycles:
            msg = (
                "Import rejected — circular dependencies detected in batch.\n"
                "Circular depends_on means neither concept can be independently "
                "grounded (conceptual smuggling).\n\n"
                + "\n".join(f"  Cycle: {c}" for c in cycles)
                + "\n\nRevise the depends_on relationships and re-import."
            )
            _log.error(msg)
            raise ValueError(msg)

        # Pass 1 — insert all objects; collect name → id map
        inserted: list[tuple[dict, int]] = []
        for obj in objects:
            try:
                oid = queries.insert_object(
                    self._conn,
                    self._session_id,
                    name=obj["name"],
                    type=obj["type"],
                    content=obj["description"],
                    tags=obj.get("tags", []),
                    math_expression=obj.get("math_expression", ""),
                    latex=obj.get("latex", ""),
                    researcher_notes=obj.get("researcher_notes", ""),
                    source_file=obj.get("source_file", ""),
                    status="pending",
                )
                self._conn.commit()
                name_to_id[obj["name"]] = oid
                inserted.append((obj, oid))
                count += 1
            except Exception as exc:
                _log.warning("failed to write object %s: %s", obj.get("name"), exc)

        # Pass 2 — resolve depends_on names → ids
        for obj, oid in inserted:
            raw = obj.get("depends_on", [])
            if not raw:
                continue
            resolved = []
            for ref in raw:
                # ref may be a name (str) or an integer id
                if isinstance(ref, int):
                    resolved.append(ref)
                elif isinstance(ref, str):
                    if ref in name_to_id:
                        resolved.append(name_to_id[ref])
                    else:
                        # try numeric string
                        try:
                            resolved.append(int(ref))
                        except ValueError:
                            _log.debug("unresolved depends_on ref %r for %r", ref, obj["name"])
            if resolved:
                try:
                    queries.update_object_depends_on(self._conn, oid, resolved)
                    self._conn.commit()
                except Exception as exc:
                    _log.warning("failed to set depends_on for %s: %s", obj["name"], exc)

        return count


def _build_node(row) -> ObjectNode:
    d = dict(row)
    return ObjectNode(
        id=d["id"],
        object_type=d.get("object_type") or "toy_model",
        epistemic_status=d.get("epistemic_status") or "draft",
        claim_level=d.get("claim_level") or "definition",
        narrative_label=d.get("narrative_label") or "N/A",
        falsifiable=d.get("falsifiable") or "unknown",
        falsification_criteria=d.get("falsification_criteria") or "",
        validation_scope=d.get("validation_scope") or "internal",
        attached_artifact_hash=d.get("attached_artifact_hash"),
    )


def _serialize_result(result: CheckResult) -> dict:
    return {
        "ok": result.ok,
        "blocks": [{"code": v.code, "message": v.message, "nodes": list(v.nodes_involved)} for v in result.blocks],
        "warns":  [{"code": v.code, "message": v.message, "nodes": list(v.nodes_involved)} for v in result.warns],
    }
