---
phase: 02-download-engine
plan: 01
subsystem: downloader
tags: [requests, tenacity, streaming, sha256, state-machine, atomic-write]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "AuthExpiredError, FileEntry dataclass, tenacity retry patterns"
provides:
  - "JobState: thread-safe file lifecycle tracking with atomic persistence"
  - "FileStatus enum: PENDING, DOWNLOADING, COMPLETE, FAILED"
  - "_download_file: single-file streaming download with retry and auth guard"
  - "_build_download_url: download.aspx URL construction"
  - "_local_path: folder-structure-preserving local path builder"
  - "WaitRetryAfter: tenacity wait respecting Retry-After headers"
affects: [02-download-engine, 03-verification]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Atomic state persistence via .tmp + Path.replace()"
    - "Incremental SHA-256 during streaming download (single I/O pass)"
    - "Auth guard before raise_for_status to prevent tenacity retry of dead sessions"
    - "WaitRetryAfter custom tenacity wait for 429 Retry-After"

key-files:
  created:
    - sharepoint_dl/state/job_state.py
    - sharepoint_dl/downloader/engine.py
    - tests/test_state.py
    - tests/test_downloader.py
  modified:
    - sharepoint_dl/state/__init__.py
    - sharepoint_dl/downloader/__init__.py
    - tests/conftest.py

key-decisions:
  - "Used reraise=True on tenacity retry so callers see HTTPError not RetryError"
  - "WaitRetryAfter inherits tenacity.wait.wait_base (not top-level tenacity.wait_base)"
  - "cleanup_interrupted uses rglob to find .part files by name (handles unknown folder depth)"

patterns-established:
  - "State persistence: write to .tmp then atomic rename on same filesystem"
  - "Download lifecycle: PENDING -> DOWNLOADING -> COMPLETE/FAILED tracked in state.json"
  - "Auth guard: check 401/403 before raise_for_status so tenacity cannot retry dead sessions"

requirements-completed: [DWNL-01, DWNL-02, DWNL-03]

# Metrics
duration: 4min
completed: 2026-03-27
---

# Phase 2 Plan 1: State + Download Engine Summary

**Thread-safe job state with atomic persistence and single-file streaming download with 8MB chunks, incremental SHA-256, auth guard, and tenacity retry with Retry-After support**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-27T20:31:28Z
- **Completed:** 2026-03-27T20:35:27Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- JobState module with atomic state.json persistence, resume logic, and .part cleanup
- Single-file download function streaming 8MB chunks with incremental SHA-256 in one I/O pass
- Auth guard raises AuthExpiredError on 401/403 before tenacity can retry
- WaitRetryAfter custom wait respecting Retry-After headers on 429 responses
- Size mismatch detection with .part cleanup
- Full TDD: 22 tests across 12 test classes, all green

## Task Commits

Each task was committed atomically:

1. **Task 1: Job state module** - `45ffaf9` (test: RED), `bb2bed8` (feat: GREEN)
2. **Task 2: Download engine** - `a158c07` (test: RED), `2183dd8` (feat: GREEN)

_TDD tasks had RED (failing tests) then GREEN (implementation) commits._

## Files Created/Modified
- `sharepoint_dl/state/job_state.py` - Thread-safe job state with FileStatus enum, atomic persistence, resume logic
- `sharepoint_dl/state/__init__.py` - Exports FileStatus, JobState
- `sharepoint_dl/downloader/engine.py` - Single-file streaming download with retry, auth guard, SHA-256
- `sharepoint_dl/downloader/__init__.py` - Exports _download_file, _build_download_url, _local_path, CHUNK_SIZE
- `tests/test_state.py` - 12 tests across 5 classes: TestResume, TestPartCleanup, TestAtomicWrite, TestInitializeIdempotent, TestFailedFiles
- `tests/test_downloader.py` - 10 tests across 7 classes: TestStreaming, TestHashing, TestSizeMismatch, TestAuthHalt, TestFailureTracking, TestRetryAfter, TestDownloadUrl
- `tests/conftest.py` - Added file_entries and mock_download_response fixtures

## Decisions Made
- Used `reraise=True` on tenacity retry decorator so callers see the original HTTPError instead of tenacity.RetryError -- cleaner error handling for the executor layer
- Imported `wait_base` from `tenacity.wait` submodule (not top-level `tenacity`) -- the class is not re-exported at package level
- `cleanup_interrupted` uses `rglob` to find .part files by name rather than reconstructing full paths -- handles arbitrary folder depth without path prefix guessing

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed tenacity wait_base import path**
- **Found during:** Task 2 (download engine implementation)
- **Issue:** `wait_base` not importable from `tenacity` top-level; only in `tenacity.wait`
- **Fix:** Changed import to `from tenacity.wait import wait_base`
- **Files modified:** sharepoint_dl/downloader/engine.py
- **Verification:** Import succeeds, all tests pass
- **Committed in:** 2183dd8

**2. [Rule 1 - Bug] Added reraise=True to tenacity retry decorator**
- **Found during:** Task 2 (download engine tests)
- **Issue:** tenacity wraps exhausted retries in RetryError, but callers expect HTTPError
- **Fix:** Added `reraise=True` to `@retry` decorator
- **Files modified:** sharepoint_dl/downloader/engine.py
- **Verification:** TestFailureTracking.test_500_retried_3_times passes
- **Committed in:** 2183dd8

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes necessary for correct operation. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- JobState and _download_file are independently tested, ready for Plan 02 to layer ThreadPoolExecutor concurrency on top
- State module provides the resume foundation (pending_files, cleanup_interrupted)
- Download function provides the single-file primitive (streaming, hashing, auth guard, retry)
- Established patterns: auth guard before raise_for_status, atomic state writes, WaitRetryAfter

---
*Phase: 02-download-engine*
*Completed: 2026-03-27*
