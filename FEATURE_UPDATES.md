# Kathoros — Feature Updates
Purpose: Lightweight, human-readable changelog for architectural and UX decisions.
Rule: If a change affects security behavior or invariants, update INVARIANTS.md in the same commit.

---

## Template

### YYYY-MM-DD — <Title>
**Type:** feature | refactor | security | bugfix | docs
**Scope:** UI | router | registry | db | agents | tools | docs | epistemic
**Status:** proposed | implemented | deprecated

### Summary
- <1–3 bullets, plain language>

### Motivation
- <why this change exists>

### Behavioral changes
- Before: <what user/agent could do>
- After: <what user/agent can do now>

### Security / invariants impact
- Affects invariants: INV-<x>, INV-<y> (or "none")
- New constraints: <if any>
- New tests: <test names or description>

### Migration / compatibility
- DB migration: yes/no (if yes, which version bump)
- Backward compatibility: preserved/broken

### Notes
- <anything you want future-you to remember>

---

## 2026-02-20 — ToolRouter 11-step pipeline (initial build)
**Type:** feature
**Scope:** router
**Status:** implemented

### Summary
- Implemented ToolRouter as the sole security boundary for all tool execution.
- 11-step pipeline: nonce, tool lookup, envelope, schema, input size, path, run-scope, approval, execute, output size, logging.
- ToolRegistry with exact-match, case-sensitive lookup and post-build locking.

### Motivation
- Security-first tool execution: agent output is untrusted until router validates it.

### Security / invariants impact
- Establishes INV-1 through INV-19.
- New tests: 56 tests (test_router.py, test_registry.py, test_validator.py)

### Migration / compatibility
- DB migration: no
- Backward compatibility: n/a (initial build)

---

## 2026-02-20 — Database layer (global.db + project.db migrations)
**Type:** feature
**Scope:** db
**Status:** implemented

### Summary
- Migration system with append-only versioned statement lists.
- global.db: agents, audit_templates, tools, global_settings, trust_overrides.
- project.db: projects, sessions, objects, cross_references, interactions, audit sessions, tool_audit_log, FTS5.
- Seeded 5 system audit templates and 8 default security settings.

### Security / invariants impact
- Cross-project DB always opens read-only (PRAGMA query_only = ON). INV-7 from project template.
- Snapshot size capped at 1MB before write.
- tool_audit_log enforces no raw args via assertion guard.

### Migration / compatibility
- DB migration: project.db v1, global.db v3
- Backward compatibility: n/a (initial build)

### Notes
- global.db and project.db must use separate connections — they share user_version PRAGMA.

---

## 2026-02-20 — Envelope parser (EnvelopeParser, 4-mode detection)
**Type:** feature
**Scope:** agents
**Status:** implemented

### Summary
- EnvelopeParser intercepts all agent output, detects tool requests in priority order.
- Priority: JSON envelope → JSON struct → XML tag → Markdown block → pass-through.
- Parser never executes — only produces ToolRequest objects for the router.

### Behavioral changes
- Before: no agent output interception.
- After: all agent output scanned; tool requests extracted and passed to router.

### Security / invariants impact
- Affects: INV-5 (envelope enforcement)
- Agent identity always taken from session registry, never from envelope payload (spoof prevention).
- Non-envelope detections set enveloped=False; router enforces UNTRUSTED/MONITORED must use envelope.
- New tests: 41 tests (test_envelope.py, test_parser.py)

### Migration / compatibility
- DB migration: no
- Backward compatibility: n/a (initial build)

---

## 2026-02-20 — Bug fixes + pipeline correction + epistemic integrity
**Type:** security + feature
**Scope:** router, db, epistemic, agents
**Status:** implemented

### Summary
- Fixed 6 bugs identified in review against INVARIANTS.md and SECURITY_CONSTRAINTS.md.
- Added epistemic graph integrity checker (6 checks, v0).
- project.db v2 migration adds epistemic fields to objects table.

### Bug fixes

**BUG-1: Pipeline order violation (critical)**
- Before: NO_ACCESS check was inside _step_tool_lookup (step 2); nonce checked first.
- After: _step_access_mode() is step 1, nonce is step 2. Matches INV-6 exactly.
- Affects: INV-6

**BUG-2: session_id + decided_at missing from log (critical)**
- Before: INV-17 required both; neither existed in RouterResult, logger, or DB.
- After: Both added to RouterResult, REQUIRED_FIELDS, log record, tool_audit_log schema.
- Affects: INV-17
- DB migration: project.db v2 adds session_id + decided_at columns to tool_audit_log.

**BUG-3: validator _schema_depth dead branch**
- Before: elif isinstance(child, dict) unreachable — same condition as if branch.
  Items depth miscounted for all schemas with items blocks.
