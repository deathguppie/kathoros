# Lessons Learned — Kathoros Development

## PyQt6 Widget Lifecycle and GC

**Problem:** Qt widgets created as local variables inside `__init__` (not stored as `self._x`) can be
garbage collected by Python even though Qt holds a C++ reference. This causes silent failures —
no crash, but the widget is dead.

**Rule:** Always store every widget and object that has signal connections or needs to survive the
constructor as an instance attribute (`self._x`). This includes:
- `QSplitter` instances
- `QThread` / worker objects
- `QShortcut` instances
- Any panel added to a tab group

---

## QSplitter Cannot Be Embedded in Nested QTabWidget

**Problem:** Placing a `QSplitter` inside a widget that is itself inside a `QTabWidget` produces:
```
QWidgetWindow(...) must be a top level window.
```
Qt treats QSplitter children as potential top-level windows, which conflicts with tab embedding.

**Fix:** Replace `QSplitter` inside panels with plain `QVBoxLayout` / `QHBoxLayout`. Use `QSplitter`
only at the top level (main window layout).

---

## QThread Signal Name Collision

**Problem:** Defining `finished = pyqtSignal(...)` on a `QThread` subclass silently shadows
`QThread.finished`, which Qt emits internally when the thread exits. The custom signal never fires
reliably, and the thread lifecycle is broken.

**Fix:** Never name a custom `QThread` signal `finished`. Use a descriptive name:
```python
compile_done = pyqtSignal(str, bool)   # good
finished     = pyqtSignal(str, bool)   # bad — shadows QThread.finished
```

---

## Nested QTabWidget Button Click Debugging

**Problem:** Button clicks inside a deeply nested `QTabWidget → QTabWidget → Panel → QWidget toolbar`
structure appeared to fire nothing — no signal, no output.

**Debugging approach that worked:**
1. Write a minimal standalone script reproducing the exact nesting structure.
2. Confirm the button fires in isolation — if it does, the bug is in the full app, not PyQt6.
3. Add a visible status label change as the very first line of the slot (`processEvents()` after)
   to confirm whether the slot is reached at all.
4. Check for GC issues (unwrapped C++ objects), event filters, and signal name collisions.

**Root cause here:** The `_CompileWorker.finished` → `QThread.finished` collision meant
`compile_done` was never properly connected/emitted.

---

## Object Routing by Content Type

**Pattern:** When an objects panel item is clicked, routing to the correct editor requires
checking multiple signals:

- Single-click on an **object row** → `object_selected(id)` → look up full object from DB
- Single-click on a **source-file child row** → `open_source_requested(id)` → open file by path
- Double-click → `object_edit_requested(id)` → open detail dialog

Each path needs its own routing logic. Don't assume all clicks hit the same handler.

**LaTeX detection heuristic (in priority order):**
1. `obj["latex"]` field is non-empty — use it directly
2. `obj["source_file"]` ends with `.tex` — read the file
3. `obj["content"]` contains LaTeX markers (`\begin{`, `\documentclass`, `\section{`) — use content
4. Otherwise → text editor

---

## LaTeX Fragment Handling

**Problem:** Research objects often store only equation environments or theorem bodies, not a
complete compilable document.

**Fix in two places:**
- `LaTeXPanel.load_content()` — wrap at load time so the user sees complete, editable LaTeX
- `LaTeXPanel.compile()` — wrap again as a safety net if the user typed partial LaTeX

**Standard wrapper:**
```latex
\documentclass{article}
\usepackage{amsmath,amssymb,amsthm}
\begin{document}
<content>
\end{document}
```

---

## DB Query Column Lists

**Problem:** Explicit `SELECT col1, col2, ...` queries silently omit columns added later
(e.g. `latex`, `source_file`, `depends_on`). Callers get `None` for missing keys and routing
logic quietly fails.

**Fix:** Either use `SELECT *` for single-object lookups (acceptable), or keep explicit column
lists up to date whenever the schema changes. Add a comment near the query listing which
columns are intentionally excluded and why.

---

## pdflatex Subprocess

- Always pass `-interaction=nonstopmode` to prevent pdflatex from blocking on errors.
- Check `os.path.exists(pdf_path)` after the run — return code alone is not sufficient.
- Run in a `tempfile.mkdtemp()` directory with `-output-directory=<tmp>` to avoid polluting
  the working directory.
- 30-second timeout is sufficient for typical research documents.
