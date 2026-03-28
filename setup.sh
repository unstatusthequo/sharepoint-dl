#!/usr/bin/env bash
# Bootstrap script for sharepoint-dl (macOS/Linux)
# Usage: ./setup.sh
set -e

echo "=== SharePoint Bulk Downloader Setup ==="
echo

# Prefer uv (handles everything cleanly)
if command -v uv &>/dev/null; then
    echo "Found uv at $(command -v uv)"
else
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Clean any corrupted state
rm -rf .venv uv.lock 2>/dev/null || true

# Let uv handle Python + venv + deps in one shot
echo
echo "Installing Python, dependencies, and project..."
uv lock
uv sync

# Playwright browser
echo
echo "Installing Chromium browser for authentication..."
uv run playwright install chromium

echo
echo "=== Setup Complete ==="
echo
echo "To use:"
echo "  uv run sharepoint-dl"
echo
echo "Or activate the venv:"
echo "  source .venv/bin/activate"
echo "  sharepoint-dl"
