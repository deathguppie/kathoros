"""
sagemath_eval tool executor.
Passes SageMath expression to the UI layer for evaluation via SageMathPanel.
Executor must not contain approval logic (INV-15).
Executor must not call the router (INV-1).
"""
import logging

from kathoros.router.models import ToolDefinition

_log = logging.getLogger("kathoros.tools.tool_sagemath_eval")

SAGEMATH_EVAL_TOOL = ToolDefinition(
    name="sagemath_eval",
    description=(
        "Evaluate a SageMath expression and display the result in the SageMath panel. "
        "The code runs in a SageMath subprocess with 'from sage.all import *' pre-imported. "
        "Use print() to produce output. Timeout is 30 seconds."
    ),
    write_capable=False,
    requires_run_scope=False,
    requires_write_approval=False,
    execute_approval_required=False,
    allowed_paths=(),
    path_fields=(),
    max_input_size=65536,
    max_output_size=1_048_576,
    aliases=("sage_eval", "run_sage"),
    output_target="sagemath",
    args_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["code"],
        "properties": {
            "code": {
                "type": "string",
                "minLength": 1,
                "maxLength": 32768,
                "description": "SageMath code to evaluate. sage.all is pre-imported.",
            },
        },
    },
)


def execute_sagemath_eval(args: dict, tool: ToolDefinition, project_root) -> dict:
    """Validate and pass through SageMath code for panel execution."""
    code = args["code"]
    _log.info("sagemath_eval: %d chars", len(code))
    return {"action": "sagemath_eval", "code": code}
