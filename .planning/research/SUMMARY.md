# Project Research Summary

**Project:** sharepoint_dl — SharePoint Bulk File Downloader
**Domain:** Forensic evidence collection via SharePoint external/guest access
**Researched:** 2026-03-27
**Confidence:** MEDIUM — core patterns HIGH confidence; auth layer is actively changing

## Executive Summary

This is a forensic-grade CLI tool for bulk-downloading files from a SharePoint Online site accessible only through a guest/external sharing link — no admin credentials, no Azure app registration, no organizational account on the target tenant. The defining constraint is that the only viable authentication path is harvesting browser session cookies (FedAuth, rtFa) after the user manually completes the external auth flow in a real browser. Playwright is the correct mechanism for this: its `storageState()` API captures the full Microsoft identity session state in one call, regardless of whether the underlying flow is the legacy OTP model or the current Entra B2B guest model. Once cookies are harvested, all folder enumeration and file downloads use the SharePoint REST API (`_api/`) directly via `requests.Session` — the Microsoft Graph API and all third-party SharePoint client libraries are unviable for this scenario.

The recommended stack is Python 3.11+, Playwright 1.58, `requests` 2.33, `rich` for progress display, `typer` for CLI, and `tenacity` for retry logic. The architecture separates concerns into Auth, Enumerator, Download Engine, Job State, and Manifest Writer modules — in that exact build order — because each layer depends on the previous one being proven correct. The two most critical architectural decisions are: enumerate fully before downloading (so a "files expected vs. files downloaded" count is always available), and stream every file download in chunks with incremental SHA-256 hashing (so 2GB evidence files never buffer in memory and hashing requires no second I/O pass).

The primary risks are: (1) the OTP authentication model assumed by the project brief is being retired — all new sharing links now use Entra B2B guest accounts, and OTP links stop working entirely in July 2026; (2) the prior Python script's silent file skips are almost certainly caused by missing API pagination handling (SharePoint truncates folder listings at ~100 items without error) combined with bare `except: continue` in the download loop. Both failures must be treated as unacceptable — they are chain-of-custody failures in a forensic context. The auth layer should be built as a swappable module from day one to survive the OTP retirement without a rewrite.

## Key Findings

### Recommended Stack

The auth-then-download pattern drives the entire stack choice. Playwright provides the only reliable session capture mechanism for external Microsoft identity flows; raw `requests` is the correct HTTP client once cookies are in hand (synchronous, stream-capable, no OAuth overhead). `rich` is strongly preferred over `tqdm` because this tool needs multiple concurrent progress lines: auth status, folder scan, per-file download, and overall progress. `tenacity` is required — hand-rolled retry loops are a pitfall source, and SharePoint throttles aggressively enough that unhandled 429s will cause silent failures.

**Core technologies:**
- **Python 3.11+**: stdlib `hashlib` for SHA-256, `tomllib`, improved async — avoid 3.9 (requests 2.33 dropped it)
- **Playwright 1.58**: `storageState()` captures full Microsoft identity session in one call — the only reliable approach for Entra B2B/OTP sessions; Selenium is inadequate
- **requests 2.33**: `stream=True` + `iter_content()` for 2GB file downloads; shares cookies from Playwright state; synchronous is correct here
- **rich 14.1**: multi-task progress bars, per-file transfer speed, ETA — required for multiple concurrent status lines
- **typer 0.15**: type-hint-driven CLI, sufficient for ~5 arguments; no need for Click's lower-level API
- **tenacity 9.x**: declarative retry with backoff and jitter — mandatory for SharePoint throttling; never hand-roll
- **uv**: fast dependency management; `uv run` avoids manual venv activation

**Explicit exclusions:** Microsoft Graph API (requires app registration, incompatible with guest access), `office365-rest-python-client` (404s on external files, OAuth-only), `sharepy` (SAML/form-digest flow incompatible with Entra B2B sessions).

### Expected Features

The MVP for forensic collection is non-negotiable on 10 features. The items deferred to v1.x and v2+ are well-defined and should not creep into the initial build.

