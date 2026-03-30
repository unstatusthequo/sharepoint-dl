# Codebase Concerns

**Analysis Date:** 2026-03-30

## Tech Debt

**State persistence rewrites the whole file on every update:**
- Issue: `sharepoint_dl/state/job_state.py` rewrites `state.json` on every `initialize()` and `set_status()` call, even when only one file changes.
- Why: Simpler atomic persistence via temp-rename and easy resume behavior.
- Impact: Many files or frequent status transitions cause extra disk I/O and lock contention; this is the main scaling bottleneck in the current design.
- Fix approach: Batch writes, debounce state flushes, or move to a journaled/append-only state format while preserving crash safety.

**Interactive folder browsing swallows enumeration errors:**
- Issue: `sharepoint_dl/cli/main.py` catches broad exceptions in `_list_subfolders()` and silently falls back to an empty folder list.
- Why: Keeps the TUI moving when SharePoint paging or auth calls fail.
- Impact: A transient API failure looks like "no subfolders", which can send the user down the wrong path without obvious feedback.
- Fix approach: Surface the exception class and folder path in the UI instead of collapsing all failures into the same empty-state behavior.

**Auth detection is tied to one cookie name:**
- Issue: `sharepoint_dl/auth/browser.py` waits specifically for the `FedAuth` cookie before saving a session.
- Why: This matches the observed login flow in the current tenant.
- Impact: If the tenant or Microsoft auth flow changes, auth can time out even though the user completed login successfully.
- Fix approach: Detect a broader success condition or support multiple auth-cookie patterns before deciding the session is ready.

## Known Bugs

**Progress summary can drift under concurrency:**
- Symptoms: The CLI can report slightly inconsistent completed-file counts while downloads are running.
- Trigger: Concurrent downloads in `sharepoint_dl/downloader/engine.py` increment `completed_count` from multiple worker threads.
- Workaround: None; the underlying downloads still complete correctly.
- Root cause: `completed_count` is updated without synchronization.

**Resume cleanup depends on usable local-path metadata:**
- Symptoms: Interrupted `.part` files can be left behind if legacy state entries are missing `local_path` and do not have enough metadata for fallback derivation.
- Trigger: Resuming a run that was written by an older state format or hand-edited state file.
- Workaround: Manually remove orphaned `.part` files in the destination folder.
- Root cause: `sharepoint_dl/state/job_state.py` only deletes tracked partial files it can resolve from state fields.

**Authentication failure path can terminate before a fresh manifest is written:**
- Symptoms: After `AuthExpiredError`, the CLI reloads persisted state and reports from disk, but the failure path depends on state being present and readable in `dest/state.json`.
- Trigger: Session expiry during `sharepoint_dl/downloader/engine.py` while downloading.
- Workaround: Re-run after re-authenticating; completed files are skipped.
- Root cause: Reporting is coupled to persisted state rather than to an in-memory download result.

## Security Considerations

**Session cookie cache is sensitive local credential material:**
- Risk: `sharepoint_dl/auth/session.py` stores SharePoint cookies in `~/.sharepoint-dl/session.json`.
- Current mitigation: The file is written with `0o600` on save and host-bound via `_host`.
- Recommendations: Treat the file as a secret, document the risk clearly, and consider stronger platform-specific protection for stored session material.

**Windows permission hardening is weaker than POSIX:**
- Risk: `os.chmod(..., 0o600)` in `sharepoint_dl/auth/session.py` does not provide the same protection semantics on Windows.
- Current mitigation: None beyond local filesystem access controls.
- Recommendations: Verify the effective ACL behavior on Windows if the cross-platform claim remains important.

**User-controlled SharePoint URLs are followed directly:**
- Risk: `sharepoint_dl/cli/main.py` and `sharepoint_dl/auth/browser.py` open and follow the provided URL without allowlisting beyond the user's input.
- Current mitigation: The tool is local and only persists cookies for the detected host.
- Recommendations: Keep the host-binding check strict and avoid widening cookie acceptance rules.

## Performance Bottlenecks

**`state.json` write path:**
- Problem: Every status mutation persists the full job-state payload.
- Measurement: No benchmark is recorded in the repo; the cost is structurally O(n) in tracked files per write.
- Cause: Thread-safe atomic file replacement is used for correctness.
- Improvement path: Reduce write frequency, especially inside `sharepoint_dl/downloader/engine.py` where many status updates happen quickly.

**Interactive listing can hide API latency behind retry/backoff:**
- Problem: `_fetch_page()` in `sharepoint_dl/enumerator/traversal.py` retries HTTP errors with tenacity, so folder scans can take noticeably longer under throttling.
- Measurement: No timing data is recorded in repo.
- Cause: Exponential backoff on SharePoint REST failures.
- Improvement path: Keep the retry policy, but make slow scans observable in the TUI so users can tell the difference between "slow" and "stalled".

