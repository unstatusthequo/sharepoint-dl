# Pitfalls Research

**Domain:** SharePoint bulk file downloader — guest/external auth, large file downloads, forensic integrity
**Researched:** 2026-03-27 (v1.0), updated 2026-03-30 (v1.1 additions)
**Confidence:** HIGH (v1.0 pitfalls verified against official Microsoft docs and confirmed GitHub issues); MEDIUM (v1.1 pitfalls grounded in codebase analysis + community patterns)

---

## v1.1 Feature Pitfalls

These are pitfalls specific to adding the nine v1.1 features to the existing codebase.

---

### Pitfall A: PyPI Package Name "spdl" Is Already Taken

**What goes wrong:**
The planned PyPI name `spdl` is already registered and actively maintained by Meta's "Scalable and Performant Data Loading" library (version 0.3.0, BSD-2-Clause, `pip install spdl`). Attempting to publish under that name will fail with a 400 error from PyPI. More critically, if users run `pip install spdl` expecting the SharePoint downloader they will receive Meta's data loading library instead.

**Why it happens:**
PyPI names are first-come, first-served. Short, pronounceable abbreviations are commonly registered. The name conflict was not checked before it appeared in the project plan.

**How to avoid:**
Before finalising the PyPI package name, verify availability at `https://pypi.org/project/<name>/`. Consider `sharepoint-dl`, `sharepoint-bulk-dl`, or `spdl-forensic`. The project's existing GitHub slug is `sharepoint_dl`, which maps naturally to `sharepoint-dl` on PyPI (hyphens and underscores are normalised equivalently). Verify the chosen name is unregistered, then claim it with an initial release immediately.

**Warning signs:**
- `pip install spdl` installs a data loading library, not the SharePoint downloader
- PyPI returns HTTP 409 or 400 on first publish attempt
- `twine check dist/*` succeeds but upload fails

**Phase to address:** PyPI publishing phase — resolve name before any other packaging work begins. Treat as a blocker.

---

### Pitfall B: Session Refresh Under Concurrent Workers — Multiple Workers Triggering Reauth Simultaneously

**What goes wrong:**
The current engine halts all workers via `auth_halt` threading.Event when any worker hits a 401. This is correct for the existing "halt and tell the user" behaviour. For v1.1 auto session refresh, the risk is building a naive refresh that is not protected by a lock: when a session expires mid-download with 3-8 workers active, all workers detect 401 nearly simultaneously. Without a mutex around the refresh operation, multiple workers each launch a browser re-auth attempt concurrently. Playwright opening three browser windows simultaneously is confusing and may corrupt the session file.

**Why it happens:**
The natural reflex is to add `if response.status_code == 401: refresh_session()` inside the worker function. With ThreadPoolExecutor running N workers, N workers can hit this branch in overlapping time windows before any of them complete the refresh.

**How to avoid:**
Protect session refresh with a single threading.Lock. Use a "first waiter wins" pattern: the first thread to see a 401 acquires the lock and performs the browser re-auth; subsequent threads block on the lock, then when they acquire it they re-check whether the session is now valid (it should be) before attempting another browser launch. This is the standard "check-lock-check" (double-checked locking) pattern for lazy initialisation under concurrency.

```python
_refresh_lock = threading.Lock()

def _maybe_refresh(session, site_url):
    with _refresh_lock:
        # Check again inside the lock — another thread may have refreshed already
        if validate_session(session, site_url):
            return  # Another thread already refreshed; nothing to do
        harvest_session(...)  # Only runs once
        # Reload and inject new cookies into session
```

The existing `auth_halt` event can be reused: set it to pause new work, perform refresh, reload cookies into the shared `requests.Session`, then clear the event or replace the session object and re-queue the failed files.

**Warning signs:**
- Multiple browser windows open simultaneously during a re-auth attempt
- `session.json` is empty or corrupt after a refresh
- Files that were in-flight when auth expired end up in an inconsistent state in `state.json`

**Phase to address:** Session refresh phase. The lock pattern must be designed before any re-auth code is written.

---

### Pitfall C: Session Object Is Shared Across Threads — Cookie Refresh Requires Atomic Swap

