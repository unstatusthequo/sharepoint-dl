---
phase: 10-tui-polish
plan: "02"
subsystem: ui
tags: [rich, typer, config, throttle, verify, tui]

requires:
  - phase: 08-new-contained-modules
    provides: parse_throttle() and TokenBucket from throttle.py, verify_manifest() from verifier.py
  - phase: 10-tui-polish-01
    provides: CSV manifest report infrastructure

provides:
  - TUI startup menu with Download / Verify a prior download options
  - Verify flow: prompts for folder path pre-filled from config, runs verify_manifest()
  - Throttle prompt after workers prompt with validation loop and config persistence
  - throttle field in Config TypedDict round-tripping through TOML
  - _run_verify() helper eliminating post-download verify code duplication

affects: [10-tui-polish-03, future-tui-changes]

tech-stack:
  added: []
  patterns:
    - "Startup menus before URL prompt pattern for TUI-first UX"
    - "Reusable _run_verify() called from both startup verify and post-download verify"
    - "Throttle prompt validates with parse_throttle() in while loop, persists raw string to config"

key-files:
  created: []
  modified:
    - sharepoint_dl/config.py
    - sharepoint_dl/cli/main.py
    - tests/test_config.py

key-decisions:
  - "Store throttle as raw human string in config (e.g. '5MB') not bytes — users see original input on reload"
  - "throttle default is empty string (no throttle), 'skip' input treated same as empty"
  - "Extracted _run_verify() to avoid duplicate verify block"

patterns-established:
  - "Config fields default to empty string for optional string fields"
  - "TUI input validation loops use while True with break on success"

requirements-completed: [UX-05]

duration: 15min
completed: 2026-03-31
---

# Phase 10 Plan 02: TUI Startup Menu and Throttle Prompt Summary

**TUI startup menu with Download/Verify options and throttle prompt with config persistence using parse_throttle() validation loop**

## Performance

- **Duration:** 15 min
- **Started:** 2026-03-31T22:26:00Z
- **Completed:** 2026-03-31T22:41:59Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added `throttle: str` to Config TypedDict with empty string default, TOML round-trip, and `_validate()` support
- Added startup menu (Download files / Verify a prior download) appearing after banner, before sharing URL prompt
- Verify flow prompts for folder path (pre-filled from config), validates manifest.json presence, runs verify_manifest()
- Throttle prompt appears after workers prompt with freeform input, validation via parse_throttle(), and config persistence
- Extracted `_run_verify()` helper from duplicated post-download verify block; both code paths now use it

## Task Commits

1. **Task 1: Add throttle field to Config and update config handling** - `1fa8cc1` (feat)
2. **Task 2: Add startup menu and throttle prompt to TUI** - `373ce90` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `sharepoint_dl/config.py` - Added `throttle: str` to TypedDict, DEFAULT_CONFIG, and `_validate()`
- `sharepoint_dl/cli/main.py` - Added `_run_verify()` helper, startup menu, verify flow, throttle prompt
- `tests/test_config.py` - Updated all Config dicts to include throttle field, added throttle round-trip test

## Decisions Made

- Store throttle as raw string ("5MB") not parsed bytes so users see their original input on next session
- Menu choice "2" branches to verify flow and returns early; choice "1" falls through to existing download flow unchanged
- "skip" and empty string both treated as no throttle (throttle_bucket = None)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

`uv run` failed in the worktree environment due to a lockfile/exclude-newer conflict. Used `uv run --no-sync` to bypass lockfile resolution while using the existing virtualenv. Tests pass.

## Next Phase Readiness

- UX-05 satisfied: TUI now offers startup menu with Download and Verify paths
- Throttle config field ready for Phase 10-03 (per-file elapsed timer)
- All 47 tests in test_cli.py and test_config.py pass

---
*Phase: 10-tui-polish*
*Completed: 2026-03-31*
