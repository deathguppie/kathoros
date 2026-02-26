#!/usr/bin/env python3
"""
kathoros_gen.py — Ollama-backed file generator for the Kathoros build workflow.

Usage:
    python kathoros_gen.py --spec specs/models.md --out models.py
    python kathoros_gen.py --spec specs/models.md --out models.py --model qwen2.5-coder:latest
    python kathoros_gen.py --spec specs/models.md --out models.py --dry-run

What it does:
    1. Reads a spec file (plain text or markdown).
    2. Sends it to Ollama as a system+user prompt.
    3. Strips markdown fences from the response.
    4. Writes the result to pending/<filename> (never overwrites without --force).
    5. Prints a summary. Does nothing else.

What it does NOT do:
    - No git operations.
    - No chaining or multi-file generation.
    - No writes outside the pending/ directory.
    - No auto-approval or auto-move to the real project tree.

Review all output in pending/ with Claude before moving files manually.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "qwen2.5-coder:latest"
OLLAMA_BASE_URL = "http://localhost:11434"
PENDING_DIR = Path("pending")
MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB hard cap on response

# ---------------------------------------------------------------------------
# Full invariant contract — embedded in system prompt so Qwen is primed
# against every rule before it sees the spec.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a senior Python engineer implementing Kathoros, a security-critical
local desktop research platform (PyQt6, SQLite, GPL-v3).

OUTPUT RULES:
- Output ONLY the requested source file. No explanation, no commentary, no preamble.
- Do not wrap output in markdown fences. Raw source code only.
- Every security-relevant decision must have an inline comment citing the
  invariant number, e.g.: # INV-13: resolve()+relative_to(), never startswith()
- When uncertain, choose the stricter behaviour and leave a TODO comment.

=== INVARIANT CONTRACT ===
The following invariants are non-negotiable. Violating any of them is a build
failure. Every file you produce will be reviewed against this list.

INV-1  Router is the only execution gateway.
       No tool invocation may execute unless it passes through the full router
       pipeline. No executor may bypass, short-circuit, or replace router checks.
       UI components may request approval but may not execute tools directly.

INV-2  NO_ACCESS is a hard stop.
       Reject immediately. Do not display schema/path/tool details.
       Log the attempt. Do not show an approval prompt.

INV-3  REQUEST_FIRST requires explicit approval per request.
       Write-capable tools still require approval. Session overrides must be
       explicit, logged, and time-bounded.

INV-4  FULL_ACCESS is still least-privilege.
       Non-write tools may auto-execute. Write-capable tools ALWAYS require
       approval. Run-scope enforcement ALWAYS applies.

INV-5  UNTRUSTED and MONITORED agents must use the envelope.
       Non-enveloped requests must be rejected with an error containing
       the word "envelope". TRUSTED agents may omit envelope but are still
       fully validated.

INV-6  Router pipeline order is immutable. Must execute in this exact order:
       1.  Access mode hard stop (NO_ACCESS)
       2.  Nonce validation
       3.  Tool lookup
       4.  Envelope enforcement
       5.  Schema validation
       6.  Input size enforcement
       7.  Path enforcement
       8.  Run-scope enforcement
       9.  Approval gate
       10. Execution via executor dispatch
       11. Output size enforcement
       12. Logging (always, even on rejection)

INV-7  Nonce mismatch: return exactly one error, do not reveal tool existence,
       schema errors, or path details. Error must include "Invalid nonce".
       Request must still be logged.

INV-8  Tool lookup: exact match by canonical name or alias. Case sensitive.
       Never fuzzy match. Unknown tool error must include "unknown tool".

INV-9  Schema validated BEFORE path checks. Must enforce: required, type,
       enum, minLength/maxLength, minimum/maximum, additionalProperties: false,
       max_depth, max_items, max_properties.
       Failure: decision=REJECTED, error must include "schema".

INV-10 Input size bounded. Serialized args must not exceed tool.max_input_size.
       Violation must reject the request.

INV-11 Output size bounded. If output exceeds tool.max_output_size:
       - Store full output to artifacts/oversized/<tool>_<request_id>.json
       - Return {"truncated": true, "artifact": "<path>"}
       - Log the artifact path.

INV-12 Absolute paths always rejected. Error must include "absolute".

INV-13 Path enforcement: resolve()+relative_to() ONLY. Never startswith().
       Steps: join under project_root -> resolve() -> relative_to(project_root)
       -> relative_to(allowed_paths) if defined.
       Must block: ../../ traversal, prefix bypass, symlink escape.
       Traversal error must include "traversal".

INV-14 Run-scope violations are hard rejects with no approval dialog.
       Requires: run_id present, run_id matches ^[a-zA-Z0-9_\\-]{8,64}$,
       at least one path under artifacts/<run_id>/.

INV-15 Approval is centralised in the router, never inside executor code.
       Required when: tool.write_capable==True OR execute_approval_required==True
       OR access_mode==REQUEST_FIRST.
       Missing callback: deny, error must include "denied".

INV-16 Every request produces a log entry (approved, pending, or rejected).

INV-17 Raw args must NEVER be logged. Log only:
       request_id, session_id, agent_id, agent_name, trust_level, access_mode,
       tool_name, raw_args_hash (SHA256 of sorted JSON — must be 64 hex chars),
       nonce_valid, enveloped, detected_via, decision, validation_ok,
       validation_errors (JSON array), output_size, execution_ms,
       artifacts (JSON array), decided_at.
       Never log: raw args, secrets, tokens, API keys.

INV-18 Router must never be a shell bridge. Must not import QTermWidget,
       call os.system, os.popen, subprocess.run/call/Popen, or execute
       arbitrary shell text from agent output.

INV-19 When uncertain: reject. Never guess user intent. Require approval
       rather than auto-execute.

INV-20 Any change that affects observable security behaviour must update
       INVARIANTS.md in the same commit and add/adjust tests.
=== END CONTRACT ===
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_spec(path: Path) -> str:
    if not path.exists():
        print(f"[ERROR] Spec file not found: {path}", file=sys.stderr)
        sys.exit(1)
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        print(f"[ERROR] Spec file is empty: {path}", file=sys.stderr)
        sys.exit(1)
    return text


def strip_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences if present."""
    pattern = re.compile(r"^```[a-zA-Z0-9_\-]*\n(.*?)```\s*$", re.DOTALL)
    match = pattern.match(text.strip())
    if match:
        return match.group(1)
    return text


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def call_ollama(model: str, spec_text: str, timeout: int) -> str:
    """
    Call Ollama /api/chat endpoint (non-streaming).
    Returns the assistant message content as a string.
    """
    payload = {
        "model": model,
        "prompt": f"{SYSTEM_PROMPT}\n\n{spec_text}",
        "stream": False,
    }

    data = json.dumps(payload).encode("utf-8")
    url = f"{OLLAMA_BASE_URL}/api/generate"

    print(f"[INFO] Sending request to Ollama ({model}) ...", flush=True)
    t0 = time.monotonic()

    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES)
    except urllib.error.URLError as exc:
        print(f"[ERROR] Could not reach Ollama at {url}: {exc}", file=sys.stderr)
        print("[INFO]  Is Ollama running? Try: ollama serve", file=sys.stderr)
        sys.exit(1)

    elapsed = time.monotonic() - t0
    print(f"[INFO] Response received in {elapsed:.1f}s")

    try:
        body = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Could not parse Ollama response as JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    # Ollama /api/chat non-streaming response shape:
    # { "message": { "role": "assistant", "content": "..." }, ... }
    try:
        content = body["response"]
    except (KeyError, TypeError):
        print("[ERROR] Unexpected Ollama response shape:", file=sys.stderr)
        print(json.dumps(body, indent=2)[:500], file=sys.stderr)
        sys.exit(1)

    return content


