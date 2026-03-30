# Architecture Research

**Domain:** SharePoint bulk file downloader — v1.1 feature integration
**Researched:** 2026-03-30
**Confidence:** HIGH — based on direct codebase inspection, no external unknowns

## Standard Architecture

### System Overview (v1.1 target state)

```
┌─────────────────────────────────────────────────────────────────┐
│                          CLI Layer                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  main.py — TUI flow, commands: auth/list/download/verify  │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  config.py (NEW) — load/save ~/.sharepoint-dl/config.json│    │
│  └────────────────────────────────────────────────────────┘     │
├─────────────────────────────────────────────────────────────────┤
│                       Core Services                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │  auth/       │  │  enumerator/ │  │  downloader/          │  │
│  │  browser.py  │  │  traversal.py│  │  engine.py            │  │
│  │  session.py  │  │              │  │  throttle.py (NEW)    │  │
│  │  refresh.py  │  │              │  │                       │  │
│  │  (NEW)       │  │              │  │                       │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬────────────┘  │
│         │                 │                      │              │
│         └─────────────────┴──────────────────────┘             │
│                           │                                     │
│                  ┌─────────┴────────────┐                       │
│                  │  requests.Session     │                       │
│                  │  (shared, auth-scoped)│                       │
│                  └──────────────────────┘                       │
├─────────────────────────────────────────────────────────────────┤
│                        State / Output Layer                      │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────┐   │
│  │  state/       │  │  manifest/    │  │  logging (NEW)    │   │
│  │  job_state.py │  │  writer.py    │  │  FileHandler per  │   │
│  │               │  │  verifier.py  │  │  dest dir         │   │
│  │               │  │  (NEW)        │  │                   │   │
│  └───────────────┘  └───────────────┘  └───────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                       Storage Layer                              │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐  │
│  │  dest_dir/           │  │  ~/.sharepoint-dl/              │  │
│  │  state.json          │  │  session.json                   │  │
│  │  manifest.json       │  │  config.json (NEW)              │  │
│  │  download.log (NEW)  │  │                                 │  │
│  └─────────────────────┘  └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | New / Modified / Unchanged |
|-----------|----------------|---------------------------|
| `cli/main.py` | TUI flow, commands, orchestration | Modified — verify command, batch loop, config pre-fill, ETA column, throttle prompt |
| `cli/config.py` | Load/save `~/.sharepoint-dl/config.json` | **NEW** |
| `auth/browser.py` | Playwright session harvest | Unchanged |
| `auth/session.py` | Cookie persistence, session build, validate | Unchanged |
| `auth/refresh.py` | Mid-download re-auth trigger | **NEW** |
| `enumerator/traversal.py` | Recursive folder walk, pagination | Unchanged |
| `downloader/engine.py` | Concurrent download orchestration, retry, progress | Modified — session refresh hook, throttle hook, ETA column |
| `downloader/throttle.py` | Token-bucket rate limiter | **NEW** |
| `state/job_state.py` | Thread-safe JSON state persistence | Unchanged |
| `manifest/writer.py` | Forensic manifest generation | Unchanged |
| `manifest/verifier.py` | Post-download SHA-256 re-verification | **NEW** |
| `pyproject.toml` | Package metadata | Modified — PyPI classifiers, `spdl` entry point |

## Recommended Project Structure

```
sharepoint_dl/
├── auth/
│   ├── __init__.py
│   ├── browser.py          # Playwright session harvest (unchanged)
│   ├── session.py          # Cookie persistence, load/validate (unchanged)
│   └── refresh.py          # NEW: mid-download re-auth trigger
├── cli/
│   ├── __init__.py
│   ├── main.py             # Modified: verify cmd, batch loop, config pre-fill
│   └── config.py           # NEW: ~/.sharepoint-dl/config.json read/write
├── downloader/
│   ├── __init__.py
│   ├── engine.py           # Modified: refresh hook, throttle hook, ETA column
│   └── throttle.py         # NEW: token-bucket rate limiter
├── enumerator/
│   ├── __init__.py
│   └── traversal.py        # Unchanged
├── manifest/
│   ├── __init__.py
│   ├── writer.py           # Unchanged
│   └── verifier.py         # NEW: disk re-hash vs manifest comparison
├── state/
│   ├── __init__.py
│   └── job_state.py        # Unchanged
└── __main__.py             # Unchanged
```

### Structure Rationale

- **auth/refresh.py separated from session.py:** Session persistence is read-only at runtime. The refresh flow involves launching Playwright mid-download, which is stateful and side-effectful — it belongs in its own module to avoid making `session.py` stateful.
- **downloader/throttle.py separated from engine.py:** The token-bucket is a standalone, testable component. Engine passes chunk bytes through it; throttle has no knowledge of files or workers.
- **manifest/verifier.py separated from writer.py:** Writer produces output during download (sequential, at-completion). Verifier is an independent read-only operation that runs on demand after download. These have different I/O patterns and different error modes — merging them would couple unrelated responsibilities.
- **cli/config.py separated from main.py:** main.py is already long. Config logic (schema, defaults, load, save, merge with CLI args) is self-contained enough to isolate cleanly. main.py calls `load_config()` at startup.

## Architectural Patterns

### Pattern 1: Session Refresh via Pause-and-Resume

**What:** When `AuthExpiredError` fires inside a download worker, signal a shared `auth_halt` event (already exists), wait for all in-flight workers to drain, re-harvest the session via `auth/refresh.py`, update the shared `requests.Session` cookie jar in place, then re-submit failed files.

**When to use:** Session refresh only. All other errors (429, 5xx) continue to use the existing tenacity retry path.

**Trade-offs:** Patching `session.cookies` in place requires the shared session to be mutable across threads — it already is (`requests.Session` is not thread-safe for concurrent writes, but cookie replacement is a single operation). Workers that haven't started their current request yet will pick up fresh cookies naturally. In-flight requests that already sent a stale cookie will fail and enter the retry loop with fresh cookies on the next attempt.

**Integration point:** `engine.py` — `download_all()` currently raises `auth_error[0]` after cancelling futures. Replace that raise with a call to `auth/refresh.py`, then re-queue the auth-failed files.

```python
# In engine.py download_all()
# BEFORE (v1.0): raise auth_error[0]
# AFTER (v1.1):
from sharepoint_dl.auth.refresh import refresh_session_blocking
refresh_session_blocking(session, sharing_url)      # blocks, opens browser
# Re-queue files that failed with auth_expired
for url, reason in state.failed_files():
    if reason == "auth_expired":
        state.set_status(url, FileStatus.PENDING, error=None)
