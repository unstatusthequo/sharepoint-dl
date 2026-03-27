# Phase 1: Foundation - Research

**Researched:** 2026-03-27
**Domain:** Playwright session harvest, SharePoint REST API enumeration, Python CLI scaffolding
**Confidence:** HIGH — all core patterns verified against official sources

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Auth Flow UX**
- Tool auto-opens the default browser to the SharePoint URL via Playwright
- User completes login manually (OTP code or Entra B2B — whatever the link triggers)
- Tool detects successful auth by watching for the authenticated page state (presence of FedAuth/rtFa cookies)
- Once authenticated, tool extracts cookies and closes the browser automatically
- If auth fails or times out (2 minutes), tool exits with a clear error message

**Session Persistence**
- Save session cookies to a local file (`~/.sharepoint-dl/session.json`) after successful auth
- On subsequent runs, attempt to reuse saved session — validate with a lightweight API call before proceeding
- If saved session is expired/invalid, auto-launch browser for fresh login (no manual flag needed)
- Session file stores the SharePoint host it was created for — don't reuse across different tenants

**CLI Invocation**
- Single command with subcommands: `sharepoint-dl auth <url>`, `sharepoint-dl list <url>`, `sharepoint-dl download <url> <dest>`
- `auth` — authenticate and save session only (useful for testing)
- `list` — enumerate files and show count/tree (no download)
- `download` — full pipeline: auth (if needed) → enumerate → download
- Common flags: `--url` (SharePoint folder URL), `--dest` (download destination, required for download)
- Built with typer for auto-generated help and shell completion

**Enumeration Output**
- During enumeration: spinner with "Scanning folders..." and running file count
- After enumeration: summary table showing folder path, file count, and total size per folder
- Final line: "Found N files (X.X GB total) across M folders"
- `list` subcommand shows this without proceeding to download
- Enumeration must complete fully before any download begins (forensic requirement)

**Error Handling**
- Auth failure: clear message about what went wrong, suggest re-running `auth` subcommand
- API errors during enumeration: retry 3 times with backoff, then fail with the specific folder that failed
- Session expiry during enumeration: halt, prompt re-auth, resume enumeration from where it left off
- Never silently skip a folder during enumeration — if a folder can't be listed, that's a fatal error

### Claude's Discretion
- Exact Playwright browser launch configuration (headless vs headed)
- Cookie extraction implementation details
- REST API pagination implementation approach
- Project scaffolding choices (uv, ruff config, module layout)
- Test strategy for auth module (mock vs integration)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTH-01 | User can authenticate via Playwright browser session capture (login once, cookies reused) | Playwright `storageState()` API + `requests.Session` cookie injection; session persisted to `~/.sharepoint-dl/session.json` |
| AUTH-02 | Tool validates session is active before starting any downloads | Lightweight probe GET to `_api/web/title` before enumeration; 401/403 = stale session |
| AUTH-03 | Tool detects expired session mid-run and prompts user to re-authenticate | Treat 401/403 during enumeration as hard halt, not retriable error; re-launch Playwright auth flow |
| ENUM-01 | Tool recursively traverses all folders/subfolders via SharePoint REST API | `GetFolderByServerRelativeUrl('{path}')/Folders` recursion; DFS or BFS with an explicit stack |
| ENUM-02 | Tool paginates folder listings with `$skiptoken` to capture all files (no silent truncation) | Follow `@odata.nextLink` in a loop until absent; `$skip` does NOT work on Files endpoints |
| ENUM-03 | Tool displays total file count found before downloading begins | Accumulate `List[FileEntry]` during traversal; print summary after full traversal completes |
| CLI-01 | User can specify download destination folder at launch | typer subcommand with `dest: Path` argument; collect all inputs before auth starts |
</phase_requirements>

---

## Summary

