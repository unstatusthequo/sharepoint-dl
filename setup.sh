#!/usr/bin/env bash
# Bootstrap script for sharepoint-dl (macOS/Linux)
# Usage: ./setup.sh
set -e

echo "=== SharePoint Bulk Downloader Setup ==="
echo

# Check for Python 3.11-3.13
PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ] && [ "$minor" -le 13 ]; then
            PYTHON="$cmd"
            echo "Found Python $ver at $(command -v "$cmd")"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Python 3.11-3.13 not found. Installing via uv..."
    if ! command -v uv &>/dev/null; then
        echo "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    fi
    uv python install 3.13
    PYTHON="$(uv python find 3.13)"
    echo "Installed Python 3.13 at $PYTHON"
fi

# Create venv
echo
echo "Creating virtual environment..."
"$PYTHON" -m venv .venv

# Activate
source .venv/bin/activate

# Install
echo "Installing dependencies..."
pip install --upgrade pip -q
pip install -e . -q

# Playwright browser
echo "Installing Chromium browser for authentication..."
playwright install chromium

echo
echo "=== Setup Complete ==="
echo
echo "To use:"
echo "  source .venv/bin/activate"
echo "  sharepoint-dl --help"
echo
echo "Quick start:"
echo "  sharepoint-dl auth '<sharepoint-url>'"
echo "  sharepoint-dl list '<url>' -r '<folder-path>'"
echo "  sharepoint-dl download '<url>' /path/to/dest -r '<folder-path>' --flat"
