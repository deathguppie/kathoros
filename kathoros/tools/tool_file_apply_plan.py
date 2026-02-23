"""
file_apply_plan tool executor.
Write-capable — always requires approval (INV-15).
requires_run_scope=True — paths must be under artifacts/<run_id>/.
Executor must not contain approval logic (INV-15).
Executor must not call the router (INV-1).
All path checks use resolve()+is_relative_to() — never startswith() (INV-13).
"""
import base64
import hashlib
import logging
import shutil
from pathlib import Path

from kathoros.core.constants import ARTIFACTS_DIR
from kathoros.router.models import ToolDefinition

_log = logging.getLogger("kathoros.tools.file_apply_plan")

FILE_APPLY_PLAN_TOOL = ToolDefinition(
    name="file_apply_plan",
    description="Apply a deterministic plan of file operations to artifacts/<run_id>/.",
    write_capable=True,
    requires_run_scope=True,
    requires_write_approval=True,
    execute_approval_required=False,
    allowed_paths=("artifacts/",),
    path_fields=("operations",),
    max_input_size=524288,
    max_output_size=10_485_760,
    aliases=("apply_plan",),
    output_target="context",
    is_active=True,
    args_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["run_id", "operations"],
        "properties": {
            "run_id": {"type": "string", "minLength": 8, "maxLength": 64},
            "operations": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["op", "path"],
                    "properties": {
                        "op": {"type": "string", "enum": ["write", "delete", "mkdir"]},
                        "path": {"type": "string", "minLength": 1, "maxLength": 512},
                        "content": {"type": "string", "maxLength": 1048576},
                        "encoding": {"type": "string", "enum": ["utf-8", "binary-base64"]},
                        "expected_hash": {"type": "string", "minLength": 64, "maxLength": 64},
                    },
                },
            },
            "dry_run": {"type": "boolean"},
        },
    },
)


def execute_file_apply_plan(
    args: dict,
    tool: ToolDefinition,
    project_root: Path,
) -> dict:
    run_id: str = args["run_id"]
    dry_run: bool = args.get("dry_run", False)
    operations: list = args["operations"]

    root = project_root.resolve()
    run_scope = (project_root / ARTIFACTS_DIR / run_id).resolve()

    results = []
    ok = 0
    failed = 0

    for op in operations:
        op_type = op["op"]
        raw_path = op["path"]
        result = {"op": op_type, "path": raw_path, "status": "ok", "sha256": None, "error": None}

        try:
            resolved = (project_root / raw_path).resolve()

            # INV-13: resolve()+is_relative_to(), never startswith()
            if not resolved.is_relative_to(root):
                raise ValueError(f"traversal attempt blocked: {raw_path!r}")

            # Run-scope enforcement — must be under artifacts/<run_id>/
            if not resolved.is_relative_to(run_scope):
                raise ValueError(f"traversal attempt blocked: {raw_path!r} not under artifacts/{run_id}/")
            # Defensive: re-check against tool allowed_paths (belt-and-suspenders)
            allowed_roots = [root / p for p in tool.allowed_paths]
            if not any(resolved.is_relative_to(r) for r in allowed_roots):
                raise ValueError(f"traversal attempt blocked: {raw_path!r} outside allowed scope")

            if dry_run:
                result["status"] = "dry_run"
                ok += 1

            elif op_type == "write":
                content_str = op.get("content", "")
                encoding = op.get("encoding", "utf-8")

                if encoding == "binary-base64":
                    data = base64.b64decode(content_str)
                else:
                    data = content_str.encode("utf-8")

                resolved.parent.mkdir(parents=True, exist_ok=True)
                resolved.write_bytes(data)

                # Hash computed on actual bytes written
                digest = hashlib.sha256(data).hexdigest()
                result["sha256"] = digest
                _log.debug("wrote %s sha256=%s", raw_path, digest)

                expected = op.get("expected_hash")
                if expected and digest != expected:
                    result["status"] = "hash_mismatch"
                    result["error"] = f"expected {expected} got {digest}"
                    failed += 1
                else:
                    ok += 1

            elif op_type == "delete":
                if resolved.exists():
                    if resolved.is_dir():
                        raise ValueError(f"delete refused: {raw_path!r} is a directory")
                    resolved.unlink()
                    _log.debug("deleted %s", raw_path)
                else:
                    result["status"] = "skipped"
                ok += 1

            elif op_type == "mkdir":
                resolved.mkdir(parents=True, exist_ok=True)
                _log.debug("mkdir %s", raw_path)
                ok += 1

        except Exception as exc:
            result["status"] = "failed"
            result["error"] = str(exc)
            failed += 1

        results.append(result)

    return {
        "run_id": run_id,
        "dry_run": dry_run,
        "operations_total": len(operations),
        "operations_ok": ok,
        "operations_failed": failed,
        "results": results,
    }
