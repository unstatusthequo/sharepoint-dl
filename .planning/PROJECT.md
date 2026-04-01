# SharePoint Bulk Downloader (SPDL)

## What This Is

A reliable bulk download tool for SharePoint shared folders, designed for forensic evidence collection. Authenticates via browser session (email + OTP or SSO login), provides an interactive TUI for folder browsing, batch download, and post-download verification. Produces SHA-256 manifests in both JSON and CSV for provable completeness. Cross-platform (macOS, Windows, Linux).

## Core Value

Every file in the shared folder is downloaded, and the user can prove it — no silent failures, no missing files, no guesswork.

## Current State

**Shipped:** v1.0 MVP (2026-03-27), v1.1 Feature Expansion (2026-03-31)

**Codebase:** ~3,000 LOC Python, ~4,100 LOC tests (168 tests). Tech stack: Python 3.11-3.13, Playwright, requests, typer, rich, tenacity, tomli-w. Managed via uv.

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

### Validated (v1.1)

- [x] Auto-detect folder from sharing link — UX-01
- [x] Batch queue multiple folders — UX-02
- [x] Config file persistence — UX-03
- [x] ETA and speed display — UX-04
- [x] TUI-first verify and throttle — UX-05
- [x] Per-file elapsed timer — UX-06
- [x] Auto re-auth on 401 — REL-01
- [x] Bandwidth throttle — REL-02
- [x] Timestamped download.log — REL-03
- [x] Verify command (SHA-256 re-hash) — FOR-01
- [x] CSV manifest report — FOR-02

### Out of Scope

- Microsoft Graph API auth — guest OTP/B2B access doesn't support app registration
- Upload capability — download only
- Incremental sync — full download, not ongoing sync
- Real-time notifications — batch download tool
- PyPI publish — `spdl` name taken by Meta, keep repo distribution for now

## Context

- **Use case:** Forensic evidence collection from third-party SharePoint. Also general-purpose bulk download from shared links.
- **Auth model:** Both SharePoint OTP sharing links and authenticated SSO links supported via Playwright browser session.
- **Platform:** macOS, Windows. Linux untested but should work.
- **Distribution:** Public GitHub repo. `./run.sh` handles all setup automatically.
- **Tech stack:** Python 3.11-3.13, Playwright, requests, typer, rich, tenacity, tomli-w. Managed via uv.

## Constraints

- **Auth**: Must work with both SharePoint guest/external sharing (OTP) and authenticated SSO links
- **Reliability**: Forensic context requires provable completeness (manifest + hashes)
- **File size**: Must handle files up to ~2GB without corruption
- **UX**: Interactive TUI is primary; CLI flags for scripting/automation
- **Resilience**: run.sh must handle all setup — no manual pip install or playwright install

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Browser session-based auth | Guest OTP doesn't support OAuth app registration | Validated v1.0 |
| SHA-256 manifest | Forensic evidence requires provable completeness | Validated v1.0 |
| Interactive TUI as primary UX | Long URLs and paths are error-prone to type manually | Validated v1.0 |
| python -m invocation via run.sh | uv entrypoint scripts unreliable; __main__.py always works | Validated v1.0 |
| Keep source folders default | Flat mode causes filename collisions with multi-folder downloads | Changed v1.1 (was flat default) |
| Metadata at job root, files in timestamped subdir | Forensic separation between tool artifacts and evidence | Validated v1.1 |
| CSV alongside JSON manifest | Human-readable reporting for forensic/legal review | Validated v1.1 |
| Token bucket throttle (single shared instance) | Per-worker throttle multiplies effective bandwidth | Validated v1.1 |
| Check-lock-check re-auth pattern | Only one browser window across N workers on 401 | Validated v1.1 |
| Parent-domain cookie loading | SharePoint rtFa cookie on .sharepoint.com needed for authenticated links | Validated v1.1 |
| run.sh Playwright health check | Node.js upgrades break Playwright driver; auto-repair on launch | Validated v1.1 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone:**
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-31 — v1.1 Feature Expansion complete*
