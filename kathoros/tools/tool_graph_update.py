"""
graph_update tool executor.
Accepts nodes and edges, returns them for the UI layer to apply to the
GraphPanel. The executor itself is UI-free — main_window handles rendering.
"""
import logging
from kathoros.router.models import ToolDefinition

_log = logging.getLogger("kathoros.tools.tool_graph_update")

GRAPH_UPDATE_TOOL = ToolDefinition(
    name="graph_update",
    description=(
        "Display nodes and edges on the Graph panel. "
        "Provide 'nodes' (list of {id, label}) and optional 'edges' (list of {source, target}). "
        "Set 'clear' to true to replace the existing graph."
    ),
    write_capable=False,
    requires_run_scope=False,
    requires_write_approval=False,
    execute_approval_required=False,
    allowed_paths=(),
    path_fields=(),
    max_input_size=65536,
    max_output_size=1_048_576,
    aliases=("update_graph", "show_graph"),
    output_target="graph",
    args_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["nodes"],
        "properties": {
            "nodes": {
                "type": "array",
                "minItems": 1,
                "maxItems": 500,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "label"],
                    "properties": {
                        "id": {"type": "string", "minLength": 1, "maxLength": 256},
                        "label": {"type": "string", "minLength": 1, "maxLength": 256},
                    },
                },
            },
            "edges": {
                "type": "array",
                "maxItems": 2000,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["source", "target"],
                    "properties": {
                        "source": {"type": "string", "minLength": 1, "maxLength": 256},
                        "target": {"type": "string", "minLength": 1, "maxLength": 256},
                    },
                },
            },
            "clear": {
                "type": "boolean",
                "description": "If true, clear existing graph before adding nodes/edges.",
            },
        },
    },
)


def execute_graph_update(args: dict, tool: ToolDefinition, project_root) -> dict:
    """
    Validate and pass through graph data. The actual rendering is handled
    by main_window after it receives the RouterResult.
    """
    nodes = args.get("nodes", [])
    edges = args.get("edges", [])
    clear = args.get("clear", False)

    _log.info("graph_update: %d nodes, %d edges, clear=%s", len(nodes), len(edges), clear)

    return {
        "nodes": nodes,
        "edges": edges,
        "clear": clear,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