- After: properties iterates .values(); items recurses directly. Fixed and tested.

**BUG-4: additionalProperties: false not enforced recursively**
- Before: only checked at top-level schema; nested object schemas unguarded.
- After: _validate_object() checks all nested object nodes. SECURITY_CONSTRAINTS §6.
- New tests: TestValidatorRecursiveAdditionalProperties

**BUG-5: AccessModeError defined inside router.py**
- Before: AccessModeRejected was a private class in router.py, untestable in isolation.
- After: AccessModeError in core/exceptions.py with all other exceptions.

**BUG-6: FEATURE_UPDATES.md blank template**
- Before: no changelog entries.
- After: this file.

### Epistemic integrity checker

- New module: kathoros/epistemic/checker.py
- New enums: EpistemicType, EpistemicStatus, ClaimLevel, Provenance, NarrativeLabel,
  Falsifiable, ValidationScope in core/enums.py
- 6 checks: EP001 premise gate, EP002 TOY_MODEL label, EP003 ontology prediction ban,
  EP004 framework ontology link, EP005 cycle detection, EP006 validation scope
- Conspiracy drift attack scenario test included (TestConspiracyDriftScenario)
- Checker is read-only/stateless — never mutates object status.
- Upstream validation never inferred (C1 invariant — directional only).

### New invariants introduced
- EPINV-1: Cannot validate any object whose depends_on targets are not all validated.
- EPINV-2: interpretation claim_level requires narrative_label=TOY_MODEL until validated.
- EPINV-3: speculative_ontology cannot have claim_level=prediction.
- EPINV-4: depends_on graph must be acyclic.

### Migration / compatibility
- DB migration: project.db v2 (ALTER TABLE objects adds 8 epistemic columns; ALTER TABLE tool_audit_log adds session_id + decided_at)
- Backward compatibility: ALTER TABLE with defaults — existing rows automatically get default values.
- New tests: 33 tests (test_checker.py + additions to test_router.py, test_validator.py)

### Notes
- EP004 and EP006 are WARN not BLOCK in v0 — escalate to BLOCK once patterns are established.
- EpistemicStatus is separate from ObjectStatus (git pipeline) — both coexist on objects.
- Checker designed to run pre-save and pre-promote-to-validated in the UI layer.

---

## 2026-02-21 — QScintilla deferred, QPlainTextEdit used for Editor tab
**Type:** docs
**Scope:** UI, tools
**Status:** proposed

### Summary
- QScintilla (python3-pyqt6.qsci) is available as a system apt package but incompatible with miniconda PyQt6 (Qt 6.10 version mismatch)
- Editor tab implemented with QPlainTextEdit + QSyntaxHighlighter as fallback
- QScintilla is the intended upgrade path

### Migration / compatibility
- When packaging as AppImage: bundle Qt6 + QScintilla together from a single Qt source
- Do not mix system Qt6 and miniconda PyQt6
- Check: dpkg -L python3-pyqt6.qsci for .so location when revisiting

### Notes
- libqscintilla2-qt6-15 is installed on system at /usr/lib/python3/dist-packages/PyQt6/Qsci.abi3.so
- Incompatible with miniconda PyQt6 due to Qt version mismatch

---

## 2026-02-21 — QTermWidget deferred, Shell tab placeholder
**Type:** docs
**Scope:** UI
**Status:** proposed

### Summary
- python3-pyqt6.qtermwidget not available in apt on this system
- Shell tab will show informative placeholder until packaged properly
- QTermWidget is the intended implementation

### Migration / compatibility
- When packaging as AppImage: bundle QTermWidget with Qt6
- Alternative: consider embedding a VTE terminal or xterm via QWindow::fromWinId
- INV-18 still applies: router must never import QTermWidget

### Notes
- Check availability on target distro before packaging

---

## 2026-02-21 — SageMath via conda subprocess
**Type:** feature
**Scope:** UI, tools
**Status:** proposed

### Summary
- SageMath 10.5 installed in conda env 'sage' (Python 3.10)
- Main app runs Python 3.13 — cannot share process
- Communication via: conda run -n sage sage -c "from sage.all import *; ..."
- SageMath panel runs evaluation in QThread, displays results

### Notes
- conda env path: sage
- Test: conda run -n sage sage -c "from sage.all import *; print(factor(x^2-1))"

---

## 2026-02-22 — Audit findings (minor, non-blocking)
**Type:** security / hardening
**Scope:** router, tools
**Status:** implemented

### Summary
- Replaced literal `"artifacts"` string in run-scope enforcement with `ARTIFACTS_DIR` constant
- Added static test `test_static_hygiene.py`: fails if `startswith(` appears on non-comment code lines in `router/` or `tools/` without `# nosec startswith` annotation
- `@dataclass(frozen=True)` on `ToolDefinition` was already in place — no change needed

