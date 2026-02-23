# Kathoros — macOS Porting Requirements

**Prepared:** 2026-02-22
**Source platform:** Ubuntu 25.10 (glibc 2.42), Python 3.13.11, PyQt6 6.10.2
**Target platform:** macOS 11.0+ (Big Sur and later)

> **Note on macOS 10.x:** PyQt6 6.10.x wheels target macOS 11.0 minimum.
> Targeting macOS 10.x (Catalina/Mojave) would require downgrading to PyQt6 ≤ 6.4.x
> and Python ≤ 3.11, which introduces significant constraint propagation across the
> whole dependency tree. macOS 11+ (2020 onward) is the recommended minimum target.

---

## Summary

| Category | Count |
|---|---|
| Hard blockers (app will not launch) | 4 |
| Silent degradations | 2 |
| Build / packaging differences | 4 |
| No changes needed | ~20 features |

---

## 1. Hard Blockers — app will not start

### 1.1 Shell panel: X11-only terminal embedding

**File:** `kathoros/ui/panels/shell_panel.py`
**Lines:** 73–110

The shell panel embeds `xterm` using the `-into <winId>` flag, which passes an X11
window ID to xterm so it renders inside a Qt widget. On macOS (Quartz compositor)
`winId()` does not return a usable X11 window ID — this architecture is
fundamentally Linux/X11-only.

The fallback path activates when `xterm` is not found in `PATH`, which will always
be the case on macOS without XQuartz. The fallback shows a hardcoded
`apt install xterm` message (see §2.1).

**Fix options (pick one):**

| Option | Effort | Quality |
|---|---|---|
| **A — QTermWidget** via Homebrew (`brew install qtermwidget`) | Medium | Full PTY terminal, same as original intent |
| **B — PTY widget** using `os.openpty()` + `QProcess` + `QPlainTextEdit` | Medium | ~90% of shell use cases, no external deps |
| **C — Graceful disable** on non-Linux with a platform-aware message | Minimal | Honest limitation; rest of app unaffected |

Option C is recommended for an initial port; Option A or B can follow as a
subsequent feature.

---

### 1.2 `QT_QPA_PLATFORM` hardcoded to `xcb`

**File:** `scripts/build_appimage.sh`
**Line:** 153

```bash
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
```

`xcb` is the X11 Qt platform plugin. macOS requires the `cocoa` plugin. This line
causes the app to exit immediately with:

```
This plugin does not support createPlatformOpenGLContext!
Could not find the Qt platform plugin "xcb"
```

**Fix:** Remove this line from `AppRun`. Qt selects the correct platform plugin
(`cocoa` on macOS, `xcb` on Linux) automatically when the variable is not set.
The guard is only needed in the Linux AppImage context and should not be in
general-purpose launch code.

---

### 1.3 AppImage is a Linux-only format

**File:** `scripts/build_appimage.sh`
**File:** `Dockerfile.build`

AppImage is a Linux-specific packaging format. macOS cannot mount or execute
`.AppImage` files. A separate macOS distribution pipeline is required.

**Required additions:**

- `scripts/build_macos.sh` — PyInstaller invocation with macOS-specific flags:
  - `--osx-bundle-identifier com.kathoros.app`
  - `--target-arch x86_64` (Intel) or `arm64` (Apple Silicon) or `universal2`
  - Output: `Kathoros.app` bundle
- `scripts/make_dmg.sh` — Wrap `.app` in a distributable `.dmg` using
  `create-dmg` (Homebrew) or `hdiutil`
- Code signing: `codesign --deep --sign "Developer ID Application: ..."` required
  for Gatekeeper (unsigned apps are blocked by default on macOS 10.15+)
- Notarization: `xcrun notarytool submit` required for distribution outside
  the Mac App Store

**PyInstaller macOS flags that differ from Linux:**

```bash
pyinstaller \
    --osx-bundle-identifier com.kathoros.app \
    --target-arch universal2 \        # Intel + Apple Silicon
    --add-data "kathoros/assets:kathoros/assets" \
    --windowed \                      # suppress terminal window
    main.py
```

---

### 1.4 Dockerfile installs X11/XCB libraries only