**What goes wrong:**
`requests.Session` objects are not thread-safe for mutation. The current codebase passes a single `session` object to all workers, which is safe during download-only operation because workers only read from the session (issuing GET requests). If session refresh modifies the session's `cookies` jar mid-download, a worker in the middle of streaming a response may read a partially-updated cookie store and receive a 401 on the next chunk request.

**Why it happens:**
`requests.Session.cookies` is a `RequestsCookieJar` which is not documented as thread-safe for concurrent reads and writes. The Python GIL does not protect multi-step attribute mutations. Updating cookies while workers are actively using the session creates a data race.

**How to avoid:**
Two safe approaches:
1. Pause all workers (via auth_halt), perform the refresh, create a new `requests.Session` with the new cookies, resume workers with the new session reference. This is the simplest and most compatible with the existing halt-on-auth-error pattern.
2. Use a session wrapper with a RWLock that blocks readers during cookie updates. This is more complex and not worth it given the project's concurrency model.

Approach 1 is correct here because the existing code already halts on auth expiry. The v1.1 change is to make it resume after refresh rather than abort.

**Warning signs:**
- Intermittent 401 errors that appear during the first download attempt after a refresh
- `requests.Session.cookies` contains a mix of old and new cookie values

**Phase to address:** Session refresh phase. Design the "pause, refresh, resume" flow as a unit.

---

### Pitfall D: Playwright Browser Launch During Download Is Blocking and UX-Disruptive

**What goes wrong:**
The existing `harvest_session` function opens a headed browser window and polls for the FedAuth cookie with a busy loop (`time.sleep(2)`). This blocks the calling thread. If called from within the download engine (on the same thread that owns the progress display), the Rich progress bars freeze for the entire authentication duration — up to 180 seconds by default. The user sees a frozen terminal plus a browser window with no explanation.

**Why it happens:**
`harvest_session` was designed to be called from the main thread before downloads start. Reusing it mid-download means calling it at a point where the Rich `Progress` context is live and the terminal is in a controlled state.

**How to avoid:**
Before launching the browser for re-auth, stop the Rich progress display (`progress.stop()`) and print a clear message: "Session expired. Please complete authentication in the browser window." After re-auth completes and the new session is loaded, restart the progress display with the same tasks but updated `completed` values so it reflects what was already downloaded.

Alternatively, pause progress display with `progress.live.stop()`, run re-auth, then `progress.live.start()`.

**Warning signs:**
- Terminal appears frozen with no output during browser-based re-auth
- Progress bars show stale values after re-auth completes

**Phase to address:** Session refresh phase, with explicit testing of the progress display interaction.

---

### Pitfall E: Bandwidth Throttling Applied Per-Worker Multiplies Effective Bandwidth

**What goes wrong:**
If a token bucket or rate limiter is instantiated per worker, each worker has its own independent limit. With 4 workers each limited to 1 MB/s, the actual throughput is 4 MB/s. The user who configured "1 MB/s" sees 4 MB/s used. This is the most common mistake in per-thread rate limiting.

**Why it happens:**
The natural place to add throttling is inside the `worker()` function or `_download_file()` function — the same place where chunks are written. If the limiter is created inside the worker closure, it is a new object per worker.

**How to avoid:**
The throttle token bucket must be a single shared instance passed to all workers, protected by a threading.Lock. All workers draw from the same bucket. Use monotonic time (`time.monotonic()`) for bucket refill calculations — `time.time()` is affected by NTP adjustments and can jump or go backward.

```python
# Shared, not per-worker
throttle = TokenBucket(capacity=limit_bytes, refill_rate=limit_bytes)

def on_chunk(n: int) -> None:
    throttle.consume(n)  # Blocks until n bytes are available
    progress.update(task, advance=n)
```

**Warning signs:**
- Measured network usage is `workers * configured_limit` rather than `configured_limit`
- Throttling only kicks in when a single worker is active

**Phase to address:** Bandwidth throttling phase.

---

### Pitfall F: Throttling Interacts Badly With the Existing Retry-After Backoff

**What goes wrong:**
The existing `WaitRetryAfter` tenacity wait respects SharePoint's `Retry-After` header and uses exponential backoff as fallback. If bandwidth throttling is implemented by sleeping inside the chunk callback (`on_chunk`), it adds sleep time inside an active streaming response. SharePoint may close the connection if no data is consumed for too long (server-side read timeout). A throttled chunk loop that waits too long between reads will receive a broken pipe or connection reset, which appears as a `ChunkedEncodingError` — different from the 429 errors that tenacity currently handles.

