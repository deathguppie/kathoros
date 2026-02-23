#!/usr/bin/env bash
# build_appimage.sh — Build a portable Kathoros AppImage
#
# DEFAULT (recommended): builds inside a Docker container based on Ubuntu 22.04
# (glibc 2.35), so the AppImage runs on any distro with glibc >= 2.35.
#
# Flags:
#   --local    Skip Docker; build directly on this machine.
#              Only suitable for local testing — portability is not guaranteed
#              because the binary will require the host's glibc version.
#   --rebuild  Force rebuild of the Docker image before building.
#
# Usage:
#   bash scripts/build_appimage.sh            # Docker build (portable)
#   bash scripts/build_appimage.sh --local    # Local build (dev/test only)
#   bash scripts/build_appimage.sh --rebuild  # Rebuild Docker image first
#
# Output: dist/Kathoros-x86_64.AppImage

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist"
BUILD_DIR="$REPO_ROOT/build"
APPDIR="$BUILD_DIR/Kathoros.AppDir"
ICON="$REPO_ROOT/kathoros/assets/logo.jpg"
DOCKER_IMAGE="kathoros-builder"

USE_LOCAL=0
REBUILD_IMAGE=0
for arg in "$@"; do
    case "$arg" in
        --local)   USE_LOCAL=1 ;;
        --rebuild) REBUILD_IMAGE=1 ;;
    esac
done

cd "$REPO_ROOT"

# ── Docker path (default) ─────────────────────────────────────────────────────
if [[ $USE_LOCAL -eq 0 ]]; then
    if ! command -v docker &>/dev/null; then
        echo "Docker not found. Falling back to local build."
        echo "WARNING: resulting AppImage requires glibc $(ldd --version 2>&1 | head -1 | grep -oP '\d+\.\d+$')."
        USE_LOCAL=1
    fi
fi

if [[ $USE_LOCAL -eq 0 ]]; then
    echo "==> Docker build (Ubuntu 22.04, glibc 2.35 target)"

    # Build or pull Docker image
    if [[ $REBUILD_IMAGE -eq 1 ]] || ! docker image inspect "$DOCKER_IMAGE" &>/dev/null; then
        echo "==> Building Docker image '$DOCKER_IMAGE'..."
        docker build -f "$REPO_ROOT/Dockerfile.build" -t "$DOCKER_IMAGE" "$REPO_ROOT"
    else
        echo "==> Using existing Docker image '$DOCKER_IMAGE' (pass --rebuild to refresh)"
    fi

    mkdir -p "$DIST_DIR"

    # Run the build inside Docker, mounting source and dist/
    docker run --rm \
        -v "$REPO_ROOT:/build:ro" \
        -v "$DIST_DIR:/build/dist" \
        -v "$BUILD_DIR:/build/build" \
        --env ARCH=x86_64 \
        "$DOCKER_IMAGE" \
        "bash /build/scripts/build_appimage.sh --local"

    echo ""
    echo "==> Done (Docker build)"
    echo "    Output: $DIST_DIR/Kathoros-x86_64.AppImage"
    [[ -f "$DIST_DIR/Kathoros-x86_64.AppImage" ]] && \
        echo "    Size:   $(du -sh "$DIST_DIR/Kathoros-x86_64.AppImage" | cut -f1)"
    exit 0
fi

# ── Local build ───────────────────────────────────────────────────────────────
GLIBC_VER=$(ldd --version 2>&1 | head -1 | grep -oP '\d+\.\d+' | tail -1 || echo "unknown")
echo "==> Local build (glibc $GLIBC_VER — AppImage requires glibc >= $GLIBC_VER)"

# 1. Locate / install tools ---------------------------------------------------
if ! python -c "import PyInstaller" 2>/dev/null; then
    echo "    Installing PyInstaller..."
    pip install pyinstaller
fi

APPIMAGETOOL=""
for candidate in \
    /usr/local/bin/appimagetool \
    "$REPO_ROOT/appimagetool-x86_64.AppImage" \
    "$HOME/.local/bin/appimagetool" \
    "$(which appimagetool 2>/dev/null || true)"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
        APPIMAGETOOL="$candidate"
        break
    fi
done

if [[ -z "$APPIMAGETOOL" ]]; then
    echo "    Downloading appimagetool..."
    TOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    curl -fsSL -o "$REPO_ROOT/appimagetool-x86_64.AppImage" "$TOOL_URL"
    chmod +x "$REPO_ROOT/appimagetool-x86_64.AppImage"
    APPIMAGETOOL="$REPO_ROOT/appimagetool-x86_64.AppImage"
fi

# 2. PyInstaller bundle -------------------------------------------------------
echo "==> Running PyInstaller..."
rm -rf "$DIST_DIR/kathoros" "$BUILD_DIR/pyinstaller_work"

pyinstaller \
    --noconfirm \
    --clean \
    --name kathoros \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR/pyinstaller_work" \
    --add-data "kathoros/assets:kathoros/assets" \
    --hidden-import "PyQt6.QtWidgets" \
    --hidden-import "PyQt6.QtCore" \
    --hidden-import "PyQt6.QtGui" \
    --hidden-import "PyQt6.QtNetwork" \
    --hidden-import "PyQt6.QtSvg" \
    --hidden-import "fitz" \
    --hidden-import "anthropic" \
    --hidden-import "httpx" \
    --hidden-import "pygments" \
    --hidden-import "pygments.lexers" \
    --hidden-import "pygments.styles" \
    --hidden-import "git" \
    --hidden-import "ollama" \
    --collect-all "fitz" \
    --collect-all "pygments" \
    --collect-all "anthropic" \
    --collect-submodules "kathoros" \
    main.py

# 3. Assemble AppDir ----------------------------------------------------------
echo "==> Assembling AppDir..."
rm -rf "$APPDIR"
mkdir -p \
    "$APPDIR/usr/bin" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -r "$DIST_DIR/kathoros/." "$APPDIR/usr/bin/"

cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
export LD_LIBRARY_PATH="$HERE/usr/bin/_internal:${LD_LIBRARY_PATH:-}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
exec "$HERE/usr/bin/kathoros" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

cat > "$APPDIR/usr/share/applications/kathoros.desktop" << 'DESKTOP'
[Desktop Entry]
Name=Kathoros
Comment=Physics Research Platform
Exec=kathoros
Icon=kathoros
Type=Application
Categories=Science;Education;
Terminal=false
DESKTOP
ln -sf usr/share/applications/kathoros.desktop "$APPDIR/kathoros.desktop"

# Icon: prefer png (appimagetool works better with it)
if command -v convert &>/dev/null; then
    convert "$ICON" "$APPDIR/usr/share/icons/hicolor/256x256/apps/kathoros.png"
    cp "$APPDIR/usr/share/icons/hicolor/256x256/apps/kathoros.png" "$APPDIR/kathoros.png"
elif command -v ffmpeg &>/dev/null; then
    ffmpeg -i "$ICON" "$APPDIR/kathoros.png" -y -loglevel error
else
    # appimagetool accepts jpeg too if renamed .png (it reads the magic bytes)
    cp "$ICON" "$APPDIR/kathoros.png"
fi

# 4. Pack AppImage ------------------------------------------------------------
echo "==> Packing AppImage..."
mkdir -p "$DIST_DIR"
OUTPUT="$DIST_DIR/Kathoros-x86_64.AppImage"
ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "$OUTPUT"

echo ""
echo "Done: $OUTPUT"
echo "Size: $(du -sh "$OUTPUT" | cut -f1)"
echo "Requires: glibc >= $GLIBC_VER"
