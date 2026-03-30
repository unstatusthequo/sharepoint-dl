# External Integrations

**Analysis Date:** 2026-03-30

## APIs & External Services

**External APIs:**
- SharePoint Online REST API - Used for folder enumeration, session validation, and file downloads
  - Integration method: `requests.Session` calls in `sharepoint_dl/enumerator/traversal.py`, `sharepoint_dl/auth/session.py`, and `sharepoint_dl/downloader/engine.py`
  - Auth: Browser-derived cookies persisted in `~/.sharepoint-dl/session.json`
  - Endpoints used: `/_api/web/title`, `/_api/web/GetFolderByServerRelativeUrl(...)`, and `/_layouts/15/download.aspx?SourceUrl=...`
  - Example paths: `sharepoint_dl/cli/main.py`, `sharepoint_dl/enumerator/traversal.py`

**Browser / Auth Flow:**
- Chromium via Playwright - Used to complete interactive SharePoint login and capture the authenticated session
  - SDK/Client: `playwright.sync_api.sync_playwright`
  - Auth: User completes email + OTP or tenant login in the browser window
  - Session capture: Playwright `storage_state` is written, then converted to `session.json`
  - Example paths: `sharepoint_dl/auth/browser.py`, `sharepoint_dl/auth/session.py`

## Data Storage

**File Storage:**
- Local filesystem destination chosen by the user - Download target for retrieved SharePoint files
  - Integration method: Direct writes to the selected destination directory
  - Artifacts: downloaded files, `state.json`, `manifest.json`, and transient `.part` files
  - Example paths: `sharepoint_dl/downloader/engine.py`, `sharepoint_dl/manifest/writer.py`, `sharepoint_dl/state/job_state.py`

**Session Storage:**
- User home directory state - Cached auth session for re-use across runs
  - Location: `~/.sharepoint-dl/session.json`
  - Purpose: Persist SharePoint cookies and bind them to the originating host
  - Example paths: `sharepoint_dl/auth/session.py`

## Authentication & Identity

**Auth Provider:**
- SharePoint / Microsoft 365 tenant authentication - Interactive browser login, then cookie-based reuse
  - Implementation: Playwright logs in, `requests.Session` replays cookies for API access
  - Token storage: cookies in the local session file, not OAuth tokens in environment variables
  - Session management: host-bound validation before reuse via `/_api/web/title`
  - Example paths: `sharepoint_dl/auth/browser.py`, `sharepoint_dl/auth/session.py`

## Monitoring & Observability

**Logs:**
- Standard output / standard error only - No external logging or observability service is wired in
  - Integration: Rich renders progress and status directly in the terminal
  - Example paths: `sharepoint_dl/cli/main.py`, `sharepoint_dl/downloader/engine.py`

## CI/CD & Deployment

**Hosting:**
- None - The project is a local CLI tool, not a hosted application

**CI Pipeline:**
- Not defined in the repository snapshot

## Environment Configuration

**Development:**
- Required inputs: a SharePoint sharing URL and access to the target tenant
- Browser dependency: Playwright-managed Chromium must be installed before auth
- Secrets location: session cookies are stored locally on disk, not in repo files

**Production:**
- No production backend or remote service is managed by this repository
- Output is written locally to the user-selected destination

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

---

*Integration audit: 2026-03-30*
*Update when adding/removing external services*
