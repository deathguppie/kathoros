# tests/unit/db/test_migrations.py
import sqlite3
import unittest
from kathoros.db.migrations import (
    run_migrations, get_version, set_version,
    GLOBAL_MIGRATIONS, PROJECT_MIGRATIONS,
    _validate_migration_list,
)


class TestMigrationRunner(unittest.TestCase):

    def _mem_conn(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def test_global_migrations_apply(self):
        conn = self._mem_conn()
        applied = run_migrations(conn, GLOBAL_MIGRATIONS, "global.db")
        self.assertEqual(applied, len(GLOBAL_MIGRATIONS))
        self.assertEqual(get_version(conn), len(GLOBAL_MIGRATIONS))

    def test_project_migrations_apply(self):
        conn = self._mem_conn()
        applied = run_migrations(conn, PROJECT_MIGRATIONS, "project.db")
        self.assertEqual(applied, len(PROJECT_MIGRATIONS))
        self.assertEqual(get_version(conn), len(PROJECT_MIGRATIONS))

    def test_idempotent(self):
        conn = self._mem_conn()
        run_migrations(conn, GLOBAL_MIGRATIONS)
        applied = run_migrations(conn, GLOBAL_MIGRATIONS)
        self.assertEqual(applied, 0)

    def test_version_increments(self):
        conn = self._mem_conn()
        run_migrations(conn, GLOBAL_MIGRATIONS)
        self.assertEqual(get_version(conn), len(GLOBAL_MIGRATIONS))

    def test_invalid_migration_list_raises(self):
        bad = [(2, "skipped version 1", "SELECT 1")]
        with self.assertRaises(ValueError):
            _validate_migration_list(bad)

    def test_partial_migration(self):
        """Apply only first migration, then apply rest."""
        conn = self._mem_conn()
        first = GLOBAL_MIGRATIONS[:1]
        run_migrations(conn, first)
        self.assertEqual(get_version(conn), 1)
        # Now apply all — should only apply remaining
        applied = run_migrations(conn, GLOBAL_MIGRATIONS)
        self.assertEqual(applied, len(GLOBAL_MIGRATIONS) - 1)


class TestGlobalSchema(unittest.TestCase):

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        run_migrations(self.conn, GLOBAL_MIGRATIONS)

    def test_agents_table_exists(self):
        self.conn.execute("SELECT id FROM agents LIMIT 1")

    def test_audit_templates_seeded(self):
        count = self.conn.execute(
            "SELECT COUNT(*) FROM audit_templates WHERE is_system_default = 1"
        ).fetchone()[0]
        self.assertEqual(count, 5)

    def test_global_settings_seeded(self):
        row = self.conn.execute(
            "SELECT value FROM global_settings WHERE key = 'default_access_mode'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "REQUEST_FIRST")

    def test_tools_table_exists(self):
        self.conn.execute("SELECT id FROM tools LIMIT 1")

    def test_trust_overrides_table_exists(self):
        self.conn.execute("SELECT id FROM trust_overrides LIMIT 1")

    def test_agent_trust_level_constraint(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO agents (name, type, trust_level) VALUES (?, ?, ?)",
                ("bad-agent", "local", "superadmin"),
            )
            self.conn.commit()

    def test_agent_type_constraint(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO agents (name, type) VALUES (?, ?)",
                ("bad-agent", "unknown_type"),
            )
            self.conn.commit()


class TestProjectSchema(unittest.TestCase):

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        run_migrations(self.conn, PROJECT_MIGRATIONS)

    def _make_project(self):
        self.conn.execute(
            "INSERT INTO projects (name) VALUES (?)", ("Test Project",)
        )
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _make_session(self, project_id):
        self.conn.execute(
            "INSERT INTO sessions (project_id, name) VALUES (?, ?)",
            (project_id, "session-1"),
        )
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def test_tables_exist(self):
        for table in [
            "projects", "sessions", "objects", "concept_nodes",
            "cross_references", "interactions", "audit_sessions",
            "audit_results", "conflict_rulings", "tool_audit_log",
        ]:
            self.conn.execute(f"SELECT * FROM {table} LIMIT 1")

    def test_fts_table_exists(self):
        self.conn.execute("SELECT * FROM objects_fts LIMIT 1")

    def test_object_status_constraint(self):
        pid = self._make_project()
        sid = self._make_session(pid)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO objects (session_id, name, type, status) VALUES (?,?,?,?)",
                (sid, "obj", "concept", "invalid_status"),
            )
            self.conn.commit()

    def test_object_type_constraint(self):
        pid = self._make_project()
        sid = self._make_session(pid)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO objects (session_id, name, type) VALUES (?,?,?)",
                (sid, "obj", "unknown_type"),
            )
            self.conn.commit()

    def test_fts_trigger_insert(self):
        pid = self._make_project()
        sid = self._make_session(pid)
        self.conn.execute(
            "INSERT INTO objects (session_id, name, type, content) VALUES (?,?,?,?)",
            (sid, "Planck constant", "definition", "h = 6.626e-34 J·s"),
        )
        self.conn.commit()
        rows = self.conn.execute(
            "SELECT * FROM objects_fts WHERE objects_fts MATCH 'Planck'"
        ).fetchall()
        self.assertEqual(len(rows), 1)

    def test_tool_audit_log_schema(self):
        # Verify all required columns exist
        cols = {
            row[1] for row in
            self.conn.execute("PRAGMA table_info(tool_audit_log)").fetchall()
        }
        required = {
            "request_id", "agent_id", "agent_name", "trust_level", "access_mode",
            "tool_name", "raw_args_hash", "nonce_valid", "enveloped", "detected_via",
            "decision", "validation_ok", "validation_errors", "output_size",
            "execution_ms", "artifacts",
        }
        self.assertTrue(required.issubset(cols), f"Missing columns: {required - cols}")

    def test_cascade_delete_session_deletes_objects(self):
        pid = self._make_project()
        sid = self._make_session(pid)
        self.conn.execute(
            "INSERT INTO objects (session_id, name, type) VALUES (?,?,?)",
            (sid, "obj", "concept"),
        )
        self.conn.commit()
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        self.conn.commit()
        count = self.conn.execute(
            "SELECT COUNT(*) FROM objects WHERE session_id = ?", (sid,)
        ).fetchone()[0]
        self.assertEqual(count, 0)