# Then fall through to existing retry loop
```

### Pattern 2: Token-Bucket Throttle via on_chunk Callback

**What:** The existing `on_chunk` callback already fires for every chunk written. Insert the throttle check there: record bytes sent, sleep if the rolling rate exceeds the target.

**When to use:** Only when `--throttle` is provided. Default is unlimited (no-op path).

**Trade-offs:** Sleeping inside a worker thread pauses that worker but not others. With N workers each respecting the per-worker share (`target_bps / workers`), the aggregate approaches the target. A shared token bucket (with a lock) is more accurate across workers but adds lock contention on every chunk. For the expected use case (1-4 workers, MB/s scale), per-worker division is accurate enough and simpler.

**Integration point:** `engine.py` — the `on_chunk` closure already calls `progress.update()`. Extend it to also call `throttle.consume(n)` if a throttle is configured.

```python
# downloader/throttle.py
class TokenBucket:
    def __init__(self, rate_bytes_per_sec: float): ...
    def consume(self, n: int) -> None:
        # Compute sleep needed to maintain rate; time.sleep() if needed
        ...

# In engine.py
def on_chunk(n: int, _t=_task, _o=_overall) -> None:
    progress.update(_t, advance=n)
    if _o is not None:
        progress.update(_o, advance=n)
    if throttle is not None:
        throttle.consume(n)         # sleeps if over budget
```

### Pattern 3: ETA via Rich TimeRemainingColumn

**What:** Replace `TimeElapsedColumn` (or add alongside it) with `TimeRemainingColumn` on the overall progress task. Rich computes ETA natively from `completed / total` and elapsed time — no custom logic needed.

**When to use:** Always. This is a single-line change to `_make_progress()` in `engine.py`.

**Trade-offs:** Rich's ETA is based on average rate since start, not rolling average. For downloads where throughput ramps up (slow start due to session overhead), ETA will be pessimistic early and stabilize. This is acceptable behavior.

**Integration point:** `engine.py` — `_make_progress()` column list.

```python
from rich.progress import TimeRemainingColumn

