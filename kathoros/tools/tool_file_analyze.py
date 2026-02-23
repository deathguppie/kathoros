"""
file_analyze tool executor.
Read-only — no writes, no approval needed, no run_id needed.
Executor must not contain approval logic (INV-15).
Executor must not call the router (INV-1).
"""
from pathlib import Path
from kathoros.router.models import ToolDefinition
from kathoros.utils.paths import resolve_safe_path
from kathoros.core.exceptions import AbsolutePathError, TraversalError
import hashlib
import json
import mimetypes
import logging
from datetime import datetime

FILE_ANALYZE_TOOL = ToolDefinition(
    name="file_analyze",
    description="Read files in staging/ or docs/ and return metadata + suggestions.",
    write_capable=False,
    requires_run_scope=False,
    requires_write_approval=False,
    execute_approval_required=False,
    allowed_paths=("staging/", "docs/"),
    path_fields=("targets",),
    max_input_size=65536,
    max_output_size=10_485_760,
    aliases=("analyze_file", "file_meta"),
    output_target="context",
    args_schema={
        "type": "object",
        "additionalProperties": False,
        "required": ["targets"],
        "properties": {
            "targets": {
                "type": "array",
                "minItems": 1,
                "maxItems": 200,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["path"],
                    "properties": {
                        "path": {"type": "string", "minLength": 1, "maxLength": 512},
                        "hint": {"type": "string", "maxLength": 256}
                    }
                }
            },
            "analysis_mode": {
                "type": "string",
                "enum": ["metadata_only", "light_summary", "deep_summary"]
            },
            "max_bytes_per_file": {
                "type": "integer",
                "minimum": 1024,
                "maximum": 10485760
            },
            "include_hashes": {"type": "boolean"},
            "extract": {
                "type": "array",
                "maxItems": 20,
                "items": {
                    "type": "string",
                    "enum": [
                        "sha256", "mime_type", "size_bytes", "page_count",
                        "title_guess", "author_guess", "created_guess",
                        "keywords_guess", "language_guess", "sections_outline",
                        "citations_guess"
                    ]
                }
            }
        }
    }
)

def execute_file_analyze(
    args: dict,
    tool: ToolDefinition,
    project_root: Path,
) -> dict:

    results = []
    for target in args["targets"]:
        try:
            raw = target["path"]
            # Use shared utility — single enforcement policy (INV-13, INV-1)
            allowed_roots = [project_root / p for p in tool.allowed_paths]
            file_path = resolve_safe_path(raw, project_root, allowed_roots)
        except (AbsolutePathError, TraversalError, ValueError) as e:
            results.append({"path": target["path"], "exists": False,
                            "size_bytes": 0, "error": str(e)})
            continue

        if not file_path.exists():
            results.append({"path": target["path"], "exists": False, "size_bytes": 0})
            continue

        metadata = {
            "path": target["path"],
            "exists": True,
            "size_bytes": file_path.stat().st_size
        }

        if "sha256" in args.get("extract", []):
            with open(file_path, "rb") as f:
                sha256_hash = hashlib.sha256(f.read()).hexdigest()
                metadata["sha256"] = sha256_hash

        if "mime_type" in args.get("extract", []):
            mime_type, _ = mimetypes.guess_type(file_path)
            metadata["mime_type"] = mime_type or "application/octet-stream"

        analysis_mode = args.get("analysis_mode", "metadata_only")
        max_bytes = args.get("max_bytes_per_file", 1_048_576)
        if analysis_mode != "metadata_only":
            preview_len = 500 if analysis_mode == "light_summary" else 2000
            try:
                raw_bytes = file_path.read_bytes()[:max_bytes]
                try:
                    preview = raw_bytes.decode("utf-8", errors="strict")[:preview_len]
                except UnicodeDecodeError:
                    preview = "<binary file>"
                metadata["preview"] = preview
            except OSError as e:
                metadata["preview_error"] = str(e)

        results.append(metadata)

    return {
        "results": results,
        "total_files": len(results),
        "errors": sum(1 for result in results if result.get("error") is not None)
    }
