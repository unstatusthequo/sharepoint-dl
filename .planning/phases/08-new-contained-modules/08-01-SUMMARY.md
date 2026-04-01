---
phase: 08-new-contained-modules
plan: 01
subsystem: config, downloader
tags: [toml, tomllib, tomli-w, token-bucket, throttle, bandwidth]

# Dependency graph
requires: []
provides:
  - "Config module: load_config, save_config, merge_config with TOML persistence"
  - "TokenBucket: thread-safe bandwidth throttle shared across workers"
  - "parse_throttle: CLI string parser for human-friendly rate limits"
affects: [08-02-integration, cli, download-engine]

# Tech tracking
tech-stack:
  added: [tomli-w]
  patterns: [token-bucket-with-future-advancing-refill, atomic-file-write-via-rename, typed-dict-config]

key-files:
  created:
    - sharepoint_dl/config.py
    - sharepoint_dl/downloader/throttle.py
    - tests/test_config.py
    - tests/test_throttle.py
  modified:
    - pyproject.toml

key-decisions:
  - "Token bucket advances _last_refill into future on deficit to correctly serialize concurrent thread waits"
  - "Added tomli-w as runtime dependency in pyproject.toml"

patterns-established:
  - "Config TypedDict pattern: typed defaults, validate-and-clamp on load, merge for CLI overrides"
  - "Atomic file write: write to .tmp then rename for crash safety"

requirements-completed: [UX-03, REL-02]

# Metrics
duration: 16min
completed: 2026-03-30
---

# Phase 8 Plan 1: Config & Throttle Modules Summary

**TOML config persistence with load/save/merge and thread-safe token bucket bandwidth throttle with CLI parser**

## Performance

- **Duration:** 16 min
- **Started:** 2026-03-30T21:24:14Z
- **Completed:** 2026-03-30T21:40:49Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Config module loads TOML from ~/.sharepoint-dl/config.toml, returns typed defaults on missing/corrupt files, saves atomically
- Token bucket correctly rate-limits aggregate bandwidth across all download workers via shared mutex
- parse_throttle converts "10MB"/"500KB"/"1GB" CLI strings to bytes-per-second values
- 20 passing unit tests across both modules (TDD: red then green)

## Task Commits

Each task was committed atomically:

1. **Task 1: Config file module (RED)** - `4a0dff3` (test)
2. **Task 1: Config file module (GREEN)** - `bea671d` (feat)
3. **Task 2: Token bucket throttle (RED)** - `ccdcaeb` (test)
4. **Task 2: Token bucket throttle (GREEN)** - `a81581c` (feat)

_TDD tasks have separate test and implementation commits._

## Files Created/Modified
- `sharepoint_dl/config.py` - Config TypedDict, load/save/merge with TOML persistence
- `sharepoint_dl/downloader/throttle.py` - TokenBucket class and parse_throttle function
- `tests/test_config.py` - 9 tests covering load, save, roundtrip, corrupt files, merge
- `tests/test_throttle.py` - 11 tests covering parse_throttle and TokenBucket (including thread safety)
- `pyproject.toml` - Added tomli-w runtime dependency

## Decisions Made
- Token bucket uses future-advancing refill timestamp to correctly serialize concurrent thread waits (prevents multiple threads from simultaneously getting short sleep times)
- Added tomli-w as runtime dependency (tomllib is stdlib for reading, tomli-w needed for writing)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed tomli-w dependency**
- **Found during:** Pre-task setup
- **Issue:** tomli-w not installed in venv, not in pyproject.toml dependencies
- **Fix:** Installed via uv pip, added to pyproject.toml dependencies list
- **Files modified:** pyproject.toml
- **Verification:** Import succeeds, tests pass
- **Committed in:** bea671d (Task 1 GREEN commit)

**2. [Rule 1 - Bug] Fixed token bucket thread safety with future-advancing refill**
- **Found during:** Task 2 (thread safety test)
- **Issue:** Multiple threads computed short sleep times simultaneously because _last_refill wasn't advanced, causing effective rate to exceed target by 6x
- **Fix:** Advance _last_refill into the future when sleeping on deficit so queued threads see the reserved time
- **Files modified:** sharepoint_dl/downloader/throttle.py
- **Verification:** Thread safety test passes (4 threads stay within 2.5x target rate)
- **Committed in:** a81581c (Task 2 GREEN commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes essential for correctness. No scope creep.

## Issues Encountered
- Python venv had stale/broken packages (pygments, urllib3, rich) requiring reinstallation -- resolved with uv pip reinstall

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - both modules are fully implemented with no placeholder data.

## Next Phase Readiness
- Config and throttle modules ready for wiring into CLI and download engine in Plan 02
- Clean import interfaces: `from sharepoint_dl.config import load_config, save_config, merge_config, Config`
- Clean import interfaces: `from sharepoint_dl.downloader.throttle import TokenBucket, parse_throttle`

---
*Phase: 08-new-contained-modules*
*Completed: 2026-03-30*
