# Architecture Research

**Domain:** SharePoint bulk file downloader with browser-session auth
**Researched:** 2026-03-27
**Confidence:** MEDIUM — REST API patterns HIGH, auth layer MEDIUM (OTP retirement changes the landscape)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Layer                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  main.py — entry point, argument parsing, orchestration│  │
│  └─────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│                      Core Services                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Auth Module │  │  Enumerator  │  │  Download Engine │  │
│  │  (session +  │  │  (folder     │  │  (concurrent,    │  │
│  │   cookies)   │  │   traversal) │  │   retry, stream) │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│         └─────────────────┴────────────────────┘           │
│                           │                                 │
│                  ┌─────────┴──────────┐                     │
│                  │  HTTP Client Layer  │                     │
│                  │  (requests/httpx +  │                     │
│                  │   shared session)   │                     │
│                  └────────────────────┘                     │
├─────────────────────────────────────────────────────────────┤
│                       State Layer                            │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Job State    │  │  Manifest    │  │  Progress Store  │  │
│  │  (completed,  │  │  Writer      │  │  (in-memory +    │  │
│  │  failed,      │  │  (filename,  │  │   console output)│  │
│  │  pending)     │  │  size, hash) │  └──────────────────┘  │
│  └───────────────┘  └──────────────┘                        │
├─────────────────────────────────────────────────────────────┤
│                     Storage Layer                            │
│  ┌──────────────────┐  ┌───────────────────────────────┐   │
│  │  Local Filesystem │  │  manifest.json / .csv         │   │
│  │  (mirrored paths) │  │  (written at completion)      │   │
│  └──────────────────┘  └───────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| CLI / Orchestrator | Entry point, flag parsing, wires components together, prints summary | `argparse` or `click`, synchronous bootstrap |
| Auth Module | Prompts for email + OTP (or Entra B2B flow), captures session cookies (FedAuth, rtFa), provides authenticated HTTP session | `requests.Session` or Playwright for browser-backed flows |
| HTTP Client Layer | Shared, authenticated session used by all components; handles cookie injection, retries, timeouts | `requests.Session` with injected cookies + `urllib3` retry adapter |
| File Enumerator | Walks SharePoint folder tree recursively, builds a flat list of (file_url, server_relative_path, size) tuples | SharePoint REST `_api/web/GetFolderByServerRelativeUrl('{path}')/Files` + `/Folders` recursion |
| Download Engine | Consumes the file list; downloads files concurrently with bounded parallelism; writes bytes to local paths; computes hash during streaming | `concurrent.futures.ThreadPoolExecutor` or `asyncio` + `aiohttp`; HTTP Range headers for 2 GB files |
| Job State | Tracks which files are completed, failed, or pending; persists to disk so resumption works without re-downloading | JSON file (`state.json`) written after each completed file |
| Manifest Writer | Appends a row per file (name, remote path, size, SHA-256) after each download; writes final manifest | CSV or JSON; hashed incrementally during download streaming |
| Progress Store | In-process counters surfaced to console; no persistence needed | `tqdm` or plain print; updated by download engine |

## Recommended Project Structure

```
sharepoint_dl/
├── auth/
│   ├── __init__.py
│   ├── session.py          # Build authenticated requests.Session from cookies
│   └── otp_flow.py         # Interactive email + OTP prompt, returns cookies
├── enumerator/
│   ├── __init__.py
│   └── traversal.py        # Recursive folder walk via SharePoint REST API
├── downloader/
│   ├── __init__.py
│   ├── engine.py           # Concurrent download orchestration
│   └── streaming.py        # Chunked streaming + hash computation for large files
├── state/
│   ├── __init__.py
│   └── job.py              # Load/save state.json; completed/failed/pending sets
├── manifest/
│   ├── __init__.py
│   └── writer.py           # Append rows; finalize manifest file
├── cli/
│   ├── __init__.py
│   └── main.py             # argparse entry; wires all modules; prints summary
└── tests/
    ├── test_traversal.py
    ├── test_engine.py
    └── fixtures/           # Mocked API responses
```

### Structure Rationale

