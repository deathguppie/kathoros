# kathoros/agents/envelope.py
"""
PROXENOS_TOOL_REQUEST envelope format.

The envelope is the canonical, verifiable wrapper that agents use to
signal a tool invocation request. It carries the nonce, agent identity,
and the tool call payload in a tamper-evident structure.

Envelope format (JSON):
{
    "proxenos_tool_request": {
        "nonce":      "<session nonce>",
        "agent_id":   "<agent id>",
        "agent_name": "<agent name>",
        "run_id":     "<run id or null>",
        "tool":       "<tool name>",
        "args":       { ... }
    }
}

The envelope builder (this module) is used by agent stubs.
The envelope parser (parser.py) is used by the router pipeline.

Security notes:
- Nonce is set by the session, never by the agent.
- Agent identity fields come from the session registry, not from the envelope.
- The envelope is parsed but agent_id/agent_name are ALWAYS taken from the
  session's registered agent record, not from what the envelope claims.
  This prevents spoofing of agent identity via crafted envelopes.
"""
from __future__ import annotations

import json
from typing import Any, Optional

# The canonical envelope root key — exact string match required
ENVELOPE_KEY = "proxenos_tool_request"

# Required fields inside the envelope payload
REQUIRED_ENVELOPE_FIELDS = frozenset(["nonce", "agent_id", "agent_name", "tool", "args"])


def build_envelope(
    nonce: str,
    agent_id: str,
    agent_name: str,
    tool_name: str,
    args: dict,
    run_id: Optional[str] = None,
) -> str:
    """
    Build a JSON-encoded PROXENOS_TOOL_REQUEST envelope string.
    Used by agent stubs when constructing tool requests.
    Returns a compact JSON string.
    """
    payload: dict[str, Any] = {
        "nonce":      nonce,
        "agent_id":   agent_id,
        "agent_name": agent_name,
        "tool":       tool_name,
        "args":       args,
    }
    if run_id is not None:
        payload["run_id"] = run_id

    return json.dumps({ENVELOPE_KEY: payload}, separators=(",", ":"))


def parse_envelope(raw: str) -> Optional[dict]:
    """
    Attempt to parse a PROXENOS_TOOL_REQUEST envelope from a raw string.

    Returns the inner payload dict if valid, or None if not an envelope.
    Does NOT validate nonce or agent identity — that is the router's job.

    Rejects if:
    - Not valid JSON
    - Root key is not exactly ENVELOPE_KEY
    - Any required field is missing
    - args is not a dict
    """
    try:
        parsed = json.loads(raw.strip())
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(parsed, dict):
        return None

    payload = parsed.get(ENVELOPE_KEY)
    if payload is None or not isinstance(payload, dict):
        return None

    # All required fields must be present
    for field in REQUIRED_ENVELOPE_FIELDS:
        if field not in payload:
            return None

    # args must be a dict
    if not isinstance(payload["args"], dict):
        return None

    return payload


def is_envelope(raw: str) -> bool:
    """Quick check — returns True if raw looks like a valid envelope."""
    return parse_envelope(raw) is not None