**File:** `Dockerfile.build`
**Lines:** 18–24

The build image installs only X11/XCB display libraries:

```dockerfile
libxcb-xinerama0 libxcb-icccm4 libxcb-image0 ...
libx11-6 libxext6 libxrender1 ...
```

These packages do not exist on macOS. A macOS build does not need a Dockerfile at
all — the host machine provides Cocoa/Metal via the OS. PyInstaller should run
directly in a local virtual environment.

**Fix:** The Docker build path is Linux-specific by design and should remain so.
Add a detection gate at the top of `build_appimage.sh`:

```bash
if [[ "$(uname)" != "Linux" ]]; then
    echo "AppImage is Linux-only. Use scripts/build_macos.sh on macOS."
    exit 1
fi
```

---

## 2. Silent Degradations

### 2.1 Shell fallback message references `apt`

**File:** `kathoros/ui/panels/shell_panel.py`
**Lines:** 141–144

```python
"Shell unavailable: xterm not found.\n\n"
"Install with:  sudo apt install xterm"
```

On macOS the message is shown but the install instruction is wrong.

**Fix:** Detect platform and adjust the message:

```python
import sys
if sys.platform == "darwin":
    install_hint = "brew install --cask xquartz  # then log out and back in"
elif sys.platform.startswith("linux"):
    install_hint = "sudo apt install xterm"
else:
    install_hint = "Install xterm for your platform"
```

---

### 2.2 Shell hardcodes `bash`

**File:** `kathoros/ui/panels/shell_panel.py`
**Lines:** 113–115

```python
init_cmd = f"cd {shlex.quote(self._cwd)}; exec bash --login"
args += ["-e", "bash", "--login", "-c", init_cmd]
```

macOS has used `zsh` as the default shell since macOS Catalina (10.15). Hardcoding
`bash` works if bash is installed but ignores the user's configured shell.

**Fix:** Read `os.environ.get("SHELL", "bash")` to use the user's shell.

---

## 3. Build & Packaging Differences

### 3.1 `ldd` is Linux-only

**File:** `scripts/build_appimage.sh`
**Lines:** 44, 80–81

```bash
GLIBC_VER=$(ldd --version 2>&1 | head -1 | grep -oP '\d+\.\d+' | tail -1)
```

`ldd` does not exist on macOS (`otool -L` is the equivalent). This causes the
script to error if run on macOS.

**Fix:** Guard with `uname` check (see §1.4) — the entire script exits before
reaching this line.

---

### 3.2 glibc portability model does not apply to macOS

**File:** `scripts/build_appimage.sh`
**Lines:** 4–5, comments throughout

The entire glibc version strategy (build on Ubuntu 22.04 to target glibc ≥ 2.35)
is a Linux-specific concern. macOS uses a different C runtime (`libSystem.dylib`)
and backward compatibility is handled differently:

- macOS deployment target set via `-mmacosx-version-min` at compile time
- PyInstaller respects `MACOSX_DEPLOYMENT_TARGET` environment variable
- A binary built on macOS 13 can target macOS 11 if compiled with
  `MACOSX_DEPLOYMENT_TARGET=11.0`

No Docker build sandbox is needed for macOS portability.

---

### 3.3 PyInstaller output structure differs

**File:** `scripts/build_appimage.sh`
**Lines:** 113–137

Linux PyInstaller output (one-dir mode):
```
dist/kathoros/
├── kathoros          # ELF executable
├── _internal/        # bundled libs
└── kathoros/assets/
```

macOS PyInstaller output (app bundle mode):
```
dist/Kathoros.app/
└── Contents/
    ├── MacOS/kathoros     # Mach-O executable
    ├── Resources/         # assets go here
    └── Frameworks/        # bundled .dylib files
```

The `AppDir` assembly step in `build_appimage.sh` is entirely Linux-specific and
has no macOS equivalent.

---

### 3.4 Code signing and notarization

No equivalent exists in the Linux build process. macOS requires:

