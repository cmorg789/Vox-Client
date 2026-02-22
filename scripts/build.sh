#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV="$PROJECT_ROOT/.venv"

cd "$PROJECT_ROOT"

# Check for venv
if [ ! -d "$VENV" ]; then
    echo "ERROR: .venv not found at $VENV"
    echo "Create it with: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'"
    exit 1
fi

PYTHON="$VENV/bin/python"

# Ensure pyinstaller is installed
if ! "$PYTHON" -m PyInstaller --version &>/dev/null; then
    echo "Installing PyInstaller..."
    "$VENV/bin/pip" install "pyinstaller>=6.0"
fi

# Clean previous builds
echo "Cleaning build/ and dist/..."
rm -rf build/ dist/

# Run PyInstaller
echo "Building with PyInstaller..."
"$PYTHON" -m PyInstaller vox-client.spec --noconfirm

echo ""
echo "Build complete!"
echo ""

if [ "$(uname)" = "Darwin" ]; then
    echo "macOS app bundle: dist/Vox Client.app"
    echo "  Launch:  open \"dist/Vox Client.app\""
    echo "  Direct:  dist/Vox Client.app/Contents/MacOS/vox-client"
else
    echo "Linux distributable: dist/vox-client/"
    echo "  Launch: ./dist/vox-client/vox-client"
fi