- **auth/:** Isolated because the auth mechanism is the highest-uncertainty component (OTP retirement, Entra B2B transition). Keeping it behind a clean interface lets the rest of the tool survive an auth swap without rewriting.
- **enumerator/:** Separate from downloader because enumeration and downloading have different error profiles. Full enumeration before download enables a "files expected" count for completeness reporting.
- **downloader/:** Split into engine (concurrency control, retry) and streaming (byte-level I/O + hashing) because these are independently testable.
- **state/:** Dedicated module so the job file schema is owned in one place. The downloader and CLI both read/write through this module.
- **manifest/:** Separate from state — state is operational (resume), manifest is the forensic deliverable. They must not be conflated.

## Architectural Patterns

### Pattern 1: Enumerate-Then-Download (Two-Phase)

**What:** Complete the full recursive folder walk and build a file list before starting any downloads. The manifest can then report "N files found, M downloaded."
**When to use:** Always for this tool. It is the only way to produce a meaningful completeness report. Interleaving enumeration and download makes it impossible to know how many files remain.
**Trade-offs:** Adds a few seconds of latency before downloads start. Worth it for the completeness guarantee.

**Example:**
```python
# Phase 1: enumerate
file_list = enumerator.walk(root_url, session)  # returns List[FileEntry]
print(f"Found {len(file_list)} files")

# Phase 2: download
results = engine.download_all(file_list, dest_dir, session, state)
manifest.finalize(results, dest_dir)
```

### Pattern 2: Cookie-Injected requests.Session

**What:** After authentication, extract the FedAuth and rtFa cookies from the browser session and inject them into a `requests.Session`. Every subsequent REST call and file download uses this session.
**When to use:** Appropriate for the Entra B2B guest flow where auth happens in a real browser (Playwright) and the resulting cookies are then harvested for the programmatic download phase.
**Trade-offs:** Cookies have a finite lifetime (typically 8–24 hours). For very large downloads that span a session expiry, the tool needs to detect a 401/403 and re-authenticate. For the target workload (one-shot forensic download), session expiry mid-run is a real risk to plan for.

**Example:**
```python
session = requests.Session()
session.cookies.set("FedAuth", fed_auth_value, domain=".sharepoint.com")
session.cookies.set("rtFa", rtfa_value, domain=".sharepoint.com")
# All REST and download calls share this session
resp = session.get(f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{path}')/Files")
```

### Pattern 3: Streaming Download with Incremental Hashing

**What:** Download files in chunks (`iter_content` or `iter_chunks`), write each chunk to disk, and feed it to a running hash object simultaneously. Never load a full 2 GB file into memory.
**When to use:** Required for all files in this tool. Even small files should use the same streaming path to keep the codebase simple and tested.
**Trade-offs:** Slightly more complex than a one-shot download, but eliminates OOM risk and means the hash is computed for free during the download pass.

**Example:**
```python
import hashlib

def download_streaming(url, dest_path, session):
    h = hashlib.sha256()
    with session.get(url, stream=True, timeout=(30, 300)) as resp:
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):  # 8 MB chunks
                f.write(chunk)
                h.update(chunk)
    return h.hexdigest()
```

## Data Flow

### Auth Flow (startup)

```
User launches tool
    ↓
CLI prompts for SharePoint URL
    ↓
auth/otp_flow.py opens Playwright browser (headless: False)
    → user enters email
    → user receives and enters OTP (or Entra B2B MFA flow)
    → browser lands on SharePoint page
    ↓
otp_flow.py extracts FedAuth + rtFa cookies from browser context
    ↓
auth/session.py builds requests.Session with injected cookies
    ↓
Session passed to Enumerator and Download Engine
```

### Enumeration Flow

```
Session + root folder URL
    ↓
enumerator/traversal.py calls:
  GET /_api/web/GetFolderByServerRelativeUrl('{path}')/Files  → file entries
  GET /_api/web/GetFolderByServerRelativeUrl('{path}')/Folders → subfolder entries
    ↓ (recurse for each subfolder)
Flat List[FileEntry(name, server_relative_url, size, remote_path)]
    ↓
Returned to CLI, printed as "Found N files"
```

