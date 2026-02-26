"""
ToolService — instantiates and manages the ToolRouter for a session.
Single entry point for tool execution from the UI layer.
Wires registry, executors, and approval callback together.
"""
import logging
import uuid
from pathlib import Path

from kathoros.core.enums import AccessMode, TrustLevel
from kathoros.router.models import RouterResult, ToolRequest
from kathoros.router.registry import ToolRegistry
from kathoros.router.router import ToolRouter
from kathoros.tools.tool_db_execute import DB_EXECUTE_TOOL, execute_db_execute
from kathoros.tools.tool_file_analyze import FILE_ANALYZE_TOOL, execute_file_analyze
from kathoros.tools.tool_file_apply_plan import FILE_APPLY_PLAN_TOOL, execute_file_apply_plan
from kathoros.tools.tool_graph_update import GRAPH_UPDATE_TOOL, execute_graph_update
from kathoros.tools.tool_matplot_render import MATPLOT_RENDER_TOOL, execute_matplot_render
from kathoros.tools.tool_object_create import OBJECT_CREATE_TOOL, execute_object_create
from kathoros.tools.tool_object_update import OBJECT_UPDATE_TOOL, execute_object_update
from kathoros.tools.tool_sagemath_eval import SAGEMATH_EVAL_TOOL, execute_sagemath_eval

_log = logging.getLogger("kathoros.services.tool_service")


def _build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(DB_EXECUTE_TOOL)
    registry.register(FILE_ANALYZE_TOOL)
    registry.register(FILE_APPLY_PLAN_TOOL)
    registry.register(GRAPH_UPDATE_TOOL)
    registry.register(MATPLOT_RENDER_TOOL)
    registry.register(OBJECT_CREATE_TOOL)
    registry.register(OBJECT_UPDATE_TOOL)
    registry.register(SAGEMATH_EVAL_TOOL)
    registry.build()
    return registry


class ToolService:
    def __init__(
        self,
        project_root: Path,
        session_nonce: str,
        session_id: str = "",
        access_mode: AccessMode = AccessMode.REQUEST_FIRST,
        approval_callback=None,
    ) -> None:
        self._registry = _build_registry()
        self._access_mode = access_mode
        self._router = ToolRouter(
            registry=self._registry,
            project_root=project_root,
            session_nonce=session_nonce,
            session_id=session_id,
            access_mode=access_mode,
            approval_callback=approval_callback,
            executors={
                "db_execute": execute_db_execute,
                "file_analyze": execute_file_analyze,
                "file_apply_plan": execute_file_apply_plan,
                "graph_update": execute_graph_update,
                "matplot_render": execute_matplot_render,
                "object_create": execute_object_create,
                "object_update": execute_object_update,
                "sagemath_eval": execute_sagemath_eval,
            },
        )
        _log.info("ToolService ready: project_root=%s", project_root)

    def handle(
        self,
        tool_name: str,
        args: dict,
        agent_id: str = "",
        agent_name: str = "",
        trust_level: TrustLevel = TrustLevel.MONITORED,
        nonce: str = "",
        detected_via: str = "none",
        enveloped: bool = False,
    ) -> RouterResult:
        request = ToolRequest(
            request_id=str(uuid.uuid4()),
            tool_name=tool_name,
            args=args,
            agent_id=agent_id,
            agent_name=agent_name,
            trust_level=trust_level,
            access_mode=self._access_mode,
            nonce=nonce,
            detected_via=detected_via,
            enveloped=enveloped,
        )
        return self._router.handle(request)

    def get_tool_descriptions(self) -> str:
        """Return tool descriptions with schemas for injection into agent system prompt."""
        blocks = []
        for tool in self._registry.all_tools():
            schema = dict(tool.args_schema)
            props = schema.get("properties", {})
            required = schema.get("required", [])
            # Build a compact parameter summary
            params = []
            for name, spec in props.items():
                req = " (required)" if name in required else ""
                params.append(f"    - {name}: {spec.get('type', '?')}{req}")
            block = f"### {tool.name}\n{tool.description}\nParameters:\n" + "\n".join(params)
            blocks.append(block)
        return "\n\n".join(blocks)
