import unittest, sqlite3, sys, os
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

def _seed(conn, sid, name, epistemic_status="draft"):
    conn.execute(
        "INSERT INTO objects (session_id, name, type, status, object_type, "
        "epistemic_status, claim_level, narrative_label, falsifiable, validation_scope) "
        "VALUES (?,?,'concept','pending','toy_model',?,'definition','N/A','unknown','internal')",
        (sid, name, epistemic_status)
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

class TestSetStatus(unittest.TestCase):
    def test_blocks_when_dep_not_validated(self):
        conn = _make_db(); sid = _make_session(conn); svc = SessionService(conn, sid)
        b = _seed(conn, sid, "B", "draft")
        a = _seed(conn, sid, "A", "draft")
        svc.add_reference(a, b, "depends_on")
        r = svc.set_object_status(a, "validated")
        self.assertFalse(r["ok"])
        self.assertIn("EP001", r["error"])

    def test_allows_when_dep_validated(self):
        conn = _make_db(); sid = _make_session(conn); svc = SessionService(conn, sid)
        b = _seed(conn, sid, "B", "validated")
        a = _seed(conn, sid, "A", "draft")
        svc.add_reference(a, b, "depends_on")
        r = svc.set_object_status(a, "validated")
        self.assertTrue(r["ok"])

    def test_inspired_by_does_not_block(self):
        conn = _make_db(); sid = _make_session(conn); svc = SessionService(conn, sid)
        b = _seed(conn, sid, "B", "draft")
        a = _seed(conn, sid, "A", "draft")
        conn.execute("INSERT INTO cross_references (source_object_id, target_object_id, reference_type) VALUES (?,?,'supports')", (a, b))
        conn.commit()
        r = svc.set_object_status(a, "validated")
        self.assertTrue(r["ok"])

class TestReferences(unittest.TestCase):
    def test_roundtrip(self):
        conn = _make_db(); sid = _make_session(conn); svc = SessionService(conn, sid)
        a = _seed(conn, sid, "A"); b = _seed(conn, sid, "B")
        self.assertTrue(svc.add_reference(a, b, "depends_on")["ok"])
        cnt = conn.execute("SELECT COUNT(*) FROM cross_references WHERE source_object_id=? AND target_object_id=?", (a,b)).fetchone()[0]
        self.assertEqual(cnt, 1)
        self.assertTrue(svc.remove_reference(a, b, "depends_on")["ok"])
        cnt2 = conn.execute("SELECT COUNT(*) FROM cross_references WHERE source_object_id=? AND target_object_id=?", (a,b)).fetchone()[0]
        self.assertEqual(cnt2, 0)

class TestUIDoesNotImportQueries(unittest.TestCase):
    def test_no_direct_query_imports_in_ui(self):
        ui_dir = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "kathoros", "ui"))
        violations = []
        for fname in os.listdir(ui_dir):
            if not fname.endswith(".py"): continue
            content = open(os.path.join(ui_dir, fname)).read()
            if "kathoros.db.queries" in content or "from kathoros.db import queries" in content:
                violations.append(fname)
        self.assertEqual(violations, [], f"UI must not import queries directly: {violations}")

if __name__ == "__main__":
    unittest.main()
