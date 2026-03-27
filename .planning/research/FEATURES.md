# Feature Research

**Domain:** SharePoint bulk download tool — forensic evidence collection
**Researched:** 2026-03-27
**Confidence:** HIGH (core features), MEDIUM (forensic-grade specifics)

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Recursive folder traversal | Any bulk downloader must walk the tree; flat download is useless for multi-level structures | LOW | SharePoint REST API: GET `/_api/web/GetFolderByServerRelativeUrl('{path}')/Folders` and `/Files`; paginate with `$skiptoken` |
| Preserve folder structure locally | Users expect local layout to mirror remote; flat dump is confusing and loses context | LOW | Create directory tree from folder path segments before writing files |
| User-specified download destination | Downloading to a hardcoded or implicit path is never acceptable | LOW | CLI argument or interactive prompt at startup |
| Progress indication | Large downloads take time; users need feedback that something is happening | LOW | Per-file and overall progress; `tqdm` or equivalent |
| Error reporting per file | Silent skip is the original failure mode; every error must surface | LOW | Log to stderr AND to a structured error file; never swallow exceptions |
| Resume / skip completed files | Re-downloading everything from scratch after an interruption is a non-starter for 2GB files | MEDIUM | Check file existence + size match before downloading; full hash verification optional |
| Handle large files (2GB+) | EnCase `.E01`/`.L01` files are routinely 1–2GB; streaming download required | MEDIUM | Stream response in chunks; avoid loading whole file to memory; use HTTP Range requests if server supports them |
| Correct file naming | Downloaded files must have the same name as the source | LOW | Pull `Name` field from SharePoint REST API item; sanitize path-unsafe characters |
| Authentication via existing session | No admin credentials or app registration are available on the target tenant; tool must reuse the browser session established after OTP login | HIGH | Browser session cookie extraction (Playwright `storageState` or manual cookie injection); see PITFALLS for OTP retirement timeline |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Verification manifest (filename, size, hash) | Forensic use requires provable completeness — "I downloaded it" is not evidence; a manifest with SHA-256 per file is | MEDIUM | Generate JSON/CSV on completion; record remote-reported size AND local post-download hash; mark each file pass/fail |
| Expected vs. actual count report | Lets user immediately see if any files are missing without manually auditing | LOW | Count files from directory listing before download; compare to successfully downloaded count at end |
| Structured error log (machine-readable) | Enables downstream audit workflows; human-readable stderr is not enough for forensic documentation | LOW | Write `errors.json` with file path, attempted URL, error code, timestamp |
| Post-download integrity re-verification | Allows running manifest check on a previously completed download to confirm nothing changed in transit or on disk | MEDIUM | Separate `verify` subcommand that re-hashes local files against manifest |
| Configurable concurrency with back-off | SharePoint throttles aggressively; blind parallel downloads cause 429s and silent stalls | MEDIUM | Semaphore-bounded concurrency (default 3–5 workers); exponential back-off on 429/503 with `Retry-After` header respect |
| Audit trail / download log | Documents who ran the tool, when, against which URL, and what was downloaded — chain of custody requirement | LOW | Append-only log: timestamp, operator (current OS user), source URL, file path, hash, size, outcome |
| Dry-run / list-only mode | Before committing to a long download, user can verify what will be downloaded and how many files | LOW | Walk folder tree, print file list and total size, exit without downloading |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Incremental sync (two-way, ongoing) | Users think they want a persistent mirror | Forensic context requires a discrete, timestamped capture — not a living sync that can silently incorporate post-collection changes; also massively increases scope | One-time full download with dated output directory; re-run explicitly when needed |
| GUI / browser interface | "Easier to use" | Adds a heavyweight UI framework dependency, complicates distribution on Mac, and is irrelevant to the CLI forensic workflow | Clean CLI output; clear progress bars; structured logs are sufficient |
| Upload capability | Symmetry reflex — if you can download, why not upload? | Completely out of scope; adds API surface, auth complexity, and risk of accidentally modifying evidence | Explicitly reject; document as out-of-scope |
| Parallel chunked download (byte-range splitting) | Faster downloads for large files | SharePoint Online does not reliably support multi-range parallel downloads for guest sessions; adds complexity for marginal gain; risks partial-file corruption that is hard to detect | Single-connection streaming with retry on failure; verify hash on completion |
| Automatic re-authentication / token refresh loop | Unattended operation sounds appealing | OTP auth (currently being retired in favor of Entra B2B) cannot be automated without a real user; auto-refresh attempts introduce silent partial downloads when auth silently fails mid-session | Detect auth expiry early; fail loudly with a clear re-auth instruction; do not silently retry against an expired session |
| File filtering / selective download | "Just download the PDFs" | Forensic collection must be complete; filters create accidental exclusions that are difficult to audit after the fact | Download everything; let the user filter locally after verification |
| Cloud-to-cloud transfer | Transfer directly without local copy | Loses the local manifest and hash verification step that makes the download forensically defensible | Always materialize locally; hash the local file |