Phase 1 establishes the three pillars everything else depends on: a working authenticated session, a verified complete file enumeration, and the CLI scaffold that wires them together. Because this is a greenfield project with no existing code, the phase also includes project creation (uv, pyproject.toml, ruff, pytest). The most uncertain element is not the code — it is the auth flow of the specific target SharePoint link. Whether it triggers the legacy OTP email code or the current Entra B2B guest flow cannot be known until manually probed. Playwright handles both correctly because `storageState()` captures the entire browser session regardless of the underlying identity provider. The implementation pattern is the same either way: open browser, user authenticates, capture `storageState()`, close browser, inject cookies into `requests.Session`.

SharePoint folder enumeration has one critical pitfall that the prior Python script almost certainly hit: `GetFolderByServerRelativeUrl/Files` returns at most 100 items by default with no error and no warning. Pagination is via `@odata.nextLink` in the response body. The prior script almost certainly iterated what the first response returned and stopped there. This phase must verify the enumerated count against the SharePoint browser UI count before it can be called complete — that single verification step closes the most dangerous gap.

The CLI is a typer app with three subcommands (`auth`, `list`, `download`). Phase 1 implements `auth` and `list` fully; `download` is a stub that raises NotImplementedError. The project module layout is fixed here and extended in Phase 2: `auth/`, `enumerator/`, `cli/`, with `downloader/`, `state/`, and `manifest/` added in later phases.

**Primary recommendation:** Build in wave order — project scaffold first, then auth in isolation (prove it works against the real link), then enumeration with verified pagination, then CLI wiring. Do not build enumeration before auth is proven against the actual target URL.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11+ | Runtime | stdlib `hashlib`, `tomllib`, `pathlib`; requests 2.33 dropped 3.9 |
| playwright | 1.58.0 | Browser session harvest | `storageState()` captures full Microsoft identity session (cookies + localStorage + IndexedDB) in one call; only reliable mechanism for Entra B2B/OTP guest flows |
| requests | 2.33.0 | HTTP client for REST API + file downloads | `stream=True` + `iter_content()` for large files; synchronous is correct (bottleneck is SharePoint, not Python); `requests.Session` accepts injected cookies directly |
| rich | 14.1.0 | Terminal output | Multi-task progress, spinner, summary tables; required because Phase 1 has concurrent status lines (auth status + folder scan spinner + running count) |
| typer | 0.15.x | CLI | Type-hint-driven subcommands; auto-generated `--help`; `no_args_is_help=True` shows help on bare invocation |
| tenacity | 9.x | Retry with backoff | Mandatory for SharePoint 429/5xx; never hand-roll retry logic |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pathlib` (stdlib) | built-in | Path handling | Always — never string concatenation for file paths |
| `json` (stdlib) | built-in | Session state + future manifest | Always — `json.dumps` / `json.loads` for `session.json` |
| `hashlib` (stdlib) | built-in | SHA-256 (Phase 3, but module layout set in Phase 1) | Included in module scaffold now; used in Phase 2+ |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Dependency management and venv | `uv init`, `uv add`, `uv run` — never manual pip |
| pytest | Test runner | `uv add --dev pytest` — configured in `pyproject.toml` |
| pytest-playwright | Playwright fixtures for pytest | `page` and `browser` fixtures; useful for future auth integration tests |
| ruff | Linter + formatter | Replaces flake8 + black; zero extra config needed |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `playwright` | `selenium` | Selenium requires per-domain cookie extraction and ChromeDriver version pinning; Playwright's `storageState()` is a single call that captures everything |
| `requests` | `httpx` | httpx is async-first; no benefit here since downloads are sequential and bottleneck is network/SharePoint; adds complexity |
| `typer` | `click` | Click is more widely used for complex subcommand trees; typer is sufficient for 3 subcommands with ~4 args each |
| `tenacity` | hand-rolled retry loop | Never acceptable; tenacity handles backoff, jitter, exception filtering declaratively |

**Installation:**
```bash
uv init sharepoint-dl
cd sharepoint-dl
uv add playwright requests rich typer tenacity
uv run playwright install chromium
uv add --dev pytest pytest-playwright ruff
```

---

## Architecture Patterns

### Recommended Project Structure

```
sharepoint_dl/
├── auth/
│   ├── __init__.py
│   ├── browser.py          # Playwright session harvest; returns path to session.json
│   └── session.py          # Load session.json, build requests.Session, validate session
├── enumerator/
│   ├── __init__.py
│   └── traversal.py        # Recursive folder walk via SharePoint REST; returns List[FileEntry]
├── cli/
│   ├── __init__.py
│   └── main.py             # typer app with auth/list/download subcommands
├── downloader/             # Stub in Phase 1 — populated in Phase 2
│   └── __init__.py
├── state/                  # Stub in Phase 1 — populated in Phase 2
│   └── __init__.py
├── manifest/               # Stub in Phase 1 — populated in Phase 3
│   └── __init__.py
└── tests/
    ├── conftest.py
    ├── test_auth.py
    └── test_traversal.py
