# Phase 9: Batch and Session Resilience - Research

**Researched:** 2026-03-30
**Domain:** Python threading synchronization, Playwright session refresh, batch TUI flow
**Confidence:** HIGH

## Summary

Phase 9 adds two tightly-coupled capabilities on top of the existing codebase. The first is **automatic session re-authentication** (REL-01): when a worker hits a 401/403, the engine pauses all workers, runs Playwright on the main thread to capture fresh cookies, updates the shared `requests.Session` in-place, then resumes all workers. The second is **batch queue UX** (UX-02): after a successful download the interactive TUI asks "Queue another folder?" and, if yes, loops back to folder selection while reusing the same authenticated session.

All key design decisions are already locked in CONTEXT.md by the user. The main research question is: what are the precise Python `threading` primitives to use, where exactly do code changes land, and what edge cases must the planner cover? The codebase is well-understood from reading the canonical files; no new external libraries are needed.

The re-auth flow follows the **check-lock-check** pattern (also called "double-checked locking") using a `threading.Lock` and a `threading.Event`. Workers that lose the lock race block on the event until the winner's Playwright session completes. The entire re-auth callback executes on the main thread (Playwright's GUI requirement), keeping Playwright entirely out of `engine.py`.

**Primary recommendation:** Implement re-auth as a `ReauthController` object that lives in `cli/main.py` and is injected into `download_all()` as a callback. This keeps `engine.py` Playwright-free and the CLI owns the retry counter and browser lifecycle.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Session Refresh Flow (REL-01)**
- **D-01:** When a worker hits 401/403, pause all workers (existing `auth_halt` Event), then open Playwright browser **automatically** with a Rich console message "Session expired -- re-authenticating..." — no user prompt before browser opens
- **D-02:** Use check-lock-check pattern: first worker to detect 401 acquires a re-auth lock and triggers Playwright on the main thread. Subsequent 401 workers see the lock is held and wait instead of opening additional browser windows
- **D-03:** After successful re-auth, update cookies on the **existing shared `requests.Session` object** in-place (thread-safe with a lock). Workers resume using the same session reference — no object swapping or executor restart
- **D-04:** The file that triggered 401 is **re-downloaded from byte 0** with the fresh session. state.json already marks it FAILED, so the existing resume logic handles retry naturally
- **D-05:** Maximum **3 re-auth attempts** per download run. After 3 failures (user closes browser, OTP fails, network error), abort the download with a clear error and save progress
- **D-06:** Playwright re-auth runs on the **main thread** (GUI constraint). Worker threads block on a threading.Event until re-auth completes or fails
- **D-07:** Log each re-auth event: attempt number, success/failure, elapsed time

**Batch Queue UX (UX-02)**
- **D-08:** After a download completes in interactive mode, offer to queue another folder (same sharing link, different path OR new URL)
- **D-09:** Each batch job writes to its own subdirectory with its own `manifest.json`, `state.json`, and `download.log` — no cross-job state collision (per v1.1 research decision)
- **D-10:** Session object is shared across batch jobs — re-auth from job N carries over to job N+1

### Claude's Discretion
- Subdirectory naming convention for batch jobs
- Exact Rich UI for the "queue another folder" prompt
- Whether batch jobs show a summary table at the end of all jobs
- Threading synchronization implementation details (Lock vs RLock, Event signaling)
- How to structure the re-auth module (new file vs extending auth/session.py)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UX-02 | User can queue multiple folders for download in a single interactive session | Batch loop in `_interactive_mode_inner()` post-download; per-job subdirectory with own state.json/manifest/log; shared session object reuse |
| REL-01 | Tool automatically re-authenticates mid-download when session expires (no manual re-run) | `ReauthController` injected into `download_all()` as callback; check-lock-check with `threading.Lock` + `threading.Event`; cookies updated in-place on shared `requests.Session`; max 3 attempts |
</phase_requirements>

---

## Standard Stack

No new libraries are needed. All required primitives exist in the current dependencies.

