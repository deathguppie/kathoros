#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/make_audit_bundle.sh run-YYYYMMDD-HHMM
#
# Output:
#   artifacts/<run_id>/audit_bundle/

RUN_ID="${1:-run-$(date +%Y%m%d-%H%M%S)}"
OUT_DIR="artifacts/${RUN_ID}/audit_bundle"

mkdir -p "${OUT_DIR}"

echo "[1/8] Repo identity..."
git rev-parse HEAD > "${OUT_DIR}/git_head.txt"
git status --porcelain > "${OUT_DIR}/git_status_porcelain.txt" || true
git log -n 50 --decorate --oneline > "${OUT_DIR}/git_log_50.txt"

echo "[2/8] Build files..."
cp -f pyproject.toml "${OUT_DIR}/" 2>/dev/null || true
cp -f requirements.txt "${OUT_DIR}/" 2>/dev/null || true
cp -f requirements-dev.txt "${OUT_DIR}/" 2>/dev/null || true
ls -la > "${OUT_DIR}/ls_root.txt"

echo "[3/8] Security + invariants docs..."
for f in INVARIANTS.md SECURITY_CONSTRAINTS.md LLM_IMPLEMENTATION_RULES.md FEATURE_UPDATES.md; do
  if [[ -f "$f" ]]; then cp -f "$f" "${OUT_DIR}/"; fi
done

echo "[4/8] Core source: router/db/tools/ui..."
mkdir -p "${OUT_DIR}/src"
# Copy only the areas relevant to the security boundary + execution paths.
rsync -a --prune-empty-dirs \
  --include='*/' \
  --include='kathoros/router/***' \
  --include='kathoros/tools/***' \
  --include='kathoros/db/***' \
  --include='kathoros/ui/***' \
  --include='kathoros/core/***' \
  --exclude='*' \
  . "${OUT_DIR}/src/"

echo "[5/8] Tests (structure + key files)..."
mkdir -p "${OUT_DIR}/tests"
rsync -a --prune-empty-dirs \
  --include='*/' \
  --include='kathoros/tests/***' \
  --exclude='*' \
  . "${OUT_DIR}/tests/"

echo "[6/8] Run tests and capture output (best effort)..."
# Don't fail the bundle if tests fail; we want the log.
{
  python -m pytest -q
} > "${OUT_DIR}/pytest_q.txt" 2>&1 || true

{
  python -m pytest -q --disable-warnings --durations=20
} > "${OUT_DIR}/pytest_durations.txt" 2>&1 || true

echo "[7/8] Include local audit artifacts if present..."
# Grab common audit evidence files without sweeping secrets.
for f in kathoros_audit_log.txt audit_evidence.txt kathoros_review.txt; do
  if [[ -f "$f" ]]; then cp -f "$f" "${OUT_DIR}/"; fi
done

echo "[8/8] Redaction guard (basic)..."
# Show (don’t copy) suspicious files so you can verify before sharing.
{
  echo "Potential secret-bearing files (NOT copied):"
  find . -maxdepth 3 -type f \( \
    -name ".env" -o -name "*.key" -o -name "*.pem" -o -name "*token*" -o -name "*secret*" \
  \) -print
} > "${OUT_DIR}/redaction_report.txt" 2>&1 || true

# Package it
tar -czf "artifacts/${RUN_ID}/audit_bundle.tar.gz" -C "artifacts/${RUN_ID}" "audit_bundle"

echo
echo "Audit bundle created:"
echo "  artifacts/${RUN_ID}/audit_bundle.tar.gz"
echo "  (and expanded at ${OUT_DIR})"
