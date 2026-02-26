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

---

## Adding a New Agent Tool

**Pattern:** All tools follow executor → registry → router → main_window side-effect:

1. **New file:** `kathoros/tools/tool_<name>.py` with a `ToolDefinition` and an executor function
   `execute_<name>(args, tool, project_root) -> dict`.
2. **Registry:** Import and register in `kathoros/services/tool_service.py`:
   - `registry.register(TOOL_DEF)` in `_build_registry()`
   - `"<name>": execute_<name>` in the `executors={}` dict
3. **Main window:** Add `elif tool_name == "<name>"` in `_on_tool_request` and a
   `_apply_<name>(data)` handler for any UI side effects (panel rendering, DB writes, etc.).
4. **System prompt:** Add PROXENOS envelope example in `context_builder.py`'s `_TOOL_ENVELOPE_HINT`.

**Key design rules:**
- Executors are **pure functions** — no Qt imports, no DB access, no approval logic (INV-15).
- Executors validate and **pass through data**; actual side effects happen in main_window handlers.
- Tools needing UI interaction (graph, matplot, sagemath) return data that main_window applies
  to the relevant panel, then auto-switches to the correct tab.
- `write_capable=True` triggers the router's approval gate (step 8).
- `output_target` is descriptive only — routing is done by tool name in main_window.

---

## PROXENOS Envelope: Agent Identity and Trust Levels

**Problem:** Agents at UNTRUSTED or MONITORED trust level must use the full PROXENOS envelope
format. The simpler `{"tool": "...", "args": {...}}` format (json_struct) is detected but
rejected at the router's envelope enforcement step (step 3).

**Solution:** The system prompt must teach agents the exact PROXENOS format with their identity
pre-filled. Pass `agent_id` and `agent_name` into the dispatch context so `context_builder.py`
can inject them into the envelope template:
```
{"proxenos_tool_request": {"nonce": "<nonce>", "agent_id": "<id>", "agent_name": "<name>",
  "tool": "<tool>", "args": {...}}}
```

**Common agent mistakes:**
- Using `{"tool": ..., "args": ...}` without the `proxenos_tool_request` wrapper → rejected
- Wrapping valid JSON in markdown ` ```json ` blocks → envelope scanner must extract from within
- Dropping trailing `}` braces (truncated output) → parser repair needed

---

## EnvelopeParser: Handling Malformed Agent Output

**Problem:** LLM agents (especially GPT-4o) frequently produce malformed tool calls:
1. Missing trailing `}` braces (truncated JSON)
2. Wrapping JSON in markdown ` ```json ` code blocks
3. Using ` ```python ` blocks for code examples (falsely detected as tool calls)

**Fixes applied:**
- **Brace repair:** `_extract_embedded_envelope` tracks the last `}` position. If braces don't
  balance, appends missing `}` characters and retries parsing. This recovers truncated envelopes.
- **Language blocklist:** `_try_markdown_block` checks the code-block tag against a blocklist of
  common language names (`python`, `json`, `bash`, `sql`, etc.). Prevents false tool detection.
- **Balanced-brace walker:** `_try_json_struct` uses `_extract_balanced_json` instead of a simple
  regex, correctly handling nested objects and arrays in tool args.

---

## Matplotlib Embedded Figure: Don't Use pyplot Figure Manager

**Problem:** `Figure()` objects created directly (not via `plt.figure()`) are not registered with
pyplot's figure manager. In newer matplotlib versions, `self._fig.number` raises
`AttributeError` or returns a deprecation warning. Calling `plt.figure(self._fig.number)` fails.

**Solution:** Use a `_PltProxy` class that intercepts `plt.*` calls and routes them to the
embedded figure's axes:
```python
class _PltProxy:
    def plot(self, *a, **kw): return _panel_ax.plot(*a, **kw)
    def title(self, *a, **kw): _panel_ax.set_title(*a, **kw)
    def xlabel(self, *a, **kw): _panel_ax.set_xlabel(*a, **kw)
    # ... etc
    def show(self): pass  # no-op
    def close(self, *a, **kw): pass  # no-op
```
Pass `_PltProxy()` as `plt` in the exec namespace. Agent code calls `plt.plot()` etc. and it
all draws on the embedded canvas without touching pyplot's global state.

---

## SQLite: execute() vs executescript()

**Problem:** `sqlite3.Connection.execute()` only accepts a single SQL statement. Agents often
send multiple semicolon-separated statements (e.g., `CREATE TABLE ...; INSERT INTO ...;`),
which raises `"You can only execute one statement at a time."`.

**Fix:** Use `conn.executescript(sql)` for write operations (CREATE, INSERT, UPDATE, DELETE).
Keep `conn.execute(sql)` for SELECT/PRAGMA queries that need to return rows via `fetchall()`.
`executescript()` issues an implicit COMMIT before executing, so it handles transactions
automatically.

---

## SQLite Spreadsheet: Limiting Editable Columns

**Pattern:** When building an editable `QTableWidget` over a database table, not all columns
should be user-editable. Use Qt item flags to control this per-cell:

```python
_EDITABLE_COLUMNS = {"name", "tags"}

for c, val in enumerate(row):
    item = QTableWidgetItem(str(val) if val is not None else "")
    if columns[c].lower() not in _EDITABLE_COLUMNS:
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    table.setItem(r, c, item)
```

The `QTableWidget` edit trigger (`DoubleClicked`) still fires, but Qt silently ignores it for
items without `ItemIsEditable`. No custom event filter needed.
