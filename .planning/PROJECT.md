# SharePoint Bulk Downloader (SPDL)

## What This Is

A reliable bulk download tool for SharePoint shared folders, designed for forensic evidence collection. Authenticates via browser session (email + OTP code), provides an interactive TUI for folder browsing and download, and produces a verification manifest with SHA-256 hashes to prove completeness. Cross-platform (macOS, Windows, Linux).

## Core Value

Every file in the shared folder is downloaded, and the user can prove it — no silent failures, no missing files, no guesswork.

## Current Milestone: v1.1 Feature Expansion

**Goal:** Make SPDL easier to use, more reliable during long downloads, verifiable after download, and distributable via PyPI.

**Target features:**
- Auto-detect root folder from sharing link (eliminate manual `-r` flag)
- Multi-folder batch download (queue multiple custodians in one session)
- Post-download integrity verification (`verify` command)
- Publish to PyPI as `spdl`
- Smart session refresh mid-download (auto re-auth on 401)
- Bandwidth throttling
- Download speed estimation & ETA
- Config file for saved settings
- Timestamped log file for audit trail

## Requirements

### Validated (v1.0)

- [x] Browser session capture via Playwright (AUTH-01)
- [x] Session validation before downloads (AUTH-02)
- [x] Session expiry detection mid-run (AUTH-03)
- [x] Recursive folder traversal with pagination (ENUM-01, ENUM-02)
- [x] Pre-download file count display (ENUM-03)
- [x] Streaming 8MB chunk downloads for 2GB+ files (DWNL-01)
- [x] Resume interrupted runs (DWNL-02)
- [x] Explicit failure tracking (DWNL-03)
- [x] Non-zero exit on failure (DWNL-04)
- [x] Concurrent downloads 1-8 workers (DWNL-05)
- [x] SHA-256 hashes during download (VRFY-01)
- [x] JSON manifest with per-file metadata (VRFY-02)
- [x] Completeness report (VRFY-03)
- [x] Download destination selection (CLI-01)
- [x] Progress bars (CLI-02)
- [x] Error summary (CLI-03)
- [x] Interactive TUI with folder browser
- [x] Cross-platform support (macOS, Windows)

### Active (v1.1)

See REQUIREMENTS.md for full v1.1 requirements.

### Out of Scope

- Microsoft Graph API auth — guest OTP access doesn't support app registration
- Upload capability — download only
- Incremental sync — full download, not ongoing sync
- Real-time notifications — batch download tool

## Context

- **Use case:** Forensic evidence collection from third-party SharePoint. Also general-purpose bulk download from shared links.
- **Auth model:** SharePoint external sharing — email + OTP code via Playwright browser session.
- **Platform:** macOS, Windows. Linux untested but should work.
- **Distribution:** Public GitHub repo. PyPI planned for v1.1.
- **Tech stack:** Python 3.11-3.13, Playwright, requests, typer, rich, tenacity. Managed via uv.

## Constraints

- **Auth**: Must work with SharePoint guest/external sharing — no admin access or app registrations
- **Reliability**: Forensic context requires provable completeness (manifest + hashes)
- **File size**: Must handle files up to ~2GB without corruption
- **UX**: Interactive TUI is primary; CLI flags for scripting/automation

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Browser session-based auth | Guest OTP doesn't support OAuth app registration | Validated v1.0 |
| SHA-256 manifest | Forensic evidence requires provable completeness | Validated v1.0 |
| Interactive TUI as primary UX | Long URLs and paths are error-prone to type manually | Validated v1.0 |
| python -m invocation via run.sh | uv entrypoint scripts unreliable; __main__.py always works | Validated v1.0 |
| Flat download as TUI default | Users don't want deep folder nesting for evidence files | Validated v1.0 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-30 — Milestone v1.1 started*