def _make_progress() -> Progress:
    return Progress(
        SpinnerColumn(style="bright_magenta"),
        TextColumn("[bright_cyan]{task.description}[/bright_cyan]"),
        BarColumn(bar_width=None, ...),
        DownloadColumn(binary_units=True),
        TransferSpeedColumn(),
        TimeRemainingColumn(),      # replaces TimeElapsedColumn
        TextColumn("{task.fields[status]}"),
    )
```

### Pattern 4: Config File as Defaults Layer

**What:** `cli/config.py` loads `~/.sharepoint-dl/config.json` at startup. It returns a typed config object with `None` for any unset key. `main.py` uses config values as prompt defaults — if config has a URL, pre-fill the URL prompt; if it has a destination, pre-fill that. Config is never mandatory; it just reduces repetitive input.

**When to use:** On every interactive invocation and as default values for CLI flags.

**Trade-offs:** Config must not silently override explicit CLI flags. The merge order is: explicit CLI arg > config file default > hardcoded default. Saving config happens at end of successful interactive run (not on failure or cancellation).

**Integration point:** `cli/main.py` — `_interactive_mode_inner()` reads config at top, uses values as `default=` in `Prompt.ask()` calls.

### Pattern 5: Verify Command as Standalone Read-Only Pass

**What:** `spdl verify <dest_dir>` reads `manifest.json` from `dest_dir`, iterates the files list, re-hashes each file from disk, and reports matches vs mismatches. It does not touch `state.json`, does not re-download anything, and has no side effects.

**When to use:** After a download completes, or at any future point to prove chain-of-custody integrity.

**Trade-offs:** Re-reading every file from disk for a 237 GB collection will take minutes. This is expected and acceptable — it's an on-demand command, not part of the normal download flow. No streaming optimization needed; standard `hashlib.sha256()` with 8 MB reads is correct.

**Integration point:** `manifest/verifier.py` does the verification logic. `cli/main.py` adds the `verify` command that calls it.

```python
# manifest/verifier.py
def verify_manifest(dest_dir: Path) -> tuple[list[str], list[str]]:
    """Returns (ok_paths, mismatch_paths)."""
    manifest = json.loads((dest_dir / "manifest.json").read_text())
    ok, mismatch = [], []
    for entry in manifest["files"]:
        local = dest_dir / entry["local_path"]
        actual = _sha256_file(local)
        if actual == entry["sha256"]:
            ok.append(entry["local_path"])
        else:
            mismatch.append(entry["local_path"])
    return ok, mismatch
```

### Pattern 6: Log File via Python logging FileHandler

**What:** At the start of a download run, configure a `logging.FileHandler` pointing to `dest_dir/download.log`. All existing `logger.getLogger(__name__)` calls in `engine.py` and `traversal.py` automatically write to this file. Add log calls at key lifecycle points (auth, enumeration complete, each file start/complete/fail, final summary).

**When to use:** Always, for every download run. The log is written alongside `state.json` — in the destination directory, not in `~/.sharepoint-dl/`.

**Trade-offs:** Log files grow unboundedly across re-runs. A simple approach is to append (not overwrite) so resume runs add to the same log. Timestamped entries make multi-run logs readable.

**Integration point:** `cli/main.py` — configure the FileHandler before calling `download_all()`. `engine.py` and `traversal.py` already use `logger`; they need log-level calls added at key points.

### Pattern 7: Multi-Folder Batch via Interactive Queue

**What:** After the user selects a folder and before download starts, the TUI asks "Add another folder?". If yes, repeat folder selection and append to a queue. After all folders are queued, run them sequentially — each folder gets its own `dest_dir`, `state.json`, `manifest.json`, and log file.

**When to use:** TUI mode only. CLI `download` command remains single-folder (multi-target is handled by shell scripting for CLI users).

**Trade-offs:** Sequential (not parallel) folder downloads keeps resource usage predictable and avoids concurrent session issues. Each folder is fully independent — its own state, its own manifest. No changes to `engine.py` needed.

**Integration point:** `cli/main.py` — `_interactive_mode_inner()` wraps the existing folder-select + download block in a loop with an "Add another?" prompt.

### Pattern 8: Auto-Detect Root Folder in CLI Mode

**What:** The `list` and `download` commands already call `_resolve_sharing_link()` in interactive mode. Make `--root-folder` optional in CLI mode by calling `_resolve_sharing_link()` when the flag is absent, and failing with a clear error only if auto-detection also fails.

**When to use:** CLI `list` and `download` commands when `--root-folder` is not provided.

**Trade-offs:** One extra HTTP request (the sharing link redirect) before enumeration begins. Negligible cost.

**Integration point:** `cli/main.py` — `list_files()` and `download()` commands. Make `root_folder` an `Optional[str]` with `default=None`; add auto-detect fallback.

### Pattern 9: PyPI Publish via pyproject.toml + GitHub Actions

**What:** Add PyPI classifiers, license, and the `spdl` console script entry point to `pyproject.toml`. Publish via `uv publish` or `twine`. Add a GitHub Actions workflow for automated publish on version tag.

**When to use:** One-time setup. Does not change runtime behavior.

**Trade-offs:** The package name `spdl` may be taken on PyPI — verify before building toward it. The Playwright browser install (`playwright install chromium`) is a post-install step that cannot be automated by `pip install` alone. Document this in README and provide a `spdl install-deps` command or clear post-install message.

**Integration point:** `pyproject.toml` — metadata, entry points. No code changes to any module.

## Data Flow

### v1.1 Interactive Download Flow (with new features)

```
User runs: spdl
    ↓
