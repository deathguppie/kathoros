#!/usr/bin/env python3
# scripts/setup_project_dir.py
"""
Create a new Kathoros project directory structure on disk.
Run once per new project. Safe to re-run (idempotent).
"""
from pathlib import Path
import sys


def create_project(base_path: Path, project_name: str) -> None:
    root = base_path / project_name
    dirs = [
        root / "repo",
        root / "docs",
        root / "artifacts" / "oversized",
        root / "manifests",
        root / "exports",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  created: {d}")

    print(f"\nProject '{project_name}' ready at: {root}")


if __name__ == "__main__":
    base = Path.home() / ".kathoros" / "projects"
    name = sys.argv[1] if len(sys.argv) > 1 else "default_project"
    create_project(base, name)