## Fragile Areas

**`sharepoint_dl/downloader/engine.py`:**
- Why fragile: It combines concurrency, retry policy, progress updates, state persistence, and retry rounds in one function.
- Common failures: Racey status summaries, difficult-to-trace partial failures, and subtle interactions between auth expiry and retry handling.
- Safe modification: Change one concern at a time and preserve the state-machine behavior already covered by tests in `tests/test_downloader.py`.
- Test coverage: Good unit coverage, but concurrency timing and real network behavior are still largely untested.

**`sharepoint_dl/cli/main.py`:**
- Why fragile: The CLI mixes parsing, interactive prompting, folder resolution, reporting, and manifest generation in a single flow.
- Common failures: Broad exception handling masks root causes, and UX changes can accidentally break command behavior.
- Safe modification: Keep CLI output stable and add tests in `tests/test_cli.py` before changing prompts or flow control.
- Test coverage: Strong command-level tests, but the interactive path in `_interactive_mode()` is not exercised end-to-end.

**`sharepoint_dl/enumerator/traversal.py`:**
- Why fragile: It depends on SharePoint REST response shape, `__next` pagination, and the assumption that folder trees do not loop.
- Common failures: API shape changes, hidden folders, or unexpected SharePoint system paths can break traversal.
- Safe modification: Preserve pagination handling and the `/Forms` filtering rules when changing traversal logic.
- Test coverage: The traversal tests in `tests/test_traversal.py` cover pagination and auth expiry, but not malformed or mixed-shape REST payloads.

## Scaling Limits

**Single-destination job state:**
- Current capacity: One `state.json` per destination directory, updated serially under a single lock.
- Limit: High file counts or fast worker churn amplify lock contention and disk writes.
- Symptoms at limit: Slower downloads, noisy progress reporting, and more time spent persisting metadata than transferring data.
- Scaling path: Decouple state persistence from per-chunk progress updates.

**Manual browser authentication:**
- Current capacity: One interactive auth flow per session cache, centered around `~/.sharepoint-dl/session.json`.
- Limit: Not designed for unattended fleet use or high-throughput automation.
- Symptoms at limit: Sessions expire and require manual intervention.
- Scaling path: No obvious path without changing the auth model.

## Dependencies at Risk

**SharePoint REST API and `download.aspx`:**
- Risk: The code depends on SharePoint REST endpoints for enumeration and on `/_layouts/15/download.aspx` for downloads in `sharepoint_dl/downloader/engine.py`.
- Impact: Microsoft-side behavior changes can break enumeration, large-file handling, or auth validation without any local code change.
- Migration plan: Keep the download workaround and REST response parsing isolated so a future API migration is localized.

**Playwright browser automation:**
- Risk: `sharepoint_dl/auth/browser.py` depends on a headed Chromium session and the current Playwright launch model.
- Impact: Browser installation or login-flow changes can block auth entirely.
- Migration plan: Keep auth logic narrow and well-tested against the current supported OS matrix.

## Missing Critical Features

**No resumable partial-file transfer:**
- Problem: Interrupted downloads are cleaned up and retried from scratch, but there is no byte-range resume.
- Current workaround: Re-run the download and let completed files skip automatically.
- Blocks: Large files still pay the full transfer cost again after interruption.
- Implementation complexity: Medium, because it needs server support, integrity handling, and state tracking changes.

**No end-to-end integration test against live SharePoint:**
- Problem: The test suite in `tests/` is mostly mocked and does not verify real tenant behavior.
- Current workaround: Manual validation against a real SharePoint link.
- Blocks: Changes in auth, folder enumeration, and download behavior can regress without detection.
- Implementation complexity: High, because it requires a stable test tenant and careful secret handling.

## Test Coverage Gaps

**Concurrency and state race conditions:**
- What's not tested: Contended `JobState.set_status()` calls and progress reporting under actual parallel worker timing.
- Risk: Counts or persisted status can drift in ways the current unit tests do not expose.
- Priority: High
- Difficulty to test: Requires deterministic concurrency control or stress-style tests.

**Interactive CLI flow:**
- What's not tested: `_interactive_mode()` in `sharepoint_dl/cli/main.py`, including auth, folder browsing, and cancellation.
- Risk: The user-facing happy path can break while the command-level tests still pass.
- Priority: High
- Difficulty to test: Requires TTY-style interaction or higher-level harnesses.

**Windows-specific path and permissions behavior:**
- What's not tested: `os.chmod`, path normalization, and file-renaming behavior on Windows.
- Risk: Cross-platform claims can drift from actual behavior.
- Priority: Medium
- Difficulty to test: Requires a Windows runner.

---

*Concerns audit: 2026-03-30*
*Update as issues are fixed or new ones discovered*
