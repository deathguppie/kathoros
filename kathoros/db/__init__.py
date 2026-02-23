# kathoros/db — SQLite layer
# Two databases: global.db (agents, tools, settings) and project.db (research data).
# Cross-project access is always read-only, enforced at connection layer.
from kathoros.db.connection import open_global_db, open_project_db, open_project_db_readonly
from kathoros.db.migrations import run_migrations, GLOBAL_MIGRATIONS, PROJECT_MIGRATIONS

__all__ = [
    "open_global_db",
    "open_project_db",
    "open_project_db_readonly",
    "run_migrations",
    "GLOBAL_MIGRATIONS",
    "PROJECT_MIGRATIONS",
]
