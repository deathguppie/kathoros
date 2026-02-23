#!/usr/bin/env bash
# scripts/pre_commit.sh — run before any git commit
set -e

echo "==> Security scan (bandit)"
bandit -r kathoros/ -ll -q

echo "==> Code quality (ruff)"
ruff check kathoros/ tests/

echo "==> Dependency CVE check (pip-audit)"
pip-audit --quiet

echo "==> Smoke tests"
python -m unittest discover -s tests/smoke -p "test_*.py" -v

echo "==> All checks passed."