class TestConnectionHelpers(unittest.TestCase):

    def test_validate_snapshot_ok(self):
        from kathoros.db.connection import validate_snapshot
        result = validate_snapshot('{"ui": "state"}')
        self.assertIsNotNone(result)

    def test_validate_snapshot_oversized(self):
        from kathoros.db.connection import validate_snapshot
        big = "x" * (1_048_576 + 1)
        with self.assertRaises(ValueError):
            validate_snapshot(big)

    def test_readonly_connection_raises_on_missing_db(self):
        from kathoros.db.connection import open_project_db_readonly
        from pathlib import Path
        with self.assertRaises(FileNotFoundError):
            open_project_db_readonly(Path("/tmp/does_not_exist_kathoros.db"))


class TestQueries(unittest.TestCase):

    def setUp(self):
        # global.db and project.db are separate files with separate user_version.
        # Use two connections to correctly simulate real usage.
        self.gconn = sqlite3.connect(":memory:")
        self.gconn.execute("PRAGMA foreign_keys = ON")
        self.gconn.row_factory = sqlite3.Row
        run_migrations(self.gconn, GLOBAL_MIGRATIONS)

        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.row_factory = sqlite3.Row
        run_migrations(self.conn, PROJECT_MIGRATIONS)

    def test_insert_and_get_agent(self):
        from kathoros.db.queries import insert_agent, get_agent
        aid = insert_agent(
            self.gconn,
            name="deepseek-r1",
            type="local",
            trust_level="monitored",
        )
        self.gconn.commit()
        row = get_agent(self.gconn, aid)
        self.assertEqual(row["name"], "deepseek-r1")
        self.assertEqual(row["trust_level"], "monitored")

    def test_insert_object_fts_searchable(self):
        from kathoros.db.queries import insert_object, search_objects_fts, insert_project, insert_session
        pid = insert_project(self.conn, name="Test")
        self.conn.commit()
        sid = insert_session(self.conn, pid, "s1")
        self.conn.commit()
        insert_object(
            self.conn, sid,
            name="Uncertainty Principle",
            type="definition",
            content="Delta x * Delta p >= hbar/2",
        )
        self.conn.commit()
        results = search_objects_fts(self.conn, "Uncertainty")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Uncertainty Principle")

    def test_tool_audit_log_rejects_raw_args(self):
        from kathoros.db.queries import insert_tool_audit_log
        with self.assertRaises(AssertionError):
            insert_tool_audit_log(
                self.conn,
                args={"path": "docs/secret.pdf"},   # must be rejected
                request_id="req-001",
                agent_id="agent-1",
                agent_name="test",
                trust_level="MONITORED",
                access_mode="REQUEST_FIRST",
                tool_name="file_analyze",
                raw_args_hash="a" * 64,
                nonce_valid=True,
                enveloped=True,
                detected_via="json",
                decision="APPROVED",
                validation_ok=True,
            )

    def test_global_setting_roundtrip(self):
        from kathoros.db.queries import get_global_setting, set_global_setting
        set_global_setting(self.gconn, "test_key", "test_value")
        self.gconn.commit()
        val = get_global_setting(self.gconn, "test_key")
        self.assertEqual(val, "test_value")


if __name__ == "__main__":
    unittest.main()
