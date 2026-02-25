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

## QPlainTextEdit setReadOnly and Focus Policy

**Problem:** Calling `setReadOnly(True)` on a `QPlainTextEdit` (or `QTextEdit`) silently resets
the widget's focus policy to `Qt::NoFocus`. This means the widget can never receive keyboard
focus, so `keyPressEvent` — even on a subclass — is never called.

**Symptom:** Custom key handling in a subclass appears to work in isolation but does nothing
when the widget is inside a larger application. No errors, no warnings.

**Fix:** Always explicitly restore the focus policy after `setReadOnly(True)`:
```python
self.setReadOnly(True)
self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # Qt resets this — restore it
```

---

## Embedded Terminal: xterm vs pty

**Problem:** `xterm -into <winId>` is unreliable for embedding:
- Timing-dependent: the container X11 window must be mapped before xterm launches
- Broken on Wayland/XWayland: `winId()` returns an XCB handle that xterm can't embed into
- Restart also fails: even when the widget IS visible, embedding doesn't work consistently

**Solution:** Use Python's `pty` module + `subprocess.Popen` directly:
```python
master_fd, slave_fd = pty.openpty()
process = subprocess.Popen(
    ["bash", "--login"],
    stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
    close_fds=True, preexec_fn=os.setsid, cwd=cwd,
)
os.close(slave_fd)  # parent only needs master end
# Read from master_fd via QSocketNotifier
```
This is truly embedded, works on X11 and Wayland, and gives a real interactive bash session.

**Send TIOCSWINSZ on resize** so tools like `ls` format to the correct column width:
```python
import fcntl, termios, struct
winsize = struct.pack("HHHH", rows, cols, 0, 0)
fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
```

---

## Preventing QPlainTextEdit from Editing Its Own Content

**Problem:** Using an event filter (`installEventFilter`) to intercept key presses on a
`QPlainTextEdit` is not reliable. Qt can still insert characters through the input method
(iBus, fcitx) pipeline even when the filter returns `True`. Result: each keystroke appears
twice (Qt inserts it, pty echoes it back).

**Fix:** Subclass `QPlainTextEdit` and override `keyPressEvent` directly. Never call
`super().keyPressEvent()` for keys you are consuming. This is called before any input method
processing and is the only reliable interception point:
```python
class _TermWidget(QPlainTextEdit):
    def keyPressEvent(self, event):
        data = _key_to_bytes(event)
        if data:
            self.key_pressed.emit(data)
            # Do NOT call super() — prevents Qt from editing the document
        else:
            super().keyPressEvent(event)  # allow copy, etc.
```

To write output programmatically to a read-only widget, use the document cursor directly:
```python
cursor = self.document().rootFrame().lastCursorPosition()
cursor.insertText(text)  # bypasses the read-only guard on the view
```

---

## Session Snapshot: Avoid Restoring Navigation State That Surprises Users

**Problem:** Saving and restoring the active tab index means users always return to the last
tab they had open — including the System/Shell tab. This is surprising on startup.

**Rule:** Only restore "content" state (which document was open, which sub-tab was selected
within a work area). Do not restore which top-level panel group was active. Always open on
the primary work area (Documents tab) at startup.

---

## pdflatex Subprocess

- Always pass `-interaction=nonstopmode` to prevent pdflatex from blocking on errors.
- Check `os.path.exists(pdf_path)` after the run — return code alone is not sufficient.
- Run in a `tempfile.mkdtemp()` directory with `-output-directory=<tmp>` to avoid polluting
  the working directory.
- 30-second timeout is sufficient for typical research documents.

---

## Adding a New Agent Backend Provider

**Pattern:** All agent backends (`OllamaBackend`, `AnthropicBackend`, `OpenAIBackend`,
`GeminiBackend`) follow the same contract:

1. **New file:** `kathoros/agents/backends/<provider>_backend.py` with a class exposing
   `stream(messages, on_chunk, on_done, on_error, system_prompt)` and `test_connection() -> bool`.
2. **Dispatcher:** Add `elif provider == "<name>":` in `kathoros/agents/dispatcher.py`.
3. **Agent dialog:** Add `"<name>"` to the provider combo in `agent_dialog.py`.
4. **Settings panel:** Add `("<name>", "Label")` to the API key providers list in `settings_panel.py`.

**Security checklist (SECURITY_CONSTRAINTS.md §14):**
- API key loaded via `load_key()` inside method calls, never in `__init__`, never stored on `self`.
- Key never logged, never injected into messages or system prompt, never persisted in snapshots.
- Backend must not import Qt, call subprocess, or touch the DB — it is a pure API client.
- No tool execution or approval logic — that belongs exclusively to the ToolRouter (§1.1).

**Gemini-specific notes:**
- SDK: `google-genai` (`from google import genai`), not `google-generativeai`.
- Message format: role is `"user"` or `"model"` (not `"assistant"`).
- System prompt goes in `config={"system_instruction": system_prompt}`, not in the messages list.
