"""
Static code hygiene checks for router/ and tools/.

These tests enforce INV-13 (path enforcement — resolve+relative_to only)
by scanning source files for prohibited patterns.

Rules:
  - startswith( must not appear in non-comment code in router/ or tools/
    UNLESS the line is annotated with `# nosec startswith`
  - The only approved use is run_id prefix matching in router.py step 7,
    which is explicitly annotated.
"""
from __future__ import annotations

import ast
import pathlib
import tokenize
import unittest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]  # kathoros_main/
_KATHOROS = _REPO_ROOT / "kathoros"
_SCAN_DIRS = [_KATHOROS / "router", _KATHOROS / "tools"]


def _source_lines(path: pathlib.Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


class TestNoStartswithInPathCode(unittest.TestCase):
    """
    Fail if `.startswith(` appears on an executable (non-comment) line
    in router/ or tools/ without the `# nosec startswith` annotation.

    Background: path containment MUST use resolve()+relative_to() per INV-13.
    startswith() on path strings is a known footgun — it silently fails on
    symlinks, case differences, and paths with trailing slashes.

    Approved exception: run_id prefix check in router.py step 7, annotated
    with `# nosec startswith` on the same line.
    """

    def _get_violations(self) -> list[tuple[pathlib.Path, int, str]]:
        violations = []
        for scan_dir in _SCAN_DIRS:
            if not scan_dir.exists():
                continue
            for py_file in sorted(scan_dir.rglob("*.py")):
                lines = _source_lines(py_file)
                for lineno, line in enumerate(lines, start=1):
                    stripped = line.strip()
                    # Skip pure comment lines
                    if stripped.startswith("#"):
                        continue
                    # Skip lines inside docstrings (heuristic: check for startswith in quotes)
                    # Full approach: check if the occurrence is in a string literal
                    # For robustness we use a token-level check below.
                    if "startswith(" not in line:
                        continue
                    # If the annotation is present on this line, it's approved
                    if "# nosec startswith" in line:
                        continue
                    # Check if startswith( is inside a string literal on this line
                    if _startswith_in_string_only(py_file, lineno, line):
                        continue
                    violations.append((py_file, lineno, line.rstrip()))
        return violations

    def test_no_unannotated_startswith(self):
        violations = self._get_violations()
        if violations:
            msg_parts = [
                f"{p.relative_to(_REPO_ROOT)}:{n}: {l}"
                for p, n, l in violations
            ]
            self.fail(
                "startswith( found in router/tools code without '# nosec startswith' annotation.\n"
                "Use resolve()+relative_to() for path containment (INV-13).\n"
                "If this is NOT a path check, add `# nosec startswith` to the line.\n\n"
                + "\n".join(msg_parts)
            )


def _startswith_in_string_only(path: pathlib.Path, lineno: int, line: str) -> bool:
    """
    Return True if all occurrences of 'startswith(' on this line
    are inside string literals (i.e., in a comment-string or docstring context).
    Uses a simple heuristic: check if the token at the startswith position is STRING.
    Falls back to False (conservative — flags the line) on parse errors.
    """
    # Simple heuristic: if the line contains 'startswith' only inside quotes
    # we check by looking at the content between quote characters.
    # A full AST walk is expensive; instead we check if the raw occurrence
    # is in a string by seeing if it's inside matching quotes.
    try:
        import re
        # Remove all string literals from the line and check if startswith remains
        cleaned = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '""', line)
        cleaned = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", "''", cleaned)
        cleaned = re.sub(r'""".*?"""', '""""""', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"'''.*?'''", "''''''", cleaned, flags=re.DOTALL)
        return "startswith(" not in cleaned
    except Exception:
        return False  # conservative: flag it


if __name__ == "__main__":
    unittest.main()
