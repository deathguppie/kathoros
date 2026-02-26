"""
matplot_render tool executor.
Passes matplotlib code to the UI layer for execution via MatPlotPanel.
Executor must not contain approval logic (INV-15).
Executor must not call the router (INV-1).
"""
import logging
from kathoros.router.models import ToolDefinition

_log = logging.getLogger("kathoros.tools.tool_matplot_render")

MATPLOT_RENDER_TOOL = ToolDefinition(
    name="matplot_render",
    description=(
        "Execute matplotlib code and display the plot in the MatPlot panel. "
        "The code runs with 'plt' (matplotlib.pyplot), 'np' (numpy), and 'fig' "
        "(the panel's Figure) available in the namespace. "
        "Use plt.plot(), plt.title(), etc. to build the figure."
    ),
    write_capable=False,
    requires_run_scope=False,
    requires_write_approval=False,
    execute_approval_required=False,
    allowed_paths=(),
    path_fields=(),
    max_input_size=65536,
    max_output_size=1_048_576,
    aliases=("render_plot", "matplotlib", "plot"),
    output_target="matplot",
    args_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["code"],
        "properties": {
            "code": {
                "type": "string",
                "minLength": 1,
                "maxLength": 32768,
                "description": (
                    "Matplotlib code. 'plt', 'np', and 'fig' are pre-imported. "
                    "Do not call plt.show()."
                ),
            },
        },
    },
)


def execute_matplot_render(args: dict, tool: ToolDefinition, project_root) -> dict:
    """Validate and pass through matplotlib code for panel execution."""
    code = args["code"]
    _log.info("matplot_render: %d chars", len(code))
    return {"action": "matplot_render", "code": code}