**Must have (v1 — table stakes and forensic requirements):**
- Session authentication via browser cookie harvest — prerequisite for everything
- Recursive folder traversal with `$skiptoken` pagination — must handle >5,000 items; missing pagination is the prior script's failure
- Streaming download of 2GB+ files — `.E01`/`.L01` forensic evidence files are routinely 1-2GB
- Resume/skip completed files — multi-hour downloads require interruption tolerance
- Verification manifest (filename, remote path, size, SHA-256) — non-negotiable forensic deliverable
- Per-file error reporting with no silent skips — fixes prior script's known failure mode
- Expected vs. actual file count report — completeness proof
- Preserve folder structure locally
- User-specified download destination
- Progress indication (per-file and overall)

**Should have (v1.x — after validation):**
- Audit trail / download log (chain-of-custody, append-only)
- Post-download integrity re-verification (`verify` subcommand)
- Configurable concurrency with backoff
- Dry-run / list-only mode

**Defer (v2+):**
- Entra B2B auth migration support (OTP retirement completes July 2026; design auth as swappable module now)
- Cross-platform support (Windows/Linux) — Mac-only meets current deadline

**Anti-features to reject explicitly:** incremental sync, GUI, upload capability, parallel chunked download, automatic re-auth loops, file filtering, cloud-to-cloud transfer.

### Architecture Approach

The architecture is a six-layer pipeline with strict separation between the forensic deliverable (manifest) and the operational state (resume tracking). The two-phase Enumerate-Then-Download pattern is mandatory — interleaving enumeration and download makes it impossible to report a meaningful completeness count, which is a forensic requirement. The auth module is deliberately isolated because it is the highest-uncertainty component in the system and must be swappable without touching download logic.

**Major components:**
1. **Auth Module** (`auth/`) — Playwright session harvest; returns `requests.Session` with injected cookies; isolated behind clean interface for OTP→Entra B2B swap
2. **File Enumerator** (`enumerator/`) — recursive `GetFolderByServerRelativeUrl` calls with `$skiptoken` pagination; returns flat `List[FileEntry]` before any downloads start
3. **Download Engine** (`downloader/`) — bounded `ThreadPoolExecutor` (3-4 workers); streaming chunks + incremental SHA-256; explicit `failed` list; `tenacity` retry on 429/5xx; halt on 401/403
4. **Job State** (`state/`) — `state.json` written atomically after each file; enables resume; separate from manifest
5. **Manifest Writer** (`manifest/`) — append-only forensic deliverable; SHA-256 per file computed during streaming; finalized at run completion
6. **CLI Orchestrator** (`cli/main.py`) — thin wiring layer; collects all inputs before auth; prints summary with non-zero exit if any failures

### Critical Pitfalls

1. **Pagination truncation causes silent missing files** — `GetFolderByServerRelativeUrl/Files` returns ~100 items by default with no error; must follow `@odata.nextLink` in a loop. This is almost certainly the direct cause of the prior script's silent omissions. Verify enumerated count against SharePoint UI before trusting the file list.

2. **Silent skip via bare `except: continue`** — the other likely cause of prior script failures. Every exception must be caught, logged, and appended to an explicit `failed` list. Tool must exit non-zero if any file failed. Never acceptable in a forensic context.