### Core (existing — no new installs)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `threading` | stdlib | `Lock`, `Event` for re-auth coordination | Already used for `auth_halt` in engine.py |
| `playwright` (sync) | in-project | Playwright session harvest for re-auth | Already used in `auth/browser.py::harvest_session()` |
| `requests` | in-project | `Session.cookies.set()` for in-place cookie update | Already used everywhere |
| `rich` | in-project | Console messages during re-auth pause | Already used for all TUI output |
| `pytest` | dev | Unit tests for new logic | Already used for all tests |

**No new installation required.**

### Threading Primitive Selection (Claude's Discretion — DECIDED HERE)

Use `threading.Lock` (not `RLock`). The re-auth critical section is single-depth — no recursive acquisition. `RLock` adds complexity without benefit.

Use `threading.Event` (not `Condition`). Workers need to block until re-auth finishes; `Event.wait()` is the correct primitive. `Condition` adds unnecessary complexity for this use case.

## Architecture Patterns

### Recommended New File

Create `sharepoint_dl/auth/reauth.py` — a standalone `ReauthController` class. This keeps re-auth logic isolated, testable, and out of both `engine.py` and `main.py`'s body.

**Rationale for new file (not extending session.py):** `session.py` handles persistence (load/save/validate). Re-auth is a runtime orchestration concern (lock, event, attempt counter, callback). Mixing them violates single responsibility.

### Pattern 1: ReauthController (check-lock-check)

**What:** A class that owns the re-auth lock, completion event, attempt counter, and cookie-update logic.
**When to use:** Injected into `download_all()` as the `on_auth_expired` callable.

```python
# Source: threading stdlib + project patterns
import threading
import time
import logging
from typing import Callable
import requests

logger = logging.getLogger(__name__)

class ReauthController:
    """Coordinates automatic session re-authentication for download workers.

    Uses check-lock-check pattern: first worker to call trigger() acquires
    the lock and runs the re-auth callback on the main thread. Subsequent
    callers wait on a threading.Event until re-auth completes or fails.

    Max attempts enforced per controller instance (one download run).
    """

    MAX_ATTEMPTS = 3

    def __init__(
        self,
        session: requests.Session,
        sharepoint_url: str,
        on_reauth: Callable[[str], None],  # callback that runs harvest_session
    ) -> None:
        self._session = session
        self._sharepoint_url = sharepoint_url
        self._on_reauth = on_reauth
        self._lock = threading.Lock()
        self._done_event = threading.Event()
        self._attempts = 0
        self._last_result: bool = False  # True = success, False = failure

    def trigger(self) -> bool:
        """Called by a worker thread on 401/403. Returns True if session refreshed.

        First caller acquires lock and runs re-auth on main thread.
        Subsequent callers wait for the event, then read _last_result.
        """
        # Check before acquiring lock (fast path for waiting workers)
        if self._done_event.is_set():
            return self._last_result

        acquired = self._lock.acquire(blocking=False)
        if acquired:
            try:
                if self._attempts >= self.MAX_ATTEMPTS:
                    self._last_result = False
                    self._done_event.set()
                    return False

                self._attempts += 1
                self._done_event.clear()  # Reset for this round
                t0 = time.monotonic()
                try:
                    self._on_reauth(self._sharepoint_url)
                    self._refresh_cookies()
                    elapsed = time.monotonic() - t0
                    logger.info(
                        "Re-auth attempt %d succeeded in %.1fs",
                        self._attempts, elapsed,
                    )
                    self._last_result = True
                except Exception as exc:
                    elapsed = time.monotonic() - t0
                    logger.error(
                        "Re-auth attempt %d failed in %.1fs: %s",
                        self._attempts, elapsed, exc,
                    )
                    self._last_result = False
                finally:
                    self._done_event.set()
            finally:
                self._lock.release()
        else:
            # Another thread is running re-auth — wait for it
            self._done_event.wait()

        return self._last_result

    def reset_for_retry(self) -> None:
        """Reset completion event so next download round can re-block."""
        self._done_event.clear()

    def _refresh_cookies(self) -> None:
        """Update cookies on the shared session in-place from saved session.json."""
        from sharepoint_dl.auth.session import build_session, _session_file
        from urllib.parse import urlparse

        host = urlparse(self._sharepoint_url).netloc
        new_session = build_session(_session_file(), host)
        # Clear old cookies and inject fresh ones
        self._session.cookies.clear()
        for cookie in new_session.cookies:
            self._session.cookies.set(
                cookie.name, cookie.value,
                domain=cookie.domain, path=cookie.path,
            )
```

