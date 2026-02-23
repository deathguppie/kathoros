# kathoros/router/registry.py
"""
ToolRegistry — canonical store for all registered tools.
Lookup is exact-match and case-sensitive only.
Aliases are supported but resolve to the canonical ToolDefinition.
No fuzzy matching. No fallback. Unknown tool = hard error.
"""
from __future__ import annotations
from kathoros.router.models import ToolDefinition
from kathoros.core.exceptions import UnknownToolError


class ToolRegistry:
    """
    Immutable after build() is called.
    Thread-safe for reads (no mutation post-build).
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._aliases: dict[str, str] = {}   # alias -> canonical name
        self._locked = False

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool. Raises if registry is locked or name conflicts."""
        if self._locked:
            raise RuntimeError("ToolRegistry is locked — cannot register after build()")
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name!r}")
        self._tools[tool.name] = tool
        for alias in tool.aliases:
            if alias in self._aliases or alias in self._tools:
                raise ValueError(f"Alias conflict: {alias!r}")
            self._aliases[alias] = tool.name

    def build(self) -> None:
        """Lock the registry. Call once at startup after all tools registered."""
        self._locked = True

    def lookup(self, name: str) -> ToolDefinition:
        """
        Exact-match lookup. Alias allowed. Case-sensitive. No fuzzy match.
        Raises UnknownToolError (message contains 'unknown tool') if not found.
        """
        # Resolve alias first
        canonical = self._aliases.get(name, name)
        tool = self._tools.get(canonical)
        if tool is None:
            raise UnknownToolError(name)
        return tool

    def exists(self, name: str) -> bool:
        canonical = self._aliases.get(name, name)
        return canonical in self._tools

    def all_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())