3. **Large file truncation without streaming** — `response.content` on a 2GB file causes OOM or socket timeout, producing a truncated local file with no error. Use `stream=True` + `iter_content(chunk_size=8MB)` for every download. Use `download.aspx` URL (not `/$value`) for large files — the `/$value` endpoint has a confirmed bug for large files (sp-dev-docs#5247).

4. **Auth expiry mid-run causing silent 401/403** — FedAuth/rtFa cookies expire in 1-8 hours. Treat 401/403 as hard halt requiring re-auth, not as retriable errors. Validate session with a probe request before starting a large batch.

5. **OTP auth model mismatch** — the project brief assumes email+OTP; that model is retired as of July 2025 for new links. Manually probe the specific sharing link to determine whether it triggers OTP or Entra B2B before building any auth logic. Design the auth layer as swappable regardless.

## Implications for Roadmap

Based on the dependency graph from ARCHITECTURE.md and the pitfall-to-phase mapping from PITFALLS.md, a 3-phase structure is recommended. The build order is dictated by hard dependencies: auth must be proven before enumeration, enumeration before download, download before manifest. Each phase has a clearly testable deliverable.

### Phase 1: Foundation — Auth and Folder Enumeration

**Rationale:** Everything else depends on a working authenticated session and a correct, complete file listing. Auth is the highest-risk component (auth flow is uncertain until tested against the actual sharing link). Enumeration must be proven complete — with pagination verified against SharePoint UI count — before building any download logic on top of it. Discovering auth or pagination issues late is expensive. Address pitfalls 1 and 4-5 here.

**Delivers:** A working `requests.Session` from Playwright cookie harvest; a verified flat file list from recursive folder traversal with full pagination; project scaffold with `uv`, module structure, and `ruff`/`pytest` configured.

**Addresses features:** Session authentication, recursive folder traversal with pagination, dry-run/list-only mode (enumerate only, print count and exit).

**Avoids:** OTP vs Entra B2B mismatch (probe the actual link first), pagination truncation (verify count against UI), Graph API temptation.

**Must validate:** Enumerated file count matches SharePoint browser UI count for the target folder before proceeding.

### Phase 2: Download Engine — Streaming, Retry, Resume, and Error Handling

**Rationale:** Once enumeration is proven, build the download loop with all reliability mechanisms from the start — not as afterthoughts. The error-tracking scaffolding (`failed` list, non-zero exit) must be built first, before any download logic, to ensure silent skips are structurally impossible. Streaming and retry are not optional improvements — they are prerequisites for correctness on 2GB files and SharePoint throttling. Address pitfalls 2, 3, and partial 4.

**Delivers:** Complete download loop with `ThreadPoolExecutor`, `tenacity` retry on 429/5xx, hard halt on 401/403, streaming + incremental SHA-256, resume via `state.json`, per-file error reporting, and progress output via `rich`.

**Addresses features:** Streaming large-file download, resume/skip completed files, per-file error reporting, progress indication, configurable concurrency with backoff.

**Avoids:** Exception swallowing, non-streamed downloads, ignoring `Retry-After` headers, treating auth expiry as a retriable error.

**Must validate:** Intentionally inject a 403 mid-run and confirm it halts with a clear message; test with a file >1GB and verify hash; kill mid-run and verify resume works.

### Phase 3: Forensic Deliverables — Manifest, Verification, and CLI Polish

**Rationale:** With a correct, complete, reliable download proven in Phase 2, build the forensic output layer. Manifest generation must be last because it depends on a correct download having occurred — but its schema and append behavior should be designed not to conflict with the `state.json` operational state. Address pitfall 6 (integrity model) and finalize CLI UX.

**Delivers:** Final `manifest.json` with filename, remote path, size, SHA-256, and per-file download status; expected vs. actual count report; non-zero exit code on any failures; clean end-of-run summary; all CLI inputs collected before auth starts.

**Addresses features:** Verification manifest (SHA-256), expected vs. actual count report, CLI polish, audit trail / download log (append-only, v1.x), post-download re-verification subcommand (v1.x).

**Avoids:** Server-side hash reliance (compute SHA-256 from local bytes only), MD5 in manifest (use SHA-256 minimum), conflating operational state with forensic manifest.

**Must validate:** Manifest file count matches SharePoint UI count; re-run `verify` subcommand against completed download; confirm non-zero exit when any file fails.

### Phase Ordering Rationale

- **Auth before everything** because without a working authenticated session, no other component can be tested against real SharePoint data. Auth is also the highest-uncertainty component — manual probing of the actual link before writing any auth code is required.
- **Enumerate before download** because the completeness proof (files expected = files downloaded) is only possible if the full file list is built before any downloads start. This is not a performance optimization; it is a forensic requirement.
- **Download reliability before manifest** because a manifest built on top of an unreliable download loop is worthless. The download engine must be proven correct — including edge cases (large files, throttling, auth expiry, resume) — before the forensic deliverable is generated from its output.
- **OTP vs Entra B2B is a Phase 1 discovery task,** not a design decision to make in advance. The auth module interface is fixed; the implementation is determined by what the actual sharing link triggers.

### Research Flags

Phases likely needing additional research during planning:
- **Phase 1 (Auth):** The specific auth flow triggered by the target sharing link is unknown until manually probed. The Playwright session capture approach is well-understood, but the downstream flow (OTP code entry vs. Entra B2B MFA) determines the user interaction model. Test before designing.
- **Phase 2 (Download endpoint):** The `/$value` endpoint has a confirmed large-file bug (sp-dev-docs#5247). The `download.aspx` URL is the recommended alternative but its behavior for guest sessions specifically should be validated against the actual target site before relying on it.

Phases with standard patterns (skip research-phase):
- **Phase 3 (Manifest/CLI):** SHA-256 hashing, JSON manifest structure, CLI argument handling with typer — all well-documented patterns with no SharePoint-specific surprises.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core libraries verified via official PyPI/docs. Auth tool selection (Playwright) is well-justified by `storageState()` API and the Entra B2B session model. The only uncertainty is auth flow specifics, which don't affect stack choice. |
| Features | HIGH | Table stakes are clear and well-supported. Forensic requirements (manifest, chain of custody, no silent skips) are unambiguous. Anti-features are well-reasoned. |
| Architecture | HIGH | REST API patterns verified against official Microsoft docs. Two-phase enumerate-then-download is standard for bulk download tools with completeness requirements. Module boundaries are clean and independently testable. |
| Pitfalls | HIGH | Most pitfalls verified against official GitHub issues and Microsoft docs with confirmed reproduction. Pagination truncation and exception swallowing are direct diagnoses of the prior script's failure mode. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Actual auth flow on target link:** Must probe the specific SharePoint sharing URL manually before Phase 1 implementation begins. Both OTP (legacy, pre-July 2026 links) and Entra B2B (new links) are live in the wild as of March 2026. This is not resolvable from research alone.
- **`download.aspx` vs `/$value` for guest sessions:** The `/$value` large-file bug is confirmed, but the `download.aspx` URL's behavior for externally-shared guest links specifically needs hands-on validation in Phase 2. It may require a different cookie set or URL construction.
- **Session cookie lifetime on the target tenant:** The 1-8 hour range is the documented default, but conditional access policies on the host tenant can shorten it significantly. Validate before estimating how long the download window is for a single authenticated session.

## Sources

### Primary (HIGH confidence)
- [Playwright Python auth docs](https://playwright.dev/python/docs/auth) — `storageState()` API, session capture
- [SharePoint REST API file/folder operations](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/working-with-folders-and-files-with-rest) — `GetFolderByServerRelativeUrl`, file download
- [SharePoint sp-dev-docs Issue #5247](https://github.com/SharePoint/sp-dev-docs/issues/5247) — large file `/$value` endpoint bug
- [PnPCore Issue #228](https://github.com/pnp/pnpcore/issues/228) — TaskCanceled on 2GB+ file downloads
- [Microsoft MC1243549](https://mc.merill.net/message/MC1243549) — official OTP retirement announcement
- [Microsoft Learn — SharePoint throttling](https://learn.microsoft.com/en-us/sharepoint/dev/general-development/how-to-avoid-getting-throttled-or-blocked-in-sharepoint-online)
- [Microsoft Learn — Configurable token lifetimes](https://learn.microsoft.com/en-us/entra/identity-platform/configurable-token-lifetimes)
- [playwright PyPI 1.58.0](https://pypi.org/project/playwright/), [requests PyPI 2.33.0](https://pypi.org/project/requests/), [rich PyPI 14.1.0](https://pypi.org/project/rich/)

### Secondary (MEDIUM confidence)
- [SharePoint OTP retirement timeline blog](https://steve-chen.blog/2025/06/23/sharepoint-online-otp-authentication-gets-out-of-support-on-july-1st-2025/) — retirement dates, corroborated by Microsoft notices
- [Guest accounts replacing OTP (March 2026)](https://office365itpros.com/2026/03/06/guest-accounts-spo/) — current state of B2B migration
- [SharePoint REST API pagination community blog](https://www.robinsandra.com/the-infamous-5000-item-limit-paging-with-the-sharepoint-rest-api/) — `$skiptoken` behavior, consistent with Microsoft Q&A
- [Office365-REST-Python-Client Issue #553](https://github.com/vgrem/Office365-REST-Python-Client/issues/553) — confirms 404 behavior for external guest files
- [rclone SharePoint throttling forum](https://forum.rclone.org/t/throttling-of-rclone-with-sharepoint-saga-continues/29874) — throttling behavior in practice

### Tertiary (LOW confidence)
- [httpx vs requests 2025 comparison](https://www.morethanmonkeys.co.uk/article/comparing-requests-and-httpx-in-python-which-http-client-should-you-use-in-2025/) — used only to confirm requests is sufficient for sequential large-file downloads; not a deciding factor

---
*Research completed: 2026-03-27*
*Ready for roadmap: yes*
