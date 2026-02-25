# Kathoros Changelog

## [Unreleased] — 2026-02-24

### Added
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
- QSplitter GC bug: splitters now stored as `self._splitter` / `self._left_panel` instance vars
- `MathematicsTabGroup` panels stored as instance vars to prevent Python GC destroying Qt wrappers
- `_CompileWorker` signal renamed from `finished` to `compile_done` to avoid collision with `QThread.finished`
- `_open_file_in_reader` now correctly routes `.tex` files to the LaTeX panel instead of text editor
- LaTeX object routing checks both `latex` field and content markers, not just `latex` field

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
