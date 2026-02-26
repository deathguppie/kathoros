# kathoros/router/models.py
"""
Data models for the ToolRouter layer.
All fields are immutable after construction (frozen dataclasses).
No business logic here — pure data containers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Optional

from kathoros.core.enums import AccessMode, Decision, TrustLevel


@dataclass(frozen=True)
class ToolDefinition:
    """
    Registry entry for a single tool.
    Immutable — loaded once at startup, never mutated at runtime.
    args_schema is stored as MappingProxyType so deep mutation is also blocked.
    """
    name: str
    description: str
    args_schema: MappingProxyType          # JSON Schema object (read-only view)
    write_capable: bool = False
    requires_run_scope: bool = False       # enforced only if write_capable=True
    requires_write_approval: bool = True
    execute_approval_required: bool = False
    allowed_paths: tuple[str, ...] = ()   # relative path prefixes (validated via Path)
    path_fields: tuple[str, ...] = ()     # arg keys that contain paths
    max_input_size: int = 1_048_576       # 1MB default
    max_output_size: int = 10_485_760     # 10MB default
    aliases: tuple[str, ...] = ()
    output_target: str = "context"

    def __post_init__(self) -> None:
        # Wrap args_schema in a read-only proxy if a plain dict was passed.
        # Uses object.__setattr__ because the dataclass is frozen.
        if isinstance(self.args_schema, dict):
            object.__setattr__(self, "args_schema", MappingProxyType(self.args_schema))


@dataclass(frozen=True)
class ToolRequest:
    """
    A validated-envelope request from an agent before router processing.
    Created by the envelope parser — not by agents directly.
    """
    request_id: str
    agent_id: str
    agent_name: str
    trust_level: TrustLevel
    access_mode: AccessMode
    tool_name: str
    args: dict
    nonce: str
    enveloped: bool
    detected_via: str                      # e.g. "json_envelope", "xml_tag", "regex"
    run_id: Optional[str] = None


@dataclass
class RouterResult:
    """
    Output of a single router pipeline run.
    Mutable during pipeline construction, then passed to logger.
    """
    request_id: str
    agent_id: str
    agent_name: str
    trust_level: str
    access_mode: str
    tool_name: str
    raw_args_hash: str                     # SHA256, always 64 chars
    nonce_valid: bool = False
    enveloped: bool = False
    detected_via: str = ""
    decision: Decision = Decision.REJECTED
    validation_ok: bool = False
    validation_errors: list[str] = field(default_factory=list)
    output_size: int = 0
    execution_ms: float = 0.0
    artifacts: list[str] = field(default_factory=list)
    session_id: Optional[str] = None
    decided_at: str = ""
    output: Optional[Any] = None
