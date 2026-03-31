#!/usr/bin/env bash
# Launcher for sharepoint-dl
# Handles: uv installation, venv creation, dependency sync, Playwright browser
# install, and Playwright driver health checks. Users clone and run — no manual
# setup required.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# ── 1. Ensure uv is available ──────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Refresh PATH so uv is available in this session
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        echo "Error: uv installation failed. Install manually: https://docs.astral.sh/uv/"
        exit 1
    fi
fi

# ── 2. Deep import check — rebuild venv if any core dependency is broken ───
if [ -d "$DIR/.venv" ]; then
    "$DIR/.venv/bin/python3" -c "from sharepoint_dl.cli.main import app" 2>/dev/null || {
        echo "Repairing environment (broken dependency detected)..."
        rm -rf "$DIR/.venv"
    }
fi

# ── 3. Ensure venv exists and dependencies are synced ──────────────────────
if [ ! -d "$DIR/.venv" ]; then
    echo "Setting up environment..."
    uv sync 2>&1 | grep -v "^$" || true
    echo "Installing Chromium browser for authentication..."
    "$DIR/.venv/bin/python3" -m playwright install chromium 2>&1 | tail -1 || true
fi

# ── 4. Playwright health check — driver breaks when Node.js upgrades ──────
if ! "$DIR/.venv/bin/python3" -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    pass
" 2>/dev/null; then
    echo "Repairing Playwright (driver mismatch with Node.js)..."
    uv pip install --force-reinstall playwright 2>/dev/null
    "$DIR/.venv/bin/python3" -m playwright install chromium 2>/dev/null
    # Verify the repair worked
    if ! "$DIR/.venv/bin/python3" -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    pass
" 2>/dev/null; then
        echo "Error: Playwright repair failed. Try: rm -rf .venv && ./run.sh"
        exit 1
    fi
fi

# ── 5. Launch ──────────────────────────────────────────────────────────────
exec "$DIR/.venv/bin/python3" -m sharepoint_dl "$@"
