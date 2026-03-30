# Architecture

**Analysis Date:** 2026-03-30

## Pattern Overview

**Overall:** Single-package CLI with layered file-backed workflow

**Key Characteristics:**
- One main Typer CLI entry point in `sharepoint_dl/cli/main.py`
- Browser-based auth via Playwright, then plain `requests.Session` usage for API calls
- File-backed state in the destination directory (`state.json`, `manifest.json`)
- Concurrent worker pool for downloads, with retry and resume behavior

## Layers

**Command / Presentation Layer:**
- Purpose: Parse CLI arguments, drive the interactive flow, and format terminal output
- Contains: Typer commands, prompts, progress display, status reporting
- Depends on: auth, enumeration, downloader, state, manifest modules
- Used by: `sharepoint_dl/__main__.py`, the `sharepoint-dl` console script

**Auth Layer:**
- Purpose: Acquire and reuse SharePoint session cookies
- Contains: Playwright session harvest and session loading/validation
- Depends on: Playwright, `requests`, local session file storage
- Used by: CLI before any enumeration or download work

**Enumeration Layer:**
- Purpose: Walk SharePoint folders and produce a list of files to download
- Contains: REST pagination handling, recursive traversal, auth-expiry detection
- Depends on: authenticated `requests.Session`, SharePoint REST endpoints
- Used by: `list` and `download` CLI flows

**Download / Orchestration Layer:**
- Purpose: Stream files, manage concurrency, retry failures, and respect auth expiry
- Contains: worker pool, `.part` handling, checksum calculation, retry logic
- Depends on: `FileEntry`, `JobState`, `tenacity`, `rich.progress`
- Used by: CLI download flow

**State / Output Layer:**
- Purpose: Persist progress and generate forensic output artifacts
- Contains: `JobState`, `state.json`, `generate_manifest`
- Depends on: destination directory, tracked file metadata, completed download state
- Used by: downloader and CLI reporting

## Data Flow

**Interactive Download Flow:**

1. User runs `sharepoint-dl` or `python -m sharepoint_dl`
2. `sharepoint_dl/cli/main.py` parses the sharing URL and enters interactive mode
3. Auth is loaded from `~/.sharepoint-dl/session.json` or harvested via `sharepoint_dl/auth/browser.py`
4. The CLI resolves the target folder and calls `enumerate_files()` from `sharepoint_dl/enumerator/traversal.py`
5. `download_all()` in `sharepoint_dl/downloader/engine.py` initializes `JobState` and downloads files concurrently
6. Each file is streamed to a `.part` file, hashed, verified, and renamed into place
7. `sharepoint_dl/manifest/writer.py` emits `manifest.json` from the persisted state
8. The CLI prints a completeness report and exits with a status code that reflects success or failure

**List Flow:**

1. User runs `sharepoint-dl list <url> --root-folder <path>`
2. CLI loads and validates the cached session
3. `enumerate_files()` walks the folder tree
4. CLI groups the returned `FileEntry` objects into a summary table

**State Management:**
- Authentication state lives outside the repo in `~/.sharepoint-dl/session.json`
- Download progress lives beside the output in `state.json`
- Manifest output is generated from `JobState`, not by re-reading downloaded files
- Atomic temp-rename writes are used for both `state.json` and `manifest.json`

## Key Abstractions

**`FileEntry`:**
- Purpose: Canonical representation of a discovered SharePoint file
- Examples: `sharepoint_dl.enumerator.traversal.FileEntry`
- Pattern: Dataclass used as the unit of work for downloads

**`JobState`:**
- Purpose: Track per-file lifecycle and resume metadata
- Examples: `sharepoint_dl.state.job_state.JobState`
- Pattern: Thread-safe in-memory map with atomic disk persistence

**`FileStatus`:**
- Purpose: Represent per-file lifecycle states
- Examples: `PENDING`, `DOWNLOADING`, `COMPLETE`, `FAILED`
- Pattern: String enum for persisted state interoperability

**Retry / Halt Controls:**
- Purpose: Separate transient HTTP retries from auth-expiry cancellation
- Examples: `WaitRetryAfter`, `AuthExpiredError`
- Pattern: Exception-driven control flow with tenacity wrappers

## Entry Points

**Console Script Entry:**
- Location: `sharepoint_dl.cli.main:app` from `pyproject.toml`
- Triggers: `sharepoint-dl <command>`
- Responsibilities: Register commands, dispatch to handlers, manage prompts and output

**Module Entry:**
- Location: `sharepoint_dl/__main__.py`
- Triggers: `python -m sharepoint_dl`
- Responsibilities: Import and invoke the Typer app

**Command Handlers:**
- Location: `sharepoint_dl/cli/main.py`
- Triggers: `auth`, `list`, `download`, and interactive default mode
- Responsibilities: Orchestrate the full workflow around the lower-level modules

## Error Handling

**Strategy:** Raise domain-specific exceptions for auth expiry, use tenacity for retryable HTTP failures, and let the CLI convert outcomes into exit codes

**Patterns:**
- `AuthExpiredError` stops enumeration or download immediately when SharePoint returns 401/403
- `requests.HTTPError` is retried for transient failures in `_fetch_page()` and `_download_file()`
- CLI catches auth expiry and keyboard interrupts to preserve state and emit a deterministic report

## Cross-Cutting Concerns

**Logging:**
- `logging.getLogger(__name__)` is used in traversal and downloader modules for retry diagnostics

**Validation:**
- Session validation probes `/_api/web/title` before work starts
- Downloaded file size is checked against the enumerated `Length`
- Local output paths are normalized and safety-checked in `sharepoint_dl/state/job_state.py`

**Progress / UX:**
- Rich progress updates are driven from the download worker pool
- The CLI keeps the operator informed with section headers, summaries, and completion reports

**Persistence:**
- Resume and forensic output are file-based, not database-backed
- `state.json` and `manifest.json` are written atomically to avoid partial-file corruption

---

*Architecture analysis: 2026-03-30*
*Update when major patterns change*
