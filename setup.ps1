# Bootstrap script for sharepoint-dl (Windows)
# Usage: powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"

Write-Host "=== SharePoint Bulk Downloader Setup ===" -ForegroundColor Cyan
Write-Host ""

# Find or install uv
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if ($uvCmd) {
    Write-Host "Found uv at $($uvCmd.Source)" -ForegroundColor Green
} else {
    Write-Host "Installing uv..." -ForegroundColor Yellow
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression

    # Add uv to PATH for this session
    $uvHome = "$env:USERPROFILE\.local\bin"
    if (-not (Test-Path $uvHome)) {
        $uvHome = "$env:USERPROFILE\.cargo\bin"
    }
    if (Test-Path $uvHome) {
        $env:PATH = "$uvHome;$env:PATH"
        Write-Host "Added $uvHome to PATH" -ForegroundColor Green
    }

    # Verify uv is now available
    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCmd) {
        Write-Host "ERROR: uv installed but not found in PATH." -ForegroundColor Red
        Write-Host "Close this terminal, open a new one, and re-run setup.ps1" -ForegroundColor Yellow
        exit 1
    }
}

# Clean any corrupted state
Remove-Item -Recurse -Force .venv, uv.lock -ErrorAction SilentlyContinue

# Let uv handle Python + venv + deps
Write-Host ""
Write-Host "Installing Python, dependencies, and project..."
uv lock
uv sync

# Playwright browser
Write-Host ""
Write-Host "Installing Chromium browser for authentication..."
uv run playwright install chromium

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "To use:" -ForegroundColor Cyan
Write-Host "  .\run.ps1"
