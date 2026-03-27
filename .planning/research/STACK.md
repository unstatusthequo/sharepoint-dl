# Stack Research

**Domain:** SharePoint bulk file downloader (guest/external auth, forensic manifest)
**Researched:** 2026-03-27
**Confidence:** MEDIUM — core patterns are well-established; the auth layer has a critical moving-target risk described below.

---

## Critical Context: OTP Authentication Is Being Retired

SharePoint Online's email + one-time passcode (OTP) auth for external guests **is in active deprecation**. The timeline:

- **July 2025**: Microsoft began retiring OTP for tenants that opted into Entra B2B Collaboration.
- **May 2026**: New external sharing invitations automatically use Entra B2B guest accounts instead of OTP.
- **July 2026**: All remaining OTP links stop working entirely.

The PROJECT.md describes "email + one-time code" as the expected auth model. That model will stop functioning within 4 months of this writing. The practical replacement is Entra B2B guest account redemption — the external user authenticates via their own Microsoft/Entra identity (or via email verification into a guest account). The browser session mechanics are similar: the user gets a session cookie after clicking a sharing link and authenticating. The critical difference is that the user's **own browser** now holds the session state, not an anonymous OTP session.

**Implication for the stack:** The tool should guide the user to authenticate in a real browser, then harvest the resulting session cookies for use in API calls. Playwright is the right mechanism for this, and the approach works the same way whether the underlying auth is OTP (while it still exists) or Entra B2B guest.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11+ | Runtime | Stdlib `hashlib` handles SHA-256 natively; 3.11 `tomllib` and improved async performance. 3.12 is also fine. Avoid 3.9 (requests 2.33.0 dropped it). |
| playwright (Python) | 1.58.0 | Browser automation for session harvest | Playwright's `storageState()` serializes cookies + localStorage + IndexedDB into a JSON file in one call. This is the only reliable way to capture the full Microsoft identity session state (which spans cookies, localStorage tokens, and sometimes IndexedDB). Selenium requires manual cookie extraction across each domain. |
| requests | 2.33.0 | HTTP downloads after session harvest | Once cookies are extracted from Playwright, `requests.Session` with those cookies can call the SharePoint REST API (`_api/web/GetFolderByServerRelativeUrl`) and stream file downloads. `stream=True` + `iter_content(chunk_size=8192)` keeps 2GB files off-heap. requests is synchronous, which is correct here — the bottleneck is network I/O to SharePoint, not concurrency. |
| rich | 14.1.0 | Terminal progress display | Multi-file progress bars, per-file transfer speed, ETA. `rich.progress.Progress` supports concurrent task tracking out of the box. Much better UX than tqdm for a tool with multiple simultaneous status lines (auth status, folder scan, per-file download). |
| typer | 0.15.x | CLI interface | Type-hint-driven CLI with zero boilerplate. The tool needs ~5 arguments (URL, dest folder, resume flag). Typer's automatic `--help` and validation is sufficient; no need for Click's lower-level API. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `hashlib` (stdlib) | built-in | SHA-256 file hashing for manifest | Always — no external dependency needed. Read files in 65536-byte chunks to hash 2GB files without loading them into memory. |
| `json` (stdlib) | built-in | Manifest output format | Always — manifest is a JSON file with filename, size_bytes, sha256, download_status per file. |
| `pathlib` (stdlib) | built-in | Cross-platform path handling | Always — use `Path` throughout, never string concatenation for file paths. |
| `tenacity` | 9.x | Retry logic with exponential backoff | For the download loop — any request that fails gets retried 3x with backoff before being recorded as a failure in the manifest. Do not hand-roll retry loops. |
| `python-dotenv` | 1.x | Load a `.env` file for the session state path | Optional, but useful if the user wants to pre-configure the session file location across runs. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uv` | Fast dependency management and virtual env | Preferred over `pip` + `venv` for new projects in 2025. `uv run` executes scripts in the project venv without activating it. |
| `pytest` | Test runner | Unit tests for manifest generation, path normalization, retry logic. Playwright integration tests can run against a local mock server. |
| `pytest-playwright` | Playwright fixtures for pytest | Provides `page` and `browser` fixtures; useful for testing the auth harvest flow in CI (headless). |
| `ruff` | Linter + formatter | Replaces flake8 + black. Fast, single tool, zero config needed. |

---

## Installation

```bash
# Create project with uv
uv init sharepoint_dl
cd sharepoint_dl

# Core runtime dependencies
uv add playwright requests rich typer tenacity

# Install Playwright browsers (Chromium only — smallest footprint)
uv run playwright install chromium

