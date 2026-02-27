# Kathoros Changelog

## [Unreleased] — 2026-02-26

### Added
- **File import browser** — "Add Files..." button opens native file dialog; copies files into organized subfolders (`pdf/`, `markdown/`, `latex/`, `python/`, `json/`) with collision handling
- **PDF support in import panel** — `.pdf` added to supported types with 📑 icon
- **Google Gemini backend** — fourth AI provider via `google-genai` SDK with streaming (default model: `gemini-2.0-flash`)
- **Agent tool system** — 8 tools registered: `object_create`, `object_update`, `db_execute`, `file_analyze`, `file_apply_plan`, `graph_update`, `matplot_render`, `sagemath_eval`
- **Fullscreen SQLite spreadsheet** — editable spreadsheet dialog with dirty-cell tracking, row add/delete, batch save
- **Object tag editing** — right-click context menu "Edit Tags..." with comma-separated input dialog
- **Object parent reassignment** — right-click "Set Parent" submenu to pick parent or detach to root
- **Agent manager styling** — trust level color coding (red/yellow/green), styled buttons
- LaTeX panel moved from Mathematics tab to Documents tab (index 2, between Editor and Audit Log)
- LaTeX objects now open automatically in the LaTeX editor when selected in the objects panel
- `.tex` source-file children in the objects tree now open in the LaTeX editor (not text editor)
- `load_content()` auto-wraps bare LaTeX fragments with `\documentclass{article}` + amsmath header/footer
- `list_objects` DB query now returns `source_file`, `depends_on`, and `tags` columns
- Import panel now supports `.txt` and `.text` file types
- AI import prompt now requests `latex`, `math_expression`, `researcher_notes`, `depends_on`, `source_file` fields
- Object routing detects LaTeX by: `latex` field, `.tex` source_file extension, or LaTeX markers in content

### Changed
- MathematicsTabGroup no longer contains a LaTeX tab (SageMath, Graph, MatPlot only)
- EditorPanel language selector drops the "LaTeX" option and its toolbar
- `.tex` files are no longer detected as "latex" language in the EditorPanel
- LaTeX PDF compilation result opens in the Reader panel automatically via `pdf_ready` signal

### Fixed
- 19 bug fixes across security hardening, SQL injection prevention, path traversal blocking, and code cleanup
- QSplitter GC bug: splitters now stored as `self._splitter` / `self._left_panel` instance vars
- `MathematicsTabGroup` panels stored as instance vars to prevent Python GC destroying Qt wrappers
- `_CompileWorker` signal renamed from `finished` to `compile_done` to avoid collision with `QThread.finished`
- `_open_file_in_reader` now correctly routes `.tex` files to the LaTeX panel instead of text editor
- LaTeX object routing checks both `latex` field and content markers, not just `latex` field
- Shell panel: xterm `-into` embedding replaced with native pty-based terminal
- Shell panel: unified single pane — output and input in one area, no separate input line
- Shell panel: correct key map (Ctrl+CDLZAUEKW, arrows, Home/End, Delete, Tab, Esc)
- Shell panel: TIOCSWINSZ sent on resize so tools like `ls` use correct column width
- App always opens on Documents tab at startup (System tab no longer restored from session)
- SQL injection via dynamic column names in `update_agent()` — whitelisted with `_AGENT_EDITABLE`
- Path traversal in key storage — strict regex validation + resolve() check
- Cycle detection OOM — replaced path-copying DFS with O(V+E) visited/rec_stack approach
- Cross-thread SQLite access in search worker — separate connection per thread
- Async state loss between dispatch and callback — `_active_import_paths` pattern

### Fixed (shell)
- xterm launched as floating external window due to X11 embedding timing / Wayland incompatibility → replaced entirely with pty+subprocess approach
- `setReadOnly(True)` on `QPlainTextEdit` silently resets focus policy to `NoFocus`, blocking all keyboard input → `_TermWidget` subclass restores `StrongFocus` after `setReadOnly`
- Double keystroke input: Qt inserted characters AND pty echoed them back → `_TermWidget` overrides `keyPressEvent` and never calls `super()` for terminal keys, widget kept read-only
- Session snapshot was restoring System tab as the active right-panel tab on startup → outer tab index no longer saved/restored

---

## [0.1.0] — Initial release

### Added
- Local-first physics research platform: PyQt6 + SQLite + AI backends
- Objects pipeline with epistemic status, claim-level ceiling, and circular dependency detection
- Agent dispatcher with tool approval workflow
- Import pipeline: PDF, Markdown, LaTeX, Python, JSON, TXT
- Rich context injection for agent system prompt (selected objects, session state)
- Git integration panel
- Notes panel with export (Markdown / LaTeX / Plain Text)
- SageMath evaluator panel
- Cross-project search
- SQLite explorer
- Session snapshot save/restore
