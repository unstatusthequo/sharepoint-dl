# Technology Stack

**Analysis Date:** 2026-03-30

## Languages

**Primary:**
- Python 3.11-3.13 - All application code in `sharepoint_dl/` and tests in `tests/`

**Secondary:**
- Bash - Setup/run scripts such as `run.sh` and `setup.sh`
- PowerShell - Windows setup/run scripts such as `run.ps1` and `setup.ps1`

## Runtime

**Environment:**
- CPython 3.11 or newer, but below 3.14, as declared in `pyproject.toml`
- Chromium browser installed by Playwright for auth flows

**Package Manager:**
- `uv` - Used by the setup scripts and manual install flow in `README.md`
- Lockfile: `uv.lock` present

## Frameworks

**Core:**
- None - This is a CLI-first Python application, not a web app

**Testing:**
- `pytest` - Unit test runner configured in `pyproject.toml`

**Build/Dev:**
- `hatchling` - Build backend declared in `pyproject.toml`
- `ruff` - Linting configuration in `pyproject.toml`
- `playwright` - Browser automation dependency for interactive auth

## Key Dependencies

**Critical:**
- `playwright` - Launches Chromium and captures authenticated SharePoint session state in `sharepoint_dl/auth/browser.py`
- `requests` - HTTP client for SharePoint REST calls, session validation, and file downloads in `sharepoint_dl/auth/session.py` and `sharepoint_dl/downloader/engine.py`
- `typer` - CLI entrypoint and command wiring in `sharepoint_dl/cli/main.py`
- `rich` - Interactive terminal UI, prompts, tables, progress bars, and status output in `sharepoint_dl/cli/main.py` and `sharepoint_dl/downloader/engine.py`
- `tenacity` - Retry policy for SharePoint API pagination and download retries in `sharepoint_dl/enumerator/traversal.py` and `sharepoint_dl/downloader/engine.py`

**Infrastructure:**
- Python standard library - `pathlib`, `hashlib`, `json`, `threading`, `concurrent.futures`, and `urllib.parse` underpin the app

## Configuration

**Environment:**
- No required environment variables
- Runtime state is persisted under `~/.sharepoint-dl/session.json` for browser auth reuse

**Build:**
- `pyproject.toml` - Project metadata, dependencies, scripts, pytest, and ruff settings
- `requirements.txt` - Alternate dependency listing for non-`uv` installs

## Platform Requirements

**Development:**
- Cross-platform: macOS, Linux, and Windows are all supported
- Chromium must be available for the auth flow, but Playwright installs it during setup

**Production:**
- Distributed as a local CLI tool rather than a hosted service
- Runs in the user's terminal against their SharePoint tenant and local download destination

---

*Stack analysis: 2026-03-30*
*Update after major dependency changes*
