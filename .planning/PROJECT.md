# SharePoint Bulk Downloader

## What This Is

A reliable bulk download tool for SharePoint shared folders, designed for forensic evidence collection. It authenticates via the browser's existing guest session (email + one-time code), downloads all files from a target folder, and produces a verification manifest with file sizes and hashes to prove completeness. Built for Mac, with cross-platform support planned for later.

## Core Value

Every file in the shared folder is downloaded, and the user can prove it — no silent failures, no missing files, no guesswork.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Bulk download all files from a SharePoint shared folder
- [ ] Authenticate using existing browser session (guest email + OTP auth)
- [ ] Recursive traversal of folder structure (custodian → subfolder → files)
- [ ] Preserve folder structure in local download destination
- [ ] User chooses download destination at launch
- [ ] Generate verification manifest (filename, size, hash for every file)
- [ ] Report on completeness: files expected vs files downloaded
- [ ] Resume/retry failed downloads without re-downloading completed files
- [ ] Handle large files (up to ~2GB per file)
- [ ] Clear error reporting — never silently skip a file

### Out of Scope

- Windows/Linux support — Mac-only for v1, cross-platform later
- Microsoft Graph API auth — guest OTP access doesn't support this cleanly
- Upload capability — download only
- File preview or browsing UI — just download what's there
- Incremental sync — full download, not ongoing sync

## Context

- **Use case:** Forensic evidence collection from third-party SharePoint. Files are EnCase evidence files (.E01, .L01 etc.) and logical evidence files, typically up to ~2GB each.
- **Structure:** `Images/[custodian name]/[subfolder(s)]/[100+ files]`. Currently 3 custodians to download. Files are concentrated in leaf folders, not spread across the tree.
- **Auth model:** SharePoint external sharing — user receives a link, enters email, gets a one-time code. This creates a browser session but doesn't provide API tokens in a standard OAuth flow.
- **Prior attempt:** A Python script existed that downloaded files but silently skipped some. Root cause unknown — could be pagination, auth expiry, timeout on large files, or API issues.
- **Urgency:** Active project deadline. Needs to work reliably on first real use.

## Constraints

- **Auth**: Must work with SharePoint guest/external sharing (email + OTP code) — no admin access or app registrations available on the target tenant
- **Reliability**: Forensic context means completeness must be provable. A manifest with hashes is non-negotiable.
- **File size**: Must handle files up to ~2GB without corruption or timeout
- **Platform**: Mac (macOS) for v1

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Browser session-based auth over API auth | Guest OTP access doesn't support standard OAuth app registration; leveraging browser session is the practical path | — Pending |
| Manifest with hashes for verification | Forensic evidence requires provable completeness — file count alone isn't sufficient | — Pending |
| Mac-only v1 | Urgent need is on Mac; cross-platform deferred to avoid scope creep | — Pending |

---
*Last updated: 2026-03-27 after initialization*