**How to avoid:**
Do not sleep inside the chunk-reading loop. Instead, throttle at the pre-request level: before issuing each file download request, check if the throttle bucket has capacity. Alternatively, use a leaky bucket that absorbs burst without stalling the active stream. The connection timeout in `_download_file` is `timeout=(30, 600)` — the 600s read timeout accommodates slow streams, but sleeping inside the loop eats into that budget unpredictably.

**Warning signs:**
- `ChunkedEncodingError` or `ConnectionResetError` appearing only when throttling is active
- Downloads that complete successfully without throttling fail with throttling enabled
- Throttling causes files to fail on the 3rd tenacity retry due to exhausted read timeout

**Phase to address:** Bandwidth throttling phase. Test with a large file (>200MB) at a low throttle limit.

---

### Pitfall G: Playwright Post-Install Browser Download Not Triggered by "pip install"

**What goes wrong:**
`pip install sharepoint-dl` (or whatever the PyPI name becomes) installs the Python package but does NOT install the Playwright browser binaries. Users must separately run `playwright install chromium`. If this step is missing from the setup documentation, the first run fails with: `Error: Executable doesn't exist at /path/to/chromium`. This error is opaque to users unfamiliar with Playwright.

There is no supported mechanism in `pyproject.toml` to automatically run `playwright install` as a post-install hook. PyPI explicitly discourages post-install scripts, and `pip` does not run them reliably across platforms.

**Why it happens:**
Playwright separates the Python package (small) from the browser binaries (large, ~250MB per browser). The Python package includes a CLI tool that downloads binaries, but this must be invoked explicitly. This is by design — browsers are large and users may not need all of them.

**How to avoid:**
Two mitigations:
1. Add a startup check in `__main__.py` that detects missing Playwright browsers and prints a clear actionable error: "Run `playwright install chromium` to complete setup." This converts the cryptic Playwright error into a friendly message.
2. Document the two-step install prominently in README and PyPI description: `pip install sharepoint-dl && playwright install chromium`.

Do not attempt to automate the browser install via a custom `setup.py` post-install hook — it is fragile, platform-specific, and runs with elevated pip permissions that are inappropriate for downloading 250MB binary blobs.

**Warning signs:**
- `playwright._impl._errors.Error: Executable doesn't exist` on first run after pip install
- No mention of `playwright install` in the install instructions

**Phase to address:** PyPI publishing phase. Add the startup check before publishing.

---

### Pitfall H: Batch Mode State Collision — Multiple Jobs Writing to the Same state.json

**What goes wrong:**
The existing `JobState` uses a single `state.json` per destination directory. In batch mode, if two custodian downloads are directed to the same destination directory (or the user re-runs a batch with the same dest), the second job's `JobState.initialize()` call is idempotent — it skips files already in state. But if the first job's files and the second job's files have overlapping `server_relative_url` keys (e.g., two custodians have identically-named files at the same relative path), they will collide in state.json. The second job's file will be treated as already complete.

**Why it happens:**
`JobState` keys on `server_relative_url`, which is unique per SharePoint instance. But in batch mode where two separate SharePoint folders are being downloaded, files from different folders can have the same server-relative path only if the folders themselves share a name — unlikely but possible. The higher risk is the user pointing both jobs at the same local directory.

**How to avoid:**
Two approaches:
1. In batch mode, each job gets a subdirectory in the destination: `dest/<job_name>/`. This isolates state.json files and avoids collision entirely.
2. Detect and warn if a batch job's destination directory already contains a `state.json` with entries from a different SharePoint folder root.

Approach 1 is simpler and should be the default for batch mode.

**Warning signs:**
- Second batch job reports "all files already complete" without downloading anything
- Manifest for the second job contains file hashes from the first job

**Phase to address:** Batch mode phase.

---

### Pitfall I: Batch Mode Partial Failure Handling — One Failed Job Blocks the Queue

**What goes wrong:**
In a naive batch implementation, if job 2 of 5 fails (auth expiry, all files error, etc.), the batch runner either aborts all remaining jobs or silently continues and reports everything as done. The first option discards completed-recoverable work; the second hides failures.

