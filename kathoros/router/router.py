# kathoros/router/router.py
"""
ToolRouter — the ONLY security boundary for all tool invocations.

Pipeline (immutable order per LLM_IMPLEMENTATION_RULES §2):
  1.  Nonce check          — hard stop on failure, no info leakage
  2.  Tool existence check — exact match only
  3.  Envelope enforcement — required for UNTRUSTED/MONITORED
  4.  Schema validation    — full JSON Schema + caps
  5.  Input size limit     — reject oversized args before processing
  6.  Path enforcement     — resolve + relative_to, never startswith
  7.  Run-scope enforcement — write+scoped tools must have valid run_id
  8.  Approval gate        — write or approval-required tools need callback
  9.  Execution            — call executor, time it
  10. Output size limit    — store oversized output as artifact
  11. Logging              — always last, always runs

This module must NOT:
  - import QTermWidget
  - call os.system / subprocess.*
  - execute arbitrary shell
  - contain approval logic in executors
  - reorder pipeline steps
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from kathoros.core.constants import (
    ARTIFACTS_DIR,
    OVERSIZED_DIR,
    RUN_ID_PATTERN,
    RAW_ARGS_HASH_LENGTH,
)
from kathoros.core.enums import AccessMode, Decision, TrustLevel
from kathoros.core.exceptions import (
    AbsolutePathError,
    ApprovalDeniedError,
    EnvelopeError,
    NonceError,
    RunScopeError,
    SchemaError,
    TraversalError,
    UnknownToolError,
)
from kathoros.router.logger import log_result
from kathoros.router.models import RouterResult, ToolDefinition, ToolRequest
from kathoros.router.registry import ToolRegistry
from kathoros.router.validator import validate_args
from kathoros.utils.hashing import hash_args
from kathoros.utils.paths import resolve_safe_path

# Type alias for approval callback
ApprovalCallback = Callable[[ToolRequest, ToolDefinition], bool]
# Type alias for executor
ExecutorFn = Callable[[dict, ToolDefinition, Path], Any]

_RUN_ID_RE = re.compile(RUN_ID_PATTERN)


class ToolRouter:
    """
    Security boundary for all tool execution.
    Instantiated once per session.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        project_root: Path,
        session_nonce: str,
        session_id: Optional[str] = None,
        access_mode: AccessMode = AccessMode.REQUEST_FIRST,
        approval_callback: Optional[ApprovalCallback] = None,
        executors: Optional[dict[str, ExecutorFn]] = None,
    ) -> None:
        self._registry = registry
        self._project_root = project_root.resolve()
        self._session_nonce = session_nonce
        self._session_id = session_id
        self._access_mode = access_mode
        self._approval_callback = approval_callback
        self._executors: dict[str, ExecutorFn] = executors or {}

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def handle(self, request: ToolRequest) -> RouterResult:
        """
        Run the 11-step pipeline for a single tool request.
        Always returns a RouterResult. Always logs (step 11).
        Never raises — all exceptions are caught and recorded.
        """
        result = RouterResult(
            request_id=request.request_id,
            session_id=self._session_id,
            agent_id=request.agent_id,
            agent_name=request.agent_name,
            trust_level=str(request.trust_level),
            access_mode=str(request.access_mode),
            tool_name=request.tool_name,
            raw_args_hash=hash_args(request.args),
            enveloped=request.enveloped,
            detected_via=request.detected_via,
        )

        t_start = time.monotonic()

        try:
            # ── Step 1: Nonce check ─────────────────────────────────────
            if self._access_mode == AccessMode.NO_ACCESS:
                result.decision = Decision.REJECTED
                result.validation_errors = ["Tool access disabled"]
                raise AccessModeRejected("Tool access disabled")
            self._step_nonce(request, result)

            # ── Step 2: Tool existence ──────────────────────────────────
            tool = self._step_tool_lookup(request, result)

            # ── Step 3: Envelope enforcement ────────────────────────────
            self._step_envelope(request, tool, result)

            # ── Step 4: Schema validation ───────────────────────────────
            self._step_schema(request, tool, result)

            # ── Step 5: Input size limit ────────────────────────────────
            self._step_input_size(request, tool, result)

            # ── Step 6: Path enforcement ────────────────────────────────
            self._step_paths(request, tool, result)

            # ── Step 7: Run-scope enforcement ───────────────────────────
            self._step_run_scope(request, tool, result)

            # ── Step 8: Approval gate ───────────────────────────────────
            self._step_approval(request, tool, result)

            # ── Step 9: Execution ───────────────────────────────────────
            output = self._step_execute(request, tool, result)

            # ── Step 10: Output size limit ──────────────────────────────
            self._step_output_size(output, request, tool, result)

        except Exception as exc:
            # Any unhandled exception = reject + record error
            if not result.validation_errors:
                result.validation_errors.append(str(exc))
            result.decision = Decision.REJECTED
            result.validation_ok = False

        finally:
            # ── Step 11: Logging — always runs ─────────────────────────
            result.execution_ms = (time.monotonic() - t_start) * 1000
            from datetime import datetime, timezone
            result.decided_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            log_result(result)

        return result

    # ------------------------------------------------------------------
    # Pipeline steps (private — call only from handle())
    # ------------------------------------------------------------------

    def _step_nonce(self, req: ToolRequest, result: RouterResult) -> None:
        """
        Step 1: Nonce check.
        Hard stop on failure. Reveals nothing beyond "Invalid nonce".
        Exactly one validation error on failure.
        """
        result.nonce_valid = (req.nonce == self._session_nonce)
        if not result.nonce_valid:
            result.decision = Decision.REJECTED
            result.validation_ok = False
            result.validation_errors = ["Invalid nonce"]
            raise NonceError()

    def _step_tool_lookup(
        self, req: ToolRequest, result: RouterResult
    ) -> ToolDefinition:
        """
        Step 2: Tool existence check.
        Exact match only. Case sensitive. No fuzzy.
        Error contains "unknown tool".
        """
      
        if self._access_mode == AccessMode.NO_ACCESS:
            result.decision = Decision.REJECTED
            result.validation_ok = False
            result.validation_errors = ["Tool access disabled"]
            raise AccessModeRejected("Tool access disabled")

        try:
            tool = self._registry.lookup(req.tool_name)
        except UnknownToolError as exc:
            result.decision = Decision.REJECTED
            result.validation_ok = False
            result.validation_errors = [str(exc)]
            raise

        return tool

    def _step_envelope(
        self, req: ToolRequest, tool: ToolDefinition, result: RouterResult
    ) -> None:
        """
        Step 3: Envelope enforcement.
        UNTRUSTED and MONITORED must use PROXENOS_TOOL_REQUEST envelope.
        Error contains "envelope".
        """
        requires_envelope = req.trust_level in (
            TrustLevel.UNTRUSTED, TrustLevel.MONITORED
        )
        if requires_envelope and not req.enveloped:
            result.decision = Decision.REJECTED
            result.validation_ok = False
            result.validation_errors = [
                "envelope required: UNTRUSTED/MONITORED agents must use "
                "PROXENOS_TOOL_REQUEST envelope"
            ]
            raise EnvelopeError()

    def _step_schema(
        self, req: ToolRequest, tool: ToolDefinition, result: RouterResult
    ) -> None:
        """
        Step 4: Schema validation.
        Full JSON Schema + depth/items/properties caps.
        All errors contain "schema".
        """
        try:
            errors = validate_args(req.args, tool.args_schema)
        except SchemaError as exc:
            result.decision = Decision.REJECTED
            result.validation_ok = False
            result.validation_errors = [str(exc)]
            raise

        if errors:
            result.decision = Decision.REJECTED
            result.validation_ok = False
            result.validation_errors = errors
            raise SchemaError("; ".join(errors))

    def _step_input_size(
        self, req: ToolRequest, tool: ToolDefinition, result: RouterResult
    ) -> None:
        """Step 5: Input size limit."""
        serialized = json.dumps(req.args, separators=(",", ":"))
        size = len(serialized.encode("utf-8"))
        if size > tool.max_input_size:
            msg = f"input size error: input size {size} exceeds limit {tool.max_input_size}"
            result.decision = Decision.REJECTED
            result.validation_ok = False
            result.validation_errors = [msg]
            raise ValueError(msg)

    def _step_paths(
        self, req: ToolRequest, tool: ToolDefinition, result: RouterResult
    ) -> None:
        """
        Step 6: Path enforcement.
        Every declared path field validated via resolve_safe_path().
        Never startswith(). Errors contain "absolute" or "traversal".
        """
        if not tool.path_fields:
            return

        allowed_roots = [
            self._project_root / p for p in tool.allowed_paths
        ]

        for field_name in tool.path_fields:
            raw = req.args.get(field_name)
            if raw is None:
                continue
            # Handle both string and list-of-dict cases
            paths_to_check = _extract_paths(raw, field_name)
            for raw_path in paths_to_check:
                try:
                    resolve_safe_path(raw_path, self._project_root, allowed_roots)
                except (AbsolutePathError, TraversalError) as exc:
                    result.decision = Decision.REJECTED
                    result.validation_ok = False
                    result.validation_errors = [str(exc)]
                    raise

    def _step_run_scope(
        self, req: ToolRequest, tool: ToolDefinition, result: RouterResult
    ) -> None:
        """
        Step 7: Run-scope enforcement.
        Only applies if tool.write_capable AND tool.requires_run_scope.
        Hard reject — no approval dialog.
        """
        if not (tool.write_capable and tool.requires_run_scope):
            return

        run_id = req.run_id
        if not run_id:
            msg = "run_id required for run-scoped write tool"
            result.decision = Decision.REJECTED
            result.validation_ok = False
            result.validation_errors = [msg]
            raise RunScopeError(msg)

        if not _RUN_ID_RE.match(run_id):
            msg = f"run_id format invalid: {run_id!r}"
            result.decision = Decision.REJECTED
            result.validation_ok = False
            result.validation_errors = [msg]
            raise RunScopeError(msg)

        # At least one path must be under artifacts/<run_id>/
        required_prefix = f"{ARTIFACTS_DIR}/{run_id}/"
        all_paths = _collect_all_paths(req.args, tool.path_fields)
        if not any(p.startswith(required_prefix) for p in all_paths):  # nosec startswith
            # NOTE: startswith used here for run_id prefix check only,
            # not for security containment (that's done in step 6 via resolve_safe_path).
            msg = f"run-scoped tool: at least one path must be under {ARTIFACTS_DIR}/{run_id}/"
            result.decision = Decision.REJECTED
            result.validation_ok = False
            result.validation_errors = [msg]
            raise RunScopeError(msg)

    def _step_approval(
        self, req: ToolRequest, tool: ToolDefinition, result: RouterResult
    ) -> None:
        """
        Step 8: Approval gate.
        Required if write_capable OR execute_approval_required.
        REQUEST_FIRST mode always requires approval.
        If no callback: deny. Error contains "denied".
        Approval logic NEVER in executor.
        """
        needs_approval = (
            tool.write_capable
            or tool.execute_approval_required
            or self._access_mode == AccessMode.REQUEST_FIRST
        )

        if not needs_approval:
            return

        if self._approval_callback is None:
            msg = "denied: no approval callback registered"
            result.decision = Decision.REJECTED
            result.validation_ok = False
            result.validation_errors = [msg]
            raise ApprovalDeniedError(msg)

        approved = self._approval_callback(req, tool)
        if not approved:
            msg = "denied: researcher rejected tool request"
            result.decision = Decision.REJECTED
            result.validation_ok = False
            result.validation_errors = [msg]
            raise ApprovalDeniedError(msg)

    def _step_execute(
        self, req: ToolRequest, tool: ToolDefinition, result: RouterResult
    ) -> Any:
        """
        Step 9: Execution.
        Calls registered executor. Records decision=APPROVED on success.
        Executor must not contain approval logic.
        """
        executor = self._executors.get(tool.name)
        if executor is None:
            raise RuntimeError(f"No executor registered for tool: {tool.name!r}")

        output = executor(req.args, tool, self._project_root)
        result.decision = Decision.APPROVED
        result.validation_ok = True
        return output

    def _step_output_size(
        self,
        output: Any,
        req: ToolRequest,
        tool: ToolDefinition,
        result: RouterResult,
    ) -> None:
        """
        Step 10: Output size limit.
        If oversized, store artifact and return truncated sentinel.
        Artifact must be inside project root.
        """
        try:
            serialized = json.dumps(output, separators=(",", ":"))
        except (TypeError, ValueError):
            serialized = str(output)

        size = len(serialized.encode("utf-8"))
        result.output_size = size

        if size <= tool.max_output_size:
            result.output = output
            return

        # Store oversized output as artifact
        artifact_dir = self._project_root / OVERSIZED_DIR
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_name = f"{tool.name}_{req.request_id}.json"
        artifact_path = artifact_dir / artifact_name

        # Verify artifact stays inside project root
        try:
            artifact_path.resolve().relative_to(self._project_root)
        except ValueError:
            raise RuntimeError("Oversized artifact path escaped project root")

        artifact_path.write_text(serialized, encoding="utf-8")
        rel_path = str(artifact_path.relative_to(self._project_root))
        result.artifacts.append(rel_path)
        result.output = {"truncated": True, "artifact": rel_path}


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _extract_paths(value: Any, field_name: str) -> list[str]:
    """Extract path strings from a field value (string or list-of-dicts)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        paths = []
        for item in value:
            if isinstance(item, str):
                paths.append(item)
            elif isinstance(item, dict) and "path" in item:
                paths.append(item["path"])
        return paths
    return []


def _collect_all_paths(args: dict, path_fields: tuple[str, ...]) -> list[str]:
    """Collect all raw path strings from declared path fields."""
    paths = []
    for field_name in path_fields:
        val = args.get(field_name)
        if val is not None:
            paths.extend(_extract_paths(val, field_name))
    return paths


class AccessModeRejected(Exception):
    """Internal: raised when NO_ACCESS blocks a request."""
