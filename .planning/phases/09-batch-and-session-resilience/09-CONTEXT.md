# Phase 9: Batch and Session Resilience - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Two capabilities: (1) multi-folder batch queuing in the TUI so users can download multiple custodian folders in one session without restarting, and (2) automatic session refresh mid-download so unattended multi-hour runs survive session expiry.

</domain>

<decisions>
## Implementation Decisions

### Session Refresh Flow (REL-01)
- **D-01:** When a worker hits 401/403, pause all workers (existing `auth_halt` Event), then open Playwright browser **automatically** with a Rich console message "Session expired -- re-authenticating..." — no user prompt before browser opens
- **D-02:** Use check-lock-check pattern: first worker to detect 401 acquires a re-auth lock and triggers Playwright on the main thread. Subsequent 401 workers see the lock is held and wait instead of opening additional browser windows
- **D-03:** After successful re-auth, update cookies on the **existing shared `requests.Session` object** in-place (thread-safe with a lock). Workers resume using the same session reference — no object swapping or executor restart
- **D-04:** The file that triggered 401 is **re-downloaded from byte 0** with the fresh session. state.json already marks it FAILED, so the existing resume logic handles retry naturally
- **D-05:** Maximum **3 re-auth attempts** per download run. After 3 failures (user closes browser, OTP fails, network error), abort the download with a clear error and save progress
- **D-06:** Playwright re-auth runs on the **main thread** (GUI constraint). Worker threads block on a threading.Event until re-auth completes or fails
- **D-07:** Log each re-auth event: attempt number, success/failure, elapsed time

### Batch Queue UX (UX-02)
- **D-08:** After a download completes in interactive mode, offer to queue another folder (same sharing link, different path OR new URL)
- **D-09:** Each batch job writes to its own subdirectory with its own `manifest.json`, `state.json`, and `download.log` — no cross-job state collision (per v1.1 research decision)
- **D-10:** Session object is shared across batch jobs — re-auth from job N carries over to job N+1

### Claude's Discretion
- Subdirectory naming convention for batch jobs
- Exact Rich UI for the "queue another folder" prompt
- Whether batch jobs show a summary table at the end of all jobs
- Threading synchronization implementation details (Lock vs RLock, Event signaling)
- How to structure the re-auth module (new file vs extending auth/session.py)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Auth & Session
- `sharepoint_dl/auth/session.py` — Current session load/save/validate; re-auth must integrate here
- `sharepoint_dl/auth/browser.py` — Playwright browser session capture; re-auth reuses this flow
- `sharepoint_dl/enumerator/traversal.py` — `AuthExpiredError` class and 401/403 detection

### Download Engine
- `sharepoint_dl/downloader/engine.py` — `download_all()` with `auth_halt` Event, `_download_file()` with 401 detection, ThreadPoolExecutor worker model
- `sharepoint_dl/state/job_state.py` — Per-job state tracking, `FileStatus.FAILED` for auth-expired files

### CLI & Interactive Mode
- `sharepoint_dl/cli/main.py` — Interactive mode flow (folder selection loop), download command, auth command
- `sharepoint_dl/cli/resolve.py` — Sharing link resolution (reusable for batch folder input)

### Config
- `sharepoint_dl/config.py` — Config load/save; batch mode may need to handle save-after-which-job

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `auth_halt = threading.Event()` in `download_all()` — already pauses workers on 401; extend to pause-and-resume instead of pause-and-abort
- `AuthExpiredError` — raised by both `_download_file()` and `enumerate_files()`, caught in CLI
- `save_session()` / `load_session()` / `build_session()` in `auth/session.py` — session persistence
- `browser.py` — full Playwright session capture flow (email + OTP)
- Interactive mode already loops for folder selection — extend loop for batch

### Established Patterns
- `threading.Event` for cross-worker signaling (auth_halt)
- `tenacity` retry decorator on `_download_file()` (retries 429/5xx, NOT 401/403)
- Rich progress bars with per-worker and overall tasks
- state.json tracks per-file status — FAILED files are retried on resume

### Integration Points
- `download_all()` → add re-auth callback parameter (called when auth_halt fires)
- `_download_file()` → instead of raising AuthExpiredError immediately, signal auth_halt and wait for re-auth completion
- `cli/main.py` interactive mode → extend post-download flow with "Queue another folder?" prompt
- `cli/main.py` download command → wrap in batch loop for multi-folder CLI mode

</code_context>

<specifics>
## Specific Ideas

- The check-lock-check pattern ensures exactly one browser window: first worker acquires lock, others wait on Event
- Re-auth callback pattern: `download_all()` accepts an `on_auth_expired: Callable` that the CLI provides — this keeps Playwright dependency out of the engine module
- Batch jobs are sequential (not parallel) — one folder downloads at a time, same session reused

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

### Reviewed Todos (not folded)
- "Auto-detect root folder from sharing link" — already complete (Phase 7)
- "Bandwidth throttling option" — already complete (Phase 8)
- "Config file for saved settings" — already complete (Phase 8)
- "Post-download integrity verification command" — already complete (Phase 8)

</deferred>

---

*Phase: 09-batch-and-session-resilience*
*Context gathered: 2026-03-30*
