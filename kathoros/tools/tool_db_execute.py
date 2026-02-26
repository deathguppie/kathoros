"""
db_execute tool executor.
Runs SQL statements (SELECT, INSERT, UPDATE, DELETE, CREATE TABLE)
against the project or global SQLite database.
Executor validates and passes through — actual DB execution happens in main_window.
Executor must not contain approval logic (INV-15).
Executor must not call the router (INV-1).
"""
import logging
import re

from kathoros.router.models import ToolDefinition

_log = logging.getLogger("kathoros.tools.tool_db_execute")

# Allowed SQL statement prefixes
_ALLOWED_PREFIXES = ("select", "insert", "update", "delete", "create", "alter", "pragma")

# Dangerous operations that are never allowed
_BLOCKED_PATTERNS = re.compile(
    r"\b(drop\s+(database|table|view|trigger|index)|attach\s+database|detach\s+database)\b",
    re.IGNORECASE,
)

DB_EXECUTE_TOOL = ToolDefinition(
    name="db_execute",
    description=(
        "Execute a SQL statement against the project or global SQLite database. "
        "Supports SELECT, INSERT, UPDATE, DELETE, and CREATE TABLE. "
        "Use 'db' arg to choose 'project' (default) or 'global'. "
        "DROP DATABASE, ATTACH, and DETACH are blocked. "
        "For research objects, prefer object_create/object_update tools instead."
    ),
    write_capable=True,
    requires_run_scope=False,
    requires_write_approval=True,
    execute_approval_required=False,
    allowed_paths=(),
    path_fields=(),
    max_input_size=65536,
    max_output_size=1_048_576,
    aliases=("sql", "run_sql", "sqlite"),
    output_target="database",
    args_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["sql"],
        "properties": {
            "sql": {
                "type": "string",
                "minLength": 1,
                "maxLength": 32768,
                "description": "SQL statement to execute.",
            },
            "db": {
                "type": "string",
                "enum": ["project", "global"],
                "description": "Which database to target. Defaults to 'project'.",
            },
        },
    },
)


def execute_db_execute(args: dict, tool: ToolDefinition, project_root) -> dict:
    """Validate SQL and pass through for main_window to execute against the DB."""
    sql = args["sql"].strip()
    db = args.get("db", "project")

    # Check against blocked patterns
    if _BLOCKED_PATTERNS.search(sql):
        return {"error": "Blocked: dangerous SQL operation not allowed."}

    # Check that the statement starts with an allowed prefix
    first_word = sql.split()[0].lower() if sql.split() else ""
    if first_word not in _ALLOWED_PREFIXES:
        return {"error": f"Blocked: '{first_word}' statements not allowed. "
                f"Use: {', '.join(_ALLOWED_PREFIXES)}"}

    _log.info("db_execute: db=%s sql=%.80s", db, sql)
    return {"action": "db_execute", "sql": sql, "db": db}