def write_pending(out_name: str, content: str, force: bool) -> Path:
    """Write content to pending/<out_name>. Refuses to overwrite unless --force."""
    PENDING_DIR.mkdir(exist_ok=True)
    dest = PENDING_DIR / out_name

    if dest.exists() and not force:
        print(
            f"[ERROR] {dest} already exists. Use --force to overwrite.",
            file=sys.stderr,
        )
        sys.exit(1)

    dest.write_text(content, encoding="utf-8")
    return dest


def print_summary(spec_path: Path, dest: Path, content: str, model: str) -> None:
    lines = content.count("\n") + 1
    size_kb = len(content.encode("utf-8")) / 1024
    digest = sha256_of(content)

    print()
    print("=" * 60)
    print("  Kathoros Gen — Output Summary")
    print("=" * 60)
    print(f"  Spec:      {spec_path}")
    print(f"  Model:     {model}")
    print(f"  Output:    {dest}")
    print(f"  Lines:     {lines}")
    print(f"  Size:      {size_kb:.1f} KB")
    print(f"  SHA256:    {digest[:16]}...{digest[-8:]}")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()
    print("  Next steps:")
    print(f"    1. Paste contents of {dest} to Claude for security review.")
    print("    2. Fix any flagged invariant violations.")
    print("    3. Only after Claude approval: move file to the real project tree.")
    print("    4. Do NOT commit until Claude signs off.")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a single Kathoros source file via Ollama."
    )
    parser.add_argument(
        "--spec",
        required=True,
        type=Path,
        help="Path to the spec file (markdown or plain text).",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=str,
        help="Output filename (written to pending/<out>).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Ollama model to use (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Request timeout in seconds (default: 300).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing file in pending/ if it exists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the system prompt and spec, then exit without calling Ollama.",
    )

    args = parser.parse_args()

    # Validate output filename — no path separators allowed
    if os.sep in args.out or (os.altsep and os.altsep in args.out):
        print(
            f"[ERROR] --out must be a plain filename, not a path. Got: {args.out}",
            file=sys.stderr,
        )
        sys.exit(1)

    spec_text = read_spec(args.spec)

    if args.dry_run:
        print("[DRY RUN] System prompt:")
        print("-" * 40)
        print(SYSTEM_PROMPT)
        print("-" * 40)
        print("[DRY RUN] Spec content:")
        print("-" * 40)
        print(spec_text)
        print("-" * 40)
        print(f"[DRY RUN] Would write to: {PENDING_DIR / args.out}")
        sys.exit(0)

    raw_response = call_ollama(args.model, spec_text, args.timeout)
    clean_content = strip_fences(raw_response)

    dest = write_pending(args.out, clean_content, args.force)
    print_summary(args.spec, dest, clean_content, args.model)


if __name__ == "__main__":
    main()
