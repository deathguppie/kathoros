<p align="center">
  <img src="kathoros/assets/logo.jpg" alt="Kathoros" width="480"/>
</p>

<h1 align="center">Kathoros</h1>
<p align="center"><em>Local-first physics research platform — AI agents, structured knowledge, and a secure tool pipeline in a single desktop app.</em></p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"/>
  <img src="https://img.shields.io/badge/PyQt6-6.6%2B-green" alt="PyQt6"/>
  <img src="https://img.shields.io/badge/license-GPL--3.0-orange" alt="GPL-3.0"/>
  <img src="https://img.shields.io/badge/platform-Linux%20%7C%20macOS-lightgrey" alt="Platform"/>
</p>

---

## Download

| Platform | File | Notes |
|---|---|---|
| **Linux x86_64** | [Kathoros-x86_64.AppImage](../../releases/latest) | No install needed — `chmod +x` and run |
| **macOS** | Build from source (see below) | [Porting guide](docs/porting-macos.md) |

> **Linux:** Requires glibc ≥ 2.35 (Ubuntu 22.04+, Debian 12+, Fedora 36+, RHEL 9+).

---

## Overview

Kathoros is a **local-first desktop research environment** designed for physicists who want AI assistance without surrendering their data to a cloud service. Every session, every object, and every tool call stays on your machine. Agents can only do what the security router explicitly permits.

The platform combines:
- A **multi-panel Qt workspace** for reading papers, writing notes, running code, and visualising results
- **Three AI backends** (Anthropic Claude, OpenAI, Ollama) with streaming output and a structured import pipeline
- A **secure tool router** (11-step pipeline) that validates, audits, and gates every agent action
- A **knowledge graph** of typed, versioned research objects with epistemic integrity enforcement
- **Git-native version control** of your research objects, tracked inside the app

---

## Features

### AI Agent Integration
- **Anthropic Claude** (claude-sonnet-4-6, claude-opus-4-6, etc.) via official SDK with streaming
- **OpenAI / GPT-4** via `openai` SDK
- **Ollama** — fully local models (Llama 3, Mistral, Phi-3, …) at `localhost:11434`; no data leaves your machine
- Agent output is streamed live into the output panel; tool requests are intercepted and routed through the security pipeline before execution
- **Agent Manager** — create, edit, and switch agents with per-agent system prompts and model selection

### Secure Tool Router (11-step pipeline)
Every tool call from an agent passes through:
1. Access mode check (NO_ACCESS → reject immediately)
2. Nonce validation (replay prevention)
3. Tool lookup (exact-match, case-sensitive registry)
4. Envelope validation (JSON/XML/Markdown envelope detection)
5. Schema validation (JSON Schema, depth-limited, `additionalProperties: false` enforced recursively)
6. Input size limit
7. Path enforcement (`.resolve()` + `.relative_to()`, never `startswith()`)
8. Run-scope gate (write tools require active run)
9. Human approval dialog (configurable per tool and trust level)
10. Tool execution
11. Output size limit + structured audit logging

Trust levels: UNTRUSTED → MONITORED → TRUSTED → PRIVILEGED. Approval policy is per-tool and per-trust level. All decisions are written to the append-only audit log.

### Structured Import Pipeline
Drop a PDF or paste text → the agent extracts:
- **Concepts** — definitions, terminology
- **Derivations** — step-by-step mathematical derivations
- **Predictions** — testable physical predictions
- **Evidence** — experimental or observational support
- **Open questions** — unresolved problems
- **Data** — numerical results

Objects are validated against the **epistemic integrity checker** (6 rules) before being committed to the project database. Example rules: a speculative-ontology object cannot carry a `prediction` claim level; validation cannot propagate upstream; depends-on graphs must be acyclic.

### PDF Reader
- Background rendering in a dedicated thread — UI never blocks during page load
- **Fit-to-width** zoom (default); explicit zoom steps 50%–300%; 150 ms debounce on resize
- **Rubber-band text selection** → clipboard copy (pixel rect → fitz rect via zoom factor, `get_text("words")`)
- Keyboard navigation: arrow keys, Page Up/Down, Space; jump-to-page input
- Works with multi-hundred-page PDFs without freezing the main thread

### Knowledge Objects Panel
- **Dependency tree view** — objects are arranged as a hierarchy based on their `depends_on` links
- Left-click → load object content into the editor panel
- Right-click → context menu (edit, delete, view details)
- Object types: concept, definition, derivation, prediction, evidence, open_question, data

### Editor Panel
- Syntax-highlighted editor (Pygments + QSyntaxHighlighter)
- Loads research objects formatted as structured markdown
- Line numbers, monospace font

### Notes Panel
- Per-project free-form notes stored in SQLite
- Full CRUD; notes persist across sessions

### Git Integration
- Browse commit history and file status for the current project directory
- Stage, unstage, and commit from inside the app (via GitPython)
- Designed to track your research objects under version control

### Cross-Project Search
- SQLite **FTS5 full-text search** across all projects simultaneously
- Searches notes, object content, tags, and researcher annotations
- Results show project, object type, and matching snippet

### Interactive Shell
- Embeds a real `xterm` terminal inside the Qt window (Linux, via X11 `winId`)
- `set_cwd()` method restarts the shell in the current project directory
- Toolbar shows current working directory; Restart button
- Graceful fallback with platform-appropriate install instructions when xterm is absent

