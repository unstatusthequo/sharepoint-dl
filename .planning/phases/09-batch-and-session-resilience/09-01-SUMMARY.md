---
phase: 09-batch-and-session-resilience
plan: 01
subsystem: auth
tags: [reauth, session-refresh, threading, check-lock-check, rel-01]

# Dependency graph
requires: [sharepoint_dl/auth/session.py, sharepoint_dl/auth/browser.py]
provides:
  - "ReauthController: check-lock-check session refresh coordinator"
  - "trigger() -> bool: acquires lock, calls on_reauth, refreshes cookies in-place"
  - "reset_for_retry(): clears done event between re-auth rounds"
affects: [09-02-engine-integration, 09-03-batch-tui]

# Tech tracking
tech-stack:
  added: []
  patterns: [check-lock-check-with-threading-lock-and-event, in-place-cookie-refresh, dependency-injection-callback]

key-files:
  created:
    - sharepoint_dl/auth/reauth.py
    - tests/test_reauth.py
  modified: []

key-decisions:
  - "Use threading.Lock (not RLock) — single-depth critical section, RLock adds complexity without benefit"
  - "Use threading.Event (not Condition) — Event.wait() is the correct primitive for waiting workers"
  - "_done_event.clear() called inside the lock at start of each trigger() to correctly reset for concurrent workers"
  - "on_reauth callback pattern keeps Playwright dependency out of engine.py — CLI owns browser lifecycle"

patterns-established:
  - "Check-lock-check: fast-path event check -> non-blocking lock acquire -> check again inside lock"
  - "In-place cookie refresh: clear old cookies, copy new ones from build_session() result onto same session object"

requirements-completed: [REL-01]

# Metrics
duration: 8min
completed: 2026-03-30
---

# Phase 9 Plan 1: ReauthController Summary

**ReauthController with check-lock-check pattern using threading.Lock + threading.Event, cookies updated in-place on shared session, max 3 attempts enforced, Playwright dependency isolated in browser.py**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-30T22:58:33Z
- **Completed:** 2026-03-30T23:06:00Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments

- ReauthController class in `sharepoint_dl/auth/reauth.py` (115 lines)
- check-lock-check pattern: first 401 worker acquires Lock, others wait on Event
- MAX_ATTEMPTS=3 enforced: after 3 calls, trigger() returns False without re-auth
- _refresh_cookies() updates shared session.cookies in-place (no object swap, per D-03)
- Each trigger() logs attempt number, success/failure, elapsed time (per D-07)
- No playwright import in reauth.py (Playwright stays in browser.py per D-06)
- 19 unit tests covering all behaviors (TDD: red then green)
- Full suite: 149 tests passing, no regressions

## Task Commits

Each TDD phase committed atomically:

1. **Task 1: Failing tests (RED)** - `92799d4` (test)
2. **Task 1: Implementation (GREEN)** - `746420e` (feat)

_TDD tasks have separate test and implementation commits._

## Files Created/Modified

- `sharepoint_dl/auth/reauth.py` - ReauthController class with trigger(), reset_for_retry(), _refresh_cookies()
- `tests/test_reauth.py` - 19 unit tests covering lock acquisition, concurrent waiting, max attempts, cookie refresh, logging, no-playwright check

## Decisions Made

- threading.Lock (not RLock): re-auth critical section is single-depth, no recursive acquisition needed
- threading.Event (not Condition): Event.wait() is the correct primitive for workers that simply need to wait for completion
- _done_event.clear() called inside the lock before each re-auth attempt to correctly gate concurrent workers on this round (not a stale previous round)
- on_reauth is a Callable[[str], None] callback — keeps Playwright out of engine.py, CLI owns browser lifecycle

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed logging tests breaking in full test suite**
- **Found during:** GREEN verification (full suite run)
- **Issue:** setup_download_logger() from test_logging.py sets propagate=False on the sharepoint_dl logger, preventing caplog from capturing logs in test_reauth.py when running the full suite
- **Fix:** Save and restore sharepoint_dl.propagate=True around caplog assertions in the two logging tests
- **Files modified:** tests/test_reauth.py
- **Verification:** 149 tests pass in full suite run
- **Committed in:** 746420e (GREEN commit)

---

**Total deviations:** 1 auto-fixed (cross-test logging isolation bug)
**Impact on plan:** No scope creep. Fix was isolated to test setup, no production code change.

## Issues Encountered

None — environment from Phase 8 was clean, no dependency installation needed.

## User Setup Required

None.

## Known Stubs

None — ReauthController is fully implemented. The on_reauth callback is injected at construction time; Plans 09-02 and 09-03 wire it to harvest_session() in the engine and CLI.

## Next Phase Readiness

- ReauthController ready for injection into download_all() in Plan 09-02
- Clean import: `from sharepoint_dl.auth.reauth import ReauthController`
- Constructor: `ReauthController(session, sharepoint_url, on_reauth)` where on_reauth is `Callable[[str], None]`
- engine.py integration: add `on_auth_expired: Callable[[], bool] | None = None` parameter to download_all() that calls `ctrl.trigger()`

## Self-Check

### Files Exist

- [x] `sharepoint_dl/auth/reauth.py` — FOUND
- [x] `tests/test_reauth.py` — FOUND
- [x] `09-01-SUMMARY.md` — this file

### Commits Exist

- [x] `92799d4` — test(09-01): add failing tests for ReauthController
- [x] `746420e` — feat(09-01): implement ReauthController with check-lock-check pattern

## Self-Check: PASSED

---
*Phase: 09-batch-and-session-resilience*
*Completed: 2026-03-30*
