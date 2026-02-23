"""
ToolService — instantiates and manages the ToolRouter for a session.
Single entry point for tool execution from the UI layer.
Wires registry, executors, and approval callback together.
"""
import logging
import uuid
from pathlib import Path
from kathoros.router.registry import ToolRegistry
from kathoros.router.router import ToolRouter
from kathoros.router.models import ToolRequest, RouterResult
from kathoros.core.enums import AccessMode, TrustLevel
from kathoros.tools.tool_file_analyze import FILE_ANALYZE_TOOL, execute_file_analyze

_log = logging.getLogger("kathoros.services.tool_service")


def _build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(FILE_ANALYZE_TOOL)
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
            executors={"file_analyze": execute_file_analyze},
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
        """Return tool descriptions for injection into agent system prompt."""
        lines = ["Available tools:"]
        for tool in self._registry.all_tools():
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines)
