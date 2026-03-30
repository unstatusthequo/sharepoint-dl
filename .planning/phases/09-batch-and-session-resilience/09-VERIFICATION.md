---
phase: 09-batch-and-session-resilience
verified: 2026-03-30T16:25:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 9: Batch and Session Resilience Verification Report

**Phase Goal:** Users can queue multiple custodian folders in one session without restarting, and unattended multi-hour runs survive session expiry automatically
**Verified:** 2026-03-30T16:25:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | First worker to hit 401 acquires the re-auth lock and runs harvest_session | VERIFIED | `reauth.py` lines 77-115: non-blocking lock acquire, on_reauth called exactly once under lock |
| 2 | Concurrent 401 workers wait on Event instead of opening additional browsers | VERIFIED | `reauth.py` lines 117-118: lock losers call `_done_event.wait()`; test_only_one_reauth_runs_concurrently confirms 1 call with 5 workers |
| 3 | After successful re-auth, cookies are updated in-place on the shared session object | VERIFIED | `reauth.py:_refresh_cookies()` lines 130-147: clears old cookies, copies new ones onto same session object; identity assertion in tests |
| 4 | After 3 failed re-auth attempts, trigger() returns False and no more attempts are made | VERIFIED | `reauth.py` lines 84-87: `_attempts >= MAX_ATTEMPTS` check before calling on_reauth; test_max_attempts_enforced confirms on_reauth called exactly 3 times |
| 5 | Each re-auth event is logged with attempt number, success/failure, and elapsed time | VERIFIED | `reauth.py` lines 97-111: logger.info on success and logger.error on failure both include attempt number and elapsed |
| 6 | When a worker hits 401, on_auth_expired callback is invoked instead of immediately raising AuthExpiredError | VERIFIED | `engine.py` lines 300-305: `if on_auth_expired is not None:` block calls callback before abort path |
| 7 | If on_auth_expired returns True, auth_halt is cleared and workers resume; 401 file stays FAILED for retry loop | VERIFIED | `engine.py` line 304: `auth_halt.clear()` after `if refreshed:`; TestReauthIntegration.test_on_auth_expired_true_resumes asserts 0 failed |
| 8 | After a download completes in interactive mode, user is offered to queue another folder | VERIFIED | `main.py` line 436: `Confirm.ask("  [bold]Queue another folder?[/bold]", default=False)` inside batch loop |
| 9 | Each batch job writes to its own timestamped subdirectory; session reused across batch jobs | VERIFIED | `_job_dest()` at line 535 creates `{YYYY-MM-DD_HHMMSS}_{leaf}`; `job_dest` passed to all four per-job calls; `session` not re-acquired inside loop |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `sharepoint_dl/auth/reauth.py` | ReauthController class with check-lock-check pattern | VERIFIED | 148 lines; exports ReauthController; imports from sharepoint_dl.auth.session; no playwright |
| `tests/test_reauth.py` | Unit tests for ReauthController | VERIFIED | 456 lines; 19 tests in TestReauthController covering all behaviors |
| `sharepoint_dl/downloader/engine.py` | download_all() with on_auth_expired callback parameter | VERIFIED | Line 183: `on_auth_expired: "Callable[[], bool] | None" = None`; line 300: callback invocation |
| `sharepoint_dl/cli/main.py` | ReauthController wiring in interactive mode and download command; _job_dest helper; batch loop | VERIFIED | Line 17: import; lines 309-319: interactive wiring; lines 923-939: download command wiring; line 535: _job_dest; line 290: job_dest usage |
| `tests/test_downloader.py` | TestReauthIntegration class | VERIFIED | Lines 486-543: 3-test class covering None/True/False callback paths |
| `tests/test_cli.py` | TestBatchMode class | VERIFIED | Lines 892-933: 3 tests for _job_dest naming, slash-path handling, and directory creation |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `sharepoint_dl/auth/reauth.py` | `sharepoint_dl/auth/session.py` | `from sharepoint_dl.auth.session import _session_file, build_session` | WIRED | Line 21 of reauth.py; both symbols used in `_refresh_cookies()` |
| `sharepoint_dl/downloader/engine.py` | `ReauthController.trigger` | `on_auth_expired` callback parameter | WIRED | Line 183 signature + line 302 call site; ReauthController.trigger passed at line 319 in main.py |
| `sharepoint_dl/cli/main.py` | `sharepoint_dl/auth/reauth.py` | `from sharepoint_dl.auth.reauth import ReauthController` | WIRED | Line 17 import; instantiated at lines 313 and 927 |
| `main.py (_job_dest)` | `download_all, generate_manifest, setup_download_logger, JobState` | `job_dest` passed as dest_dir to all four | WIRED | Lines 293, 317, 323/333/338, 345 all use `job_dest` |
| `main.py (batch loop)` | `shutdown_download_logger` | called at end of each job | WIRED | Line 361: `shutdown_download_logger()` inside the loop before `batch_results.append` |