### Download Flow

```
List[FileEntry] + Session + dest_dir + state.json
    ↓
engine.py filters out already-completed files (resume)
    ↓
ThreadPoolExecutor(max_workers=3) consumes queue
    ↓ (per file)
  streaming.py: GET file/$value with stream=True
    → chunks written to local path
    → SHA-256 computed incrementally
    ↓
  On success:
    state.py marks file completed
    manifest/writer.py appends row (name, path, size, sha256)
  On failure (after N retries):
    state.py marks file failed
    error logged (never silently skipped)
    ↓
Engine completes, returns summary
    ↓
CLI prints: "Downloaded M/N files. X failed."
Manifest finalized to manifest.csv
```

### Key Data Flows

1. **Auth → REST calls:** FedAuth/rtFa cookies flow from the browser session into every HTTP request. This is the single most fragile dependency in the system.
2. **Enumerator → Download Engine:** A flat list of `FileEntry` objects. Decoupled — enumerator does not know about concurrency; downloader does not know about API pagination.
3. **Download Engine → State + Manifest:** Both are written after each successful download. State enables resume; manifest is the forensic deliverable. These writes must be atomic (write to temp file, rename) to avoid corruption on crash.
4. **State → Download Engine (resume):** On startup, completed file paths are loaded from state.json and filtered out of the download queue.

## Scaling Considerations

This is a single-user CLI tool, not a multi-tenant service. The relevant scaling axis is file count and file size, not user count.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| < 500 files, files < 100 MB | Sequential download is acceptable; no concurrency needed |
| 500–5000 files, some files up to 2 GB | ThreadPoolExecutor with 2–4 workers; streaming downloads mandatory; session expiry risk rises |
| > 5000 files in a single folder | SharePoint REST API list view threshold (5000 items) becomes a hard blocker — requires pagination via `$skiptoken` or library-level queries instead of folder-level |

### Scaling Priorities

1. **First bottleneck:** SharePoint REST API rate limiting and session expiry. Implement retry with exponential backoff and detect 401/403 as a signal to re-authenticate.
2. **Second bottleneck:** Local disk write speed for 2 GB files. The 8 MB chunk size handles this well; avoid anything that buffers a full file in memory.

## Anti-Patterns

### Anti-Pattern 1: Interleaved Enumerate + Download

**What people do:** Start downloading files as they are discovered during the folder walk, to save time.
**Why it's wrong:** The tool cannot report "N files expected, M downloaded" if enumeration and download run together. In a forensic context, the inability to state total file count undermines the completeness proof. Also complicates error handling significantly.
**Do this instead:** Full enumeration first, then download. The extra seconds are worth the architectural clarity.

### Anti-Pattern 2: Loading Entire Files into Memory

**What people do:** `content = response.content` — fetches the whole response body into a bytes object.
**Why it's wrong:** A 2 GB file requires 2 GB of RAM. The prior Python script that silently skipped files may have been hitting MemoryError or timeout on large files.
**Do this instead:** Always stream with `stream=True` and iterate `iter_content(chunk_size=8*1024*1024)`.

### Anti-Pattern 3: Ignoring Session Expiry

**What people do:** Authenticate once at startup and assume cookies are valid for the entire run.
**Why it's wrong:** SharePoint FedAuth cookies are session cookies (expire on browser close, or after 8–24 hours). A long download run (100+ large files) can exceed the cookie lifetime, causing silent 403s that look like successful requests unless status codes are checked.
**Do this instead:** Check response status on every request. On 401/403, surface a clear error: "Session expired — please re-authenticate." Structure the auth module so re-authentication can be triggered mid-run without restarting the download.

### Anti-Pattern 4: Using Microsoft Graph API for Guest Access

**What people do:** Attempt to use the Graph API (`/v1.0/sites/{site}/drives/{drive}/items`) because it is well-documented.
**Why it's wrong:** Graph API requires an OAuth2 app registration with delegated or application permissions in the target tenant. Guest access via an external sharing link does not grant this. The prior tool failure may have been an attempt to use Graph without proper permissions.
**Do this instead:** Use the SharePoint REST API (`_api/web/GetFolderByServerRelativeUrl`) with the FedAuth/rtFa cookies from the browser session. This is what the browser itself uses.

