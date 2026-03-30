---
phase: 09-batch-and-session-resilience
plan: "03"
subsystem: cli
tags: [batch, interactive-mode, per-job-isolation, session-reuse]
dependency_graph:
  requires: [09-01, 09-02]
  provides: [batch-loop, job-dest-helper, batch-summary]
  affects: [sharepoint_dl/cli/main.py, tests/test_cli.py]
tech_stack:
  added: []
  patterns: [per-job timestamped subdirectory, batch loop with session reuse, shutdown_download_logger between jobs]
key_files:
  created: []
  modified:
    - sharepoint_dl/cli/main.py
    - tests/test_cli.py
decisions:
  - "_job_dest uses timestamp prefix YYYY-MM-DD_HHMMSS plus sanitized folder leaf for unique per-job directory naming"
  - "batch_root captured once before the batch loop; job_dest computed per iteration so each job is fully isolated"
  - "shutdown_download_logger called at end of each job to release file handles before next job opens new log"
  - "Session object reused across all batch jobs per D-10 — no re-authentication between jobs"
metrics:
  duration: "~10min"
  completed_date: "2026-03-30"
  tasks_completed: 1
  files_modified: 2
---

# Phase 09 Plan 03: Batch Queue UX — Interactive Mode Summary

Batch queue UX added to interactive mode: _job_dest helper creates timestamped per-job subdirectories, download flow wrapped in batch loop, session shared across jobs, batch summary table shown after 2+ jobs.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 (RED) | Add failing TestBatchMode tests for _job_dest helper | 091d4b8 |
| 1 (GREEN) | Implement _job_dest helper and batch loop in _interactive_mode_inner | 8ee02b8 |

## What Was Built

**`_job_dest(batch_root, folder_path) -> Path`** — helper that creates a timestamped subdirectory for each batch job under the user-specified root:
- Naming convention: `{YYYY-MM-DD_HHMMSS}_{sanitized_folder_leaf}`
- Sanitizes leaf: only alphanumeric, `-`, `_` allowed; all others replaced with `_`
- Creates directory immediately (mkdir parents=True, exist_ok=True)

**Batch loop in `_interactive_mode_inner`:**
- Destination and workers configured once before the loop
- Each iteration: folder selection -> enumeration -> confirmation -> `job_dest = _job_dest(batch_root, server_relative_path)`
- `job_dest` passed to `setup_download_logger`, `download_all`, `JobState`, `generate_manifest` — per-job isolation enforced
- `shutdown_download_logger()` called at end of each job before next iteration
- After completeness report: `Confirm.ask("Queue another folder?", default=False)`
- If yes, resets `current_path = root_path` and loops back to folder selection
- `session` NOT re-acquired — reused across all jobs per D-10

**Batch summary table:**
- Shown only when `len(batch_results) > 1`
- Columns: Folder, Files, Status, Time
- Status column styled green for OK, red for FAILED/AUTH_EXPIRED/CANCELLED

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- `sharepoint_dl/cli/main.py` exists and contains `_job_dest`, `Queue another folder?`, `BATCH SUMMARY`, `batch_results`
- `tests/test_cli.py` exists and contains `class TestBatchMode`
- Commits 091d4b8 and 8ee02b8 exist
- `pytest tests/test_cli.py` — 37 passed
- `python -c "from sharepoint_dl.cli.main import _job_dest, app; print('OK')"` — OK