### Pattern 2: engine.py integration — `on_auth_expired` callback

**What:** `download_all()` accepts a new optional `on_auth_expired: Callable[[], bool] | None` parameter. When a worker catches `AuthExpiredError`, instead of immediately setting `auth_halt` and raising, it calls `on_auth_expired()` and resumes if it returns `True`.

**Key change to `_download_file` worker closure in `download_all()`:**

```python
# Current behavior (raises immediately):
except AuthExpiredError as e:
    auth_halt.set()
    auth_error.append(e)
    state.set_status(url, FileStatus.FAILED, error="auth_expired")
    raise

# New behavior (try re-auth first):
except AuthExpiredError as e:
    state.set_status(url, FileStatus.FAILED, error="auth_expired")
    logger.error("Failed: %s -- auth expired", file_entry.name)
    if on_auth_expired is not None:
        auth_halt.set()  # Pause new submissions
        refreshed = on_auth_expired()
        if refreshed:
            auth_halt.clear()  # Let workers proceed with new session
            # File stays FAILED — retry loop in download_all will pick it up
            return
    # No callback or refresh failed — fall through to raise
    auth_halt.set()
    auth_error.append(e)
    raise
```

**Important:** After `on_auth_expired()` returns `True`, the worker returns normally (does NOT retry inline). The existing retry-failed-files loop in `download_all()` will pick up the FAILED file on the next round.

### Pattern 3: Batch loop in _interactive_mode_inner()

**What:** After the completeness report, offer to queue another folder. If accepted, loop back to folder selection (Step 3 in the current flow) without re-authenticating.

```python
# After the completeness report block, replace the early-exit logic:
while True:  # Batch loop
    # ... existing download flow here ...
    # After report is printed:

    if not Confirm.ask("  [bold]Queue another folder?[/bold]", default=False):
        break

    # Reset for next job
    _section_header("02", "SELECT TARGET FOLDER")
    current_path = root_path  # Reset to shared root, user navigates again
    # ... folder selection and download again ...
```

**Key constraints for batch loop:**
- Session is NOT re-acquired — existing `session` variable is reused
- `root_path` is re-resolved from the SAME `sharing_url` (same sharing link context)
- Each job gets its own `dest` subdirectory (named per D-09 convention)

### Pattern 4: Per-job subdirectory naming (Claude's Discretion — DECIDED HERE)

Use a timestamp-based subdirectory: `{dest}/{YYYY-MM-DD_HHMMSS}_{folder_leaf_name}/`

**Why:** Unambiguous, sortable, collision-free, human-readable in file explorer. Alternatives (sequential numbers like `job_001`) require scanning the dest dir for existing jobs, which adds complexity with no benefit.

**Example:** Download to `~/Downloads/sharepoint-dl/2026-03-30_143022_custodian1/`

The base `dest` directory entered by the user becomes the **batch root**. Each job creates its own dated subdirectory inside it.

### Pattern 5: Batch summary table (Claude's Discretion — DECIDED HERE)

Show a summary table after all jobs complete. This is useful for multi-hour runs where the user wants a single at-a-glance view. Use Rich `Table` (already used for error display).

```
  ╔══════════════════════════════════════╗
  ║  BATCH SUMMARY                       ║
  ╠══════════╦════════╦════════╦════════╗
  ║ Folder   ║ Files  ║ Status ║ Time   ║
  ╠══════════╬════════╬════════╬════════╣
  ║ custodian1 ║ 48   ║ OK     ║ 12m    ║
  ║ custodian2 ║ 32   ║ OK     ║ 8m     ║
  ╚══════════╩════════╩════════╩════════╝
```

