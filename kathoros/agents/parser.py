# kathoros/agents/parser.py
"""
EnvelopeParser — intercepts all agent output and detects tool requests.

Detection priority order (per project template Tool Parser spec):
  1. PROXENOS_TOOL_REQUEST JSON envelope  (detected_via = "json_envelope")
  2. Structured JSON  {"tool": "...", "args": {...}}  (detected_via = "json_struct")
  3. XML-style tags   <tool:name>...</tool:name>       (detected_via = "xml_tag")
  4. Markdown blocks  ```toolname\n...\n```            (detected_via = "markdown_block")
  5. No match → ParseResult with tool_request=None     (pass-through)

Security rules:
  - Parser NEVER executes anything. It only produces ParseResult objects.
  - All results are passed to the ToolRouter — the router decides execution.
  - Regex-triggered invocation (modes 2-4) is flagged as non-enveloped.
    The router will enforce envelope requirements based on trust level.
  - Parser does not validate nonce, schema, or paths — router does that.
  - Raw agent output is never stored — only the parsed structure + hash.
  - A unique request_id (UUID4) is assigned to every detected tool request.

Output:
  ParseResult — always returned, even on no-match. Callers check
  .tool_request to determine if a tool was detected.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Optional

from kathoros.agents.envelope import ENVELOPE_KEY, parse_envelope
from kathoros.core.enums import AccessMode, TrustLevel
from kathoros.router.models import ToolRequest

# ---------------------------------------------------------------------------
# Compiled regex patterns — compiled once at import time
# ---------------------------------------------------------------------------

# JSON struct: {"tool": "name", "args": {...}}  (top-level only)
# Only used to locate candidates — actual parsing done with balanced-brace walker
_RE_JSON_TOOL_KEY = re.compile(r'"tool"\s*:\s*"([^"]+)"')

# XML tag: <tool:toolname>content</tool:toolname>
_RE_XML_TAG = re.compile(
    r'<tool:([a-zA-Z0-9_\-]+)>(.*?)</tool:\1>',
    re.DOTALL,
)

# Markdown fenced block: ```toolname\ncontent\n```
_RE_MARKDOWN = re.compile(
    r'```([a-zA-Z0-9_\-]+)\n(.*?)```',
    re.DOTALL,
)

# Maximum raw text length the parser will scan (security: avoid ReDoS on huge inputs)
MAX_PARSE_INPUT_BYTES = 524_288  # 512KB

# Common code-block language tags that should NOT be treated as tool names.
# Prevents false positives when agents show code examples in markdown.
_CODE_LANG_BLOCKLIST = frozenset({
    "python", "py", "javascript", "js", "typescript", "ts", "java", "c",
    "cpp", "csharp", "cs", "go", "rust", "ruby", "php", "swift", "kotlin",
    "scala", "r", "sql", "bash", "sh", "zsh", "shell", "powershell",
    "html", "css", "xml", "yaml", "yml", "toml", "json", "markdown", "md",
    "text", "txt", "plaintext", "latex", "tex", "lua", "perl", "haskell",
    "elixir", "erlang", "clojure", "lisp", "scheme", "ocaml", "fsharp",
    "dart", "zig", "nim", "julia", "matlab", "sage", "diff", "dockerfile",
    "makefile", "cmake", "ini", "cfg", "conf", "csv", "log",
})


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ParseResult:
    """
    Output of a single parser run against one chunk of agent output.

    tool_request: populated if a tool was detected, else None.
    display_text: the agent output with the tool block stripped out,
                  ready for display. If no tool detected, equals input.
    detected_via: how the tool was found (or "none").
    raw_block:    the exact substring that was parsed as a tool call.
                  Never stored — only used for display/debugging in session.
    """
    tool_request: Optional[ToolRequest]
    display_text: str
    detected_via: str = "none"
    raw_block: str = ""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class EnvelopeParser:
    """
    Stateless parser. One instance per session; safe to reuse across calls.
    All session context (agent_id, trust_level, etc.) passed per-call.
    """

    def parse(
        self,
        raw_output: str,
        agent_id: str,
        agent_name: str,
        trust_level: TrustLevel,
        access_mode: AccessMode,
        session_nonce: str,
        run_id: Optional[str] = None,
    ) -> ParseResult:
        """
        Parse one chunk of agent output.

        Returns ParseResult. Never raises — parse failures return no-match.
        Agent identity (agent_id, agent_name) comes from the session registry,
        NOT from any envelope content, to prevent identity spoofing.
        """
        if not raw_output or not raw_output.strip():
            return ParseResult(tool_request=None, display_text=raw_output or "")

        # Enforce input size limit before scanning
        if len(raw_output.encode("utf-8")) > MAX_PARSE_INPUT_BYTES:
            return ParseResult(
                tool_request=None,
                display_text=raw_output,
                detected_via="none",
            )

        # Try each detection method in priority order
        for method in (
            self._try_json_envelope,
            self._try_json_struct,
            self._try_xml_tag,
            self._try_markdown_block,
        ):
            result = method(
                raw_output, agent_id, agent_name,
                trust_level, access_mode, session_nonce, run_id,
            )
            if result is not None:
                return result

        # No tool detected — pass through as display text
        return ParseResult(tool_request=None, display_text=raw_output)

    # ------------------------------------------------------------------
    # Detection methods
    # ------------------------------------------------------------------

    def _try_json_envelope(
        self, raw: str, agent_id: str, agent_name: str,
        trust_level: TrustLevel, access_mode: AccessMode,
        nonce: str, run_id: Optional[str],
    ) -> Optional[ParseResult]:
        """
        Priority 1: PROXENOS_TOOL_REQUEST envelope.
        Attempts to parse the entire output as a single JSON envelope.
        Also scans for an envelope embedded anywhere in the text.
        """
        # Try whole-string first (most common for well-behaved agents)
        payload = parse_envelope(raw.strip())

        # If not, scan for envelope embedded in larger text
        if payload is None:
            payload, raw_block = _extract_embedded_envelope(raw)
            if payload is None:
                return None
        else:
            raw_block = raw.strip()

        # Agent identity always from session, not envelope payload
        request = ToolRequest(
            request_id=str(uuid.uuid4()),
            agent_id=agent_id,          # from session registry
            agent_name=agent_name,      # from session registry
            trust_level=trust_level,
            access_mode=access_mode,
            tool_name=payload["tool"],
            args=payload["args"],
            nonce=payload.get("nonce", ""),   # router validates this
            enveloped=True,
            detected_via="json_envelope",
            run_id=payload.get("run_id", run_id),
        )
        display = raw.replace(raw_block, "").strip()
        return ParseResult(
            tool_request=request,
            display_text=display,
            detected_via="json_envelope",
            raw_block=raw_block,
        )

    def _try_json_struct(
        self, raw: str, agent_id: str, agent_name: str,
        trust_level: TrustLevel, access_mode: AccessMode,
        nonce: str, run_id: Optional[str],
    ) -> Optional[ParseResult]:
        """
        Priority 2: Structured JSON {"tool": "name", "args": {...}}.
        Uses balanced-brace extraction to handle nested JSON (arrays of objects, etc.).
        Not enveloped — router enforces envelope requirement by trust level.
        """
        match = _RE_JSON_TOOL_KEY.search(raw)
        if not match:
            return None

        # Walk backwards to find the opening brace of the enclosing object
        brace_start = raw.rfind("{", 0, match.start())
        if brace_start == -1:
            return None

        # Walk forward with balanced braces to find the complete JSON object
        raw_block = _extract_balanced_json(raw, brace_start)
        if raw_block is None:
            return None

        try:
            parsed = json.loads(raw_block)
        except json.JSONDecodeError:
            return None

        if not isinstance(parsed, dict):
            return None
        if "tool" not in parsed or "args" not in parsed:
            return None
        if not isinstance(parsed["args"], dict):
            return None

        request = ToolRequest(
            request_id=str(uuid.uuid4()),
            agent_id=agent_id,
            agent_name=agent_name,
            trust_level=trust_level,
            access_mode=access_mode,
            tool_name=parsed["tool"],
            args=parsed["args"],
            nonce=parsed.get("nonce", nonce),
            enveloped=False,
            detected_via="json_struct",
            run_id=run_id,
        )
        display = raw.replace(raw_block, "").strip()
        return ParseResult(
            tool_request=request,
            display_text=display,
            detected_via="json_struct",
            raw_block=raw_block,
        )

    def _try_xml_tag(
        self, raw: str, agent_id: str, agent_name: str,
        trust_level: TrustLevel, access_mode: AccessMode,
        nonce: str, run_id: Optional[str],
    ) -> Optional[ParseResult]:
        """
        Priority 3: XML-style <tool:name>content</tool:name>.
        Content is parsed as JSON args if possible, else wrapped as {"input": content}.
        Not enveloped.
        """
        match = _RE_XML_TAG.search(raw)
        if not match:
            return None

        tool_name = match.group(1)
        content = match.group(2).strip()
        args = _parse_args_from_content(content)

        raw_block = match.group(0)
        request = ToolRequest(
            request_id=str(uuid.uuid4()),
            agent_id=agent_id,
            agent_name=agent_name,
            trust_level=trust_level,
            access_mode=access_mode,
            tool_name=tool_name,
            args=args,
            nonce=nonce,
            enveloped=False,
            detected_via="xml_tag",
            run_id=run_id,
        )
        display = raw.replace(raw_block, "").strip()
        return ParseResult(
            tool_request=request,
            display_text=display,
            detected_via="xml_tag",
            raw_block=raw_block,
        )

    def _try_markdown_block(
        self, raw: str, agent_id: str, agent_name: str,
        trust_level: TrustLevel, access_mode: AccessMode,
        nonce: str, run_id: Optional[str],
    ) -> Optional[ParseResult]:
        """
        Priority 4: Markdown fenced block ```toolname\\ncontent```.
        Content parsed as JSON if possible, else {"input": content}.
        Not enveloped.
        """
        match = _RE_MARKDOWN.search(raw)
        if not match:
            return None

        tool_name = match.group(1)
        # Skip common programming language tags — not tool calls
        if tool_name.lower() in _CODE_LANG_BLOCKLIST:
            return None
        content = match.group(2).strip()
        args = _parse_args_from_content(content)

        raw_block = match.group(0)
        request = ToolRequest(
            request_id=str(uuid.uuid4()),
            agent_id=agent_id,
            agent_name=agent_name,
            trust_level=trust_level,
            access_mode=access_mode,
            tool_name=tool_name,
            args=args,
            nonce=nonce,
            enveloped=False,
            detected_via="markdown_block",
            run_id=run_id,
        )
        display = raw.replace(raw_block, "").strip()
        return ParseResult(
            tool_request=request,
            display_text=display,
            detected_via="markdown_block",
            raw_block=raw_block,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_balanced_json(text: str, start: int) -> Optional[str]:
    """
    Extract a balanced JSON object from text starting at position `start`.
    Handles nested braces, brackets, and quoted strings correctly.
    Returns the substring or None if no balanced object found.
    """
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            if in_string:
                escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{" or ch == "[":
            depth += 1
        elif ch == "}" or ch == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _parse_args_from_content(content: str) -> dict:
    """
    Try to parse content as a JSON object.
    If it fails or produces a non-dict, wrap it as {"input": content}.
    """
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return {"input": content}


def _extract_embedded_envelope(text: str) -> tuple[Optional[dict], str]:
    """
    Scan text for an embedded JSON envelope object.
    Returns (payload_dict, raw_block_string) or (None, "").

    Walks character by character to find balanced { } blocks that
    contain the envelope key. Avoids regex on potentially large inputs.
    """
    key = f'"{ENVELOPE_KEY}"'
    start = text.find(key)
    if start == -1:
        return None, ""

    # Find the opening brace before the key
    brace_start = text.rfind("{", 0, start)
    if brace_start == -1:
        return None, ""

    # Walk forward to find matching closing brace
    depth = 0
    in_string = False
    escape = False
    last_brace_pos = -1
    for i, ch in enumerate(text[brace_start:], start=brace_start):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            last_brace_pos = i
            if depth == 0:
                raw_block = text[brace_start:i + 1]
                payload = parse_envelope(raw_block)
                if payload is not None:
                    return payload, raw_block
                break

    # Repair: if braces didn't balance (agent truncated output), try appending missing '}'
    if depth > 0 and last_brace_pos > brace_start:
        repaired = text[brace_start:last_brace_pos + 1] + ("}" * depth)
        payload = parse_envelope(repaired)
        if payload is not None:
            return payload, text[brace_start:last_brace_pos + 1]

    return None, ""
