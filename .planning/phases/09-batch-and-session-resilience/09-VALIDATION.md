---
phase: 09
slug: batch-and-session-resilience
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-30
---

# Phase 09 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `.venv/bin/python -m pytest -q --tb=short` |
| **Full suite command** | `.venv/bin/python -m pytest -v --tb=long` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest -q --tb=short`
- **After every plan wave:** Run `.venv/bin/python -m pytest -v --tb=long`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | REL-01 | unit | `.venv/bin/python -m pytest tests/test_reauth.py -q` | ❌ W0 | ⬜ pending |
| 09-01-02 | 01 | 1 | REL-01 | unit | `.venv/bin/python -m pytest tests/test_reauth.py -q` | ❌ W0 | ⬜ pending |
| 09-02-01 | 02 | 2 | UX-02 | unit | `.venv/bin/python -m pytest tests/test_batch.py -q` | ❌ W0 | ⬜ pending |
| 09-02-02 | 02 | 2 | UX-02,REL-01 | integration | `.venv/bin/python -m pytest tests/test_cli.py -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_reauth.py` — stubs for ReauthController, lock contention, max attempts, cookie injection
- [ ] `tests/test_batch.py` — stubs for batch queue loop, per-job subdirectory isolation

*Existing `tests/test_cli.py` covers CLI integration; extend with batch and re-auth scenarios.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Browser popup on 401 | REL-01 | Playwright GUI requires display | Trigger 401 during download, verify browser opens automatically |
| Re-auth across 4 workers | REL-01 | Requires real SharePoint session | Run download with --workers 4, expire session, verify single browser |
| Batch folder queue UX | UX-02 | Interactive TUI prompt | Complete download, verify "Queue another folder?" appears |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