### Recommended Project Structure Changes

```
sharepoint_dl/
├── auth/
│   ├── browser.py       # Existing — harvest_session() unchanged
│   ├── session.py       # Existing — unchanged
│   └── reauth.py        # NEW — ReauthController class
├── cli/
│   └── main.py          # MODIFIED — batch loop, ReauthController wiring
└── downloader/
    └── engine.py        # MODIFIED — on_auth_expired callback parameter

tests/
└── test_reauth.py       # NEW — unit tests for ReauthController
```

### Anti-Patterns to Avoid

- **Swapping the session object:** D-03 requires updating the SAME object in-place. If `main.py` held a reference `session = load_session(...)` and `engine.py` also holds that reference, creating a NEW session object in `_refresh_cookies()` and returning it would leave `engine.py` holding the stale reference. Always update `session.cookies` in-place.
- **Running Playwright from a worker thread:** Playwright's `sync_api` uses a GUI event loop on the main thread. Calling `harvest_session()` from a `ThreadPoolExecutor` thread will deadlock or crash.
- **Blocking the main thread with `threading.Event.wait()`:** The main thread must not block — it needs to respond to the re-auth callback. The call flow is: worker calls `ReauthController.trigger()` → controller calls `on_reauth()` on the main thread via the callback mechanism → `on_reauth` calls `harvest_session()`. The main thread IS the one calling `download_all()`, so `on_reauth` runs synchronously during the callback.
- **Cross-job state.json collision:** Each batch job MUST get its own `dest` subdirectory. If two jobs write to the same `dest`, `JobState.__init__` loads existing state and `initialize()` is idempotent for known keys — a second job for a different folder would silently skip files with matching URLs if keys collide (they won't if folders differ, but dest subdirs eliminate ambiguity entirely).
- **Retrying 401 inline in `_download_file`:** `_download_file` is decorated with `@retry(retry_if_exception_type(requests.HTTPError))`. `AuthExpiredError` is NOT an `HTTPError` — tenacity correctly does NOT retry it. Do not change this. The re-auth loop runs at the `download_all()` level.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thread-safe "only one browser" | Custom flag variable | `threading.Lock(blocking=False)` + `threading.Event` | Lock's `acquire(blocking=False)` is the correct atomicity primitive |
| Cookie update from new session | Manual JSON parse | `requests.Session.cookies.set()` + existing `build_session()` | `build_session()` already handles domain-filtered cookie injection |
| New Playwright auth flow | New browser code | Existing `harvest_session()` in `browser.py` | It already handles FedAuth detection, timeout, and session save |
| Retry FAILED files after re-auth | New retry loop | Existing retry-failed-files loop in `download_all()` | Lines 325-365 in `engine.py` already retry FAILED files; FAILED state from 401 is automatically retried |

**Key insight:** The re-auth feature is fundamentally a PAUSE-REFRESH-RESUME wrapping the existing retry infrastructure. The least-code path reuses everything already built.

## Common Pitfalls

### Pitfall 1: auth_halt.clear() race condition

**What goes wrong:** Worker A sets `auth_halt`, runs re-auth, clears `auth_halt`. Meanwhile Worker B, which was already past the `if auth_halt.is_set(): return` guard, has started a download request. If B then gets a 401 again (e.g., re-auth failed silently), B calls `trigger()` again while A's lock is still held.

**Why it happens:** `auth_halt` is cleared before all workers have acknowledged they are paused.

**How to avoid:** The `ReauthController` owns the `auth_halt.clear()` call, only inside the lock, only after `harvest_session()` succeeds. Workers that return after `auth_halt.clear()` with a FAILED file are handled by the retry loop — they don't retry inline.

**Warning signs:** Multiple browser windows opening, OR auth loop reaching max attempts on what should have been a single-attempt run.

### Pitfall 2: ThreadPoolExecutor future cancellation vs. waiting

**What goes wrong:** After `on_auth_expired()` returns `True`, the code calls `auth_halt.clear()` — but previously submitted futures that checked `auth_halt.is_set()` before the clear have already returned early (no-ops). Those file URLs were not marked FAILED — they stayed PENDING, so the engine's retry loop won't pick them up.

**Why it happens:** Workers that short-circuit `if auth_halt.is_set(): return` at the TOP of the worker closure don't set the file to FAILED — the file stays DOWNLOADING or PENDING depending on when the check fires.

**How to avoid:** In the worker closure's `auth_halt.is_set()` guard, only skip files that are already COMPLETE. For PENDING/DOWNLOADING files caught by the halt, set them to PENDING explicitly (or leave as-is — `pending_files()` returns DOWNLOADING as retryable). Verify `pending_files()` returns PENDING | FAILED | DOWNLOADING so no file is lost.

**Warning signs:** File count mismatch between enumerated and downloaded+failed totals after a re-auth run.

### Pitfall 3: download.log FileHandler not rotated between batch jobs

**What goes wrong:** `setup_download_logger(dest)` attaches a FileHandler to `dest/download.log`. If batch job 2 uses a different `dest` subdirectory, but `shutdown_download_logger()` was not called after job 1, both jobs append to job 1's log file.

**Why it happens:** `setup_download_logger()` is idempotent and removes existing FileHandlers before adding the new one — but only if called again with the new `dest`. If the batch loop calls `setup_download_logger(job_dest)` for each job, this is handled correctly.

**How to avoid:** Call `shutdown_download_logger()` at end of each job, then `setup_download_logger(new_job_dest)` at the start of the next. The existing `downloader/log.py` already handles this correctly (removes existing handlers before adding new one).

**Warning signs:** A single `download.log` file in the first job's directory containing entries from multiple jobs.

### Pitfall 4: ReauthController._done_event not reset between retry rounds

**What goes wrong:** After the first re-auth (event set to True), a second 401 in the same run calls `trigger()`. The fast-path check `if self._done_event.is_set(): return self._last_result` returns immediately with the PREVIOUS result (True) without running re-auth again.

**Why it happens:** `_done_event` is a one-way gate — once set, it stays set.

**How to avoid:** `reset_for_retry()` must be called by the lock-holder worker at the START of `trigger()`, before running `harvest_session()`. The implementation template above handles this: `self._done_event.clear()` is called inside the lock before the re-auth attempt.

**Warning signs:** Re-auth runs only once but worker 401s recur; second 401 skips re-auth silently.

### Pitfall 5: batch subdirectory + manifest path

**What goes wrong:** `generate_manifest()` in `manifest/writer.py` writes to `dest / "manifest.json"`. If `dest` is the batch root instead of the job subdirectory, all jobs overwrite the same manifest.

**Why it happens:** The current interactive mode uses a single `dest`. Batch mode needs `job_dest` per job.

**How to avoid:** Verify `dest` passed to `download_all()`, `generate_manifest()`, `setup_download_logger()`, and `JobState()` is the PER-JOB subdirectory (not the batch root). The batch root is only used for prompting the user.

**Warning signs:** `manifest.json` in batch root containing only the last job's files.

## Code Examples

### Verified pattern: `requests.Session.cookies.set()` in-place update

```python
# Source: requests library — CookieJar manipulation
# Pattern used in existing build_session() in auth/session.py
session.cookies.clear()
for cookie in new_cookies:
    session.cookies.set(
        cookie["name"],
        cookie["value"],
        domain=cookie.get("domain", ""),
        path=cookie.get("path", "/"),
    )
```

Updating cookies on the existing session object is thread-safe when wrapped in the `ReauthController._lock` — `requests.Session` is not itself thread-safe for concurrent modifications, but the `_refresh_cookies()` call happens inside the acquired lock.

### Verified pattern: non-blocking lock acquisition

```python
# Source: threading stdlib
acquired = lock.acquire(blocking=False)
if acquired:
    try:
        # Only winner enters here
        ...
    finally:
        lock.release()
else:
    # Others wait on the event
    done_event.wait()
```

This is the canonical check-lock-check pattern. `blocking=False` returns immediately with `True` or `False` — no spinning.

### Verified pattern: download_all() signature extension

```python
# Current signature (engine.py line 174):
def download_all(
    session: requests.Session,
    files: list[FileEntry],
    dest_dir: Path,
    site_url: str,
    workers: int = 3,
    progress: Progress | None = None,
    flat: bool = False,
    throttle: "TokenBucket | None" = None,
) -> tuple[list[str], list[tuple[str, str]]]:

# New signature (backward-compatible — on_auth_expired defaults to None):
def download_all(
    session: requests.Session,
    files: list[FileEntry],
    dest_dir: Path,
    site_url: str,
    workers: int = 3,
    progress: Progress | None = None,
    flat: bool = False,
    throttle: "TokenBucket | None" = None,
    on_auth_expired: "Callable[[], bool] | None" = None,
) -> tuple[list[str], list[tuple[str, str]]]:
```

All existing call sites continue working unchanged (they don't pass `on_auth_expired`).

### Verified pattern: batch subdirectory naming

```python
from datetime import datetime

def _job_dest(batch_root: Path, folder_path: str) -> Path:
    """Create a timestamped subdirectory for a batch job."""
    folder_leaf = folder_path.rsplit("/", 1)[-1] if "/" in folder_path else folder_path
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    job_dir = batch_root / f"{ts}_{folder_leaf}"
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir
```

### Verified pattern: `harvest_session()` returns a Path — not a session object

Looking at `auth/browser.py`, `harvest_session()` saves to disk and returns the session file `Path`. After re-auth, the controller must call `build_session()` (from `auth/session.py`) to create a fresh session object, then copy its cookies into the existing session. The controller does NOT use the returned Path directly.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| On 401: abort download, show "Re-run to resume" | On 401: pause workers, re-auth automatically, resume | Phase 9 | Unattended multi-hour runs survive session expiry |
| One folder per session | Batch queue in same session | Phase 9 | Multiple custodian folders in one run |

**Current behavior that changes:**
- `engine.py` line 321: `if auth_error: raise auth_error[0]` — after Phase 9, this only fires if re-auth fails (max attempts exceeded or no callback provided)
- `cli/main.py` line 389-393: `auth_expired` branch exits with code 1 — after Phase 9, this branch is only reached if `ReauthController` exhausts all attempts

## Open Questions

1. **What happens if the user queues a folder from a DIFFERENT sharing link?**
   - What we know: D-08 says "same sharing link, different path OR new URL"
   - What's unclear: If a new URL is entered, the `site_url` and potentially the `host` change — the existing session may not be valid for the new host
   - Recommendation: For the "new URL" case, call `validate_session(session, new_site_url)` before starting the download. If it fails, trigger a fresh `harvest_session()` for the new URL before proceeding. This is a natural extension of the existing auth flow.

2. **Does `auth_halt.clear()` need to be the ReauthController's responsibility or the engine's?**
   - What we know: `auth_halt` is created inside `download_all()` — it's local state
   - What's unclear: Should the controller receive the `auth_halt` Event, or should `download_all()` clear it after `on_auth_expired()` returns True?
   - Recommendation: `download_all()` owns `auth_halt` and clears it after the callback returns True. `ReauthController` does not need a reference to `auth_halt` — cleaner separation.

3. **Re-auth retry rounds: should engine's existing 2-round retry loop interact with re-auth rounds?**
   - What we know: `download_all()` has a 2-round retry loop for network errors (lines 325-365). D-05 says max 3 re-auth attempts.
   - What's unclear: If re-auth succeeds on attempt 1 and some files still fail (non-auth reasons), the 2-round retry loop runs for those. If THOSE retries trigger another 401, re-auth attempt 2 fires. This is correct behavior — it's separate retry layers.
   - Recommendation: Document this clearly in the implementation. The 2-round retry loop and the re-auth attempt counter are orthogonal.

## Environment Availability

Step 2.6: SKIPPED — No new external dependencies. All required tools (Python, pytest, playwright, requests, rich, threading) are already in the project and verified to be installed (Phase 8 ran successfully in this environment).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `pytest tests/test_reauth.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REL-01 | First 401 worker acquires lock, runs re-auth, resumes | unit | `pytest tests/test_reauth.py::TestReauthController::test_first_worker_acquires_lock -x` | ❌ Wave 0 |
| REL-01 | Concurrent 401 workers: only one browser window opens | unit | `pytest tests/test_reauth.py::TestReauthController::test_only_one_reauth_runs_concurrently -x` | ❌ Wave 0 |
| REL-01 | Cookies updated in-place on existing session object | unit | `pytest tests/test_reauth.py::TestReauthController::test_cookies_updated_in_place -x` | ❌ Wave 0 |
| REL-01 | Max 3 re-auth attempts, then abort | unit | `pytest tests/test_reauth.py::TestReauthController::test_max_attempts_enforced -x` | ❌ Wave 0 |
| REL-01 | Re-auth event logged (attempt, result, elapsed) | unit | `pytest tests/test_reauth.py::TestReauthController::test_reauth_logged -x` | ❌ Wave 0 |
| REL-01 | engine.py: on_auth_expired callback invoked on 401 | unit | `pytest tests/test_downloader.py::TestReauthIntegration -x` | ❌ Wave 0 |
| UX-02 | Each batch job has own subdirectory with own state.json | unit | `pytest tests/test_cli.py::TestBatchMode::test_per_job_subdirectory -x` | ❌ Wave 0 |
| UX-02 | Session reused across batch jobs (no re-auth between jobs) | unit | `pytest tests/test_cli.py::TestBatchMode::test_session_shared_across_jobs -x` | ❌ Wave 0 |
| UX-02 | _job_dest() naming convention | unit | `pytest tests/test_cli.py::TestBatchMode::test_job_dest_naming -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_reauth.py tests/test_downloader.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_reauth.py` — covers REL-01 (ReauthController unit tests)
- [ ] `tests/test_downloader.py` — extend with `TestReauthIntegration` class for engine callback
- [ ] `tests/test_cli.py` — extend with `TestBatchMode` class for UX-02 batch behavior

## Sources

### Primary (HIGH confidence)
- Direct code read of `sharepoint_dl/downloader/engine.py` — full understanding of `download_all()`, `auth_halt` Event, worker closure, retry loops, and `AuthExpiredError` handling
- Direct code read of `sharepoint_dl/auth/browser.py` — `harvest_session()` return type (Path), FedAuth cookie detection pattern
- Direct code read of `sharepoint_dl/auth/session.py` — `build_session()` cookie injection pattern, `save_session()` file format
- Direct code read of `sharepoint_dl/cli/main.py` — complete interactive mode flow, all integration points for batch loop
- Direct code read of `sharepoint_dl/state/job_state.py` — `pending_files()` returns PENDING|FAILED|DOWNLOADING, confirming FAILED files from 401 are retried automatically
- Python `threading` stdlib documentation — `Lock.acquire(blocking=False)`, `Event.wait()`, `Event.clear()` — canonical primitives

### Secondary (MEDIUM confidence)
- Phase 9 CONTEXT.md decisions D-01 through D-10 — locked implementation decisions from user discussion
- Accumulated knowledge in STATE.md: "Session refresh must run on main thread — Playwright GUI constraint; use check-lock-check pattern for concurrent 401 detection"
- Phase 8 SUMMARY — confirms `auth_halt = threading.Event()` pattern, identifies `_interactive_mode_inner()` as integration point

### Tertiary (LOW confidence)
- None — all claims verified from source code or locked decisions.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; all primitives read directly from source
- Architecture: HIGH — patterns derived directly from existing `engine.py` code; check-lock-check is a well-known stdlib pattern
- Pitfalls: HIGH — derived from careful reading of the existing code paths (`pending_files()` behavior, `auth_halt` lifecycle, `setup_download_logger` idempotence)

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (codebase is stable; no external API changes expected)
