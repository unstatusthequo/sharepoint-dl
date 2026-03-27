---
phase: 05-manifest-path-accuracy
plan: 01
subsystem: manifest
tags: [manifest, cli, state, pytest]

# Dependency graph
requires:
  - phase: 04-resume-safety-and-failure-reporting
    provides: persisted relative local_path metadata and auth-expiry reporting tail
provides:
  - manifest local_path evidence sourced from persisted relative output paths
  - shared fallback/validation for missing or invalid legacy local_path entries
  - CLI manifest generation that preserves flat-mode and auth-expired path accuracy
affects: [phase 06-audit-evidence-normalization]

# Tech tracking
tech-stack:
  added: []
  patterns: [shared local path derivation, validated persisted relative paths]

key-files:
  created:
    - .planning/phases/05-manifest-path-accuracy/05-01-SUMMARY.md
  modified:
    - sharepoint_dl/manifest/writer.py
    - sharepoint_dl/cli/main.py
    - sharepoint_dl/state/job_state.py
    - sharepoint_dl/downloader/engine.py
    - tests/test_manifest.py
    - tests/test_cli.py

key-decisions:
  - "Manifest local_path uses persisted state first and only falls back through one shared helper."
  - "Stored local_path values are accepted only when relative and traversal-safe."
  - "CLI must pass flat-mode context into manifest generation so legacy state can be backfilled correctly."

patterns-established:
  - "Downloader, resume cleanup, and manifest generation share one relative-path derivation rule."
  - "Manifest regressions should cover persisted, legacy, invalid, flat, and auth-expired state-backed paths."

requirements-completed: [VRFY-02]

# Metrics
duration: ~20min
completed: 2026-03-27
---

# Phase 05-01: Manifest Path Accuracy Summary

**Manifest path evidence now matches the actual local download path across persisted, legacy, flat, and partial-run cases**

## Performance

- **Duration:** ~20min
- **Started:** 2026-03-27T22:49:00Z
- **Completed:** 2026-03-27T23:09:25Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Made persisted `local_path` the manifest source of truth and centralized legacy path fallback/validation in shared state helpers.
- Reused the same path derivation logic in downloader placement, resume cleanup, and manifest generation.
- Extended CLI integration so manifest generation receives `flat` context and auth-expired partial manifests preserve the real local output path.
- Added regression coverage for preserved-folder, flat, legacy-missing, invalid stored, and auth-expired manifest path cases.

## Task Commits

Each task was committed atomically:

1. **Task 1: Make persisted local_path the manifest source of truth** - `61d9df5` (fix)
2. **Task 2: Propagate flat-mode context into manifest generation and verify end-to-end CLI behavior** - `900798c` (fix)

**Plan metadata:** pending closeout commit

## Files Created/Modified

- `.planning/phases/05-manifest-path-accuracy/05-01-SUMMARY.md` - Phase summary and execution record
- `sharepoint_dl/state/job_state.py` - Shared relative-path derivation, validation, and entry fallback helpers
- `sharepoint_dl/downloader/engine.py` - Local destination placement now reuses the shared derivation helper
- `sharepoint_dl/manifest/writer.py` - Manifest `local_path` comes from persisted state or the shared safe fallback
- `sharepoint_dl/cli/main.py` - Manifest generation now receives `flat` mode context
- `tests/test_manifest.py` - Direct manifest path regressions for persisted, legacy, invalid, and flat cases
- `tests/test_cli.py` - CLI integration coverage for flat-mode and auth-expired manifest path accuracy

## Decisions Made

- Treated persisted `local_path` as authoritative evidence when it is relative and traversal-safe.
- Rejected absolute and `..` paths instead of emitting unsafe manifest entries.
- Kept fallback derivation relative to `dest_dir` so manifests never record absolute local paths.

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

- A transient `.git/index.lock` conflict occurred when `git add` and `git commit` were launched in parallel; subsequent commits were done sequentially.

## User Setup Required

None.

## Next Phase Readiness

Phase 06 can now normalize the milestone evidence and planning docs against corrected Phase 05 manifest behavior.

---
*Phase: 05-manifest-path-accuracy*
*Completed: 2026-03-27*
