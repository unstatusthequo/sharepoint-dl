---
phase: 04-resume-safety-and-failure-reporting
plan: 02
subsystem: cli
tags: [typer, pytest, manifest, jobstate, auth-expiry]
requires:
  - phase: 03-forensic-deliverables
    provides: completeness reporting and manifest generation hooks
provides:
  - download preflight scope is printed before confirmation or transfer
  - auth-expired downloads continue through completeness/error reporting
  - partial manifests are generated from persisted JobState on auth expiry
affects: [05-manifest-path-accuracy, 06-audit-evidence-normalization]
tech-stack:
  added: []
  patterns:
    - "Pre-download scope is emitted unconditionally before any transfer starts."
    - "Auth expiry is treated as a failed run outcome that reloads persisted JobState for reporting."
key-files:
  created:
    - .planning/phases/04-resume-safety-and-failure-reporting/04-02-SUMMARY.md
  modified:
    - sharepoint_dl/cli/main.py
    - tests/test_cli.py
key-decisions:
  - "Print the download scope before confirmation so scripted --yes runs and interactive runs share the same preflight visibility."
  - "Reload persisted JobState after AuthExpiredError so manifest generation and run summaries use the same on-disk evidence."
patterns-established:
  - "Download commands should show scope before any transfer begins."
  - "Auth-expired runs should still reach the completeness and failure reporting tail."
requirements-completed: [ENUM-03, CLI-03]

# Metrics
duration: 25min
completed: 2026-03-27
---

# Phase 4: Resume Safety and Failure Reporting Summary

**Download scope is shown before transfer starts, and auth-expired runs still emit completeness, failure, and manifest evidence from persisted state**

## Performance

- **Duration:** 25min
- **Started:** 2026-03-27T22:02:00Z
- **Completed:** 2026-03-27T22:27:04Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Printed file count, total size, and destination before confirmation on every `download` run, including `--yes`
- Preserved the failure-reporting tail for auth-expired downloads by reloading persisted `JobState`
- Generated partial manifests from persisted state so auth-expired runs still leave evidence behind

## Task Commits

1. **Task 1: Print pre-download scope unconditionally before transfers begin** - `964be7a` (fix)
2. **Task 2: Emit completeness and failure reporting even on auth-expired runs** - `0fb19ad` (fix)

**Plan metadata:** docs(04-02): complete resume safety and failure reporting plan

## Files Created/Modified
- `.planning/phases/04-resume-safety-and-failure-reporting/04-02-SUMMARY.md` - phase summary and completion metadata
- `sharepoint_dl/cli/main.py` - preflight scope output and auth-expiry-aware reporting tail
- `tests/test_cli.py` - regression coverage for `--yes`, auth-expiry reporting, and persisted-state manifest generation

## Decisions Made
- Show the pre-download scope unconditionally so interactive and scripted runs have the same visibility.
- Treat auth expiry as a failed run outcome, not an early abort, so reporting and evidence generation still happen.
- Use persisted `JobState` as the source of truth for the partial manifest after auth expiry.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 5 can now focus on manifest path accuracy without re-litigating resume safety or auth-expiry reporting behavior.

---
*Phase: 04-resume-safety-and-failure-reporting*
*Completed: 2026-03-27*