**Why it happens:**
Batch runners commonly either propagate exceptions eagerly (aborting the loop) or swallow them (logging and continuing without clear signal). Neither is correct for a forensic use case where "job 3 failed silently" is unacceptable.

**How to avoid:**
Each job in the batch must record a per-job result: completed count, failed count, manifest path. After all jobs run (or after auth expiry halts the queue), print a per-job summary table showing which jobs succeeded and which need rerun. Auth expiry should halt the current job and the batch, prompting re-auth, then offer to resume from the halted job.

**Warning signs:**
- Batch run completes with a single success/failure line rather than per-job results
- A job that produces zero downloaded files is not highlighted as a failure

**Phase to address:** Batch mode phase.

---

### Pitfall J: Config File Migration — Existing Users Have No Config, New Flags Conflict

**What goes wrong:**
When a config file is introduced, users who have no config file must get the same defaults they had before (workers=3, flat=True, etc.). If the code's argument-precedence order is `CLI flags > config file > defaults`, adding a config file is safe. But if it is `config file > CLI flags`, existing automation scripts that relied on CLI flags may be silently overridden by a config file a user created for interactive use.

The second risk: if the config file uses a format that changes between versions (e.g., adding a new required key), users upgrading from an older version will have an invalid config that produces a confusing KeyError or validation error on startup.

**Why it happens:**
Config file handling typically lacks a migration path. Developers add new keys without considering that existing config files on disk do not have them.

**How to avoid:**
Precedence order must be: CLI flags > config file > hardcoded defaults. This makes the config file strictly additive — it never overrides an explicit flag.

For migration safety, use `config.get("key", default)` throughout — never `config["key"]`. An older config file missing a new key silently uses the default rather than crashing. Log a warning if unrecognised keys are found in the config (helps users notice outdated config files).

**Warning signs:**
- CLI `--workers 8` is ignored when a config file sets `workers = 3`
- KeyError on startup after upgrading SPDL with an existing config file
- Users report that a flag "stopped working" after they created a config file

**Phase to address:** Config file phase.

---

### Pitfall K: Log File Output Interleaves With Rich TUI Output

**What goes wrong:**
Rich's `Console` and `Progress` take control of the terminal's output stream. Writing to a log file via Python's `logging` module at the same time can cause garbled output if the log handler also writes to stdout/stderr. Specifically, `logging.StreamHandler(sys.stderr)` will interleave with Rich's live display, producing broken progress bar rendering.

**Why it happens:**
The natural setup is `logging.basicConfig(filename="spdl.log")` plus a `StreamHandler` for console output. But Rich already handles console display. Competing writes corrupt Rich's ANSI escape sequence rendering.

**How to avoid:**
Use a file-only log handler for the audit log. Do not add a StreamHandler that writes to stdout or stderr while Rich's progress is active. Rich provides `RichHandler` for integrating logging with its console — use that if console log output is needed, or route all user-facing messages through `console.print()` and all audit messages to the file handler only.

```python
file_handler = logging.FileHandler("spdl-YYYYMMDD.log")
file_handler.setLevel(logging.DEBUG)
logging.getLogger().addHandler(file_handler)
# No StreamHandler — Rich owns the terminal
```

**Warning signs:**
- Progress bars show broken or duplicated lines during download
- Log output appears mid-progress-bar on the terminal

**Phase to address:** Log file phase.

---

### Pitfall L: Speed Estimation ETA Misleads on Variable-Size File Lists

**What goes wrong:**
A naive ETA that divides `remaining_bytes / current_speed` will be wildly inaccurate when the remaining files are disproportionately large or small compared to the already-downloaded files. For example, if 90% of files are small (1MB each) and one 2GB file is last, the ETA will jump dramatically when that file starts. Users interpret the jump as a tool malfunction and interrupt the run.

**Why it happens:**
Speed-based ETAs do not account for file size distribution. They are accurate only when all files are similar in size.

**How to avoid:**
Display ETA based on `remaining_bytes / rolling_average_speed` (use a rolling window of the last 30 seconds, not a cumulative average — cumulative average is dominated by early slow startup). Additionally, show the count of remaining large files so users have context for ETA jumps. Rich's `TransferSpeedColumn` and `TimeRemainingColumn` columns can be used directly and produce the right behaviour — avoid reimplementing them.

