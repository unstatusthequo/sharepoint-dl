#!/usr/bin/env bash
# Launcher for sharepoint-dl
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Deep import check — rebuild venv if any dependency is broken
if [ -d "$DIR/.venv" ]; then
    "$DIR/.venv/bin/python3" -c "from sharepoint_dl.cli.main import app" 2>/dev/null || {
        echo "Repairing environment..."
        rm -rf .venv
    }
fi

# Ensure venv exists and is healthy
if [ ! -d "$DIR/.venv" ]; then
    echo "Setting up environment..."
    uv lock 2>/dev/null
    uv sync
    "$DIR/.venv/bin/python3" -m playwright install chromium
fi

# Playwright health check — driver can break when Node.js upgrades
if ! "$DIR/.venv/bin/python3" -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    pass
" 2>/dev/null; then
    echo "Repairing Playwright (driver mismatch)..."
    uv pip install --force-reinstall playwright 2>/dev/null
    "$DIR/.venv/bin/python3" -m playwright install chromium 2>/dev/null
fi

# Run via python -m (bypasses broken entrypoint scripts)
"$DIR/.venv/bin/python3" -m sharepoint_dl "$@"
