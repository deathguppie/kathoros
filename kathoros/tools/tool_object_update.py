"""
object_update tool executor.
Validates update fields against the Kathoros editable-field whitelist,
then returns data for the UI layer to apply via SessionService.update_object().
Executor must not contain approval logic (INV-15).
Executor must not call the router (INV-1).
"""
import logging
from kathoros.router.models import ToolDefinition

_log = logging.getLogger("kathoros.tools.tool_object_update")

_VALID_TYPES = [
    "concept", "definition", "derivation",
    "prediction", "evidence", "open_question", "data",
]

OBJECT_UPDATE_TOOL = ToolDefinition(
    name="object_update",
    description=(
        "Update fields on an existing research object by its integer ID. "
        "Editable fields: name, type, content (description), math_expression, "
        "latex, tags, depends_on, researcher_notes, source_file. "
        "Status changes are NOT allowed here — status is managed by the "
        "epistemic audit system only."
    ),
    write_capable=True,
    requires_run_scope=False,
    requires_write_approval=True,
    execute_approval_required=False,
    allowed_paths=(),
    path_fields=(),
    max_input_size=131072,
    max_output_size=1_048_576,
    aliases=("update_object", "edit_object"),
    output_target="session",
    args_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["object_id", "fields"],
        "properties": {
            "object_id": {"type": "integer", "minimum": 1},
            "fields": {
                "type": "object",
                "additionalProperties": False,
                "minProperties": 1,
                "properties": {
                    "name": {"type": "string", "minLength": 1, "maxLength": 512},
                    "type": {
                        "type": "string",
                        "enum": _VALID_TYPES,
                    },
                    "content": {"type": "string", "maxLength": 65536},
                    "math_expression": {"type": "string", "maxLength": 8192},
                    "latex": {"type": "string", "maxLength": 65536},
                    "tags": {
                        "type": "array",
                        "maxItems": 50,
                        "items": {"type": "string", "maxLength": 128},
                    },
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
)


def execute_object_update(args: dict, tool: ToolDefinition, project_root) -> dict:
    """Validate and pass through update data for SessionService application."""
    object_id = args["object_id"]
    fields = args["fields"]
    _log.info("object_update: id=%d fields=%s", object_id, list(fields.keys()))
    return {
        "action": "update",
        "object_id": object_id,
        "fields": fields,
        "field_count": len(fields),
    }
