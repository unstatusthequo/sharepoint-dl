# Bootstrap script for sharepoint-dl (Windows)
# Usage: powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"

Write-Host "=== SharePoint Bulk Downloader Setup ===" -ForegroundColor Cyan
Write-Host ""

# Check for uv
try {
    $uvPath = (Get-Command uv -ErrorAction SilentlyContinue).Source
    Write-Host "Found uv at $uvPath" -ForegroundColor Green
} catch {
    Write-Host "Installing uv..." -ForegroundColor Yellow
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
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
Write-Host "  uv run sharepoint-dl"
Write-Host ""
Write-Host "Or activate the venv:" -ForegroundColor Cyan
Write-Host "  .venv\Scripts\Activate.ps1"
Write-Host "  sharepoint-dl"