# Dev dependencies
uv add --dev pytest pytest-playwright ruff
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `requests` (sync) | `httpx` (async) | httpx 0.28.1 offers HTTP/2 and async. Use it if you need concurrent downloads of many small files. For this tool — sequential download of large files where the bottleneck is SharePoint rate limits and bandwidth, not Python concurrency — requests is simpler and sufficient. |
| `playwright` session harvest | `selenium` | Selenium requires ChromeDriver version pinning and manual cookie extraction per domain. Playwright's `storageState()` is a single-call solution. Only use Selenium if Playwright is blocked in the target environment. |
| `rich` | `tqdm` | tqdm is lighter and works if you only need a single progress bar. Use rich when you need multiple concurrent progress lines (per-file + overall) and colored status output — which this tool does. |
| `typer` | `click` | Click is fine and more widely used (38.7% of Python CLI projects). Use Click if you have complex subcommand trees or need Click plugins. Typer is preferred for simple tools with few options. |
| `tenacity` | hand-rolled retry loop | Never hand-roll retry logic. tenacity handles backoff, jitter, and exception filtering declaratively. |
| SharePoint REST API (`_api/`) | Microsoft Graph API | Graph API requires an Entra app registration with delegated permissions — not possible with external guest access where you have no admin access to the tenant. The SharePoint REST API (`https://tenant.sharepoint.com/_api/`) accepts session cookies directly and is the only viable path for guest-authenticated access. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Microsoft Graph API for this use case | Requires Azure AD app registration and OAuth token flow. External guests with shared-link access have no way to get a Graph-compatible token without tenant admin involvement. Project explicitly states no admin access available. | SharePoint REST API with session cookies |
| `office365-rest-python-client` | Built for authenticated organizational users and service accounts. GitHub issues confirm `get_file_by_guest_url()` reliably fails with 404 for externally shared files. Designed around OAuth flows, not session-cookie passthrough. | Raw `requests` with harvested cookies |
| `sharepy` | Retrieves FedAuth/rtFa via the legacy SAML/form-digest flow, which is incompatible with Entra B2B guest sessions (the session token is OIDC-based, not SAML). Only works for accounts with username + password against the target tenant. | Playwright `storageState()` + `requests` |
| Sync-only download with no streaming | Loading a 2GB `.E01` file fully into memory before writing will cause `MemoryError` on machines with <4GB RAM. | `requests.get(..., stream=True)` + `iter_content(chunk_size=65536)` |
| `urllib` / `urllib3` directly | Lower-level than requests. No meaningful advantage for this use case; adds boilerplate for cookie jar management. | `requests.Session` |

---

## Stack Patterns by Variant

**If the host tenant has completed the Entra B2B migration (post July 2026):**
- The user authenticates via their own Microsoft account or gets a guest invitation redemption flow in the browser.
- Playwright captures this session exactly the same way as OTP — the cookie names change (SPOIDCRL, ESTSAUTHPERSISTENT) but `storageState()` captures them all.
- No code changes required in the download layer.

**If the tool is used before OTP retirement (current window):**
- Playwright opens the shared link, user enters their email, enters the OTP code in the browser UI, Playwright captures the resulting session.
- Same `storageState()` export, same `requests.Session` cookie injection.

**If files exceed 2GB in the future:**
- SharePoint REST API supports byte-range requests via `Range` header. Implement chunked download with range requests and resume by checking existing partial file size.
- `tenacity` retry decorators remain applicable.

**If cross-platform support is added (Windows/Linux):**
- `pathlib.Path` throughout (already recommended) handles OS path differences.
- Playwright supports Windows/Linux with same API — no changes needed.
- `uv` works on all platforms.

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `playwright==1.58.0` | Python 3.8+ | Chromium 132+ bundled. `storageState()` API stable since 1.20. |
| `requests==2.33.0` | Python 3.10+ | Dropped Python 3.9 support in this release. |
| `rich==14.1.0` | Python 3.8+ | `Progress` multi-task API stable. |
| `typer==0.15.x` | Python 3.7+ | Built on Click 8.x. |
| `tenacity==9.x` | Python 3.8+ | `@retry` decorator API stable. |

---

## Auth Architecture Detail

The two-phase auth model is the critical design decision that makes everything else possible:

**Phase 1 — Session harvest (Playwright):**
1. Open Chromium via `playwright.sync_api` in headed mode (user must see the browser).
2. Navigate to the SharePoint sharing URL.
3. User completes authentication in the browser (email + OTP or Entra B2B — whichever is active).
4. Call `context.storage_state(path=".session/sp_auth.json")` to export all cookies and storage.
5. Close browser.

**Phase 2 — API access (requests):**
1. Load `.session/sp_auth.json`.
2. Create a `requests.Session`, inject all cookies from the state file into it.
3. Call `GET https://tenant.sharepoint.com/_api/web/GetFolderByServerRelativeUrl('/sites/site/Shared Documents/folder')/Files` with `Accept: application/json;odata=verbose`.
4. Paginate results, build file manifest.
5. Download each file with `stream=True`.
6. Hash each file as it streams (do not re-read from disk).

Key insight: hashing during streaming (not post-download) means one I/O pass per file — critical for 2GB files.

---

## Sources

- [SharePoint OTP retirement timeline](https://steve-chen.blog/2025/06/23/sharepoint-online-otp-authentication-gets-out-of-support-on-july-1st-2025/) — MEDIUM confidence (independent blog, corroborated by Microsoft Q&A results)
- [Guest accounts replacing OTP for SPO external access (March 2026)](https://office365itpros.com/2026/03/06/guest-accounts-spo/) — MEDIUM confidence (established Microsoft 365 community author)
- [Playwright Python auth docs](https://playwright.dev/python/docs/auth) — HIGH confidence (official documentation, verified February 2026)
- [playwright PyPI — version 1.58.0](https://pypi.org/project/playwright/) — HIGH confidence (official package registry)
- [requests PyPI — version 2.33.0](https://pypi.org/project/requests/) — HIGH confidence (official package registry)
- [rich PyPI — version 14.1.0](https://pypi.org/project/rich/) — HIGH confidence (official package registry)
- [Office365-REST-Python-Client guest download issue](https://github.com/vgrem/Office365-REST-Python-Client/issues/553) — MEDIUM confidence (GitHub issue confirming 404 behavior for external guest files)
- [SharePoint REST API folder/file operations](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/working-with-folders-and-files-with-rest) — HIGH confidence (official Microsoft docs)
- [httpx vs requests 2025 comparison](https://www.morethanmonkeys.co.uk/article/comparing-requests-and-httpx-in-python-which-http-client-should-you-use-in-2025/) — LOW confidence (third-party blog)

---

*Stack research for: SharePoint bulk downloader (guest auth, forensic manifest)*
*Researched: 2026-03-27*
