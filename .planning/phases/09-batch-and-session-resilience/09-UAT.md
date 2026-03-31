---
status: complete
phase: 09-batch-and-session-resilience
source: [09-01-SUMMARY.md, 09-02-SUMMARY.md, 09-03-SUMMARY.md]
started: 2026-03-31T00:00:00Z
updated: 2026-03-31T00:00:00Z
---

## Current Test

number: 1
name: Queue Another Folder After Download
expected: |
  After a download completes, the TUI asks "Queue another folder?" If you say yes, you can select another folder and it downloads sequentially in the same session without re-authenticating.
awaiting: user response

## Tests

### 1. Queue Another Folder After Download
expected: After a download completes, the TUI asks "Queue another folder?" If you say yes, you can select another folder and it downloads sequentially in the same session without re-authenticating.
result: pass

### 2. Session Survives Across Batch Jobs
expected: When queuing a second folder, the tool does NOT re-open the browser or ask you to re-authenticate. It reuses the same session from the first download.
result: pass

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
