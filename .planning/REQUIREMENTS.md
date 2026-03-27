# Requirements: SharePoint Bulk Downloader

**Defined:** 2026-03-27
**Core Value:** Every file in the shared folder is downloaded, and the user can prove it — no silent failures, no missing files, no guesswork.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Authentication

- [x] **AUTH-01**: User can authenticate via Playwright browser session capture (login once, cookies reused)
- [x] **AUTH-02**: Tool validates session is active before starting any downloads
- [x] **AUTH-03**: Tool detects expired session mid-run and prompts user to re-authenticate

### Enumeration

- [x] **ENUM-01**: Tool recursively traverses all folders/subfolders via SharePoint REST API
- [x] **ENUM-02**: Tool paginates folder listings with `$skiptoken` to capture all files (no silent truncation)
- [x] **ENUM-03**: Tool displays total file count found before downloading begins

### Download Engine

- [x] **DWNL-01**: Tool streams downloads in chunks (8MB) to handle files up to 2GB without memory issues
- [x] **DWNL-02**: Tool resumes interrupted runs — skips completed files, retries failures
- [x] **DWNL-03**: Tool tracks all failures explicitly — no file is ever silently skipped
- [x] **DWNL-04**: Tool exits with non-zero code if any file fails to download
- [x] **DWNL-05**: Tool downloads 2-4 files concurrently for speed

### Verification & Manifest

- [x] **VRFY-01**: Tool computes SHA-256 hash during download (single I/O pass, no re-read)
- [x] **VRFY-02**: Tool generates JSON manifest with file path, size, hash, and download timestamp per file
- [x] **VRFY-03**: Tool produces completeness report comparing expected vs downloaded file count

### CLI & UX

- [x] **CLI-01**: User can specify download destination folder at launch
- [x] **CLI-02**: Tool shows per-file and overall progress bars during download
- [x] **CLI-03**: Tool shows clear error summary at end of run with file-level detail

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Enumeration

- **ENUM-04**: Dry-run mode — enumerate and report without downloading

### Authentication

- **AUTH-04**: Swappable auth layer supporting both legacy OTP and Entra B2B flows
- **AUTH-05**: Headless mode after initial browser login

### CLI & UX

- **CLI-04**: Config file for saved SharePoint URLs and custodian paths
- **CLI-05**: Multi-custodian batch mode (queue multiple custodians in one run)

### Download Engine

- **DWNL-06**: Bandwidth throttling option

### Verification & Manifest

- **VRFY-04**: NIST/SWGDE-aligned forensic report format

## Out of Scope

| Feature | Reason |
|---------|--------|
| Upload capability | Download-only tool |
| File preview or browsing UI | Just download what's there; use browser for browsing |
| Ongoing sync | Full download tool, not a sync client |
| Windows/Linux support | Mac-only for v1; cross-platform later |
| Microsoft Graph API auth | Guest OTP/B2B access doesn't support app registration |
| Real-time notifications | Not needed for batch download tool |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | Phase 1 | Complete |
| AUTH-02 | Phase 1 | Complete |
| AUTH-03 | Phase 1 | Complete |
| ENUM-01 | Phase 1 | Complete |
| ENUM-02 | Phase 1 | Complete |
| ENUM-03 | Phase 4 | Complete |
| CLI-01 | Phase 1 | Complete |
| DWNL-01 | Phase 2 | Complete |
| DWNL-02 | Phase 4 | Complete |
| DWNL-03 | Phase 2 | Complete |
| DWNL-04 | Phase 2 | Complete |
| DWNL-05 | Phase 2 | Complete |
| CLI-02 | Phase 2 | Complete |
| CLI-03 | Phase 4 | Complete |
| VRFY-01 | Phase 3 | Complete |
| VRFY-02 | Phase 5 | Complete |
| VRFY-03 | Phase 3 | Complete |

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 17
- Fully satisfied: 17
- Pending gap closure: 0
- Unmapped: 0

---
*Requirements defined: 2026-03-27*
*Last updated: 2026-03-27 — Phase 05 verified complete*
