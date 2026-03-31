---
phase: 10-tui-polish
plan: "01"
subsystem: manifest-writer, download-engine
tags: [csv, manifest, progress, elapsed-timer, tdd, forensic]
dependency_graph:
  requires: []
  provides: [manifest-csv, per-file-elapsed-timer]
  affects: [sharepoint_dl/manifest/writer.py, sharepoint_dl/downloader/engine.py]
tech_stack:
  added: []
  patterns: [atomic-write, field-based-progress, tdd-red-green]
key_files:
  created: []
  modified:
    - sharepoint_dl/manifest/writer.py
    - sharepoint_dl/downloader/engine.py
    - tests/test_manifest.py
    - tests/test_downloader.py
decisions:
  - "Used csv.DictWriter with extrasaction=ignore for clean field mapping"
  - "Field-based elapsed replaces TimeElapsedColumn to allow per-file reset"
  - "overall_start captured before ThreadPoolExecutor; file_start captured per worker task"
metrics:
  duration: "~3.5 min"
  completed_date: "2026-03-30"
  tasks_completed: 2
  files_modified: 4
---

# Phase 10 Plan 01: CSV Manifest Export and Per-File Elapsed Timer Summary

## One-liner

CSV manifest export via csv.DictWriter with COMPLETE/FAILED rows; per-file elapsed timer replacing TimeElapsedColumn in Rich progress bars.

## Tasks Completed

| Task | Description | Commit | Status |
|------|-------------|--------|--------|
| 1 (RED) | Failing tests for CSV manifest generation | 3f13f2c | Done |
| 1 (GREEN) | CSV generation in writer.py | affdc06 | Done |
| 2 (RED) | Failing tests for per-file elapsed timer | 62ff521 | Done |
| 2 (GREEN) | Per-file elapsed timer in engine.py | d9348e9 | Done |

## What Was Built

### Task 1: CSV Manifest Generation

`generate_manifest()` in `sharepoint_dl/manifest/writer.py` now automatically writes `manifest.csv` alongside `manifest.json` in the destination directory. No user flag or prompt required.

CSV format:
- 7 columns: `filename`, `local_path`, `size_bytes`, `sha256`, `status`, `error`, `downloaded_at`
- Complete files: `status=COMPLETE`, blank error, full SHA-256 hex digest
- Failed files: `status=FAILED`, error reason, blank sha256/local_path/downloaded_at, size_bytes=0
- Rows sorted by `server_relative_url` (same order as JSON)
- Atomic write via `.csv.tmp` + rename pattern
- Commas/quotes in filenames properly handled by `csv.DictWriter` (QUOTE_MINIMAL)

### Task 2: Per-File Elapsed Timer

`_make_progress()` in `sharepoint_dl/downloader/engine.py` now uses a field-based elapsed timer instead of `TimeElapsedColumn`. This allows each worker's elapsed timer to reset when it picks up a new file.

Changes:
- `TimeElapsedColumn` removed from imports and `_make_progress()` columns
- `TextColumn("{task.fields[elapsed]}")` added to progress layout
- `_format_elapsed(seconds: float) -> str` helper added (formats: "0s", "12s", "2m 15s")
- All tasks initialized with `elapsed="0s"` in fields dict
- Worker resets `elapsed="0s"` when starting a new file
- `on_chunk` callback updates per-file elapsed from `file_start = time.monotonic()`
- `on_chunk` also updates overall elapsed from `overall_start = time.monotonic()`

## Verification

```
uv run --extra dev --frozen pytest tests/test_manifest.py tests/test_downloader.py -x -q
# 49 passed in 3.19s
```

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- sharepoint_dl/manifest/writer.py — exists and contains csv import, _write_manifest_csv, manifest.csv references
- sharepoint_dl/downloader/engine.py — exists and contains _format_elapsed, time.monotonic, elapsed field references
- tests/test_manifest.py — exists with TestManifestCsvGeneration class
- tests/test_downloader.py — exists with TestFormatElapsed and TestPerFileElapsedTimer classes
- All commits confirmed in git log
