---
status: complete
phase: 10-tui-polish
source: [10-01-SUMMARY.md, 10-02-SUMMARY.md]
started: 2026-03-31T00:00:00Z
updated: 2026-03-31T00:00:00Z
---

## Current Test

number: 1
name: Startup Menu
expected: |
  Run ./run.sh. After the banner, you should see a numbered menu:
  1. Download files
  2. Verify a prior download
  Selecting 1 should proceed to the sharing URL prompt as before.
awaiting: user response

## Tests

### 1. Startup Menu
expected: Run ./run.sh. After the banner, a numbered menu appears: "1. Download files  2. Verify a prior download". Selecting 1 proceeds to the sharing URL prompt.
result: pass

### 2. TUI Verify Flow
expected: From the startup menu, select 2. It should prompt for a folder path (pre-filled from your last download destination). Entering a valid path runs verification with a progress bar and shows PASS/FAIL results.
result: pass

### 3. Throttle Prompt
expected: During a download flow, after the workers prompt, you should see "Bandwidth limit? (e.g. 5MB, Enter to skip)". Pressing Enter skips it. Typing "5MB" should limit speed.
result: pass

### 4. CSV Manifest Generated
expected: After a download completes, check the download folder. A manifest.csv file should exist alongside manifest.json. Open it — it should have columns: filename, local_path, size_bytes, sha256, status, error, downloaded_at.
result: pass

### 5. Per-File Elapsed Timer
expected: During download, each file's progress row shows its own elapsed time (resetting to 0s when a new file starts on that worker), not the overall session time.
result: pass
notes: Confirmed working. Occasionally shows N-1 of N workers visible — likely timing between file assignments. Cosmetic only.

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
