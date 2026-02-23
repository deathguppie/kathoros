# kathoros/core/exceptions.py
"""
All custom exceptions for Kathoros.
Granular exception types allow precise error handling and logging.
"""


class KathorosError(Exception):
    """Base exception for all Kathoros errors."""


# --- Router / Security ---

class RouterError(KathorosError):
    """Base for all router-layer errors."""


class NonceError(RouterError):
    """Nonce validation failed. Must contain 'Invalid nonce' in message."""
    def __init__(self, msg="Invalid nonce"):
        super().__init__(msg)


class UnknownToolError(RouterError):
    """Tool not found in registry. Must contain 'unknown tool' in message."""
    def __init__(self, tool_name: str):
        super().__init__(f"unknown tool: {tool_name!r}")


class EnvelopeError(RouterError):
    """Request not properly enveloped. Must contain 'envelope' in message."""
    def __init__(self, msg="envelope required for this trust level"):
        super().__init__(msg)


class SchemaError(RouterError):
    """Schema validation failed. Must contain 'schema' in message."""
    def __init__(self, msg="schema validation failed"):
        super().__init__(f"schema error: {msg}")


class PathError(RouterError):
    """Path constraint violated."""


class AbsolutePathError(PathError):
    """Absolute path rejected. Must contain 'absolute' in message."""
    def __init__(self, path: str):
        super().__init__(f"absolute path rejected: {path!r}")


class TraversalError(PathError):
    """Path traversal attempt. Must contain 'traversal' in message."""
    def __init__(self, path: str):
        super().__init__(f"traversal attempt blocked: {path!r}")


class RunScopeError(RouterError):
    """Run-scope enforcement failed."""


class ApprovalDeniedError(RouterError):
    """Approval denied or callback missing. Must contain 'denied' in message."""
    def __init__(self, msg="denied: no approval callback registered"):
        super().__init__(msg)


class AccessModeError(RouterError):
    """Tool access rejected due to access mode."""


class InputSizeError(RouterError):
    """Input exceeds allowed size limit."""


class OutputSizeError(RouterError):
    """Output exceeds tool max_output_size — artifact stored."""


# --- DB ---

class DatabaseError(KathorosError):
    """Base for database errors."""


# --- Agent ---

class AgentError(KathorosError):
    """Base for agent/Proxenos errors."""


# --- Config ---

class ConfigError(KathorosError):
    """Configuration error."""
