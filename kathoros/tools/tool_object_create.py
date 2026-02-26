"""
object_create tool executor.
Validates object data against the Kathoros schema, then returns it for the
UI layer to insert via SessionService.insert_objects().
Executor must not contain approval logic (INV-15).
Executor must not call the router (INV-1).
"""
import logging
from kathoros.router.models import ToolDefinition

_log = logging.getLogger("kathoros.tools.tool_object_create")

_VALID_TYPES = [
    "concept", "definition", "derivation",
    "prediction", "evidence", "open_question", "data",
]

OBJECT_CREATE_TOOL = ToolDefinition(
    name="object_create",
    description=(
        "Create one or more research objects in the active session. "
        "Each object requires 'name' and 'type'. Optional fields: "
        "description, tags, math_expression, latex, depends_on, "
        "researcher_notes, source_file. "
        "Objects are inserted via SessionService with full epistemic validation."
    ),
    write_capable=True,
    requires_run_scope=False,
    requires_write_approval=True,
    execute_approval_required=False,
    allowed_paths=(),
    path_fields=(),
    max_input_size=262144,
    max_output_size=1_048_576,
    aliases=("create_object", "create_objects", "insert_objects"),
    output_target="session",
    args_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["objects"],
        "properties": {
            "objects": {
                "type": "array",
                "minItems": 1,
                "maxItems": 50,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "type"],
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "maxLength": 512},
                        "type": {
                            "type": "string",
                            "enum": _VALID_TYPES,
                        },
                        "description": {"type": "string", "maxLength": 65536},
                        "tags": {
                            "type": "array",
                            "maxItems": 50,
                            "items": {"type": "string", "maxLength": 128},
                        },
                        "math_expression": {"type": "string", "maxLength": 8192},
                        "latex": {"type": "string", "maxLength": 65536},
                        "depends_on": {
                            "type": "array",
                            "maxItems": 100,
                            "items": {"type": "string", "maxLength": 256},
                        },
                        "researcher_notes": {"type": "string", "maxLength": 65536},
                        "source_file": {"type": "string", "maxLength": 512},
                    },
                },
            },
        },
    },
)


def execute_object_create(args: dict, tool: ToolDefinition, project_root) -> dict:
    """Validate and pass through object data for SessionService insertion."""
    objects = args.get("objects", [])
    _log.info("object_create: %d objects", len(objects))
    return {"action": "insert", "objects": objects, "count": len(objects)}