**Warning signs:**
- ETA jumps from "2 minutes" to "45 minutes" suddenly
- Users report the tool "hanging" when it is actually downloading a large file

**Phase to address:** ETA / speed estimation phase.

---

## Critical Pitfalls (Carried Forward From v1.0)

These remain relevant during v1.1 because new features interact with them.

### Pitfall 1: SharePoint REST API Pagination Silently Truncates Results

**What goes wrong:**
When using `GetFolderByServerRelativeUrl(...)/Files`, SharePoint defaults to returning the first 100 items with no automatic continuation. If the code iterates what it received without checking for a `@odata.nextLink` or `skiptoken`, it processes a partial list and never knows it stopped early. No error is raised.

**Why it happens:**
Developers assume `GET /Files` returns all files. SharePoint's REST API uses opaque `$skiptoken` pagination.

**How to avoid:**
After every Files or Folders API response, inspect for `@odata.nextLink` in the response body. If present, follow it. Loop until `@odata.nextLink` is absent.

**Warning signs:**
- Downloaded file count is suspiciously round (exactly 100, 200, etc.)
- No errors in logs, but manifest shows fewer files than expected

**Phase to address:** This is validated in v1.0. Verify it remains correct when batch mode introduces multiple enumeration passes.

---

### Pitfall 2: Guest Session Expiry Mid-Download Causes Silent 401/403 Without Retry

**What goes wrong:**
The Entra B2B guest session has a finite lifetime. When it expires mid-run, subsequent HTTP requests return 401 or 403. Code that catches exceptions broadly and `continue`s swallows auth failures identically to transient errors.

**How to avoid:**
Treat HTTP 401 and 403 as hard failures that halt the run. This is implemented in v1.0 via `AuthExpiredError`. v1.1 adds auto-refresh — see Pitfalls B, C, D above for the new risks that introduces.

**Phase to address:** Session refresh phase (v1.1). Must not weaken v1.0's halt-on-auth-error guarantee.

---

### Pitfall 3: Large File Downloads (~2GB) Silently Corrupt or Truncate Without Streaming