1. **Apple Developer Program** membership ($99/year)
2. **Developer ID Application** certificate in Keychain
3. `codesign --deep --sign "Developer ID Application: <name>" Kathoros.app`
4. `xcrun notarytool submit Kathoros.dmg --apple-id ... --team-id ...`
5. `xcrun stapler staple Kathoros.dmg`

Without notarization, users on macOS 10.15+ see a Gatekeeper block dialog and
must manually allow the app in System Preferences. Distributing unsigned/unnotarized
apps is strongly discouraged.

---

## 4. No Changes Needed

The following components are fully cross-platform and require zero modification:

| Component | Reason |
|---|---|
| PDF viewer (`reader_panel.py`) | PyMuPDF + Qt — no platform code |
| Editor panel | Qt `QPlainTextEdit` + Pygments — pure Python |
| Notes panel | Qt widgets + SQLite — pure Python |
| Import pipeline | `QFileDialog` + `pathlib` — cross-platform |
| Git panel + `git_service.py` | GitPython — pure Python wrapper |
| SQLite / migrations | `sqlite3` stdlib — cross-platform |
| Ollama backend | HTTP to localhost — cross-platform |
| Anthropic / OpenAI backends | HTTPS via `httpx` — cross-platform |
| Objects panel | Qt widgets — pure Python |
| Audit window | Qt widgets — pure Python |
| Settings panel | Qt widgets — pure Python |
| Agent manager | Qt widgets — pure Python |
| Cross-project search | FTS5 + Qt — pure Python |
| Splash screen | `QSplashScreen` — cross-platform |
| Project manager / session service | `pathlib.Path.home()` — cross-platform |
| Router / tool service | Pure Python, no syscalls |
| All DB queries | `sqlite3` — cross-platform |
| Config paths (`~/.kathoros/`) | `Path.home()` — cross-platform |

---

## 5. Recommended Porting Sequence

### Phase 1 — Make the app launchable (1–2 days)

1. Remove `QT_QPA_PLATFORM=xcb` from `build_appimage.sh` AppRun block
2. Add `uname` guard to `build_appimage.sh` to prevent it running on macOS
3. Create `scripts/build_macos.sh` with PyInstaller macOS flags
4. Update shell fallback message to be platform-aware (§2.1)

### Phase 2 — Restore shell functionality (2–5 days)

Choose one of the three options in §1.1:

- **Option C** (disable + message): 1 hour, ships with Phase 1
- **Option B** (PTY widget): 2–3 days, no external deps
- **Option A** (QTermWidget): 3–5 days, requires matching Homebrew Qt version

### Phase 3 — Distribution (1–3 days)

1. Create `scripts/make_dmg.sh` using `create-dmg` or `hdiutil`
2. Set up code signing (`codesign`)
3. Set up notarization (`xcrun notarytool`)
4. Test Gatekeeper behavior on a clean macOS VM

### Phase 4 — Polish (ongoing)

- Shell: read `$SHELL` instead of hardcoding `bash` (§2.2)
- Test font rendering differences (macOS renders at higher DPI by default)
- Test `QSettings` storage path (`~/Library/Preferences/` on macOS vs `~/.config/`)
- Verify Ollama macOS app is running at `localhost:11434` (same port)

---

## 6. Dependency Availability on macOS

| Package | macOS install | Notes |
|---|---|---|
| Python 3.13 | `brew install python@3.13` or conda | ✓ |
| PyQt6 6.10.x | `pip install PyQt6` | ✓ macOS 11+ |
| PyMuPDF | `pip install pymupdf` | ✓ |
| GitPython | `pip install gitpython` | Requires `git` (Xcode CLT) |
| anthropic / httpx | `pip install anthropic` | ✓ |
| matplotlib / networkx | `pip install matplotlib networkx` | ✓ |
| Pygments | `pip install Pygments` | ✓ |
| ollama (Python client) | `pip install ollama` | Requires Ollama macOS app |
| SageMath | `conda install -c conda-forge sage` | ✓ slower install |
| QTermWidget (if chosen) | `brew install qtermwidget` + build bindings | Qt version must match PyQt6 |
| xterm (if chosen) | Requires XQuartz + `brew install xterm` | Not recommended |

---

*All file references are relative to `kathoros_main/`.*
