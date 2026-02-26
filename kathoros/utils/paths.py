# kathoros/utils/paths.py
"""
Path enforcement utilities.
All path resolution must go through resolve_safe_path().
Never use startswith() for path containment checks.
"""
from pathlib import Path

from kathoros.core.exceptions import AbsolutePathError, TraversalError


def resolve_safe_path(
    raw_path: str,
    project_root: Path,
    allowed_roots: list[Path],
) -> Path:
    """
    Resolve and validate a path field from agent args.

    Pipeline (immutable order per LLM_IMPLEMENTATION_RULES §6):
    1. Reject absolute paths.
    2. Resolve with project_root / raw_path.
    3. Follow symlinks with .resolve().
    4. Confirm resolved is under project_root.
    5. Confirm resolved is under at least one allowed_root.

    Never uses startswith() — always uses Path.relative_to().

    Raises:
        AbsolutePathError: if raw_path is absolute (message contains "absolute")
        TraversalError: if resolved path escapes bounds (message contains "traversal")
    """
    if Path(raw_path).is_absolute():
        raise AbsolutePathError(raw_path)

    resolved = (project_root / raw_path).resolve()

    # Check project root containment
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError:
        raise TraversalError(raw_path)

    # Check allowed_roots containment
    in_allowed = any(
        _is_relative_to(resolved, root.resolve())
        for root in allowed_roots
    )
    if not in_allowed:
        raise TraversalError(raw_path)

    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    """Safe relative_to check — returns bool instead of raising."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
