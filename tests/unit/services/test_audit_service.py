import unittest
import sqlite3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from kathoros.db.migrations import run_migrations, PROJECT_MIGRATIONS
from kathoros.services.session_service import SessionService


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn, PROJECT_MIGRATIONS, db_label="test")
    return conn


def _make_session(conn):
    conn.execute("INSERT INTO projects (name) VALUES ('test')")
    conn.commit()
    pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("INSERT INTO sessions (project_id, name) VALUES (?, 'test')", (pid,))
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _seed_object(conn, sid, name="Test Object"):
    conn.execute(
        "INSERT INTO objects (session_id, name, type, status, object_type, "
        "epistemic_status, claim_level, narrative_label, falsifiable, validation_scope) "
        "VALUES (?,?,'concept','pending','toy_model','draft','definition','N/A','unknown','internal')",
        (sid, name),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


class TestCreateAndCompleteAuditSession(unittest.TestCase):
    def test_create_and_complete_audit_session(self):
        conn = _make_db()
        sid = _make_session(conn)
        svc = SessionService(conn, sid)
        obj_id = _seed_object(conn, sid, "Test Concept")

        # Create audit session
        audit_id = svc.create_audit_session(
            artifact_id=obj_id,
            artifact_type="concept",
            execution_mode="linear",
            agent_ids=[1, 2],
            scope="current",
        )
        self.assertIsInstance(audit_id, int)
        self.assertGreater(audit_id, 0)

        # Start and finish an audit result
        result_id = svc.start_audit_result(audit_id, agent_id=1)
        self.assertIsInstance(result_id, int)
        self.assertGreater(result_id, 0)

        svc.finish_audit_result(result_id, verbose_output="Agent output here.", findings="None found.")

        # Add a conflict
        ruling_id = svc.add_conflict(audit_id, "Claim A contradicts claim B.")
        self.assertGreater(ruling_id, 0)

        # Complete the audit
        svc.complete_audit(audit_id, final_decision="approved", researcher_notes="Looks good.")

        # Verify completed_at and decision are set
        row = conn.execute(
            "SELECT final_decision, researcher_notes, completed_at FROM audit_sessions WHERE id=?",
            (audit_id,),
        ).fetchone()
        self.assertEqual(row["final_decision"], "approved")
        self.assertEqual(row["researcher_notes"], "Looks good.")
        self.assertIsNotNone(row["completed_at"])


class TestAuditResultOutputPersisted(unittest.TestCase):
    def test_audit_result_output_persisted(self):
        conn = _make_db()
        sid = _make_session(conn)
        svc = SessionService(conn, sid)
        obj_id = _seed_object(conn, sid, "Derivation X")

        audit_id = svc.create_audit_session(
            artifact_id=obj_id,
            artifact_type="derivation",
            execution_mode="linear",
            agent_ids=[42],
        )
        result_id = svc.start_audit_result(audit_id, agent_id=42)
        expected_output = "PASS: derivation is sound."
        svc.finish_audit_result(result_id, verbose_output=expected_output, findings="pass")

        row = conn.execute(
            "SELECT verbose_output, findings FROM audit_results WHERE id=?",
            (result_id,),
        ).fetchone()
        self.assertEqual(row["verbose_output"], expected_output)
        self.assertEqual(row["findings"], "pass")


class TestConflictRulingStored(unittest.TestCase):
    def test_conflict_ruling_stored(self):
        conn = _make_db()
        sid = _make_session(conn)
        svc = SessionService(conn, sid)
        obj_id = _seed_object(conn, sid, "Prediction Y")

        audit_id = svc.create_audit_session(
            artifact_id=obj_id,
            artifact_type="prediction",
            execution_mode="linear",
            agent_ids=[],
        )
        desc = "Contradicts established conservation laws."
        ruling_id = svc.add_conflict(audit_id, desc)

        row = conn.execute(
            "SELECT conflict_description FROM conflict_rulings WHERE id=?",
            (ruling_id,),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["conflict_description"], desc)


if __name__ == "__main__":
    unittest.main()
