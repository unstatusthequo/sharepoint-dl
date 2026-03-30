#!/usr/bin/env bash
# Launcher for sharepoint-dl
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Quick import check — rebuild venv if broken
if [ -d "$DIR/.venv" ]; then
    "$DIR/.venv/bin/python3" -c "import sharepoint_dl" 2>/dev/null || {
        echo "Repairing environment..."
        rm -rf .venv
    }
fi

# Ensure venv exists and is healthy
if [ ! -d "$DIR/.venv" ]; then
    echo "Setting up environment..."
    uv lock 2>/dev/null
    uv sync
    uv run playwright install chromium
fi

# Run via python -m (bypasses broken entrypoint scripts)
"$DIR/.venv/bin/python3" -m sharepoint_dl "$@"
