---
status: complete
phase: 07-zero-risk-ux-wins
source: [07-01-SUMMARY.md, 07-02-SUMMARY.md]
started: 2026-03-31T00:00:00Z
updated: 2026-03-31T00:00:00Z
---

## Current Test

number: 1
name: ETA and Speed in Progress Bar
expected: |
  During an active download, the progress bar shows current download speed (e.g. "2.5 MB/s") and estimated time remaining (e.g. "eta 0:01:23").
awaiting: user response

## Tests

### 1. ETA and Speed in Progress Bar
expected: During an active download, the progress bar shows current download speed (e.g. "2.5 MB/s") and estimated time remaining (e.g. "eta 0:01:23").
result: pass

### 2. Download Log File Created
expected: After a download completes, a `download.log` file exists in the download destination folder. It contains timestamped entries like "2026-03-31 14:23:01 | INFO | Authenticated successfully" and per-file download events.
result: pass
notes: User reported metadata files (download.log, manifest.json, state.json) are commingled with downloaded files — wants segregation into a "files" subfolder for downloaded content. Tracked separately.

### 3. Log Does Not Corrupt TUI
expected: During download, the Rich progress bar displays cleanly with no interleaved log text. The log writes only to the file, not to the console.
result: pass

### 4. Auto-Detect Root Folder from Sharing Link
expected: Run `./run.sh download <sharing-link> /tmp/test` WITHOUT the `--root-folder` flag. The tool auto-resolves the folder path from the URL and starts downloading (or shows "Auto-detected folder: /sites/...").
result: skipped
reason: User prefers interactive mode (run.sh) as primary UX — CLI flags are secondary. Auto-detect already works in interactive mode.

## Summary

total: 4
passed: 3
issues: 0
pending: 0
skipped: 1
blocked: 0

## Gaps