cli/config.py: load ~/.sharepoint-dl/config.json
    ↓
main.py: _interactive_mode_inner()
    Prompt for URL (pre-filled from config if saved)
    ↓
auth check → reuse session or harvest_session()
    ↓
Resolve sharing link → root_path (auto-detect, already implemented)
    ↓
Folder browser loop → server_relative_path
    ↓
[NEW] "Add another folder?" → build queue = [FolderJob, ...]
    ↓
For each FolderJob in queue:
    enumerate_files()
    Prompt dest + workers (pre-filled from config)
    [NEW] Configure log FileHandler → dest_dir/download.log
    [NEW] Configure throttle (if --throttle flag or config)
    download_all(session, files, dest, site_url, workers,
                 throttle=throttle, on_auth_expired=refresh_fn)
        ↓ (per worker)
        _download_file() → on_chunk() → throttle.consume(n) [NEW]
        [NEW] On AuthExpiredError: refresh_session_blocking() → resume
    generate_manifest()
    [NEW] Save config on success
    Completeness report
```

### Verify Flow (new command)

```
User runs: spdl verify <dest_dir>
    ↓
cli/main.py: verify()
    ↓
manifest/verifier.py: verify_manifest(dest_dir)
    Read manifest.json
    For each file: sha256_file(dest_dir / local_path)
    Compare against manifest["sha256"]
    ↓
Return (ok_list, mismatch_list)
    ↓
cli prints: N files verified OK, M mismatches [list them]
Exit 0 if clean, exit 1 if any mismatch or missing file
```

### Session Refresh Flow (new, triggered mid-download)

```
Worker: GET file → 401/403
    ↓
AuthExpiredError raised
    ↓
engine.py: auth_halt.set() [existing]
    Cancel remaining futures [existing]
    ↓
[NEW] auth/refresh.py: refresh_session_blocking(session, sharing_url)
    Opens Playwright browser
    User completes re-auth
    Browser closes
    New cookies injected into session.cookies
    ↓
engine.py: Re-queue auth-failed files as PENDING
    Fall through to existing retry_round loop
    ↓