## Feature Dependencies

```
[Session Authentication]
    └──required by──> [Folder Traversal]
                          └──required by──> [File Download]
                                                └──required by──> [Verification Manifest]
                                                └──required by──> [Expected vs Actual Count Report]
                                                └──required by──> [Audit Trail / Download Log]

[File Download]
    └──required by──> [Resume / Skip Completed Files]
    └──enhanced by──> [Configurable Concurrency with Back-off]

[Verification Manifest]
    └──enhanced by──> [Post-download Integrity Re-verification]

[Folder Traversal]
    └──enhanced by──> [Dry-run / List-only Mode]
```

### Dependency Notes

- **Session Authentication requires OTP completion before tool starts:** The tool cannot perform auth inline — the user must complete the email+OTP flow in a browser first; the tool harvests cookies from that session. This means auth is a precondition, not a feature the tool implements.
- **Folder Traversal requires pagination handling:** SharePoint enforces a 5,000-item list threshold per API call. Any folder with more than 5,000 items must use `$skiptoken` pagination or the listing is silently truncated — this is a likely root cause of the prior script's silent omissions.
- **Resume requires completed-file tracking:** A simple existence check (file exists AND size matches remote-reported size) is sufficient for resume decisions. Full hash check on resume would be correct but slow; defer to post-download verify pass.
- **Manifest requires completed Download:** Manifest is generated after all downloads complete, not incrementally. An intermediate state file (for resume) is separate from the final forensic manifest.
- **Post-download Re-verification enhances Manifest:** Re-verify subcommand reads the manifest and re-hashes all local files; they are complementary, not duplicates.

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed for the immediate forensic collection.

- [ ] Session Authentication via browser cookie harvest — without this nothing works
- [ ] Recursive folder traversal with pagination — must handle >5,000 items correctly
- [ ] Preserve folder structure locally — mirrors `Images/[custodian]/[subfolder]/files`
- [ ] User-specified download destination — chosen at launch via CLI arg or prompt
- [ ] Streaming large-file download (2GB+) — core file type requirement
- [ ] Resume / skip completed files — protect against interruptions during multi-hour downloads
- [ ] Per-file error reporting (no silent skips) — fixes the prior script's known failure mode
- [ ] Verification manifest (filename, size, SHA-256 hash) — non-negotiable for forensic use
- [ ] Expected vs. actual count report — quick completeness check at end of run
- [ ] Progress indication — per-file and overall

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] Audit trail / download log — add when workflow moves from single-operator to team use
- [ ] Post-download integrity re-verification (`verify` subcommand) — add when there's a need to re-certify downloads after transport
- [ ] Configurable concurrency with back-off — add if download speed or throttling becomes an operational issue
- [ ] Dry-run / list-only mode — useful for scoping future collections

### Future Consideration (v2+)

Features to defer until v1 is proven.