**What goes wrong:**
Loading a 2GB file into memory via `response.content` causes memory exhaustion. The `/$value` endpoint has a confirmed bug for large files (sp-dev-docs#5247).

**How to avoid:**
Use `stream=True` and 8MB chunk writes. Use `download.aspx` URL. This is implemented in v1.0. v1.1 throttling must not break the streaming loop — see Pitfall F above.

**Phase to address:** Implemented in v1.0. Verify throttling does not regress this in v1.1.

---

### Pitfall 4: SharePoint OTP Authentication Retired

**What goes wrong:**
Microsoft retired SharePoint OTP authentication effective July 1, 2025. New sharing links use Entra B2B. Code written for OTP flow will not work on migrated tenants.

**How to avoid:**
The browser-based `harvest_session` design is already flow-agnostic — it waits for FedAuth cookie regardless of which flow produces it. v1.1 session refresh must preserve this agnosticism.

**Phase to address:** Session refresh phase — verify refresh works with Entra B2B flows, not just legacy OTP.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Per-worker throttle limiter instead of shared | Simpler code | Effective bandwidth = workers × limit | Never |
| `session["key"]` instead of `session.get("key", default)` in config parsing | Slightly shorter | KeyError on config upgrade | Never |
| PyPI name without checking availability | No friction | Publish blocked; user confusion | Never |
| Reauth in a non-main thread without locking | Simpler code | Multiple browser windows, corrupt session.json | Never |
| Same dest dir for all batch jobs | Simpler user input | state.json collisions, file overwrites | Never in batch mode |
| StreamHandler + Rich progress simultaneously | Shows logs in terminal | Garbled progress bar output | Never |
| Cumulative average for ETA | Single calculation | ETA dominated by slow startup, inaccurate | Never for long-running downloads |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| SharePoint REST pagination | Assuming one API call returns all files | Always follow `@odata.nextLink` until absent |
| SharePoint `/$value` endpoint | Using it for large files | Use `download.aspx` URL; stream with `stream=True` |
| Guest session cookies | Treating 401 as retriable | 401/403 = auth expired, halt; only retry 429/5xx |
| SharePoint throttling (429) | Ignoring `Retry-After` header | Read and honour `Retry-After`; max 10 requests/second |
| Playwright post-install | Assuming `pip install` installs browsers | Document `playwright install chromium` explicitly; add startup check |
| PyPI name registration | Assuming short names are available | Check `pypi.org/project/<name>` before designing the name |
| Python logging + Rich | Adding StreamHandler while Rich is active | Use file-only handler; no StreamHandler competing with Rich |
| `requests.Session` + multiple threads | Mutating cookies while workers read | Pause workers before modifying session; atomic swap pattern |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-worker token bucket | Network usage = workers × throttle limit | Single shared bucket with mutex | Any multi-worker download |
| Sleep inside chunk loop | ChunkedEncodingError, ConnectionReset | Throttle pre-request, not mid-stream | Low throttle limits (< 500KB/s) |
| Cumulative speed average for ETA | ETA inaccurate after startup ramp | Rolling 30-second window | Any download > a few minutes |
| Re-enumerating files for each batch job | Redundant API calls, throttling risk | Cache enumeration results per job | Batch of 5+ jobs |
| State.json write on every chunk | Disk I/O bottleneck on fast connections | Write state only on status transitions (PENDING → DOWNLOADING → COMPLETE) | Fast SSD + many small files |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Persisting session cookies world-readable | Session hijack | Store with `0o600` permissions (already done in v1.0) |
| Logging full URLs with auth tokens in query params | Token exposure in log file | Redact tokens; log only filenames and status codes |
| Config file storing credentials | Credentials exposed if config is shared | Config file for settings only; never store session tokens or passwords in config |
| Log file in download directory | Log shipped with evidence files | Write log to `~/.sharepoint-dl/logs/` not to the download dest |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Browser window opens with no terminal message | User confused — is the tool broken? | Print "Opening browser for re-authentication. Complete login then close browser." before launching |
| Batch mode no per-job summary | User cannot tell which custodian failed | Print per-job result table at end: name, files, status, manifest path |
| Config key changed between versions | Startup crash after upgrade | Use `.get()` with defaults; warn on unrecognised keys, don't crash |
| ETA jumps by 10x mid-run | User thinks tool is hung | Show "downloading large file" indicator when a file > 100MB starts |
| Log file written to download dest | Evidence folder contains tool artifacts | Write log to `~/.sharepoint-dl/logs/`, not to the download directory |

---

## "Looks Done But Isn't" Checklist

**PyPI Publishing**
- [ ] PyPI name is available — verify at `pypi.org/project/<name>` before writing any packaging code
- [ ] `playwright install chromium` step is documented in README and PyPI description
- [ ] Startup check detects missing Playwright browsers and prints a friendly error
- [ ] `pip install <name>` on a clean virtualenv produces a working tool (not just a passing `twine check`)

**Session Refresh**
- [ ] Only one browser window opens, even when 4+ workers all hit 401 simultaneously
- [ ] Progress display is paused and explained to user before browser opens
- [ ] Progress display resumes with correct byte counts after re-auth
- [ ] Files that were downloading when auth expired are reset to PENDING and retried

**Throttling**
- [ ] Measured network usage at `--throttle 1MB` with 4 workers is ~1 MB/s, not ~4 MB/s
- [ ] A 500MB file downloads successfully with `--throttle 100KB/s` without connection resets
- [ ] Throttle interacts correctly with the existing Retry-After backoff

**Batch Mode**
- [ ] Each job's files go into a distinct subdirectory; no state.json collisions
- [ ] Per-job result table printed at end of batch
- [ ] Auth expiry during job 2 of 5 halts the batch and offers to resume from job 2

**Config File**
- [ ] CLI flags override config file values (not the reverse)
- [ ] Config file with missing keys does not crash on startup
- [ ] Config file with unrecognised keys prints a warning, not an error

**Log File**
- [ ] Log file is written to `~/.sharepoint-dl/logs/` not to the download directory
- [ ] Rich progress display is not garbled when log file handler is active
- [ ] Log contains enough detail to reconstruct what happened (files attempted, status, errors)

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| PyPI name taken | MEDIUM | Choose a new name; update all references in pyproject.toml, README, docs |
| Multiple browser windows on reauth | LOW | Add lock before re-implementing; no state corruption if only one completes successfully |
| Session object corrupted mid-refresh | MEDIUM | Discard session, re-auth from scratch; completed files preserved in state.json |
| Wrong throttle scope (per-worker) | LOW | Move token bucket instantiation to before executor creation; refactor is small |
| Batch state.json collision | MEDIUM | Re-enumerate affected job; re-download files whose hashes don't match expected |
| Config file KeyError after upgrade | LOW | Document config schema; add migration note in changelog |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| PyPI name "spdl" taken (Pitfall A) | PyPI publishing phase — first task | `pip install <chosen-name>` on fresh venv returns the right tool |
| Concurrent reauth race (Pitfall B) | Session refresh phase | Start 4-worker download, revoke session mid-run; confirm only one browser window opens |
| Session object mutation race (Pitfall C) | Session refresh phase | Race condition test: simulate 401 on all workers simultaneously |
| Playwright blocks progress display (Pitfall D) | Session refresh phase | Observe terminal during re-auth; progress must pause cleanly |
| Per-worker throttle bucket (Pitfall E) | Throttling phase | Measure actual network usage with 4 workers at 1MB/s limit |
| Throttle sleep breaks streaming (Pitfall F) | Throttling phase | Download 500MB file at 100KB/s; confirm no ChunkedEncodingError |
| Playwright browser not installed post-pip (Pitfall G) | PyPI publishing phase | Install on clean venv; run tool; confirm friendly error not Playwright traceback |
| Batch state.json collision (Pitfall H) | Batch mode phase | Run batch with two jobs pointing to same dest; confirm isolation |
| Batch partial failure handling (Pitfall I) | Batch mode phase | Intentionally fail job 2 of 3; confirm per-job summary shows failure |
| Config file migration (Pitfall J) | Config file phase | Remove one key from config; confirm no crash on startup |
| Log + Rich interference (Pitfall K) | Log file phase | Enable file logging; confirm no garbled progress output |
| ETA misleads on variable-size files (Pitfall L) | ETA/speed estimation phase | Test with 95 small files + 1 large file; observe ETA behaviour |

---

## Sources

**v1.1 Research Sources:**
- PyPI package `spdl` (Meta FAIR) — name conflict verified: https://pypi.org/project/spdl/
- OAuth token refresh race condition in concurrent systems: https://nango.dev/blog/concurrency-with-oauth-token-refreshes
- Race condition on concurrent token refresh (claude-code): https://github.com/anthropics/claude-code/issues/27933
- Python requests Session thread safety (Advanced Usage docs): https://docs.python-requests.org/en/latest/user/advanced/
- SharePoint throttling and Retry-After — official guidance: https://learn.microsoft.com/en-us/sharepoint/dev/general-development/how-to-avoid-getting-throttled-or-blocked-in-sharepoint-online
- RateLimit headers for proactive throttle management: https://devblogs.microsoft.com/microsoft365dev/prevent-throttling-in-your-application-by-using-ratelimit-headers-in-sharepoint-online/
- Playwright post-install browser requirement: https://playwright.dev/python/docs/intro
- Playwright Python wheel build issues on Windows: https://github.com/microsoft/playwright-python/issues/2827
- PyPI Trusted Publisher setup with GitHub Actions: https://docs.pypi.org/trusted-publishers/using-a-publisher/
- Token bucket thread-safe implementation: https://oneuptime.com/blog/post/2026-01-22-token-bucket-rate-limiting-python/view

**v1.0 Research Sources (carried forward):**
- SharePoint sp-dev-docs Issue #5247 — Incomplete content on large file downloads via `/$value`: https://github.com/SharePoint/sp-dev-docs/issues/5247
- Microsoft Learn — Avoid throttling in SharePoint Online: https://learn.microsoft.com/en-us/sharepoint/dev/general-development/how-to-avoid-getting-throttled-or-blocked-in-sharepoint-online
- Steve Chen Blog — SharePoint OTP retirement July 2025: https://steve-chen.blog/2025/06/23/sharepoint-online-otp-authentication-gets-out-of-support-on-july-1st-2025/
- Microsoft Learn — Configurable token lifetimes (Entra): https://learn.microsoft.com/en-us/entra/identity-platform/configurable-token-lifetimes

---
*Pitfalls research for: SharePoint bulk downloader — v1.1 feature additions*
*Updated: 2026-03-30*
