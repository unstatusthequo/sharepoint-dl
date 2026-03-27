# Phase 2: Download Engine - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Streaming download engine with retry, resume, concurrency, and explicit error tracking. Every file downloads correctly — 2GB files stream without memory issues, interrupted runs resume cleanly, and no file is ever silently skipped. Progress is visible throughout.

</domain>

<decisions>
## Implementation Decisions

### Download Concurrency
- 3 concurrent downloads via ThreadPoolExecutor (sweet spot for large files on typical connections)
- Configurable via `--workers` flag (default 3, range 1-8)
- Each worker handles one file at a time — no splitting individual files across workers
- Workers share a single requests.Session (thread-safe for reads)

### Streaming & Chunk Size
- Stream downloads with `requests.get(stream=True)` + `iter_content(chunk_size=8_388_608)` (8MB chunks)
- Write chunks to a `.part` temp file; rename to final name on completion
- Compute SHA-256 incrementally during download (hash each chunk as it's written — single I/O pass)
- No in-memory buffering of full files

### Resume Behavior
- State file (`state.json`) in the download destination directory tracks per-file status
- States: `pending`, `downloading`, `complete`, `failed`
- On re-run: skip `complete` files (verified by size match), retry `failed` and `downloading` (partial)
- Delete `.part` files for `downloading` state on resume (restart that file from scratch — simpler than byte-range resume for v1)
- State file written atomically (write to `.tmp`, rename) to survive crashes

### Error Handling
- Per-file retry: 3 attempts with exponential backoff via tenacity (2s, 4s, 8s)
- 401/403 during download: halt ALL workers immediately, prompt re-auth (don't retry — session is dead)
- 429 (throttled): respect Retry-After header, retry up to 3 times
- Network errors / timeouts: retry per tenacity policy
- After all retries exhausted: mark file as `failed` in state, continue to next file
- At end of run: print explicit failed file list, exit with code 1 if any failures
- NEVER catch-and-swallow exceptions in the download loop

### Progress Display
- Rich Live display with two levels:
  - Overall progress bar: "Downloading: 42/165 files (98.2 GB / 237.1 GB)"
  - Per-active-worker lines: "[worker 1] LAPTOP-5V7K1CJ4.E01 — 1.2 GB / 2.0 GB ████████░░ 60%"
- Update frequency: every chunk write (roughly every 8MB)
- On completion: summary table showing total files, total size, elapsed time, average speed
- On failure: red-highlighted failed files with error reason

### CLI Integration
- `sharepoint-dl download <url> <dest> --root-folder <path>` — full pipeline
- `--workers N` — concurrency (default 3)
- `--root-folder` required (carried from Phase 1)
- Download command: auto-auth if needed → enumerate → confirm count → download → report
- Confirmation prompt before starting: "Download 165 files (237.1 GB) to /path/to/dest? [Y/n]"

### Claude's Discretion
- Exact ThreadPoolExecutor shutdown/cancellation mechanics
- State file JSON schema details
- Temp file naming convention
- Download URL construction (download.aspx vs /$value — validate during research)
- Test fixture design for download engine

</decisions>

<specifics>
## Specific Ideas

- Real target is 165 files totaling 237.1 GB — downloads will take hours, so resume is critical
- Files are EnCase evidence files (.E01, .L01) — binary, no special encoding
- The user has 3 custodians to download — they'll run the tool multiple times with different `--root-folder` paths
- Session cookies may expire mid-download (1-8 hour lifetime) — the 401 halt-and-reauth flow is essential

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `sharepoint_dl/auth/session.py`: `load_session()`, `validate_session()`, `build_session()` — session management ready
- `sharepoint_dl/enumerator/traversal.py`: `enumerate_files()` returns `list[FileEntry]` with name, URL, folder, size
- `sharepoint_dl/enumerator/traversal.py`: `AuthExpiredError` — reuse for download auth failures
- `sharepoint_dl/cli/main.py`: `_parse_sharepoint_url()`, `_format_size()` — URL parsing and size formatting

### Established Patterns
- typer for CLI commands with rich console output
- tenacity for retry logic (already a dependency)
- `AuthExpiredError` raised on 401/403, caught at CLI level

### Integration Points
- `sharepoint_dl/downloader/` — empty module, this is where the engine goes
- `sharepoint_dl/state/` — empty module, for job state persistence
- `sharepoint_dl/cli/main.py`: `download` command currently stubs `NotImplementedError`
- Phase 3 will read SHA-256 hashes computed here to build the manifest

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-download-engine*
*Context gathered: 2026-03-27*
