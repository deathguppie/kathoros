# kathoros/router/logger.py
"""
Audit logger for all tool router decisions.
Logs every required field per LLM_IMPLEMENTATION_RULES §10.
Must NEVER log: raw args, API keys, secrets.
raw_args_hash must always be exactly 64 characters.
Append-only: one record per request, written after pipeline completes.
"""
from __future__ import annotations
import json
import logging
import time
from kathoros.router.models import RouterResult
from kathoros.core.constants import RAW_ARGS_HASH_LENGTH

# Module-level logger — output destination configured by app startup
_log = logging.getLogger("kathoros.router.audit")


# Required log fields — any missing field is a hard invariant violation
REQUIRED_FIELDS = frozenset([
    "request_id",
    "agent_id",
    "agent_name",
    "trust_level",
    "access_mode",
    "tool_name",
    "raw_args_hash",
    "nonce_valid",
    "enveloped",
    "detected_via",
    "decision",
    "validation_ok",
    "validation_errors",
    "output_size",
    "execution_ms",
    "artifacts",
])


def log_result(result: RouterResult) -> None:
    """
    Serialize RouterResult to audit log.
    Validates all required fields are present before writing.
    Raises AssertionError if any invariant is violated (fail loud, never silent).
    """
    # Invariant: hash must be exactly 64 chars
    assert len(result.raw_args_hash) == RAW_ARGS_HASH_LENGTH, (
        f"raw_args_hash length {len(result.raw_args_hash)} != {RAW_ARGS_HASH_LENGTH}"
    )

    record = {
        "request_id":        result.request_id,
        "agent_id":          result.agent_id,
        "agent_name":        result.agent_name,
        "trust_level":       result.trust_level,
        "access_mode":       result.access_mode,
        "tool_name":         result.tool_name,
        "raw_args_hash":     result.raw_args_hash,
        "nonce_valid":       result.nonce_valid,
        "enveloped":         result.enveloped,
        "detected_via":      result.detected_via,
        "decision":          result.decision.value if hasattr(result.decision, "value") else str(result.decision),
        "validation_ok":     result.validation_ok,
        "validation_errors": json.dumps(result.validation_errors),
        "output_size":       result.output_size,
        "execution_ms":      result.execution_ms,
        "artifacts":         json.dumps(result.artifacts),
    }

    # Invariant: all required fields must be present
    missing = REQUIRED_FIELDS - record.keys()
    assert not missing, f"Missing required log fields: {missing}"

    # Invariant: raw args must NOT be in record
    assert "args" not in record, "raw args must never be logged"
    assert "raw_args" not in record, "raw args must never be logged"

    _log.info(json.dumps(record))