### Audit Log
- All tool approvals, rejections, and errors are written to `tool_audit_log` in the project DB
- Audit window shows date, tool name, decision, agent, and outcome
- Built-in audit templates (5 system templates seeded on first run)
- Raw args are **never** logged — only a SHA-256 hash

### Additional Panels

| Panel | Description |
|---|---|
| LaTeX | Render LaTeX expressions using matplotlib's math renderer |
| Graph | Visualise the object dependency graph with networkx + matplotlib |
| SageMath | Run SageMath 10.x expressions in a sandboxed conda subprocess |
| Matplotlib | Plot data from objects or manual Python snippets |
| SQLite Explorer | Browse raw project and global database tables |
| Results | Collects and displays tool execution results |
| Settings | Per-project settings with global defaults; safety toggles |

### Session State
- Panel layout and open project are saved on exit and restored on next launch
- Splash screen on startup (1.5 s minimum display)

---

## Architecture

```
kathoros_main/
├── main.py                     # Entry point + splash screen
├── kathoros/
│   ├── core/                   # Constants, exceptions, enums
│   ├── router/                 # 11-step secure tool router + registry + validator
│   ├── agents/                 # Agent workers, backends (Anthropic/OpenAI/Ollama), envelope parser
│   ├── epistemic/              # Epistemic integrity checker (6 rules)
│   ├── db/                     # SQLite migrations + query layer
│   ├── services/               # Project manager, git service, search service, global service
│   ├── tools/                  # Tool implementations (file read/write, apply-plan, …)
│   └── ui/
│       ├── main_window.py      # Main window + panel wiring
│       ├── panels/             # One file per panel (20+ panels)
│       └── dialogs/            # Tool approval, object detail, agent, project dialogs
├── scripts/
│   ├── build_appimage.sh       # Docker-first AppImage build (glibc 2.35 target)
│   └── build_macos.sh          # (planned) PyInstaller macOS bundle
├── docs/
│   └── porting-macos.md        # macOS porting requirements
├── tests/                      # pytest — 130+ tests across router, epistemic, DB layers
└── Dockerfile.build            # Ubuntu 22.04 build image (portable AppImage)
```

**Data storage:** `~/.kathoros/global.db` (agents, settings, audit templates) and `<project_dir>/.kathoros/project.db` (objects, notes, sessions, audit log).

---

## Installation

### From AppImage (Linux — recommended)

```bash
# Download the AppImage from the Releases page
chmod +x Kathoros-x86_64.AppImage
./Kathoros-x86_64.AppImage
```

Requirements: glibc ≥ 2.35 (Ubuntu 22.04+, Debian 12+, Fedora 36+, RHEL 9+).

### From source

```bash
# Python 3.10+ required (3.13 recommended)
git clone https://github.com/YOUR_USERNAME/kathoros.git
cd kathoros

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python main.py
```

**Optional dependencies:**
- **Ollama** — install from [ollama.com](https://ollama.com) for fully local model support
- **xterm** — `sudo apt install xterm` for the embedded shell panel (Linux)
- **SageMath** — `conda create -n sage sage` for the SageMath panel

### Build AppImage from source

Requires Docker.

```bash
bash scripts/build_appimage.sh          # Docker build (portable, glibc 2.35 target)
bash scripts/build_appimage.sh --local  # Local build (dev/test only)
```

Output: `dist/Kathoros-x86_64.AppImage`

---

## AI Backend Setup

### Anthropic Claude

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Or set it in **Settings → API Keys** inside the app.

### OpenAI

```bash
export OPENAI_API_KEY=sk-...
```

### Ollama (fully local, no API key needed)

```bash
# Install Ollama: https://ollama.com
ollama pull llama3
# Kathoros connects to localhost:11434 automatically
```

---

## Security Model

- Agent tool calls pass through an immutable 11-step validation pipeline — agents cannot bypass it
- Path traversal is prevented via `.resolve()` + `.relative_to()` (not `startswith()`)
- Raw tool arguments are never written to disk — only a SHA-256 hash is logged
- ToolDefinition schemas are frozen at registration (`MappingProxyType`) — agents cannot mutate them
- Write-capable tools require an active "run scope" — agents cannot write outside a sanctioned run
- A static test (`test_static_hygiene.py`) fails CI if `startswith(` appears in path-handling code without an explicit `# nosec startswith` annotation

---

## Requirements

| Package | Version | Purpose |
|---|---|---|
| PyQt6 | ≥ 6.6 | UI framework |
| PyMuPDF | ≥ 1.23 | PDF rendering + text extraction |
| GitPython | ≥ 3.1 | Git integration |
| anthropic | ≥ 0.83 | Claude backend |
| httpx | ≥ 0.28 | HTTP client |
| matplotlib | ≥ 3.8 | Plotting + LaTeX rendering |
| networkx | ≥ 3.2 | Dependency graph |
| Pygments | ≥ 2.19 | Syntax highlighting |
| ollama | ≥ 0.6 | Local model backend |
| pandas | ≥ 2.0 | Data handling |

Full pinned build deps: [`requirements-build.txt`](requirements-build.txt)

---

## License

GPL-3.0 — see [LICENSE](LICENSE) for details.

---

## macOS

Kathoros runs on macOS 11.0+ (Big Sur and later) from source. The AppImage is Linux-only.
See [`docs/porting-macos.md`](docs/porting-macos.md) for the full porting guide including a recommended four-phase implementation plan.

---

<p align="center"><em>Built with PyQt6 · SQLite FTS5 · PyMuPDF · Anthropic API</em></p>
