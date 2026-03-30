---
status: testing
phase: 02-download-engine
source: [02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md]
started: 2026-03-27T21:30:00Z
updated: 2026-03-27T21:30:00Z
---

## Current Test

number: 1
name: Download with --flat flag
expected: |
  Run `sharepoint-dl download '<url>' /path/to/dest -r '<custodian-folder>' --flat --workers 1 --yes`
  Files download directly into the dest folder — no nested subdirectories.
  A .part file appears during download, renamed to final name on completion.
awaiting: user response

## Tests

### 1. Download with --flat flag
expected: Run download with `--flat`. All files land directly in the dest folder with no subdirectories. A `.part` temp file appears during download, renamed on completion.
result: [pending]

### 2. Concurrent downloads
expected: Run download with `--workers 3` (default). Multiple files download simultaneously. Progress bars show per-worker lines updating in parallel.
result: [pending]

### 3. Resume after interrupt
expected: Start a download, then Ctrl+C mid-way. Re-run the same command. Completed files are skipped ("Found X complete files, resuming..."). Only pending/failed files are retried.
result: [pending]

### 4. Error summary on failure
expected: If any file fails to download (timeout, server error), a red error table appears at the end listing each failed file and the error reason. Tool exits with code 1.
result: [pending]

### 5. Confirmation prompt
expected: Run download WITHOUT `--yes`. Tool shows "Download N files (X GB) to /path?" and waits for confirmation. Typing "n" aborts. Typing "y" or Enter proceeds.
result: [pending]

### 6. Completeness report
expected: After download completes, tool prints a completeness report showing Expected/Downloaded/Failed counts and COMPLETE or INCOMPLETE status.
result: [pending]

### 7. Manifest generation
expected: After successful download, `manifest.json` appears in the dest folder containing per-file entries with filename, path, size, SHA-256 hash, and timestamp. Tool prints "Manifest written to: /path/to/manifest.json".
result: [pending]

## Summary

total: 7
passed: 0
issues: 0
pending: 7
skipped: 0

## Gaps

[none yet]
