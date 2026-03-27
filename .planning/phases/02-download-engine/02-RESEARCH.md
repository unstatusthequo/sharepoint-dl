# Phase 2: Download Engine - Research

**Researched:** 2026-03-27
**Domain:** Streaming file download, resume/state management, concurrent workers, Rich progress UI
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Download Concurrency**
- 3 concurrent downloads via ThreadPoolExecutor (sweet spot for large files on typical connections)
- Configurable via `--workers` flag (default 3, range 1-8)
- Each worker handles one file at a time — no splitting individual files across workers
- Workers share a single requests.Session (thread-safe for reads)

**Streaming & Chunk Size**
- Stream downloads with `requests.get(stream=True)` + `iter_content(chunk_size=8_388_608)` (8MB chunks)
- Write chunks to a `.part` temp file; rename to final name on completion
- Compute SHA-256 incrementally during download (hash each chunk as it's written — single I/O pass)
- No in-memory buffering of full files

**Resume Behavior**
- State file (`state.json`) in the download destination directory tracks per-file status
- States: `pending`, `downloading`, `complete`, `failed`
- On re-run: skip `complete` files (verified by size match), retry `failed` and `downloading` (partial)
- Delete `.part` files for `downloading` state on resume (restart that file from scratch — simpler than byte-range resume for v1)
- State file written atomically (write to `.tmp`, rename) to survive crashes

**Error Handling**
- Per-file retry: 3 attempts with exponential backoff via tenacity (2s, 4s, 8s)
- 401/403 during download: halt ALL workers immediately, prompt re-auth (don't retry — session is dead)
- 429 (throttled): respect Retry-After header, retry up to 3 times
- Network errors / timeouts: retry per tenacity policy
- After all retries exhausted: mark file as `failed` in state, continue to next file
- At end of run: print explicit failed file list, exit with code 1 if any failures
- NEVER catch-and-swallow exceptions in the download loop

**Progress Display**
- Rich Live display with two levels:
  - Overall progress bar: "Downloading: 42/165 files (98.2 GB / 237.1 GB)"
  - Per-active-worker lines: "[worker 1] LAPTOP-5V7K1CJ4.E01 — 1.2 GB / 2.0 GB ████████░░ 60%"
- Update frequency: every chunk write (roughly every 8MB)
- On completion: summary table showing total files, total size, elapsed time, average speed
- On failure: red-highlighted failed files with error reason

**CLI Integration**
- `sharepoint-dl download <url> <dest> --root-folder <path>` — full pipeline
- `--workers N` — concurrency (default 3)
- `--root-folder` required (carried from Phase 1)
- Download command: auto-auth if needed → enumerate → confirm count → download → report

### Claude's Discretion
- Exact ThreadPoolExecutor shutdown/cancellation mechanics
- State file JSON schema details
- Temp file naming convention
- Download URL construction (download.aspx vs /$value — validate during research)
- Test fixture design for download engine

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DWNL-01 | Tool streams downloads in chunks (8MB) to handle files up to 2GB without memory issues | Locked: `requests.get(stream=True)` + `iter_content(chunk_size=8_388_608)`; confirmed by sp-dev-docs pitfalls |
| DWNL-02 | Tool resumes interrupted runs — skips completed files, retries failures | State file pattern with `pending`/`complete`/`failed`/`downloading` states; atomic write via temp-rename |
| DWNL-03 | Tool tracks all failures explicitly — no file is ever silently skipped | Explicit `failed` list; tenacity retry exhaustion marks file failed; never catch-and-swallow |
| DWNL-04 | Tool exits with non-zero code if any file fails to download | `raise typer.Exit(code=1)` when `len(failed) > 0` at run end |
| DWNL-05 | Tool downloads 2-4 files concurrently for speed | ThreadPoolExecutor with `max_workers=3` (configurable 1-8) |
| CLI-02 | Tool shows per-file and overall progress bars during download | Rich `Progress` with `add_task()` per worker + overall task; Live display thread-safe |
| CLI-03 | Tool shows clear error summary at end of run with file-level detail | Rich Table listing failed files with reason column; printed after executor joins |
</phase_requirements>

---

## Summary

Phase 2 builds the download loop on top of Phase 1's proven authenticated session and verified file list. The architecture is straightforward: a `ThreadPoolExecutor` with 3 workers draws from a queue of `FileEntry` objects produced by Phase 1's `enumerate_files()`, each worker streams one file at a time, and a `state.json` in the destination directory records progress for resume. The three non-negotiable constraints are streaming (never buffer a full file), explicit failure tracking (never swallow an exception), and auth-expiry detection (halt all workers on 401/403, do not retry).

The most significant open question from project-level research — which download URL to use for large files — is now resolved at the research level: `download.aspx` is confirmed as the correct endpoint. The `/$value` endpoint has a verified large-file bug (sp-dev-docs#5247) and `download.aspx` is the Microsoft-recommended alternative that supports byte-range requests. For guest sessions, the URL is constructed from the `ServerRelativeUrl` returned by the enumerator. The construction pattern and any required `?SourceUrl=` parameters must be validated against the actual target site before coding begins — this is a one-time probe, not a design risk.

The Rich progress display pattern is well-established for multi-threaded work: one `Progress` instance shared across threads, one `add_task()` call per worker (not per file), updated via `progress.update(task_id, advance=chunk_size)` from worker threads. The `requests.Session` is thread-safe for reads, so all workers share a single session — no locking required on the session itself. State file writes require a lock or atomic write pattern because multiple workers may complete simultaneously.

**Primary recommendation:** Build in this order — (1) state module with atomic write, (2) single-file download function with streaming + tenacity, (3) auth-halt mechanism, (4) ThreadPoolExecutor wrapper with shared progress, (5) CLI `download` command wiring. This order ensures each piece is testable independently before the concurrency layer is added.

---

## Standard Stack

### Core (all already in pyproject.toml)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `requests` | 2.33.0 | Streaming HTTP downloads | Already in project; `stream=True` + `iter_content()` is the correct pattern for 2GB files |
| `tenacity` | 9.x | Per-file retry with backoff | Already in project; established pattern in Phase 1's `_fetch_page()`; never hand-roll retry |
| `rich` | 14.1.0 | Progress display | Already in project; `Progress` class thread-safe for multi-worker updates |
| `typer` | 0.15.x | CLI `download` command | Already in project; `download` command stub is in `cli/main.py` |
| `hashlib` | stdlib | Incremental SHA-256 during download | No new dependency; standard library |
| `concurrent.futures` | stdlib | ThreadPoolExecutor | No new dependency; standard library |
| `threading` | stdlib | Lock for state file writes | No new dependency; standard library |
| `pathlib` | stdlib | `.part` file naming, destination paths | Already used throughout project |

### No New Dependencies Required

All libraries needed for Phase 2 are already installed. The `downloader/` and `state/` modules are empty stubs waiting to be populated.

---

## Architecture Patterns

### Recommended Module Structure

```
sharepoint_dl/
├── downloader/
│   ├── __init__.py          # exports: download_all()
│   └── engine.py            # ThreadPoolExecutor, per-file download, auth halt
├── state/
│   ├── __init__.py          # exports: JobState
│   └── job_state.py         # state.json CRUD, atomic write, status enum
└── cli/
    └── main.py              # download command (currently stub NotImplementedError)
```

### Pattern 1: Single-File Streaming Download with Incremental Hash

Each worker calls this function for one file. Tenacity wraps the HTTP call only — not the file write loop. Auth failures bubble up as `AuthExpiredError` before tenacity can retry them.

```python
# Source: established project pattern from traversal.py + requests docs
import hashlib
from pathlib import Path

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from sharepoint_dl.enumerator.traversal import AuthExpiredError, FileEntry

CHUNK_SIZE = 8_388_608  # 8 MB


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=16),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(requests.HTTPError),
)
def _download_file(
    session: requests.Session,
    file_entry: FileEntry,
    dest_path: Path,
    site_url: str,
) -> str:
    """Download one file, stream to .part, compute SHA-256, rename on success.

    Returns the hex SHA-256 digest.
    Raises AuthExpiredError on 401/403 (not retried by tenacity).
    Raises requests.HTTPError on 5xx/429 (retried by tenacity).
    """
    download_url = _build_download_url(site_url, file_entry.server_relative_url)
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")
    part_path.parent.mkdir(parents=True, exist_ok=True)

    resp = session.get(download_url, stream=True, timeout=(30, 600))

    if resp.status_code in (401, 403):
        raise AuthExpiredError("Session expired during download.")

    resp.raise_for_status()  # raises HTTPError for 429, 5xx — retried by tenacity

    sha256 = hashlib.sha256()
    with part_path.open("wb") as fh:
        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                fh.write(chunk)
                sha256.update(chunk)
                # caller updates progress here via callback

    # Verify size before accepting
    expected = file_entry.size_bytes
    actual = part_path.stat().st_size
    if expected > 0 and actual != expected:
        part_path.unlink(missing_ok=True)
        raise ValueError(f"Size mismatch: expected {expected}, got {actual}")

    part_path.rename(dest_path)
    return sha256.hexdigest()
```

### Pattern 2: Download URL Construction

The `/$value` endpoint has a confirmed bug for large files (sp-dev-docs#5247). Use `download.aspx` with the `SourceUrl` query parameter instead.

```python
from urllib.parse import quote

def _build_download_url(site_url: str, server_relative_url: str) -> str:
    """Build the download.aspx URL for a file.

    Example:
        site_url = "https://contoso.sharepoint.com/sites/shared"
        server_relative_url = "/sites/shared/Images/custodian1/evidence.E01"
        -> "https://contoso.sharepoint.com/sites/shared/_layouts/15/download.aspx
            ?SourceUrl=/sites/shared/Images/custodian1/evidence.E01"

    Confidence: MEDIUM — pattern confirmed from sp-dev-docs#5247 workaround and
    Microsoft community docs. Validate against the actual target site in Wave 0.
    """
    encoded = quote(server_relative_url, safe="/:@!$&'()*+,;=")
    return f"{site_url.rstrip('/')}/_layouts/15/download.aspx?SourceUrl={encoded}"
```

**Validation required:** Run a manual probe against the actual target site to confirm this URL format returns 200 with the correct file content for a guest session before committing to it in production code. The `/$value` URL pattern should be available as a fallback parameter if `download.aspx` fails for any file.

### Pattern 3: Atomic State File Write

Multiple workers completing simultaneously creates a write race on `state.json`. Use a threading lock + atomic rename pattern.

```python
import json
import tempfile
import threading
from pathlib import Path
from enum import Enum


class FileStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    FAILED = "failed"


class JobState:
    """Thread-safe job state persisted as state.json in destination directory."""

    def __init__(self, dest_dir: Path) -> None:
        self._path = dest_dir / "state.json"
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            self._data = json.loads(self._path.read_text())

    def _save(self) -> None:
        """Atomic write: temp file in same dir, then os.replace."""
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2))
        tmp.replace(self._path)  # atomic on POSIX (same filesystem)

    def initialize(self, files: list) -> None:
        """Populate state for all files if not already present."""
        with self._lock:
            for f in files:
                key = f.server_relative_url
                if key not in self._data:
                    self._data[key] = {
                        "name": f.name,
                        "size_bytes": f.size_bytes,
                        "status": FileStatus.PENDING,
                        "sha256": None,
                        "error": None,
                    }
            self._save()

    def set_status(self, server_relative_url: str, status: FileStatus, **kwargs) -> None:
        with self._lock:
            self._data[server_relative_url]["status"] = status
            for k, v in kwargs.items():
                self._data[server_relative_url][k] = v
            self._save()

    def pending_files(self) -> list[str]:
        """Return keys of files in pending or failed/downloading state (for retry)."""
        with self._lock:
            return [
                k for k, v in self._data.items()
                if v["status"] in (FileStatus.PENDING, FileStatus.FAILED, FileStatus.DOWNLOADING)
            ]

    def complete_files(self) -> list[str]:
        with self._lock:
            return [k for k, v in self._data.items() if v["status"] == FileStatus.COMPLETE]

    def failed_files(self) -> list[tuple[str, str]]:
        """Return (server_relative_url, error_reason) for all failed files."""
        with self._lock:
            return [
                (k, v.get("error", "unknown"))
                for k, v in self._data.items()
                if v["status"] == FileStatus.FAILED
            ]
```

### Pattern 4: ThreadPoolExecutor with Auth Halt

When any worker raises `AuthExpiredError`, a shared `threading.Event` is set to signal all other workers to stop accepting new work. Pending futures are cancelled.

```python
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

def download_all(
    session: requests.Session,
    files: list[FileEntry],
    dest_dir: Path,
    site_url: str,
    workers: int = 3,
    progress: "Progress | None" = None,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Download all files with ThreadPoolExecutor.

    Returns (completed_urls, failed_url_reason_pairs).
    Raises AuthExpiredError if session expires during downloads.
    """
    state = JobState(dest_dir)
    state.initialize(files)

    # Clean up .part files from interrupted previous run
    for f in files:
        part = _local_path(dest_dir, f).with_suffix(
            _local_path(dest_dir, f).suffix + ".part"
        )
        if part.exists() and state._data.get(f.server_relative_url, {}).get("status") == FileStatus.DOWNLOADING:
            part.unlink()
            state.set_status(f.server_relative_url, FileStatus.PENDING)

    file_map = {f.server_relative_url: f for f in files}
    pending = state.pending_files()
    auth_halt = threading.Event()
    auth_error: list[AuthExpiredError] = []

    def worker(url: str) -> str:
        if auth_halt.is_set():
            return url  # skip — auth already dead
        f = file_map[url]
        dest = _local_path(dest_dir, f)
        state.set_status(url, FileStatus.DOWNLOADING)
        try:
            sha256 = _download_file(session, f, dest, site_url)
            state.set_status(url, FileStatus.COMPLETE, sha256=sha256)
            return url
        except AuthExpiredError as e:
            auth_halt.set()
            auth_error.append(e)
            state.set_status(url, FileStatus.FAILED, error="auth_expired")
            raise
        except Exception as e:
            state.set_status(url, FileStatus.FAILED, error=str(e))
            raise

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker, url): url for url in pending}
        for future in as_completed(futures):
            if auth_halt.is_set():
                # Cancel remaining pending futures
                for f in futures:
                    f.cancel()
                break
            try:
                future.result()
            except AuthExpiredError:
                break
            except Exception:
                pass  # already recorded in state

    if auth_error:
        raise auth_error[0]

    return state.complete_files(), state.failed_files()
```

### Pattern 5: Rich Progress for Multi-Worker Display

One `Progress` instance with a task per active worker plus one overall task. Worker tasks are added before the executor starts and updated from within worker threads — `Progress.update()` is thread-safe.

```python
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)
from rich.live import Live

def _make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=None),
        DownloadColumn(),
        TransferSpeedColumn(),
        TextColumn("ETA"),
        TimeElapsedColumn(),
    )
```

**Key constraint on progress + thread interaction:** Pass `progress` object into each worker. Each worker calls `progress.update(task_id, advance=len(chunk))` after writing each chunk. Overall task advances by 1 after each file completes. Do NOT create tasks inside worker threads — create them before submitting to executor, pass `task_id` as a parameter.

### Pattern 6: 429 Retry-After Handling

SharePoint returns `Retry-After` header on 429. tenacity's `wait` parameter can be customized to read this header.

```python
import time
from tenacity import wait_base

class WaitRetryAfter(wait_base):
    """Wait the duration specified in Retry-After header, fallback to exponential."""
    def __call__(self, retry_state):
        exc = retry_state.outcome.exception()
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            if exc.response.status_code == 429:
                retry_after = exc.response.headers.get("Retry-After")
                if retry_after:
                    return float(retry_after)
        # Fallback: exponential backoff
        return min(2 ** retry_state.attempt_number, 16)
```

### Anti-Patterns to Avoid

- **`except Exception: continue` in download loop** — the exact bug in the prior script. Every exception must be caught, categorized, and recorded. Never continue silently.
- **`response.content` for large files** — buffers entire 2GB file in memory. Always `stream=True` + `iter_content()`.
- **Retrying 401/403** — auth errors are not transient. Using `retry_if_exception_type(requests.HTTPError)` on tenacity would retry 401s. Raise `AuthExpiredError` before `raise_for_status()` — exactly as done in `traversal.py`.
- **Creating new `requests.Session` per worker** — wastes cookie state. Share one session; reads are thread-safe in requests.
- **Writing `state.json` without a lock** — two workers completing simultaneously will corrupt the file. Lock is required.
- **`ThreadPoolExecutor.shutdown(cancel_futures=True)` as the auth-halt mechanism** — this cancels futures but does not interrupt in-progress downloads. The `auth_halt` Event pattern is correct — workers check it before starting new downloads.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry with backoff | Custom loop with `time.sleep()` | `tenacity` `@retry` | Already in project; handles jitter, logging, exception filtering |
| Progress bars | `print()` with `\r` | `rich.Progress` | Thread-safe, multi-task, already a dependency |
| Atomic file writes | Custom try/except around `open()` | `tmp.replace(path)` (stdlib) | `os.replace()` / `Path.replace()` is atomic on POSIX |
| SHA-256 | `hashlib.md5()` or post-download read | `hashlib.sha256()` incremental | Single I/O pass; MD5 is not acceptable for forensic evidence |
| URL-safe path encoding | String `replace(" ", "%20")` | `urllib.parse.quote()` | Handles all special characters correctly; used in traversal.py already |
| Thread pool | `threading.Thread` list | `ThreadPoolExecutor` | Handles exceptions, futures, cancellation cleanly |

**Key insight:** All required libraries are already dependencies. Phase 2 adds zero new packages — only new modules within the existing project structure.

---

## Common Pitfalls

### Pitfall 1: 401 Treated as Retriable — Workers Keep Running

**What goes wrong:** If `AuthExpiredError` is not raised before `raise_for_status()`, tenacity sees an `HTTPError` with status 401 and retries it. Three retries later, the file is marked failed. Other workers also start returning 401s. No auth halt happens. The run completes with all files failed and no clear message that the session expired.

**Why it happens:** The `retry_if_exception_type(requests.HTTPError)` in tenacity does not distinguish 401 from 503. They are both `HTTPError`.

**How to avoid:** Mirror the exact pattern from `traversal.py` `_fetch_page()` — check `resp.status_code in (401, 403)` and raise `AuthExpiredError` before calling `resp.raise_for_status()`. The `AuthExpiredError` is not in `retry_if_exception_type`, so tenacity lets it propagate immediately.

**Warning signs:** All files fail with `HTTPError: 401`, not an `AuthExpiredError` message.

### Pitfall 2: .part File Left Behind on Auth Halt

**What goes wrong:** Worker is mid-write when `AuthExpiredError` fires. The `.part` file is left in the destination. On resume, the state shows `downloading`, `.part` file exists, and the resume logic does not clean it up correctly — either the file is partially renamed or resumed from an inconsistent state.

**How to avoid:** Resume logic must: (1) find all files in `downloading` state, (2) delete their `.part` files unconditionally, (3) reset status to `pending`. This is explicitly locked in CONTEXT.md as the v1 approach (simpler than byte-range resume).

**Warning signs:** Destination directory has `.part` files after a completed or halted run. Resumed run produces different file sizes from the same source.

### Pitfall 3: Progress Update in Worker Thread Deadlocks with `Live`

**What goes wrong:** `rich.Live` and `rich.Progress` use an internal lock for rendering. If a worker thread calls `progress.update()` while the main thread is holding the render lock (e.g., during a `console.print()`), a deadlock can occur.

**How to avoid:** Never call `console.print()` from worker threads. Use `progress.log()` or `progress.console.log()` from workers, which is designed to be thread-safe. Alternatively, use `progress.update()` only (not `print`) from worker threads.

**Warning signs:** Program hangs with all workers still in progress bar state.

### Pitfall 4: State File JSON Grows Without Bound Across Runs

**What goes wrong:** If the same destination directory is reused for multiple custodians (which the user explicitly does — 3 custodians, same tool), state entries from a previous run persist. On a new run for a different `--root-folder`, the state loads entries for the previous run's files and `pending_files()` returns an empty list (all complete). The new run appears to succeed without downloading anything.

**How to avoid:** The state file is keyed by `server_relative_url`. Files from a different root folder will have different URLs — they will not collide. However, the state should be initialized per-run: if `--root-folder` changes and no matching pending files are found, the tool should warn the user rather than silently doing nothing.

**Warning signs:** `download` command prints "0 files to download" when the destination directory already has a `state.json` from a different custodian path.

### Pitfall 5: download.aspx URL Format Rejected by Guest Session

**What goes wrong:** The `download.aspx?SourceUrl=...` format is confirmed as the correct large-file download endpoint, but the exact URL encoding and whether a `guestaccesstoken` parameter is also required for external sessions is not fully documented. If the guest session cookies are sufficient (they should be, since the same cookies already work for `_api/` enumeration), the URL works as-is. If SharePoint requires an additional parameter, downloads will return 403.

**How to avoid:** Test the download URL against one file from the actual target site before wiring the full engine. A simple `requests.get(url, stream=True, cookies=session.cookies)` test against a small file is sufficient to validate the URL format. This is a Claude's Discretion item — resolve during Wave 0 of implementation.

**Warning signs:** `enumerate_files()` returns files correctly but all download attempts return 403.

### Pitfall 6: SHA-256 Not Updated Before Chunk Write

**What goes wrong:** Code writes chunk to disk, then updates the hash. If the process is killed between write and hash update (e.g., during a 2GB file), the local file is complete but the hash is for a partial file. On resume, the file appears complete (size matches) but the hash in state is wrong.

**How to avoid:** Always `sha256.update(chunk)` and `fh.write(chunk)` in the same iteration, in either order. The hash is only committed to state when the file is complete and renamed from `.part` — so a partial hash is never persisted.

---

## Code Examples

### Confirmed Pattern: Streaming with Incremental Hash (from project research)

```python
# Source: established project pattern (STACK.md, SUMMARY.md auth architecture)
import hashlib
import requests

sha256 = hashlib.sha256()
with dest_path.open("wb") as fh:
    for chunk in resp.iter_content(chunk_size=8_388_608):
        if chunk:
            sha256.update(chunk)
            fh.write(chunk)
            progress.update(task_id, advance=len(chunk))

digest = sha256.hexdigest()
```

### Confirmed Pattern: AuthExpiredError Before raise_for_status (from traversal.py)

```python
# Source: sharepoint_dl/enumerator/traversal.py (existing Phase 1 code)
if resp.status_code in (401, 403):
    raise AuthExpiredError(
        "Session expired. Run 'sharepoint-dl auth <url>' to re-authenticate."
    )
resp.raise_for_status()
```

### Confirmed Pattern: Atomic State Write (stdlib)

```python
# Source: Python stdlib pathlib — Path.replace() is atomic on POSIX
import json
from pathlib import Path

def _save(self) -> None:
    tmp = self._path.with_suffix(".tmp")
    tmp.write_text(json.dumps(self._data, indent=2))
    tmp.replace(self._path)
```

### Confirmed Pattern: Rich Progress with Multiple Worker Tasks

```python
# Source: Rich documentation (github.com/Textualize/rich) — Progress.add_task / update
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn, TextColumn

with Progress(
    TextColumn("[bold]{task.description}"),
    BarColumn(),
    DownloadColumn(),
    TransferSpeedColumn(),
) as progress:
    overall = progress.add_task("Overall", total=total_bytes)
    worker_tasks = [
        progress.add_task(f"[worker {i}] idle", total=0, visible=False)
        for i in range(workers)
    ]
    # In each worker: progress.update(worker_task_id, advance=len(chunk))
    # In main thread after each file: progress.update(overall, advance=file.size_bytes)
```

### Confirmed Pattern: ThreadPoolExecutor with as_completed

```python
# Source: Python stdlib concurrent.futures docs
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=workers) as executor:
    futures = {executor.submit(worker_fn, url): url for url in pending_urls}
    for future in as_completed(futures):
        url = futures[future]
        try:
            future.result()
        except AuthExpiredError:
            # Signal all workers, break — executor context will join remaining
            auth_halt.set()
            break
        except Exception as exc:
            # Already recorded in state; just log
            pass
```

### Download.aspx URL Construction

```python
# Source: sp-dev-docs#5247 workaround + SharePoint community docs (MEDIUM confidence)
# Validate against actual target before using in production
from urllib.parse import quote

def _build_download_url(site_url: str, server_relative_url: str) -> str:
    encoded = quote(server_relative_url, safe="/:@!$&'()*+,;=")
    return f"{site_url.rstrip('/')}/_layouts/15/download.aspx?SourceUrl={encoded}"
```

---

## State File Schema

The `state.json` schema is a discretion item. Recommended structure:

```json
{
  "/sites/shared/Images/custodian1/evidence_001.E01": {
    "name": "evidence_001.E01",
    "size_bytes": 2147483648,
    "folder_path": "/sites/shared/Images/custodian1",
    "status": "complete",
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "error": null,
    "downloaded_at": "2026-03-27T21:15:00Z"
  }
}
```

Key design choices:
- Keyed by `server_relative_url` — unique per file, matches `FileEntry.server_relative_url`
- `sha256` is `null` until file is complete — never a partial hash
- `error` is a string reason (not a traceback) — human-readable for the error summary
- `downloaded_at` is ISO 8601 UTC — used by Phase 3 manifest

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `/$value` endpoint for file downloads | `download.aspx?SourceUrl=` | Bug reported 2019 (sp-dev-docs#5247), unfixed | Large files (>~10MB) may truncate with `/$value` |
| `response.content` for all downloads | `stream=True` + `iter_content()` | Long-standing best practice | Required for 2GB files without OOM |
| `threading.Thread` + `queue.Queue` manually | `ThreadPoolExecutor` + `as_completed()` | Python 3.2+ | Exception propagation, future tracking handled automatically |
| `time.sleep(2)` retry loops | `tenacity` `@retry` | Python ecosystem shift ~2018 | Jitter, logging, stop conditions, retry conditions all declarative |
| `os.rename()` atomic writes | `Path.replace()` | Python 3.3+ `os.replace()` | `os.replace()` works on Windows too (os.rename() does not on Windows) |

---

## Open Questions

1. **download.aspx URL for guest sessions**
   - What we know: `download.aspx?SourceUrl=` is the Microsoft-recommended alternative to `/$value` for large files (sp-dev-docs#5247); the `SourceUrl` pattern is documented in SharePoint community sources
   - What's unclear: Whether the guest session cookies (FedAuth, rtFa) that work for `_api/` calls are also sufficient for `_layouts/15/download.aspx`, or whether a `guestaccesstoken` parameter is additionally required
   - Recommendation: Wave 0 task — probe the actual target site with one test file download before implementing the full engine. Fall back to `/$value` for a single test if `download.aspx` returns 403, to isolate whether the issue is the endpoint or the URL format.

2. **Worker progress task reuse vs. per-file task**
   - What we know: Rich `Progress` is thread-safe; `add_task()` can be called from any thread; `update()` is thread-safe
   - What's unclear: Whether it is cleaner to create one task per worker and reuse it (updating description to current file) or create one task per file and show only active ones
   - Recommendation: One task per worker slot (not per file) — updates description to current file name, total to current file size. Simpler lifetime management; the CONTEXT.md display spec matches this model ("worker 1: FILENAME — X GB / Y GB").

3. **Confirmation prompt implementation**
   - What we know: CONTEXT.md specifies "Confirmation prompt before starting: 'Download 165 files (237.1 GB) to /path/to/dest? [Y/n]'"
   - What's unclear: Whether to use `typer.confirm()` or a manual `input()` with rich formatting
   - Recommendation: `typer.confirm()` — integrates with `--yes` flag for non-interactive use; consistent with typer's existing CLI pattern in the project.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths = ["tests"]) |
| Quick run command | `uv run pytest tests/test_downloader.py tests/test_state.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DWNL-01 | 8MB chunk streaming, no full-file buffer | unit | `uv run pytest tests/test_downloader.py::TestStreaming -x` | Wave 0 |
| DWNL-01 | SHA-256 computed incrementally, matches full-file hash | unit | `uv run pytest tests/test_downloader.py::TestHashing -x` | Wave 0 |
| DWNL-02 | Complete files skipped on re-run (status=complete in state) | unit | `uv run pytest tests/test_state.py::TestResume -x` | Wave 0 |
| DWNL-02 | .part files deleted and file retried if status=downloading on resume | unit | `uv run pytest tests/test_state.py::TestPartCleanup -x` | Wave 0 |
| DWNL-03 | 401 mid-run: AuthExpiredError raised, not swallowed | unit | `uv run pytest tests/test_downloader.py::TestAuthHalt -x` | Wave 0 |
| DWNL-03 | Failed files appear in state, not silently skipped | unit | `uv run pytest tests/test_downloader.py::TestFailureTracking -x` | Wave 0 |
| DWNL-04 | Non-zero exit code when any file fails | unit | `uv run pytest tests/test_cli.py::TestDownloadExitCode -x` | Wave 0 |
| DWNL-05 | 3 workers submit concurrent downloads (not sequential) | unit | `uv run pytest tests/test_downloader.py::TestConcurrency -x` | Wave 0 |
| CLI-02 | Progress bar updates with each chunk write | unit | `uv run pytest tests/test_downloader.py::TestProgress -x` | Wave 0 |
| CLI-03 | Error summary table lists all failed files at run end | unit | `uv run pytest tests/test_cli.py::TestErrorSummary -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_downloader.py tests/test_state.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green (`uv run pytest tests/ -q`) before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_downloader.py` — covers DWNL-01 (streaming, hashing), DWNL-03 (auth halt, failure tracking), DWNL-05 (concurrency), CLI-02 (progress)
- [ ] `tests/test_state.py` — covers DWNL-02 (resume, .part cleanup)
- [ ] `tests/test_cli.py::TestDownloadExitCode` — covers DWNL-04
- [ ] `tests/test_cli.py::TestErrorSummary` — covers CLI-03

Existing infrastructure: `tests/conftest.py` has `mock_storage_state`, `mock_session_path`, `mock_sharepoint_responses` fixtures — all reusable. Test pattern established in `test_traversal.py` (MagicMock session + side_effect URL dispatch) is the correct model for download engine tests.

---

## Sources

### Primary (HIGH confidence)
- [sharepoint_dl/enumerator/traversal.py](traversal.py) — `AuthExpiredError`, tenacity `@retry` pattern, `_fetch_page()` auth guard — directly reused
- [Python stdlib `concurrent.futures`](https://docs.python.org/3/library/concurrent.futures.html) — `ThreadPoolExecutor`, `as_completed()`, `cancel()` behavior
- [Python stdlib `hashlib`](https://docs.python.org/3/library/hashlib.html) — `sha256()`, incremental `update()`, `hexdigest()`
- [Python stdlib `pathlib`](https://docs.python.org/3/library/pathlib.html) — `Path.replace()` atomic semantics on POSIX
- [Rich GitHub — progress.py](https://github.com/Textualize/rich/blob/master/rich/progress.py) — `Progress.add_task()`, `update()`, thread-safety
- SharePoint/sp-dev-docs Issue #5247 — large file `/$value` bug + `download.aspx` workaround confirmed

### Secondary (MEDIUM confidence)
- [Microsoft Learn — SharePoint REST folders/files](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/working-with-folders-and-files-with-rest) — confirmed download endpoint patterns
- [Microsoft Learn — SharePoint throttling](https://learn.microsoft.com/en-us/sharepoint/dev/general-development/how-to-avoid-getting-throttled-or-blocked-in-sharepoint-online) — `Retry-After` header handling
- [SharePointDiary — download.aspx URL format](https://www.sharepointdiary.com/2020/05/sharepoint-online-link-to-document-download-instead-of-open.html) — `_layouts/15/download.aspx?SourceUrl=` construction pattern
- [SuperFastPython — ThreadPoolExecutor shutdown](https://superfastpython.com/threadpoolexecutor-shutdown/) — Python 3.9+ `cancel_futures=True` behavior
- [iifx.dev — atomic file operations](https://iifx.dev/en/articles/460341744/how-to-implement-atomic-file-operations-in-python-for-crash-safe-data-storage) — `os.replace()` + temp file pattern

### Tertiary (LOW confidence)
- [liumaoli.me — Rich + ThreadPoolExecutor](https://liumaoli.me/notes/notes-about-rich/) — multi-threading + rich Progress pattern (2024 article, not official docs)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in project, patterns established in Phase 1 code
- Architecture: HIGH — module structure locked in CONTEXT.md; patterns derived from existing code
- Download URL: MEDIUM — `download.aspx` confirmed from issue tracker; guest session behavior needs hands-on validation in Wave 0
- Pitfalls: HIGH — auth halt pattern directly mirrors Phase 1 traversal.py; failure tracking and streaming are locked decisions
- Test map: HIGH — framework and fixtures exist; test file names follow established project pattern

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (stable patterns; only the download.aspx guest-session validation is time-sensitive)