```

### Pattern 1: Playwright Session Harvest

**What:** Open Chromium in headed mode, navigate to the SharePoint URL, wait for the user to complete authentication, detect session by polling for FedAuth/rtFa cookies, export `storageState()`, close browser.

**When to use:** Every auth flow — OTP and Entra B2B are both handled identically by this pattern.

**Key decision — headed vs headless:** Must be headed (non-headless). The user must see and interact with the browser to complete MFA or enter OTP codes. The `headless=False` flag is mandatory.

**Cookie detection approach:** After navigating to the SharePoint URL, poll `context.cookies()` in a loop (every 2 seconds, up to 2 minutes) checking for the presence of a cookie named `FedAuth` or `rtFa` with a non-empty value on the target domain. When found, the session is active.

**Example:**
```python
# Source: https://playwright.dev/python/docs/auth
from playwright.sync_api import sync_playwright
import json, time
from pathlib import Path

SESSION_PATH = Path.home() / ".sharepoint-dl" / "session.json"

def harvest_session(sharepoint_url: str, timeout_seconds: int = 120) -> Path:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(sharepoint_url)

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            cookies = {c["name"]: c for c in context.cookies()}
            if "FedAuth" in cookies or "rtFa" in cookies:
                context.storage_state(path=str(SESSION_PATH))
                browser.close()
                return SESSION_PATH
            time.sleep(2)

        browser.close()
        raise TimeoutError(f"Authentication not detected within {timeout_seconds}s")
```

### Pattern 2: Cookie Injection into requests.Session

**What:** Load `storageState()` JSON, extract cookies for the target domain, inject into a `requests.Session`.

**When to use:** Every REST API call and file download after auth.

**Key detail:** `storageState()` JSON has a `"cookies"` array where each element has `name`, `value`, `domain`, `path`, etc. Filter by domain matching the SharePoint host. The critical cookies are `FedAuth` and `rtFa`, but inject all matching cookies to avoid missing any that Microsoft adds.

**Example:**
```python
import json, requests
from pathlib import Path

def build_session(session_path: Path, sharepoint_host: str) -> requests.Session:
    state = json.loads(session_path.read_text())
    session = requests.Session()
    for cookie in state["cookies"]:
        if sharepoint_host in cookie["domain"]:
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie["domain"],
                path=cookie.get("path", "/"),
            )
    return session