---

### Data-Flow Trace (Level 4)

Not applicable — this phase produces control-flow infrastructure (ReauthController, batch loop) rather than data-rendering components. No component renders dynamic data fetched from a DB or API that would require a hollow-prop trace.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `_job_dest` creates correctly named timestamped directory | `uv run python -c "from sharepoint_dl.cli.main import _job_dest; ..."` | `2026-03-30_162112_custodian1`, exists=True, leaf_correct=True | PASS |
| All phase 09 tests pass | `uv run pytest tests/test_reauth.py tests/test_downloader.py::TestReauthIntegration tests/test_cli.py::TestBatchMode -x -q` | 25 passed in 0.21s | PASS |
| Full test suite — no regressions | `uv run pytest --tb=short -q` | 155 passed in 7.86s | PASS |
| CLI imports cleanly | `uv run python -c "from sharepoint_dl.cli.main import _job_dest, app; print('CLI imports OK')"` | CLI imports OK | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| REL-01 | 09-01, 09-02 | Tool automatically re-authenticates mid-download when session expires (no manual re-run) | SATISFIED | ReauthController in reauth.py implements check-lock-check; wired into engine.py and both CLI entry points; 401 triggers automatic harvest_session call; tested by TestReauthIntegration |
| UX-02 | 09-03 | User can queue multiple folders for download in a single interactive session | SATISFIED | Batch loop in _interactive_mode_inner with `Queue another folder?` prompt; session reused; per-job timestamped subdirectory via _job_dest; batch summary table for 2+ jobs; tested by TestBatchMode |

No orphaned requirements — all requirement IDs declared in PLAN frontmatter are cross-referenced and satisfied.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | No TODOs, placeholders, empty returns, or stub patterns found in phase 09 files | — | — |

Scan coverage: `sharepoint_dl/auth/reauth.py`, `sharepoint_dl/downloader/engine.py` (modified sections), `sharepoint_dl/cli/main.py` (modified sections), all three test files.

---

### Human Verification Required

#### 1. End-to-end batch mode — live SharePoint session

**Test:** Run `sharepoint-dl interactive` against a real SharePoint site. Complete one folder download. When prompted "Queue another folder?", select Yes, navigate to a different folder, confirm. Verify second download writes to a new timestamped subdirectory alongside the first.
**Expected:** Two separate subdirectories under the chosen destination, each containing their own `state.json`, `download.log`, and `manifest.json`. No re-authentication prompt between jobs.
**Why human:** Requires live SharePoint credentials and a real site; cannot verify isolation of on-disk log files without a live session.

#### 2. Mid-download session expiry — automatic re-auth

**Test:** With a valid session, start a large multi-file download. Manually expire the session (delete `session.json` or wait for expiry). Observe whether a Chromium window opens automatically with the message "Session expired -- re-authenticating..." and whether the download resumes after signing in.
**Expected:** Rich console prints yellow "Session expired -- re-authenticating..." message. Browser opens automatically. After sign-in, download resumes for the remaining files. No manual re-run required.
**Why human:** Requires a live SharePoint session that can be expired mid-download; real browser interaction needed to confirm Playwright window launches and completes login.

---

### Gaps Summary

None. All 9 must-have truths are verified. All 6 required artifacts exist and are substantive. All 5 key links are wired. Both requirements (REL-01, UX-02) are satisfied with full test coverage (155 tests passing). No anti-patterns found. The phase goal is achieved.

---

_Verified: 2026-03-30T16:25:00Z_
_Verifier: Claude (gsd-verifier)_
