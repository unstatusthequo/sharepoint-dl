# Launcher for sharepoint-dl (Windows)
$ErrorActionPreference = "Stop"
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path "$Dir\.venv")) {
    Write-Host "First run - setting up..."
    Set-Location $Dir
    uv lock 2>$null
    uv sync
    uv run playwright install chromium
}

& "$Dir\.venv\Scripts\python.exe" -m sharepoint_dl @args