### Security / invariants impact
- Affects invariants: INV-13 (path enforcement), INV-14 (run-scope)
- The one approved `startswith` use (run_id prefix check, step 7) is annotated with `# nosec startswith`
- New test: `tests/unit/router/test_static_hygiene.py::TestNoStartswithInPathCode`

---

## 2026-02-23 — Google Gemini backend
**Type:** feature
**Scope:** agents
**Status:** implemented

### Summary
- Added `GeminiBackend` as the fourth AI provider backend
- SDK: `google-genai` (`from google import genai`), streaming via `GenerateContentConfig`
- Default model: `gemini-2.0-flash`

### Behavioral changes
- Before: 3 agent backends (Anthropic, OpenAI, Ollama)
- After: 4 agent backends (+ Google Gemini)

### Security / invariants impact
- Affects invariants: none (follows existing backend contract)
- API key loaded via `load_key()` at runtime, never stored on `self`
- Backend is a pure API client — no Qt, no subprocess, no DB access

### Migration / compatibility
- DB migration: no
- Backward compatibility: preserved (additive only)

---

## 2026-02-24 — Agent tool system (8 tools)
**Type:** feature
**Scope:** tools, agents, UI
**Status:** implemented

### Summary
- Registered 8 agent tools: `object_create`, `object_update`, `db_execute`, `file_analyze`, `file_apply_plan`, `graph_update`, `matplot_render`, `sagemath_eval`
- Tools follow executor → registry → router → main_window side-effect pattern
- Each tool has a frozen `ToolDefinition` with JSON Schema validation

### Behavioral changes
- Before: agents could only produce text output
- After: agents can create/update objects, query the DB, analyze files, render plots, evaluate SageMath, and update the knowledge graph — all through the 11-step security pipeline

### Security / invariants impact
- Affects invariants: INV-1 (tool execution via router only), INV-15 (executors are pure functions)
- Write-capable tools require active run scope (INV-14)
- All tool calls audited with SHA-256 hash of args (INV-17)

### Migration / compatibility
- DB migration: no
- Backward compatibility: preserved

---

## 2026-02-24 — Fullscreen SQLite spreadsheet + object tag/parent editing
**Type:** feature
**Scope:** UI
**Status:** implemented

### Summary
- Added fullscreen editable spreadsheet dialog launched from SQLite Explorer
- Object context menu now includes "Edit Tags..." and "Set Parent" options
- Agent manager buttons styled with trust-level color coding

### Behavioral changes
- Before: SQLite Explorer was read-only; object tags and parents could only be changed via edit dialog
- After: inline tag editing, parent reassignment via context menu, spreadsheet editing with dirty-cell tracking and batch save

### Security / invariants impact
- Affects invariants: none
- Spreadsheet editable columns limited to `name` and `tags` (whitelist enforced via Qt item flags)

### Migration / compatibility
- DB migration: no
- Backward compatibility: preserved

---

## 2026-02-25 — 19 bug fixes, security hardening, and code cleanup
**Type:** security + bugfix
**Scope:** router, db, agents, tools, UI
**Status:** implemented

### Summary
- Fixed SQL injection via dynamic column names in `update_agent()` — added `_AGENT_EDITABLE` whitelist
- Fixed path traversal in key storage — strict regex + resolve() containment check
- Fixed cycle detection OOM — replaced path-copying DFS with O(V+E) algorithm
- Fixed cross-thread SQLite access in search worker — separate connection per thread
- Fixed async state loss between dispatch and callback — `_active_import_paths` pattern
- 14 additional minor fixes and cleanup

### Security / invariants impact
- SQL injection, path traversal, and resource exhaustion vulnerabilities resolved
- No new invariants; strengthens INV-13 (path enforcement) and INV-17 (audit logging)

### Migration / compatibility
- DB migration: no
- Backward compatibility: preserved

---

## 2026-02-26 — File import browser with type-organized subfolders
**Type:** feature
**Scope:** UI
**Status:** implemented

### Summary
- Added "Add Files..." button to ImportPanel — opens native file dialog
- Files copied into `docs/<type>/` subfolders (pdf/, markdown/, latex/, python/, json/)
- Added PDF (`.pdf`) to supported import types with 📑 icon
- Name collision handling with auto-incrementing suffixes

### Behavioral changes
- Before: users manually dropped files into `~/.kathoros/projects/<project>/docs/` (flat folder)
- After: native file dialog for selecting files from anywhere; automatic type-based organization

### Security / invariants impact
- Affects invariants: none
- Files are copied (not moved/linked) — original files are not modified
- New tests: 16 tests in `tests/unit/ui/test_import_panel.py`

### Migration / compatibility
- DB migration: no
- Backward compatibility: preserved (existing flat docs/ files still discovered via rglob)
