#!/usr/bin/env bash
# Launcher for sharepoint-dl
DIR="$(cd "$(dirname "$0")" && pwd)"

# Ensure venv exists
if [ ! -d "$DIR/.venv" ]; then
    echo "First run — setting up..."
    cd "$DIR"
    uv lock 2>/dev/null
    uv sync
    uv run playwright install chromium
fi

# Run via python -m (bypasses broken entrypoint scripts)
"$DIR/.venv/bin/python3" -m sharepoint_dl "$@"
