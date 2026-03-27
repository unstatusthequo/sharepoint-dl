---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` — `[tool.pytest.ini_options]` section (Wave 0 creates) |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | — | scaffold | `uv run pytest tests/ -x -q` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | AUTH-01 | unit (mock Playwright) | `uv run pytest tests/test_auth.py::test_harvest_session_writes_file -x` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | AUTH-01 | unit | `uv run pytest tests/test_auth.py::test_load_session_injects_cookies -x` | ❌ W0 | ⬜ pending |
| 01-02-03 | 02 | 1 | AUTH-01 | unit | `uv run pytest tests/test_auth.py::test_load_session_missing_file -x` | ❌ W0 | ⬜ pending |
| 01-02-04 | 02 | 1 | AUTH-01 | unit | `uv run pytest tests/test_auth.py::test_host_mismatch_returns_none -x` | ❌ W0 | ⬜ pending |
| 01-02-05 | 02 | 1 | AUTH-02 | unit (mock requests) | `uv run pytest tests/test_auth.py::test_validate_session_active -x` | ❌ W0 | ⬜ pending |
| 01-02-06 | 02 | 1 | AUTH-02 | unit (mock requests) | `uv run pytest tests/test_auth.py::test_validate_session_expired -x` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | AUTH-03 | unit (mock 401 mid-traversal) | `uv run pytest tests/test_traversal.py::test_auth_expiry_halts -x` | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 2 | ENUM-01 | unit (mocked API) | `uv run pytest tests/test_traversal.py::test_recursion_into_subfolders -x` | ❌ W0 | ⬜ pending |
| 01-03-03 | 03 | 2 | ENUM-02 | unit (mocked pagination) | `uv run pytest tests/test_traversal.py::test_pagination_follows_next_link -x` | ❌ W0 | ⬜ pending |
| 01-03-04 | 03 | 2 | ENUM-02 | unit | `uv run pytest tests/test_traversal.py::test_no_pagination_needed -x` | ❌ W0 | ⬜ pending |
| 01-03-05 | 03 | 2 | ENUM-03 | unit | `uv run pytest tests/test_traversal.py::test_file_count_accuracy -x` | ❌ W0 | ⬜ pending |
| 01-03-06 | 03 | 2 | CLI-01 | unit (mock enumerator) | `uv run pytest tests/test_cli.py::test_list_command -x` | ❌ W0 | ⬜ pending |
| 01-03-07 | 03 | 2 | CLI-01 | unit | `uv run pytest tests/test_cli.py::test_download_stub -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — `[tool.pytest.ini_options]` section with `testpaths = ["tests"]`
- [ ] `tests/conftest.py` — shared fixtures: mock session, mock SharePoint API responses with/without pagination
- [ ] `tests/test_auth.py` — AUTH-01, AUTH-02, AUTH-03 unit test stubs
- [ ] `tests/test_traversal.py` — ENUM-01, ENUM-02, ENUM-03, AUTH-03 unit test stubs
- [ ] `tests/test_cli.py` — CLI-01 unit test stubs

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Browser opens and user can complete auth flow | AUTH-01 | Requires real browser + real SharePoint | Run `sharepoint-dl auth <url>`, verify browser opens, complete login, verify session.json created |
| Enumerated file count matches SharePoint UI | ENUM-03 | Requires real SharePoint data | Run `sharepoint-dl list <url>`, compare count to browser |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