def validate_session(session: requests.Session, site_url: str) -> bool:
    """Probe with a lightweight call. Returns True if session is active."""
    try:
        resp = session.get(
            f"{site_url}/_api/web/title",
            headers={"Accept": "application/json;odata=verbose"},
            timeout=(10, 30),
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False
```

### Pattern 3: SharePoint REST Enumeration with Pagination

**What:** Call `GetFolderByServerRelativeUrl/Files` and `GetFolderByServerRelativeUrl/Folders` for a given path. Follow `@odata.nextLink` until absent. Recurse into each subfolder.

**When to use:** Enumeration phase only. Complete this fully before any download logic runs.

**Critical detail:** `$skip` does NOT work correctly on Files endpoints — it restarts from beginning. Only `$skiptoken` (via `@odata.nextLink`) works. Never compute a file count from a non-paginated response.

**The `@odata.nextLink` key:** In the response JSON, pagination continuation is in `d["__next"]` (verbose OData) or `"@odata.nextLink"` (minimal metadata). Always check both. The continuation URL is opaque — use it directly, do not reconstruct it.

**Example:**
```python
from dataclasses import dataclass
from typing import Iterator
import requests

@dataclass
class FileEntry:
    name: str
    server_relative_url: str
    size_bytes: int
    folder_path: str

def _fetch_files_page(session: requests.Session, url: str) -> tuple[list[dict], str | None]:
    resp = session.get(url, headers={"Accept": "application/json;odata=verbose"}, timeout=(10, 60))
    resp.raise_for_status()
    data = resp.json()["d"]
    results = data.get("results", [])
    next_url = data.get("__next")  # verbose OData pagination key
    return results, next_url

def enumerate_files(
    session: requests.Session,
    site_url: str,
    server_relative_path: str,
) -> list[FileEntry]:
    """Recursively enumerate all files under server_relative_path."""
    files: list[FileEntry] = []
    stack = [server_relative_path]

    while stack:
        folder_path = stack.pop()
        encoded = requests.utils.quote(folder_path, safe="")

        # Enumerate files in this folder (paginated)
        files_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{encoded}')/Files?$select=Name,ServerRelativeUrl,Length"
        while files_url:
            results, files_url = _fetch_files_page(session, files_url)
            for f in results:
                files.append(FileEntry(
                    name=f["Name"],
                    server_relative_url=f["ServerRelativeUrl"],
                    size_bytes=int(f.get("Length", 0)),
                    folder_path=folder_path,
                ))

        # Enumerate subfolders (paginated)
        folders_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{encoded}')/Folders?$select=ServerRelativeUrl"
        while folders_url:
            results, folders_url = _fetch_files_page(session, folders_url)
            for sub in results:
                stack.append(sub["ServerRelativeUrl"])

    return files
```

### Pattern 4: typer Subcommand App

**What:** A `typer.Typer()` app with multiple `@app.command()` decorated functions, one per subcommand. `no_args_is_help=True` shows help when invoked bare.

**When to use:** The CLI entry point in `cli/main.py`. All three subcommands declared here; `download` raises `NotImplementedError` in Phase 1.

**Example:**
```python
# Source: https://typer.tiangolo.com/tutorial/commands/
import typer
from pathlib import Path

app = typer.Typer(no_args_is_help=True)

@app.command()
def auth(url: str = typer.Argument(..., help="SharePoint folder URL")):
    """Authenticate and save session. Run this first."""
    ...

@app.command()
def list(url: str = typer.Argument(..., help="SharePoint folder URL")):
    """Enumerate files and show count. Requires prior auth."""
    ...

@app.command()
def download(
    url: str = typer.Argument(..., help="SharePoint folder URL"),
    dest: Path = typer.Argument(..., help="Local destination folder"),
):
    """Download all files. Requires prior auth. (Phase 2)"""
    raise NotImplementedError("Download not yet implemented (Phase 2)")

if __name__ == "__main__":
    app()
```

**pyproject.toml entry point:**
```toml
[project.scripts]
sharepoint-dl = "sharepoint_dl.cli.main:app"
```

### Pattern 5: Session File Host Binding

**What:** Store the SharePoint hostname alongside the session cookies. On load, verify the stored host matches the current URL's host before using the session.

**When to use:** Every session load.

**Why:** Prevents accidentally reusing a session from tenant A when connecting to tenant B (different tenants = different FedAuth cookies; reuse will silently fail with 401).

```python
# In session.json alongside storageState data, store:
# { "host": "contoso.sharepoint.com", "cookies": [...], ... }
# On load, assert state["host"] == urlparse(sharepoint_url).netloc
```

### Anti-Patterns to Avoid

- **Headless Playwright for auth:** User must complete MFA/OTP manually in a visible browser. `headless=True` prevents this. Always `headless=False`.
- **Treating 401 as retriable:** 401/403 during enumeration means the session expired. Retry logic should only apply to 429 and 5xx. A retried 401 will produce the same 401 — it is not transient.
- **`$skip` for pagination:** Does not work on SharePoint Files endpoints (restarts from beginning). Use `@odata.nextLink` / `d.__next` only.
- **Single-call file count:** Never report file count from a single unverified API response. Only report after full paginated traversal completes.
- **Mixing session state with host binding:** `storageState()` does not record which SharePoint host it was for. This metadata must be added manually on save.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry with backoff | Custom retry loop with `time.sleep` | `tenacity` `@retry(wait=wait_exponential(...), stop=stop_after_attempt(3))` | tenacity handles jitter, exception filtering, retry on specific status codes declaratively; hand-rolled loops accumulate subtle bugs |
| Terminal spinners + progress | Custom print-with-carriage-return | `rich.console.Console` + `rich.progress.Progress` | rich handles concurrent status lines, resize events, and Windows terminal compatibility; custom implementations break on wide file names |
| Browser-level auth scraping | Custom cookie extraction from browser profiles | `playwright storageState()` | `storageState()` captures all identity-relevant browser storage (cookies, localStorage, IndexedDB) in one call; manual extraction misses ESTSAUTHPERSISTENT and other Entra tokens |
| URL encoding for SharePoint paths | `str.replace(" ", "%20")` | `requests.utils.quote(path, safe="")` | SharePoint paths contain `/`, `(`, `)` which must NOT be encoded; `safe=""` handles this correctly |

**Key insight:** The SharePoint REST API returns opaque `@odata.nextLink` continuation tokens. Never try to construct pagination URLs manually from offset values — use the continuation URL verbatim.

---

## Common Pitfalls

### Pitfall 1: Pagination Truncation — The Core Risk

**What goes wrong:** `GetFolderByServerRelativeUrl/Files` returns first ~100 items. No error. Code iterates the partial list, reports a file count, and considers enumeration complete. Remaining files simply never appear.

**Why it happens:** The prior script did this. The response looks complete because it is valid JSON with no error flag. The `@odata.nextLink` / `d.__next` field in the response body is the only signal that more pages exist.

**How to avoid:** After every Files or Folders API response, inspect `resp.json()["d"].get("__next")`. If present, fetch it. Loop until absent.

**Warning signs:** Enumerated count is suspiciously round (100, 200). Files from early alphabet downloaded, later ones missing. Enumerated count is less than SharePoint UI count.

**Verification step (mandatory before Phase 1 can be called complete):** Compare the tool's enumerated count against the file count shown in the SharePoint browser UI for the same folder. They must match.

### Pitfall 2: Auth Flow Is Unknown Until Probed

**What goes wrong:** Code is written assuming OTP email+code flow. The actual link triggers Entra B2B guest account redemption. User gets "organization has updated its guest access settings" error.

**Why it happens:** Both flows are live in the wild as of March 2026. Links created before OTP retirement may still use OTP; newer links use Entra B2B.

**How to avoid:** Manually open the specific SharePoint sharing URL in a browser before writing any auth automation. Document which flow it triggers. Both flows are handled by the Playwright "user authenticates in headed browser" pattern — but the user interaction model differs (OTP: enter 6-digit code; Entra B2B: sign in with Microsoft account or follow guest redemption flow). The detection logic (watch for FedAuth/rtFa cookies) works for both.

**Warning signs:** Browser shows a Microsoft "check your email" OTP page OR an Entra ID "sign in" page — these are different and the user must know which to expect.

### Pitfall 3: 401 Treated as Retriable Error

**What goes wrong:** During enumeration, a 401 is caught by a broad exception handler and retried. The retry also gets 401. After 3 retries, the folder is silently skipped or the error is swallowed.

**Why it happens:** Retry logic configured for transient errors (429/5xx) is applied to auth errors (401/403) by mistake.

**How to avoid:** Classify HTTP errors before retry:
- 401/403 → halt, print "Session expired — run `sharepoint-dl auth <url>` to re-authenticate", exit non-zero
- 429 → honor `Retry-After` header, then retry
- 5xx → retry with exponential backoff (max 3 attempts)
- 404 → fatal error for that folder, log and surface (never silently skip)

### Pitfall 4: Session File Has Overly Broad Permissions

**What goes wrong:** `~/.sharepoint-dl/session.json` contains live session cookies. If the file has default `644` permissions, any process running as the user can read it. In a shared machine environment, this is a session hijack vector.

**How to avoid:** After writing the session file, `chmod 600 ~/.sharepoint-dl/session.json`. In Python: `session_path.chmod(0o600)`.

### Pitfall 5: Server-Relative URL Encoding

**What goes wrong:** Paths with spaces or special characters passed directly to the API produce 400 errors. Example: `/sites/shared/Images/Custodian A/subfolder` — the space breaks the URL.

**How to avoid:** Use `requests.utils.quote(server_relative_url, safe="")` before embedding in the API URL. Then wrap in single quotes in the OData syntax: `GetFolderByServerRelativeUrl('encoded_path')`. Test with a folder name containing spaces.

---

## Code Examples

### Session State Save/Load with Host Binding

```python
# auth/session.py
import json
from pathlib import Path
from urllib.parse import urlparse
import requests

SESSION_DIR = Path.home() / ".sharepoint-dl"

def save_session(storage_state_path: Path, sharepoint_url: str) -> Path:
    host = urlparse(sharepoint_url).netloc
    state = json.loads(storage_state_path.read_text())
    state["_host"] = host  # add host binding
    out_path = SESSION_DIR / "session.json"
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(state))
    out_path.chmod(0o600)
    return out_path

