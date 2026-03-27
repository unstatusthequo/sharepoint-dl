---
phase: 2
slug: download-engine
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 |
| **Config file** | `pyproject.toml` — `[tool.pytest.ini_options]` (existing) |
| **Quick run command** | `uv run pytest tests/test_downloader.py tests/test_state.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_downloader.py tests/test_state.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | DWNL-01 | unit | `uv run pytest tests/test_downloader.py::TestStreaming -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | DWNL-01 | unit | `uv run pytest tests/test_downloader.py::TestHashing -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | DWNL-02 | unit | `uv run pytest tests/test_state.py::TestResume -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 1 | DWNL-02 | unit | `uv run pytest tests/test_state.py::TestPartCleanup -x` | ❌ W0 | ⬜ pending |
| 02-01-05 | 01 | 1 | DWNL-03 | unit | `uv run pytest tests/test_downloader.py::TestAuthHalt -x` | ❌ W0 | ⬜ pending |
| 02-01-06 | 01 | 1 | DWNL-03 | unit | `uv run pytest tests/test_downloader.py::TestFailureTracking -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | DWNL-05 | unit | `uv run pytest tests/test_downloader.py::TestConcurrency -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | CLI-02 | unit | `uv run pytest tests/test_downloader.py::TestProgress -x` | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 2 | DWNL-04 | unit | `uv run pytest tests/test_cli.py::TestDownloadExitCode -x` | ❌ W0 | ⬜ pending |
| 02-02-04 | 02 | 2 | CLI-03 | unit | `uv run pytest tests/test_cli.py::TestErrorSummary -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_downloader.py` — TestStreaming, TestHashing, TestAuthHalt, TestFailureTracking, TestConcurrency, TestProgress
- [ ] `tests/test_state.py` — TestResume, TestPartCleanup
- [ ] `tests/test_cli.py` — TestDownloadExitCode, TestErrorSummary (extend existing file)
- [ ] `tests/conftest.py` — Add mock download response fixtures (chunked iterator, error responses)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 2GB file downloads without memory issues | DWNL-01 | Requires real SharePoint + large file | Run download against real target, monitor memory |
| Resume after kill works correctly | DWNL-02 | Requires killing process mid-download | Start download, Ctrl-C, restart, verify skip |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