Download resumes with fresh session
```

### Key Data Flows

1. **Config → CLI prompts:** Config values are defaults only. Explicit CLI args and user input always override.
2. **throttle.consume() → sleep:** Rate limiting is purely time-based inside the worker thread. No changes to the file data path — bytes still flow directly from `resp.iter_content()` to disk.
3. **AuthExpiredError → refresh → resume:** The session object passed into `download_all()` is mutated in place (cookies replaced). Workers that haven't fired yet pick up fresh cookies; workers that already fired get retried via the existing retry loop.
4. **download.log → FileHandler:** The log receives all `logger.*` calls from `engine.py` and `traversal.py`. The CLI adds structured event calls (auth success, enumeration count, final summary) around the calls to lower-level modules.

## Scaling Considerations

This is a single-user CLI tool. The relevant scale axis is total bytes and session lifetime, not user count.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| < 10 GB, single session lifetime | All v1.1 features work as designed |
| 10–250 GB, may span session expiry | Session refresh (auth/refresh.py) is the critical path; without it, multi-hour runs require manual re-runs |
| > 250 GB, multi-day runs | Not targeted for v1.1; would require persistent queue across process restarts, which is out of scope |

### Scaling Priorities

1. **First bottleneck:** Session expiry on long runs. Session refresh (feature 5) directly addresses this — it is the highest-leverage v1.1 change for reliability.
2. **Second bottleneck:** Unintended network saturation. Throttle (feature 6) addresses this for shared-connection scenarios.

## Anti-Patterns

### Anti-Pattern 1: Global Shared Token Bucket Across Worker Threads

**What people do:** Create one `TokenBucket` instance and have all workers call `consume()` with a lock, targeting the full bandwidth limit.

**Why it's wrong:** The lock becomes a serialization bottleneck on every 8 MB chunk across all workers. With 3 workers and 8 MB chunks at 50 MB/s, this is approximately 6 lock acquisitions per second — tolerable, but the implementation is complex and error-prone.

**Do this instead:** Divide the target rate by worker count and give each worker its own `TokenBucket(rate / workers)`. Accuracy within 10% is sufficient for a bandwidth cap; no lock contention.

### Anti-Pattern 2: Blocking the Main Thread on Session Refresh

**What people do:** Call `harvest_session()` (which blocks on Playwright) from inside a worker thread.

**Why it's wrong:** `harvest_session()` opens a real browser window. Calling it from a thread pool worker means it blocks that worker but also risks Playwright GUI issues on some platforms when called from non-main threads.

**Do this instead:** In `engine.py`, after `auth_halt` fires, drain all futures (they're already being cancelled), then call `refresh_session_blocking()` from the main thread before re-queuing. The main thread is idle while workers drain — this is the natural place for the refresh.

### Anti-Pattern 3: Writing Config on Every Run

**What people do:** Save config to disk every time a download completes, including partial runs and auth failures.

**Why it's wrong:** Saves stale or incomplete settings. If a run fails partway through, the partially-entered destination folder would be persisted as the new default.

**Do this instead:** Only save config when a download completes successfully (no failed files, no auth expiry, no cancellation). One explicit save at the bottom of the success path.

### Anti-Pattern 4: Verify Command That Re-Downloads

**What people do:** Implement `verify` by calling `_download_file()` against SharePoint and comparing the downloaded bytes.

**Why it's wrong:** Requires an active session, re-downloads potentially hundreds of GB, and introduces network as a variable in what should be a local integrity check.

**Do this instead:** Verify is purely local — read bytes from disk, compute SHA-256, compare against manifest.json. No network calls, no session required, no side effects.

### Anti-Pattern 5: Multi-Folder Batch with Shared state.json

**What people do:** Write all folder downloads to a single `state.json` keyed by server_relative_url.

**Why it's wrong:** Server-relative URLs across different folders can overlap in structure and create ambiguity. More critically, the manifest for each folder must be independent — mixing them into one manifest destroys the forensic per-custodian evidence boundary.

**Do this instead:** Each folder in the batch gets its own destination directory (user-specified or derived from folder name). Each has its own `state.json`, `manifest.json`, and `download.log`.

## Integration Points

### New Module Interfaces

| Module | Exported Interface | Called By |
|--------|-------------------|-----------|
| `auth/refresh.py` | `refresh_session_blocking(session, sharing_url) -> None` | `engine.py` (after auth halt drains) |
| `downloader/throttle.py` | `TokenBucket(rate_bps: float)` with `consume(n: int) -> None` | `engine.py` `on_chunk` closure |
| `manifest/verifier.py` | `verify_manifest(dest_dir: Path) -> tuple[list[str], list[str]]` | `cli/main.py` `verify` command |
| `cli/config.py` | `load_config() -> Config`, `save_config(config: Config) -> None` | `cli/main.py` at startup and on success |

### Modifications to Existing Interfaces

| Location | Change | Impact |
|----------|--------|--------|
| `engine.py::download_all()` | Add `throttle: TokenBucket | None = None` parameter | Callers in `cli/main.py` pass throttle if configured |
| `engine.py::download_all()` | Add `sharing_url: str | None = None` for refresh | Callers must pass URL |
| `engine.py::_make_progress()` | Replace `TimeElapsedColumn` with `TimeRemainingColumn` | No interface change — internal only |
| `cli/main.py::download()` | Make `root_folder` optional (`default=None`) | Existing callers unaffected (None triggers auto-detect) |
| `cli/main.py::list_files()` | Make `root_folder` optional (`default=None`) | Same as above |

### Internal Boundaries (v1.1)

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `cli/main.py` ↔ `cli/config.py` | Function call; returns Config dataclass | Config is read-only for all callers except the save-on-success path |
| `engine.py` ↔ `auth/refresh.py` | Function call from main thread after workers drain | Refresh must not be called from worker thread |
| `engine.py` ↔ `downloader/throttle.py` | `throttle.consume(n)` inside `on_chunk` closure | Throttle is optional — `None` check before calling |
| `cli/main.py` ↔ `manifest/verifier.py` | Function call; returns `(ok, mismatch)` lists | Verifier has no dependency on session or state |

## Build Order

Dependencies drive order. Each step can be built and tested independently before the next.

### Phase 1: Zero-Risk Wins (no dependency on other new features)

1. **ETA display** — single-line change to `_make_progress()` in `engine.py`. No new modules, no interface changes. Test: visual inspection of progress bar.
2. **Log file** — add `FileHandler` setup in `cli/main.py` before `download_all()`. Add `logger.*` calls at key points. No new modules needed. Test: verify `download.log` exists after a run.
3. **Auto-detect root folder in CLI** — make `root_folder` optional in `list` and `download` commands; call existing `_resolve_sharing_link()`. No new modules. Test: run `spdl download <url> <dest>` without `-r`.
4. **PyPI publish** — `pyproject.toml` changes only. No runtime impact. Verify `spdl` is available after `pip install`.

### Phase 2: New Modules, Contained Scope

5. **Config file** — build `cli/config.py`, wire into `_interactive_mode_inner()`. Test: saved URL pre-fills on second run.
6. **Bandwidth throttle** — build `downloader/throttle.py`, add parameter to `download_all()`. Test: `--throttle 5MB/s` caps observed speed.
7. **Verify command** — build `manifest/verifier.py`, add `verify` command to `cli/main.py`. Test: verify passes on intact download, reports mismatch on a corrupted file.

### Phase 3: Higher Complexity, Cross-Module Changes

8. **Multi-folder batch** — wrap the TUI download loop in `cli/main.py`; no engine changes. Test: queue 2 folders, each gets independent manifest.
9. **Session refresh** — build `auth/refresh.py`, modify `engine.py` auth-halt path. Test: simulate 401 mid-download, verify re-auth triggers and download resumes.

**Rationale for this order:**
- Phases 1-2 are deliverable independently, with no risk to the existing download path.
- Phase 3 items touch the core auth-halt flow (session refresh) and the TUI interaction loop (batch) — higher risk, built last.
- ETA is phase 1 not because it is important but because it is trivial; getting it done early removes it from the risk column.
- Session refresh is last because it requires testing against a real SharePoint session expiry, which is hard to automate and needs real-world validation.

## Sources

- Direct inspection of `sharepoint_dl/downloader/engine.py` (v1.0 codebase)
- Direct inspection of `sharepoint_dl/cli/main.py` (v1.0 codebase)
- Direct inspection of `sharepoint_dl/auth/session.py`, `sharepoint_dl/state/job_state.py`, `sharepoint_dl/manifest/writer.py`
- Rich Progress documentation: `TimeRemainingColumn` is a built-in column — https://rich.readthedocs.io/en/stable/progress.html
- Python `logging.FileHandler`: standard library — https://docs.python.org/3/library/logging.handlers.html#logging.FileHandler
- Token bucket algorithm: standard rate-limiting pattern — implementation via `time.monotonic()` and `time.sleep()`

---
*Architecture research for: SharePoint bulk downloader v1.1 feature integration*
*Researched: 2026-03-30*
