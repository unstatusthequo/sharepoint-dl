---
status: complete
phase: 08-new-contained-modules
source: [08-01-SUMMARY.md, 08-02-SUMMARY.md]
started: 2026-03-31T00:00:00Z
updated: 2026-03-31T00:00:00Z
---

## Current Test

number: 1
name: Config Saves After Download
expected: |
  After a successful download, run the tool again. The sharing URL, download destination, and worker count should be pre-filled with the values from the last run.
awaiting: user response

## Tests

### 1. Config Saves After Download
expected: After a successful download, run the tool again. The sharing URL, download destination, and worker count should be pre-filled with the values from the last run.
result: issue
reported: "Config not saving — save_config was after exit-on-failure check so downloads with any failed files never persisted preferences"
severity: major
notes: Fixed inline — moved save_config before exit checks

### 2. Verify Command
expected: Run `./run.sh verify <download-folder>` against the folder you just downloaded. It should show a Rich progress bar while re-hashing files, then display per-file PASS/FAIL results and exit 0 if all pass.
result: pass
notes: Initially showed all MISSING due to legacy double-prefixed paths (files/files/). Fixed with fallback path stripping in verifier.

### 3. Throttle Flag
expected: Run `./run.sh download <url> <dest> --throttle 5MB --yes`. The download speed should be visibly limited to ~5 MB/s in the progress bar (vs the unthrottled speed you saw earlier).
result: skipped
reason: User wants throttle and verify integrated into the TUI flow, not as CLI flags. Throttle should be a prompt after worker count; verify should be a top-level choice at startup ("Download or Verify?"). Tracked as TODO.

## Summary

total: 3
passed: 1
issues: 1
pending: 0
skipped: 1
blocked: 0

## Gaps
