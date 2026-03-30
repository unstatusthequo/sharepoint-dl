---
phase: 07-zero-risk-ux-wins
plan: 01
subsystem: ui
tags: [rich, progress-bar, logging, filehandler, eta]

requires:
  - phase: 02-download-engine
    provides: "download engine with Rich progress bar and concurrent workers"
provides:
  - "TimeRemainingColumn in Rich progress bar (ETA display)"
  - "File-only download logger with timestamped audit trail"
  - "Per-file and per-event logging in download engine and CLI"
affects: [07-zero-risk-ux-wins]

tech-stack:
  added: []
  patterns: ["FileHandler-only logging (no StreamHandler) to preserve Rich TUI"]

key-files:
  created:
    - sharepoint_dl/downloader/log.py
    - tests/test_logging.py
  modified:
    - sharepoint_dl/downloader/engine.py
    - sharepoint_dl/cli/main.py
    - tests/test_downloader.py

key-decisions:
  - "FileHandler-only logging with propagate=False to avoid corrupting Rich TUI"
  - "_format_size_bytes helper in engine.py to avoid circular import with cli module"

patterns-established:
  - "Download logger: setup at dest.mkdir, shutdown in finally block"
  - "Logger name 'sharepoint_dl' as package root — child loggers (engine) inherit FileHandler"

requirements-completed: [UX-04, REL-03]

duration: 4min
completed: 2026-03-30
---

# Phase 7 Plan 1: ETA Column and Download Logging Summary

**Rich progress bar with ETA/speed display and file-only timestamped download.log for post-run audit**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-30T20:47:01Z
- **Completed:** 2026-03-30T20:50:31Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Added TimeRemainingColumn to Rich progress bar so users see ETA during downloads
- Created sharepoint_dl/downloader/log.py with idempotent setup/shutdown for file-only logging
- Wired logging calls into both download() CLI command and interactive mode at all key events
- Added per-file download/complete/fail logging in the engine worker function

## Task Commits

Each task was committed atomically:

1. **Task 1: Add TimeRemainingColumn and logging module (RED)** - `6090d92` (test)
2. **Task 1: Add TimeRemainingColumn and logging module (GREEN)** - `202bdc7` (feat)
3. **Task 2: Wire logging calls into CLI and engine** - `8b0076a` (feat)

## Files Created/Modified
- `sharepoint_dl/downloader/log.py` - Download logging module with setup_download_logger and shutdown_download_logger
- `sharepoint_dl/downloader/engine.py` - Added TimeRemainingColumn, _format_size_bytes helper, per-file log calls in worker
- `sharepoint_dl/cli/main.py` - Imported log functions, added log calls at session/enum/download/manifest/completeness events
- `tests/test_logging.py` - 9 tests for logger setup, format, idempotency, shutdown, no-StreamHandler guarantee
- `tests/test_downloader.py` - 2 tests for TimeRemainingColumn and TransferSpeedColumn presence

## Decisions Made
- Used _format_size_bytes local helper in engine.py instead of importing _format_size from cli to avoid circular dependency
- Log format "YYYY-MM-DD HH:MM:SS | LEVEL | message" for human readability
- Logger named "sharepoint_dl" (package root) so child loggers like sharepoint_dl.downloader.engine inherit the FileHandler

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Python 3.13 sets handler.stream to None after FileHandler.close() instead of closing the stream object - adjusted test to check both conditions.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all functionality is fully wired.

## Next Phase Readiness
- ETA column and logging module ready for use
- Log file output available for Phase 7 Plan 2 or any future audit/diagnostics work

## Self-Check: PASSED

All 5 files verified present. All 3 commit hashes verified in git log.

---
*Phase: 07-zero-risk-ux-wins*
*Completed: 2026-03-30*
