"""
GlobalService — UI/DB boundary for global.db.
Owns settings reads/writes and agent registry operations.
UI must not import db.queries directly for global.db operations.
"""
import logging
from kathoros.db import queries

_log = logging.getLogger("kathoros.services.global_service")


class GlobalService:
    def __init__(self, conn) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_all_settings(self) -> dict[str, str]:
        return queries.get_all_settings(self._conn)

    def get_setting(self, key: str) -> str | None:
        return queries.get_global_setting(self._conn, key)

    def set_setting(self, key: str, value: str) -> None:
        queries.set_global_setting(self._conn, key, value)
        _log.info("setting updated: %s = %s", key, value)

    def apply_settings(self, settings: dict) -> None:
        for key, value in settings.items():
            queries.set_global_setting(self._conn, key, str(value))
        _log.info("applied %d settings", len(settings))

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    def list_agents(self) -> list[dict]:
        rows = queries.list_agents(self._conn)
        return [dict(r) for r in rows]

    def get_agent(self, agent_id: int) -> dict | None:
        row = queries.get_agent(self._conn, agent_id)
        return dict(row) if row else None

    def insert_agent(self, **fields) -> int:
        agent_id = queries.insert_agent(self._conn, **fields)
        self._conn.commit()
        _log.info("agent created: id=%d name=%s", agent_id, fields.get("name"))
        return agent_id

    def update_agent(self, agent_id: int, **fields) -> None:
        queries.update_agent(self._conn, agent_id, **fields)
        _log.info("agent updated: id=%d", agent_id)

    def delete_agent(self, agent_id: int) -> None:
        queries.delete_agent(self._conn, agent_id)
        _log.info("agent deleted: id=%d", agent_id)
