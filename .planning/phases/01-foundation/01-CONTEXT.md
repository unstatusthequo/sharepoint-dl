# Phase 1: Foundation - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Authenticated session capture + verified complete file enumeration. User can authenticate against a real SharePoint sharing link, and the tool produces a verified, complete file listing before any downloads begin. CLI accepts a SharePoint URL and destination path.

</domain>

<decisions>
## Implementation Decisions

### Auth Flow UX
- Tool auto-opens the default browser to the SharePoint URL via Playwright
- User completes login manually (OTP code or Entra B2B — whatever the link triggers)
- Tool detects successful auth by watching for the authenticated page state (presence of FedAuth/rtFa cookies)
- Once authenticated, tool extracts cookies and closes the browser automatically
- If auth fails or times out (2 minutes), tool exits with a clear error message

### Session Persistence
- Save session cookies to a local file (`~/.sharepoint-dl/session.json`) after successful auth
- On subsequent runs, attempt to reuse saved session — validate with a lightweight API call before proceeding
- If saved session is expired/invalid, auto-launch browser for fresh login (no manual flag needed)
- Session file stores the SharePoint host it was created for — don't reuse across different tenants

### CLI Invocation
- Single command with subcommands: `sharepoint-dl auth <url>`, `sharepoint-dl list <url>`, `sharepoint-dl download <url> <dest>`
- `auth` — authenticate and save session only (useful for testing)
- `list` — enumerate files and show count/tree (no download)
- `download` — full pipeline: auth (if needed) → enumerate → download
- Common flags: `--url` (SharePoint folder URL), `--dest` (download destination, required for download)
- Built with typer for auto-generated help and shell completion

### Enumeration Output
- During enumeration: spinner with "Scanning folders..." and running file count
- After enumeration: summary table showing folder path, file count, and total size per folder
- Final line: "Found N files (X.X GB total) across M folders"
- `list` subcommand shows this without proceeding to download
- Enumeration must complete fully before any download begins (forensic requirement)

### Error Handling
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

</decisions>

<specifics>
## Specific Ideas

- User has an urgent deadline — prioritize getting a working auth + enumeration flow fast over polish
- The SharePoint link structure is: `Images/[custodian]/[subfolder(s)]/[files]` — 3 custodians, ~100+ files each
- Files are EnCase evidence files (.E01, .L01 etc.), up to ~2GB each
- Auth is via external guest sharing (email + code or Entra B2B) — no admin access to the target tenant
- Previous Python script silently skipped files — likely pagination truncation and/or swallowed exceptions

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project

### Established Patterns
- None — first phase establishes patterns

### Integration Points
- Session cookies captured here feed into Phase 2's download engine
- File enumeration results (file list with paths and sizes) feed into Phase 2's download queue
- CLI structure established here is extended with download progress in Phase 2

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-03-27*