### Anti-Pattern 5: Silent File Skip on Error

**What people do:** Wrap individual file downloads in a bare `except: pass` or log-and-continue without recording the failure.
**Why it's wrong:** This is exactly the failure mode of the prior tool. In a forensic context, a silently skipped file is a chain-of-custody failure.
**Do this instead:** Every failure must be recorded in the job state as `failed` with the error message. The final summary must explicitly list every failed file by name. The tool should exit with a non-zero status code if any file failed.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| SharePoint REST API (`_api/`) | HTTP GET with FedAuth/rtFa cookies in Cookie header | Supports JSON responses with `Accept: application/json;odata=verbose`; no OAuth token needed for guest sessions |
| Microsoft Entra B2B auth flow | Playwright browser automation — open URL, await user interaction, extract cookies | NOT programmatic OAuth; user must complete MFA in real browser |
| Local filesystem | Direct file writes via `open(path, 'wb')` | Create parent directories before writing; use temp file + rename for atomicity |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| CLI ↔ Auth Module | Function call; returns `requests.Session` | CLI does not know auth implementation details |
| Auth ↔ HTTP Client | Cookie injection into `requests.Session` | Session is the only thing that crosses this boundary |
| CLI ↔ Enumerator | Function call; returns `List[FileEntry]` | Enumerator is synchronous; pagination is internal |
| CLI ↔ Download Engine | Function call with file list; returns `DownloadResult` summary | Engine manages its own thread pool |
| Download Engine ↔ State | Read on startup; write after each file; both are filesystem operations | Use file locking or sequential writes to avoid corruption |
| Download Engine ↔ Manifest Writer | Write after each successful download | Manifest append must be thread-safe if using concurrent engine |
| Download Engine ↔ Auth Module | Signal only: "session expired, re-auth needed" | Auth module must be callable mid-run |

## Build Order Implications

The dependency graph drives phase order:

1. **Auth module first** — everything else depends on an authenticated session. This is also the highest-risk component (auth flow is uncertain until tested against a real SharePoint external share). Validate it in isolation before building on top of it.
2. **HTTP Client Layer + Enumerator second** — once auth works, prove that the REST API is accessible by listing a folder. This validates the session is accepted by the API.
3. **Download Engine third** — after enumeration is proven, build the download loop with streaming and hashing. Start single-threaded, add concurrency once basic flow works.
4. **State + Resume fourth** — add job state persistence once a single download works end-to-end. This is a reliability layer, not a core capability.
5. **Manifest Writer fifth** — the forensic deliverable. Built last because it depends on a correct, complete download having happened.
6. **CLI / Orchestrator last** — wires all components together. Kept thin intentionally; logic lives in modules, not in main.

## Sources

- SharePoint REST API file/folder operations: https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/working-with-folders-and-files-with-rest
- SharePoint OTP retirement (July 2025 → Entra B2B): https://steve-chen.blog/2025/06/23/sharepoint-online-otp-authentication-gets-out-of-support-on-july-1st-2025/
- OTP retirement timeline and Entra B2B transition detail: https://office365itpros.com/2025/06/10/entra-id-b2b-collaboration-spo/
- Current guest account state (March 2026): https://office365itpros.com/2026/03/06/guest-accounts-spo/
- FedAuth/rtFa cookie mechanics: https://learn.microsoft.com/en-us/sharepoint/authentication
- SharePoint REST API pagination / list view threshold: https://learn.microsoft.com/en-us/answers/questions/2149751/unable-to-retrieve-files-from-sharepoint-library-u
- Playwright session/cookie management: https://playwright.dev/python/docs/auth
- Python concurrent download patterns: https://abhay.fyi/blog/concurrent-downloads-with-python-using-asyncio-or-thread-pools/

---
*Architecture research for: SharePoint bulk file downloader (forensic evidence collection)*
*Researched: 2026-03-27*