def load_session(sharepoint_url: str) -> requests.Session | None:
    """Returns None if session file does not exist or host does not match."""
    session_path = SESSION_DIR / "session.json"
    if not session_path.exists():
        return None
    state = json.loads(session_path.read_text())
    host = urlparse(sharepoint_url).netloc
    if state.get("_host") != host:
        return None
    session = requests.Session()
    for cookie in state["cookies"]:
        if host in cookie.get("domain", ""):
            session.cookies.set(cookie["name"], cookie["value"],
                                domain=cookie["domain"], path=cookie.get("path", "/"))
    return session
```

### Validate Session Before Use

```python
def validate_session(session: requests.Session, site_url: str) -> bool:
    try:
        resp = session.get(
            f"{site_url}/_api/web/title",
            headers={"Accept": "application/json;odata=verbose"},
            timeout=(10, 30),
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False
```

### Pagination Loop (Verified Pattern)

```python
# Source: verified against SharePoint sp-dev-docs and PITFALLS.md confirmed behavior
def _paginate(session: requests.Session, initial_url: str) -> list[dict]:
    results = []
    url = initial_url
    while url:
        resp = session.get(url, headers={"Accept": "application/json;odata=verbose"}, timeout=(10, 60))
        resp.raise_for_status()
        body = resp.json()["d"]
        results.extend(body.get("results", []))
        url = body.get("__next")  # None when no more pages
    return results
```

### Rich Spinner During Enumeration

```python
from rich.console import Console
from rich.spinner import Spinner

console = Console()

with console.status("[bold green]Scanning folders...", spinner="dots") as status:
    for folder in stack:
        files = enumerate_folder(session, folder)
        status.update(f"[bold green]Scanning folders... {len(all_files)} files found")
        all_files.extend(files)

console.print(f"[bold]Found {len(all_files)} files across {folder_count} folders[/bold]")
```

### typer App with Subcommands

```python
# cli/main.py — Source: https://typer.tiangolo.com/tutorial/commands/
import typer
from pathlib import Path

app = typer.Typer(no_args_is_help=True, help="SharePoint bulk file downloader.")

@app.command()
def auth(url: str = typer.Argument(..., help="SharePoint sharing URL")):
    """Authenticate and save session. Run once before list or download."""
    ...

@app.command(name="list")
def list_files(url: str = typer.Argument(..., help="SharePoint folder URL")):
    """Enumerate all files and print count + folder summary."""
    ...

@app.command()
def download(
    url: str = typer.Argument(..., help="SharePoint folder URL"),
    dest: Path = typer.Argument(..., help="Local download destination"),
):
    """[Phase 2] Full pipeline: auth if needed, enumerate, download."""
    raise NotImplementedError("Phase 2")

if __name__ == "__main__":
    app()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Email + OTP code for guest SharePoint access | Entra B2B guest account redemption | July 2025 (new links); July 2026 (all links) | OTP flow still live for pre-July 2025 links; must probe actual target link to know which applies |
| Manual venv + pip | `uv` with `pyproject.toml` + lockfile | 2024-2025 | `uv run` eliminates manual venv activation; deterministic installs |
| `tqdm` for progress | `rich` | 2022-2023 | `rich.progress.Progress` supports concurrent progress tasks; `tqdm` is single-bar only |
| `urllib3` retry adapter | `tenacity` | 2023+ | `tenacity` is more expressive for application-level retry logic; handles any exception type, not just HTTP |

**Deprecated/outdated:**
- `sharepy`: Uses SAML/form-digest auth — incompatible with Entra B2B guest sessions entirely
- `office365-rest-python-client`: Confirmed 404s on externally shared files; OAuth-only
- Microsoft Graph API for this use case: Requires Azure app registration; external guests with shared-link access cannot obtain Graph-compatible tokens

---

## Open Questions

1. **Which auth flow does the actual target link trigger?**
   - What we know: Both OTP (legacy) and Entra B2B are live as of March 2026. OTP retires fully July 2026.
   - What's unclear: Which specific flow the target shared link uses — cannot be determined without opening the link.
   - Recommendation: Wave 0 task — manually open the SharePoint URL in a browser and document whether it shows an OTP code entry page or an Entra ID / Microsoft account sign-in page. This must be done before implementing the Playwright auth flow, as the user interaction model differs slightly.

2. **Session cookie lifetime on the target tenant**
   - What we know: Default FedAuth/rtFa lifetime is 1-8 hours; conditional access policies can shorten it significantly.
   - What's unclear: The specific tenant's session lifetime — only discoverable by testing.
   - Recommendation: After Phase 1 auth is working, let the session sit for 30 minutes and re-validate it. This tells us if the download window will be sufficient for Phase 2's batch download.

3. **Server-relative URL format for the target sharing link**
   - What we know: SharePoint REST API requires a server-relative URL in the format `/sites/{site}/Shared Documents/{folder}` — not the sharing link URL itself.
   - What's unclear: The exact server-relative path for the target folder must be discovered from the sharing link's redirect chain.
   - Recommendation: After auth succeeds, navigate to the SharePoint page and extract the server-relative URL from the page's JSON data blob or from the address bar's `RootFolder` parameter. Document the URL format in a config or constant.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (no existing config — Wave 0 must create it) |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` section |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | `harvest_session()` writes `session.json` with valid cookie structure | unit (mock Playwright) | `uv run pytest tests/test_auth.py::test_harvest_session_writes_file -x` | Wave 0 |
| AUTH-01 | `load_session()` returns `requests.Session` with cookies injected | unit | `uv run pytest tests/test_auth.py::test_load_session_injects_cookies -x` | Wave 0 |
| AUTH-01 | `load_session()` returns `None` when session file absent | unit | `uv run pytest tests/test_auth.py::test_load_session_missing_file -x` | Wave 0 |
| AUTH-02 | `validate_session()` returns `True` on 200 probe | unit (mock requests) | `uv run pytest tests/test_auth.py::test_validate_session_active -x` | Wave 0 |
| AUTH-02 | `validate_session()` returns `False` on 401 probe | unit (mock requests) | `uv run pytest tests/test_auth.py::test_validate_session_expired -x` | Wave 0 |
| AUTH-03 | Auth expiry during enumeration halts with clear error, does not silently continue | unit (mock 401 mid-traversal) | `uv run pytest tests/test_traversal.py::test_auth_expiry_halts -x` | Wave 0 |
| ENUM-01 | `enumerate_files()` recurses into subfolders | unit (mocked API responses) | `uv run pytest tests/test_traversal.py::test_recursion_into_subfolders -x` | Wave 0 |
| ENUM-02 | `enumerate_files()` follows `@odata.nextLink` / `d.__next` until absent | unit (mocked paginated responses) | `uv run pytest tests/test_traversal.py::test_pagination_follows_next_link -x` | Wave 0 |
| ENUM-02 | Single-page folder listing (no pagination) still works correctly | unit | `uv run pytest tests/test_traversal.py::test_no_pagination_needed -x` | Wave 0 |
| ENUM-03 | File count printed after full traversal matches accumulated list length | unit | `uv run pytest tests/test_traversal.py::test_file_count_accuracy -x` | Wave 0 |
| CLI-01 | `sharepoint-dl list <url>` invokes enumeration with correct URL | unit (mock enumerator) | `uv run pytest tests/test_cli.py::test_list_command -x` | Wave 0 |
| CLI-01 | `sharepoint-dl download <url> <dest>` raises NotImplementedError in Phase 1 | unit | `uv run pytest tests/test_cli.py::test_download_stub -x` | Wave 0 |
| AUTH-01 | Host-binding: `load_session()` returns `None` when stored host != current host | unit | `uv run pytest tests/test_auth.py::test_host_mismatch_returns_none -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `pyproject.toml` — `[tool.pytest.ini_options]` section with `testpaths = ["tests"]`
- [ ] `tests/conftest.py` — shared fixtures: mock session, mock SharePoint API responses with and without pagination
- [ ] `tests/test_auth.py` — AUTH-01, AUTH-02, AUTH-03 unit tests (uses `pytest-mock` or `unittest.mock`)
- [ ] `tests/test_traversal.py` — ENUM-01, ENUM-02, ENUM-03, AUTH-03 unit tests
- [ ] `tests/test_cli.py` — CLI-01 unit tests (uses `typer.testing.CliRunner`)
- [ ] Framework install: `uv add --dev pytest pytest-playwright ruff` — no existing test infrastructure

---

## Sources

### Primary (HIGH confidence)
- [Playwright Python auth docs](https://playwright.dev/python/docs/auth) — `storageState()` API, session capture pattern, security guidance on session file storage
- [SharePoint REST API file/folder operations](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/working-with-folders-and-files-with-rest) — `GetFolderByServerRelativeUrl`, Files, Folders endpoints
- [typer commands documentation](https://typer.tiangolo.com/tutorial/commands/) — `@app.command()` pattern, `no_args_is_help`, entry point wiring
- [uv projects documentation](https://docs.astral.sh/uv/guides/projects/) — `uv init`, `uv add`, `[project.scripts]` in `pyproject.toml`
- [SharePoint sp-dev-docs Issue #1654](https://github.com/SharePoint/sp-dev-docs/issues/1654) — `$skiptoken` / `$skip` pagination behavior confirmed broken for Files endpoints
- [SharePoint sp-dev-docs Issue #5247](https://github.com/SharePoint/sp-dev-docs/issues/5247) — `/$value` endpoint confirmed broken for large files

### Secondary (MEDIUM confidence)
- [Guest accounts replacing OTP (March 2026)](https://office365itpros.com/2026/03/06/guest-accounts-spo/) — current state of OTP→Entra B2B migration, both flows simultaneously active
- [SharePoint OTP retirement blog](https://steve-chen.blog/2025/06/23/sharepoint-online-otp-authentication-gets-out-of-support-on-july-1st-2025/) — retirement timeline corroborated by Microsoft notices
- [Setting up pytest with uv](https://pydevtools.com/handbook/tutorial/setting-up-testing-with-pytest-and-uv/) — pyproject.toml configuration, `uv run pytest` pattern
- [Pagination with SharePoint REST](https://joemcshea.intellipointsolutions.com/pagination-in-sharepoint-rest-requests-using-top-and-skiptoken/) — `$skiptoken` behavior and `__next` property

### Tertiary (LOW confidence)
- [BrowserStack storageState guide](https://www.browserstack.com/guide/playwright-storage-state) — supplementary storageState usage examples (defer to official Playwright docs)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified via PyPI and official documentation
- Architecture: HIGH — Playwright session harvest pattern and SharePoint REST pagination verified against official docs and confirmed GitHub issues; module layout is standard Python CLI structure
- Pitfalls: HIGH — pagination truncation and exception swallowing verified against confirmed prior script behavior and official SharePoint issue trackers; auth flow ambiguity documented as open question, not a confidence gap

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (stable domain; auth layer has a moving target — re-check if implementation begins after July 2026)
