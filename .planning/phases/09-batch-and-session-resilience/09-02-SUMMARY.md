---
phase: 09-batch-and-session-resilience
plan: "02"
subsystem: downloader + cli
tags: [reauth, engine, callback, session-resilience]
dependency_graph:
  requires: [09-01]
  provides: [download_all-on_auth_expired, cli-reauth-wiring]
  affects: [sharepoint_dl/downloader/engine.py, sharepoint_dl/cli/main.py]
tech_stack:
  added: []
  patterns: [check-lock-check via ReauthController.trigger, on_auth_expired callback parameter]
key_files:
  created: []
  modified:
    - sharepoint_dl/downloader/engine.py
    - sharepoint_dl/cli/main.py
    - tests/test_downloader.py
decisions:
  - "on_auth_expired defaults to None for backward compatibility — existing callers unaffected"
  - "Retry loop naturally re-downloads auth-expired files after successful reauth (no extra logic needed)"
  - "TestReauthIntegration.test_on_auth_expired_true_resumes asserts 0 failed (retry loop succeeds) not 1 failed (initial state)"
metrics:
  duration: "~2.5min"
  completed_date: "2026-03-30"
  tasks_completed: 2
  files_changed: 3
---

# Phase 9 Plan 02: Wire ReauthController into Download Engine and CLI Summary

Wire the ReauthController (Plan 01) into download_all() via an on_auth_expired callback, and instantiate ReauthController in both interactive mode and download command so 401 errors trigger automatic browser re-auth instead of aborting.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Add failing tests for TestReauthIntegration | 24bbae1 | tests/test_downloader.py |
| 1 (GREEN) | Add on_auth_expired callback to download_all() | 0abd987 | engine.py, tests/test_downloader.py |
| 2 | Wire ReauthController into CLI interactive + download | ecc0d30 | sharepoint_dl/cli/main.py |

## What Was Built

**engine.py changes:**
- Added `on_auth_expired: "Callable[[], bool] | None" = None` parameter to `download_all()` (backward-compatible, defaults to None)
- Modified `except AuthExpiredError` block in the `worker()` closure: when callback is provided and returns True, `auth_halt` is cleared after setting it, and the worker returns normally (file stays FAILED for retry loop); when callback returns False or is None, original abort behavior preserved

**cli/main.py changes:**
- Added `from sharepoint_dl.auth.reauth import ReauthController` import
- Both `_interactive_mode_inner()` and `download` command now instantiate `ReauthController(session, site_url, on_reauth=_do_reauth)` and pass `reauth.trigger` as `on_auth_expired` to `download_all()`
- Rich console prints "Session expired -- re-authenticating..." automatically before browser opens (D-01)
- Existing `except AuthExpiredError` fallback preserved as final safety net if ReauthController exhausts MAX_ATTEMPTS (3)

**tests/test_downloader.py changes:**
- Added `TestReauthIntegration` class with 3 tests covering all callback branches

## Verification

```
pytest tests/test_reauth.py tests/test_downloader.py -x
# 41 passed in 3.30s

python -c "from sharepoint_dl.cli.main import app; print('OK')"
# CLI imports OK
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertion adjusted for actual retry-loop behavior**
- **Found during:** Task 1 GREEN phase
- **Issue:** `test_on_auth_expired_true_resumes` originally asserted `len(failed) >= 1` (file stays FAILED), but the existing retry loop in `download_all()` resets and re-downloads failed files after auth clears. When the session mock returns success on subsequent calls, the auth_expired file gets downloaded in retry round 1, leaving `len(failed) == 0`.
- **Fix:** Updated assertion to `assert len(failed) == 0` and `assert len(completed) == 3` — this correctly tests that reauth + retry loop delivers full completion, which is the actual production behavior.
- **Files modified:** tests/test_downloader.py
- **Commit:** 0abd987

## Known Stubs

None.

## Self-Check: PASSED