- [ ] Cross-platform support (Windows/Linux) — defer; Mac-only meets current deadline
- [ ] Entra B2B guest auth support — OTP retirement completes August 2026; tool may need to adapt auth layer; design auth as swappable module now to ease this migration

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Session authentication | HIGH | HIGH | P1 |
| Recursive traversal with pagination | HIGH | MEDIUM | P1 |
| Streaming large-file download | HIGH | MEDIUM | P1 |
| Resume / skip completed files | HIGH | MEDIUM | P1 |
| Verification manifest (SHA-256) | HIGH | MEDIUM | P1 |
| Per-file error reporting | HIGH | LOW | P1 |
| Expected vs. actual count report | HIGH | LOW | P1 |
| Preserve folder structure | HIGH | LOW | P1 |
| Progress indication | MEDIUM | LOW | P1 |
| Audit trail / download log | MEDIUM | LOW | P2 |
| Post-download re-verification | MEDIUM | MEDIUM | P2 |
| Configurable concurrency | MEDIUM | MEDIUM | P2 |
| Dry-run / list-only mode | MEDIUM | LOW | P2 |
| Entra B2B auth migration | HIGH | HIGH | P3 |
| Cross-platform support | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | rclone (SharePoint backend) | SysTools Office 365 Downloader | Playwright/custom script | Our Approach |
|---------|-----------------------------|---------------------------------|--------------------------|--------------|
| Guest OTP / browser session auth | Not supported (requires OAuth app registration) | Not supported (requires admin credentials) | Supported via storageState cookie reuse | Browser session cookie harvest — the only practical path |
| Verification manifest with hashes | Not built-in (external scripting needed) | Error log only, no hash manifest | Not built-in | First-class manifest output: every file, size, SHA-256 |
| Resume interrupted download | Yes (via sync state) | Unknown | Not built-in | Skip-completed logic keyed on file existence + size |
| Large file (2GB+) streaming | Yes | Unknown; JavaScript buffer limit known to cause failures | Yes (streaming response) | Streaming chunks; avoid full in-memory buffering |
| Pagination / >5,000 item folders | Yes | Unknown | Must implement manually | Explicit `$skiptoken` pagination loop |
| Forensic audit trail | No | No | No | Append-only structured log |
| Silent failure risk | Known throttling/stall issues | Known silent omissions reported | Risk if not explicitly handled | Fail loudly on every error; count verification at end |

## Sources

- [SharePoint 5,000 item threshold and pagination](https://www.robinsandra.com/the-infamous-5000-item-limit-paging-with-the-sharepoint-rest-api/) — MEDIUM confidence (community blog, consistent with Microsoft Q&A)
- [Large file >2GB TaskCanceled error in PnP](https://github.com/pnp/pnpcore/issues/228) — HIGH confidence (official GitHub issue tracker)
- [Silent download failure for multiple files](https://learn.microsoft.com/en-us/answers/questions/5296419/download-function-in-sharepoint-fails-to-download) — HIGH confidence (Microsoft Q&A)
- [SharePoint OTP retirement timeline (August 2026)](https://mc.merill.net/message/MC1243549) — HIGH confidence (Microsoft Message Center official notice)
- [Playwright session storageState for cookie reuse](https://playwright.dev/docs/auth) — HIGH confidence (official Playwright docs)
- [Forensic chain of custody requirements](https://acecomputers.com/chain-of-custody-in-digital-forensics/) — MEDIUM confidence (industry overview, consistent with NIST guidance)
- [ProofSnap manifest verification pattern (SHA-256 + manifest.json)](https://getproofsnap.com/verify/index.html) — MEDIUM confidence (commercial implementation demonstrating the pattern)
- [rclone SharePoint throttling issues](https://forum.rclone.org/t/throttling-of-rclone-with-sharepoint-saga-continues/29874) — MEDIUM confidence (community forum, matches known SharePoint behavior)
- [Microsoft Graph throttling limits](https://learn.microsoft.com/en-us/graph/throttling-limits) — HIGH confidence (official Microsoft docs)

---
*Feature research for: SharePoint bulk download tool — forensic evidence collection*
*Researched: 2026-03-27*
