# kathoros/db/migrations.py
"""
Schema migration system for both global.db and project.db.

Design:
- Each migration is a (version, sql_statements) tuple where sql_statements
  is a LIST of individual SQL strings — no splitting required.
- Migrations are append-only — never modify existing entries.
- Version tracked in user_version PRAGMA (SQLite built-in).
- Idempotent: safe to run on an already-migrated DB.

Security notes:
- No raw user input ever passed to migration SQL.
- Read-only connections must not run migrations (enforced by caller).
- API keys are never stored here.
"""
from __future__ import annotations
import sqlite3
import logging

_log = logging.getLogger("kathoros.db.migrations")

# ---------------------------------------------------------------------------
# global.db migrations
# Each entry: (version: int, description: str, statements: list[str])
# version must be monotonically increasing from 1.
# ---------------------------------------------------------------------------

GLOBAL_MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "initial schema: agents, audit_templates, tools, global_settings, trust_overrides",
        [
            """
            CREATE TABLE IF NOT EXISTS agents (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                name                 TEXT NOT NULL,
                alias                TEXT,
                type                 TEXT NOT NULL CHECK(type IN ('local','api')),
                provider             TEXT,
                endpoint             TEXT,
                model_string         TEXT,
                capability_tags      TEXT DEFAULT '[]',
                cost_tier            TEXT CHECK(cost_tier IN ('free','low','medium','high')),
                context_window       INTEGER,
                default_research_prompt TEXT,
                default_audit_prompt TEXT,
                trust_level          TEXT NOT NULL DEFAULT 'monitored'
                                         CHECK(trust_level IN ('untrusted','monitored','trusted')),
                require_tool_approval  INTEGER,
                require_write_approval INTEGER,
                user_notes           TEXT,
                is_active            INTEGER NOT NULL DEFAULT 1,
                created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                updated_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_templates (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                name              TEXT NOT NULL,
                description       TEXT,
                agent_id          INTEGER REFERENCES agents(id) ON DELETE SET NULL,
                prompt_template   TEXT NOT NULL DEFAULT '',
                artifact_types    TEXT NOT NULL DEFAULT '[]',
                is_system_default INTEGER NOT NULL DEFAULT 0,
                created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS tools (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                name                 TEXT NOT NULL UNIQUE,
                aliases              TEXT NOT NULL DEFAULT '[]',
                invocation_patterns  TEXT NOT NULL DEFAULT '[]',
                input_format         TEXT,
                execution_type       TEXT NOT NULL DEFAULT 'blocking'
                                         CHECK(execution_type IN ('blocking','nonblocking')),
                output_target        TEXT NOT NULL DEFAULT 'context'
                                         CHECK(output_target IN
                                               ('context','sagemath','matplotlib','shell','content_area')),
                is_active            INTEGER NOT NULL DEFAULT 1,
                description          TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS global_settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trust_overrides (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id   INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                scope      TEXT NOT NULL,
                granted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                expires_at TEXT NOT NULL,
                session_id INTEGER NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name)",
            "CREATE INDEX IF NOT EXISTS idx_agents_trust ON agents(trust_level)",
            "CREATE INDEX IF NOT EXISTS idx_trust_overrides_session ON trust_overrides(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_trust_overrides_agent ON trust_overrides(agent_id)",
        ],
    ),
    (
        2,
        "seed system default audit templates",
        [
            # Each seed row is a separate statement with literal values
            """INSERT OR IGNORE INTO audit_templates (name, description, prompt_template, artifact_types, is_system_default)
               VALUES ('Logic/Consistency', 'Find internal contradictions in the artifact.',
               'You are a rigorous logic auditor. Review the following artifact for internal contradictions, circular reasoning, or unsupported jumps. Be specific about which claims conflict.',
               '["concept","derivation","prediction","definition"]', 1)""",
            """INSERT OR IGNORE INTO audit_templates (name, description, prompt_template, artifact_types, is_system_default)
               VALUES ('Mathematical', 'Verify derivations, units, and dimensional analysis.',
               'You are a mathematical auditor. Verify all derivations step by step. Check units, dimensional analysis, and numerical claims. Flag any step that cannot be verified.',
               '["derivation","math"]', 1)""",
            """INSERT OR IGNORE INTO audit_templates (name, description, prompt_template, artifact_types, is_system_default)
               VALUES ('Conceptual', 'Examine assumptions, scope, and interpretive leaps.',
               'You are a conceptual auditor. Identify hidden assumptions, scope limitations, and interpretive leaps. Distinguish what is claimed from what is demonstrated.',
               '["concept","prediction","evidence"]', 1)""",
            """INSERT OR IGNORE INTO audit_templates (name, description, prompt_template, artifact_types, is_system_default)
               VALUES ('Peer Review', 'Academic rigor and claim strength.',
               'You are a peer reviewer. Evaluate academic rigor, strength of evidence, clarity of claims, and completeness of citations. Would this pass journal review?',
               '["concept","derivation","prediction","evidence","definition"]', 1)""",
            """INSERT OR IGNORE INTO audit_templates (name, description, prompt_template, artifact_types, is_system_default)
               VALUES ('Devil''s Advocate', 'Argue against the conclusion.',
               'You are playing devil''s advocate. Construct the strongest possible argument against the conclusion of this artifact. Do not hold back.',
               '["concept","derivation","prediction","evidence","definition"]', 1)""",
        ],
    ),
    (
        3,
        "seed default global settings",
        [
            "INSERT OR IGNORE INTO global_settings (key, value) VALUES ('default_access_mode', 'REQUEST_FIRST')",
            "INSERT OR IGNORE INTO global_settings (key, value) VALUES ('default_trust_level', 'MONITORED')",
            "INSERT OR IGNORE INTO global_settings (key, value) VALUES ('require_write_approval', '1')",
            "INSERT OR IGNORE INTO global_settings (key, value) VALUES ('require_tool_approval', '1')",
            "INSERT OR IGNORE INTO global_settings (key, value) VALUES ('require_git_confirm', '1')",
            "INSERT OR IGNORE INTO global_settings (key, value) VALUES ('require_security_scan', '1')",
            "INSERT OR IGNORE INTO global_settings (key, value) VALUES ('max_snapshot_size_bytes', '1048576')",
            "INSERT OR IGNORE INTO global_settings (key, value) VALUES ('audit_log_append_only', '1')",
        ],
    ),
]


# ---------------------------------------------------------------------------
# project.db migrations
# ---------------------------------------------------------------------------

PROJECT_MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "initial schema: projects, sessions, objects, concept_nodes, cross_references, "
        "interactions, audit_sessions, audit_results, conflict_rulings, tool_audit_log, fts",
        [
            """
            CREATE TABLE IF NOT EXISTS projects (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT NOT NULL,
                description    TEXT,
                research_goals TEXT,
                license        TEXT,
                git_repo_path  TEXT,
                created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                last_session   TEXT,
                status         TEXT NOT NULL DEFAULT 'active'
                                   CHECK(status IN ('active','archived','published'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id     INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name           TEXT,
                started_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                last_active    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                state_snapshot TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS objects (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id             INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                name                   TEXT NOT NULL,
                type                   TEXT NOT NULL
                                           CHECK(type IN (
                                               'concept','definition','derivation',
                                               'prediction','evidence','open_question','data')),
                status                 TEXT NOT NULL DEFAULT 'pending'
                                           CHECK(status IN (
                                               'pending','audited','flagged',
                                               'disputed','committed')),
                content                TEXT,
                math_expression        TEXT,
                latex                  TEXT,
                tags                   TEXT NOT NULL DEFAULT '[]',
                related_objects        TEXT NOT NULL DEFAULT '[]',
                depends_on             TEXT NOT NULL DEFAULT '[]',
                contradicts            TEXT NOT NULL DEFAULT '[]',
                source_conversation_ref TEXT,
                attached_files         TEXT NOT NULL DEFAULT '[]',
                researcher_notes       TEXT,
                ai_suggested_tags      TEXT NOT NULL DEFAULT '[]',
                version                INTEGER NOT NULL DEFAULT 1,
                created_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                committed_at           TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS concept_nodes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                object_id   INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
                parent_id   INTEGER REFERENCES concept_nodes(id) ON DELETE CASCADE,
                node_type   TEXT NOT NULL
                                CHECK(node_type IN (
                                    'root','definition','math','prediction',
                                    'evidence','implication')),
                content     TEXT,
                created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cross_references (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                source_object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
                target_object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
                reference_type   TEXT NOT NULL
                                     CHECK(reference_type IN (
                                         'supports','contradicts','extends','depends_on')),
                notes            TEXT,
                created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS interactions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id       INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                agent_id         INTEGER,
                role             TEXT NOT NULL CHECK(role IN ('user','assistant')),
                content          TEXT NOT NULL DEFAULT '',
                tool_invocations TEXT NOT NULL DEFAULT '[]',
                timestamp        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_sessions (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_id          INTEGER NOT NULL,
                artifact_type        TEXT NOT NULL,
                execution_mode       TEXT NOT NULL DEFAULT 'concurrent'
                                          CHECK(execution_mode IN ('concurrent','linear')),
                agent_order          TEXT NOT NULL DEFAULT '[]',
                cross_project_scope  TEXT NOT NULL DEFAULT 'current'
                                          CHECK(cross_project_scope IN ('current','selected','all')),
                selected_project_ids TEXT NOT NULL DEFAULT '[]',
                researcher_notes     TEXT,
                final_decision       TEXT CHECK(final_decision IN ('approved','rejected','modified')),
                created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                completed_at         TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_results (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_session_id  INTEGER NOT NULL
                                      REFERENCES audit_sessions(id) ON DELETE CASCADE,
                agent_id          INTEGER,
                verbose_output    TEXT NOT NULL DEFAULT '',
                tool_invocations  TEXT NOT NULL DEFAULT '[]',
                findings          TEXT,
                conflicts_identified TEXT NOT NULL DEFAULT '[]',
                created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS conflict_rulings (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_session_id     INTEGER NOT NULL
                                         REFERENCES audit_sessions(id) ON DELETE CASCADE,
                conflict_description TEXT NOT NULL DEFAULT '',
                researcher_ruling    TEXT,
                ruled_at             TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS tool_audit_log (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id       TEXT NOT NULL,
                agent_id         TEXT NOT NULL,
                agent_name       TEXT NOT NULL,
                trust_level      TEXT NOT NULL,
                access_mode      TEXT NOT NULL,
                tool_name        TEXT NOT NULL,
                raw_args_hash    TEXT NOT NULL,
                nonce_valid      INTEGER NOT NULL,
                enveloped        INTEGER NOT NULL,
                detected_via     TEXT NOT NULL,
                decision         TEXT NOT NULL,
                validation_ok    INTEGER NOT NULL,
                validation_errors TEXT NOT NULL DEFAULT '[]',
                output_size      INTEGER NOT NULL DEFAULT 0,
                execution_ms     REAL NOT NULL DEFAULT 0.0,
                artifacts        TEXT NOT NULL DEFAULT '[]',
                logged_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            )
            """,
            # Indexes
            "CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_objects_session ON objects(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_objects_status ON objects(status)",
            "CREATE INDEX IF NOT EXISTS idx_objects_type ON objects(type)",
            "CREATE INDEX IF NOT EXISTS idx_interactions_session ON interactions(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_audit_results_session ON audit_results(audit_session_id)",
            "CREATE INDEX IF NOT EXISTS idx_tool_audit_log_request ON tool_audit_log(request_id)",
            "CREATE INDEX IF NOT EXISTS idx_tool_audit_log_agent ON tool_audit_log(agent_id)",
            "CREATE INDEX IF NOT EXISTS idx_tool_audit_log_decision ON tool_audit_log(decision)",
            # FTS virtual table
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS objects_fts USING fts5(
                name,
                content,
                tags,
                researcher_notes,
                content='objects',
                content_rowid='id'
            )
            """,
            # FTS triggers — each is a separate statement to avoid semicolon-in-body issues
            """
            CREATE TRIGGER IF NOT EXISTS objects_fts_insert
                AFTER INSERT ON objects BEGIN
                    INSERT INTO objects_fts(rowid, name, content, tags, researcher_notes)
                    VALUES (new.id, new.name, new.content, new.tags, new.researcher_notes);
                END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS objects_fts_update
                AFTER UPDATE ON objects BEGIN
                    INSERT INTO objects_fts(objects_fts, rowid, name, content, tags, researcher_notes)
                    VALUES ('delete', old.id, old.name, old.content, old.tags, old.researcher_notes);
                    INSERT INTO objects_fts(rowid, name, content, tags, researcher_notes)
                    VALUES (new.id, new.name, new.content, new.tags, new.researcher_notes);
                END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS objects_fts_delete
                AFTER DELETE ON objects BEGIN
                    INSERT INTO objects_fts(objects_fts, rowid, name, content, tags, researcher_notes)
                    VALUES ('delete', old.id, old.name, old.content, old.tags, old.researcher_notes);
                END
            """,
        ],
    ),
]


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------

def get_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def set_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {version}")


def run_migrations(
    conn: sqlite3.Connection,
    migrations: list[tuple[int, str, list[str]]],
    db_label: str = "db",
) -> int:
    """
    Apply all pending migrations in order.
    Returns number of migrations applied.
    Each migration is a list of individual SQL statements — no splitting needed.
    """
    _validate_migration_list(migrations)

    current = get_version(conn)
    applied = 0

    for version, description, statements in migrations:
        if version <= current:
            continue

        _log.info(f"[{db_label}] applying migration {version}: {description}")

        with conn:
            for sql in statements:
                sql = sql.strip()
                if not sql:
                    continue
                # Trigger bodies contain semicolons inside BEGIN...END.
                if 'CREATE TRIGGER' in sql.upper():
                    conn.executescript(sql)
                # ALTER TABLE statements may hit duplicate column errors on re-run
                elif sql.upper().startswith('ALTER TABLE'):
                    try:
                        conn.execute(sql)
                    except Exception as e:
                        msg = str(e).lower()
                        if 'duplicate column' in msg or 'already exists' in msg:
                            _log.debug(f"[{db_label}] idempotent skip: {e}")
                        else:
                            raise
                else:
                    conn.execute(sql)
            set_version(conn, version)

        applied += 1
        _log.info(f"[{db_label}] migration {version} applied")

    if applied == 0:
        _log.debug(f"[{db_label}] schema up to date at version {current}")

    return applied


def _validate_migration_list(migrations: list[tuple[int, str, list[str]]]) -> None:
    for i, (version, _, _) in enumerate(migrations):
        expected = i + 1
        if version != expected:
            raise ValueError(
                f"Migration list invalid: expected version {expected}, got {version}"
            )


# ---------------------------------------------------------------------------
# project.db v2 migration — epistemic graph integrity fields + bug fixes
# ---------------------------------------------------------------------------

_PROJECT_MIGRATION_V2_STMTS = [
    # Add epistemic columns to objects (ALTER TABLE — idempotent pattern via
    # ignore errors on "duplicate column" which SQLite raises as OperationalError)
    "ALTER TABLE objects ADD COLUMN object_type TEXT NOT NULL DEFAULT 'toy_model'",
    "ALTER TABLE objects ADD COLUMN epistemic_status TEXT NOT NULL DEFAULT 'draft'",
    "ALTER TABLE objects ADD COLUMN origin TEXT NOT NULL DEFAULT 'human'",
    "ALTER TABLE objects ADD COLUMN claim_level TEXT NOT NULL DEFAULT 'definition'",
    "ALTER TABLE objects ADD COLUMN narrative_label TEXT NOT NULL DEFAULT 'N/A'",
    "ALTER TABLE objects ADD COLUMN falsifiable TEXT NOT NULL DEFAULT 'unknown'",
    "ALTER TABLE objects ADD COLUMN falsification_criteria TEXT DEFAULT ''",
    "ALTER TABLE objects ADD COLUMN validation_scope TEXT NOT NULL DEFAULT 'internal'",
    # Add session_id and decided_at to tool_audit_log
    "ALTER TABLE tool_audit_log ADD COLUMN session_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE tool_audit_log ADD COLUMN decided_at TEXT NOT NULL DEFAULT ''",
    # Index for epistemic queries
    "CREATE INDEX IF NOT EXISTS idx_objects_epistemic_status ON objects(epistemic_status)",
    "CREATE INDEX IF NOT EXISTS idx_objects_object_type ON objects(object_type)",
    "CREATE INDEX IF NOT EXISTS idx_objects_claim_level ON objects(claim_level)",
]


def _run_alter_statements(conn, statements: list, db_label: str) -> None:
    """Run ALTER TABLE statements, ignoring 'duplicate column' errors (idempotent)."""
    import sqlite3
    for sql in statements:
        sql = sql.strip()
        if not sql:
            continue
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "duplicate column" in msg:
                _log.debug(f"[{db_label}] column already exists (idempotent): {e}")
            elif "already exists" in msg:
                _log.debug(f"[{db_label}] index already exists (idempotent): {e}")
            else:
                raise


# Append v2 to PROJECT_MIGRATIONS
PROJECT_MIGRATIONS.append((
    2,
    "epistemic graph integrity fields on objects; session_id + decided_at on tool_audit_log",
    _PROJECT_MIGRATION_V2_STMTS,
))

# Append v3 to PROJECT_MIGRATIONS
PROJECT_MIGRATIONS.append((
    3,
    "project_settings table for project-level overrides of global defaults",
    [
        """
        CREATE TABLE IF NOT EXISTS project_settings (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
        """,
    ],
))

# Append v4 to PROJECT_MIGRATIONS
PROJECT_MIGRATIONS.append((
    4,
    "notes table for per-project researcher notes",
    [
        """
        CREATE TABLE IF NOT EXISTS notes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL DEFAULT 'Untitled',
            content    TEXT NOT NULL DEFAULT '',
            format     TEXT NOT NULL DEFAULT 'markdown',
            tags       TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
        """,
    ],
))

# Append v5 to PROJECT_MIGRATIONS
PROJECT_MIGRATIONS.append((
    5,
    "source_file column on objects — tracks originating paper, note, or dataset",
    [
        "ALTER TABLE objects ADD COLUMN source_file TEXT",
    ],
))
