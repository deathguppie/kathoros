# kathoros/core/enums.py
"""
Canonical enums for the entire system.
All enum values must match SECURITY_CONSTRAINTS.md exactly.
"""
from enum import Enum, auto


class AccessMode(str, Enum):
    NO_ACCESS = "NO_ACCESS"
    REQUEST_FIRST = "REQUEST_FIRST"
    FULL_ACCESS = "FULL_ACCESS"


class TrustLevel(str, Enum):
    UNTRUSTED = "UNTRUSTED"
    MONITORED = "MONITORED"
    TRUSTED = "TRUSTED"


class Decision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


class ObjectStatus(str, Enum):
    PENDING = "pending"
    AUDITED = "audited"
    FLAGGED = "flagged"
    DISPUTED = "disputed"
    COMMITTED = "committed"


class ObjectType(str, Enum):
    CONCEPT = "concept"
    DEFINITION = "definition"
    DERIVATION = "derivation"
    PREDICTION = "prediction"
    EVIDENCE = "evidence"
    OPEN_QUESTION = "open_question"
    DATA = "data"


class AuditMode(str, Enum):
    CONCURRENT = "concurrent"
    LINEAR = "linear"


class AgentType(str, Enum):
    LOCAL = "local"
    API = "api"


class ExecutionType(str, Enum):
    BLOCKING = "blocking"
    NONBLOCKING = "nonblocking"


class OutputTarget(str, Enum):
    CONTEXT = "context"
    SAGEMATH = "sagemath"
    MATPLOTLIB = "matplotlib"
    SHELL = "shell"
    CONTENT_AREA = "content_area"
