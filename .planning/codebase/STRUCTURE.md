# Codebase Structure

**Analysis Date:** 2026-03-30

## Directory Layout

```
sharepoint_dl/
├── auth/            # Browser auth and session persistence
├── cli/             # Typer command handlers and interactive flow
├── downloader/      # Streaming download engine and concurrency
├── enumerator/      # SharePoint folder traversal and file discovery
├── manifest/        # Forensic manifest generation
├── state/           # Resume state and local path helpers
├── __main__.py      # `python -m sharepoint_dl` entry point
└── __init__.py      # Package version
tests/               # Unit tests for each module
.planning/           # GSD planning artifacts, including codebase map
README.md            # User-facing install and usage guide
pyproject.toml       # Project metadata, dependencies, and script entry
requirements.txt     # Dependency pin snapshot for setup scripts
uv.lock              # Locked dependency resolution for uv
run.sh               # Unix launcher wrapper
run.ps1              # Windows launcher wrapper
setup.sh             # Unix bootstrap script
setup.ps1            # Windows bootstrap script
```

## Directory Purposes

**sharepoint_dl/**
- Purpose: Main Python package for the downloader
- Contains: CLI, auth, enumeration, download, manifest, and state modules
- Key files: `sharepoint_dl/cli/main.py`, `sharepoint_dl/downloader/engine.py`, `sharepoint_dl/state/job_state.py`
- Subdirectories: `auth/`, `cli/`, `downloader/`, `enumerator/`, `manifest/`, `state/`

**sharepoint_dl/auth/**
- Purpose: Authentication and session persistence helpers
- Contains: Playwright session harvest, session load/validate logic
- Key files: `sharepoint_dl/auth/browser.py`, `sharepoint_dl/auth/session.py`
- Subdirectories: None

**sharepoint_dl/cli/**
- Purpose: CLI command registration and interactive orchestration
- Contains: Typer app, command handlers, prompt helpers, URL parsing
- Key files: `sharepoint_dl/cli/main.py`
- Subdirectories: None

**sharepoint_dl/downloader/**
- Purpose: File streaming, retries, worker coordination, progress display
- Contains: Concurrent download engine and local path resolution
- Key files: `sharepoint_dl/downloader/engine.py`
- Subdirectories: None

**sharepoint_dl/enumerator/**
- Purpose: SharePoint REST traversal and file discovery
- Contains: Pagination, recursion, file entry modeling
- Key files: `sharepoint_dl/enumerator/traversal.py`
- Subdirectories: None

**sharepoint_dl/manifest/**
- Purpose: Build `manifest.json` from completed download state
- Contains: Manifest writer
- Key files: `sharepoint_dl/manifest/writer.py`
- Subdirectories: None

**sharepoint_dl/state/**
- Purpose: Track per-file status and resume metadata
- Contains: `JobState`, `FileStatus`, path derivation helpers
- Key files: `sharepoint_dl/state/job_state.py`
- Subdirectories: None

**tests/**
- Purpose: Unit tests for package modules and command behavior
- Contains: Pytest test modules with fixtures and mocks
- Key files: `tests/test_auth.py`, `tests/test_cli.py`, `tests/test_downloader.py`, `tests/test_manifest.py`, `tests/test_state.py`, `tests/test_traversal.py`, `tests/conftest.py`
- Subdirectories: None

**.planning/**
- Purpose: GSD planning and status artifacts
- Contains: `STATE.md`, roadmap/phase docs, codebase map documents
- Key files: `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/codebase/*.md`
- Subdirectories: `codebase/`, `phases/`, `research/`

## Key File Locations

**Entry Points:**
- `sharepoint_dl/__main__.py` - module entry point for `python -m sharepoint_dl`
- `sharepoint_dl/cli/main.py` - Typer app and command handlers

**Configuration:**
- `pyproject.toml` - project metadata, dependencies, console script, pytest and ruff config
- `requirements.txt` - dependency snapshot for bootstrap scripts
- `uv.lock` - resolved dependency lockfile

**Core Logic:**
- `sharepoint_dl/auth/browser.py` - Playwright auth session harvest
- `sharepoint_dl/auth/session.py` - session load, save, and validation
- `sharepoint_dl/enumerator/traversal.py` - recursive SharePoint file enumeration
- `sharepoint_dl/downloader/engine.py` - concurrent streaming downloads and retries
- `sharepoint_dl/state/job_state.py` - persistent resume state
- `sharepoint_dl/manifest/writer.py` - manifest generation

**Testing:**
- `tests/` - pytest test modules for auth, CLI, traversal, downloader, state, and manifest behavior
- `tests/conftest.py` - shared fixtures and mock response builders

**Documentation:**
- `README.md` - installation, usage, and troubleshooting
- `.planning/STATE.md` - project state and milestone history
- `.planning/codebase/*.md` - generated codebase map docs

## Naming Conventions

**Files:**
- `snake_case.py` for Python modules, matching package structure
- `test_*.py` for test modules, grouped by target module
- `run.sh` / `run.ps1` for launcher scripts
- `setup.sh` / `setup.ps1` for bootstrap scripts

**Directories:**
- Lowercase package directories with underscores avoided in directory names
- Short, domain-based package names: `auth`, `cli`, `downloader`, `enumerator`, `manifest`, `state`

**Special Patterns:**
- `__main__.py` for module execution
- `__init__.py` for package markers and exported symbols
- `.planning/codebase/*.md` for generated mapping documents

## Where to Add New Code

**New Feature:**
- Primary code: the closest existing domain package under `sharepoint_dl/`
- Tests: `tests/test_<domain>.py`
- Config if needed: `pyproject.toml`

**New CLI Command:**
- Definition: `sharepoint_dl/cli/main.py`
- Shared helpers: `sharepoint_dl/cli/` if command logic is split out later
- Tests: `tests/test_cli.py`

**New Downloader or State Behavior:**
- Implementation: `sharepoint_dl/downloader/engine.py` or `sharepoint_dl/state/job_state.py`
- Tests: `tests/test_downloader.py` or `tests/test_state.py`

**New SharePoint API Flow:**
- Enumeration logic: `sharepoint_dl/enumerator/traversal.py`
- Auth/session support: `sharepoint_dl/auth/session.py`
- Tests: `tests/test_traversal.py` or `tests/test_auth.py`

**New Manifest Fields:**
- Implementation: `sharepoint_dl/manifest/writer.py`
- Tests: `tests/test_manifest.py`

## Special Directories

**.planning/codebase/**
- Purpose: Generated codebase map for planning and future maintenance work
- Source: Written by GSD mapper agents
- Committed: Yes, because `.planning/` is already part of the repo

**`~/.sharepoint-dl/`**
- Purpose: Runtime auth session storage outside the repo
- Source: Created by `sharepoint_dl/auth/session.py` and `sharepoint_dl/auth/browser.py`
- Committed: No, user-local runtime state

---

*Structure analysis: 2026-03-30*
*Update when directory structure changes*
