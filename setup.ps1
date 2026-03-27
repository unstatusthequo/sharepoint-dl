# Bootstrap script for sharepoint-dl (Windows)
# Usage: powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"

Write-Host "=== SharePoint Bulk Downloader Setup ===" -ForegroundColor Cyan
Write-Host ""

# Check for Python 3.11-3.13
$python = $null
foreach ($cmd in @("python3", "python", "py")) {
    try {
        $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($ver) {
            $parts = $ver.Split(".")
            $major = [int]$parts[0]
            $minor = [int]$parts[1]
            if ($major -eq 3 -and $minor -ge 11 -and $minor -le 13) {
                $python = $cmd
                $path = (Get-Command $cmd).Source
                Write-Host "Found Python $ver at $path" -ForegroundColor Green
                break
            }
        }
    } catch {}
}

# Try py launcher with version flag
if (-not $python) {
    try {
        $ver = & py -3.13 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($ver) {
            $python = "py -3.13"
            Write-Host "Found Python $ver via py launcher" -ForegroundColor Green
        }
    } catch {}
}

if (-not $python) {
    Write-Host "Python 3.11-3.13 not found." -ForegroundColor Red
    Write-Host ""
    Write-Host "Install Python from: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  - Download Python 3.13"
    Write-Host "  - CHECK 'Add python.exe to PATH' during install"
    Write-Host "  - Re-run this script after installing"
    exit 1
}

# Create venv
Write-Host ""
Write-Host "Creating virtual environment..."
if ($python -like "py *") {
    & py -3.13 -m venv .venv
} else {
    & $python -m venv .venv
}

# Activate
. .venv\Scripts\Activate.ps1

# Install
Write-Host "Installing dependencies..."
pip install --upgrade pip -q
pip install -e . -q

# Playwright browser
Write-Host "Installing Chromium browser for authentication..."
playwright install chromium

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "To use:" -ForegroundColor Cyan
Write-Host "  .venv\Scripts\Activate.ps1"
Write-Host '  sharepoint-dl --help'
Write-Host ""
Write-Host "Quick start:" -ForegroundColor Cyan
Write-Host '  sharepoint-dl auth "<sharepoint-url>"'
Write-Host '  sharepoint-dl list "<url>" -r "<folder-path>"'
Write-Host '  sharepoint-dl download "<url>" D:\evidence -r "<folder-path>" --flat'
