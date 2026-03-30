# Phase 7: Zero-Risk UX Wins - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Three isolated improvements: ETA/speed in progress bars, timestamped log file, and auto-detect root folder from sharing links. No changes to download engine concurrency, auth flow, or state management.

</domain>

<decisions>
## Implementation Decisions

### ETA & Speed Display (UX-04)
- Add `TimeRemainingColumn` to `_make_progress()` in engine.py — Rich already has it built in
- Keep existing `TransferSpeedColumn` (already shows speed)
- Overall progress task gets ETA; per-worker tasks show speed only (ETA per-file is noisy)
- No new dependencies needed

### Timestamped Log File (REL-03)
- Write `download.log` in the download destination directory (alongside state.json and manifest.json)
- Use Python stdlib `logging` with `FileHandler` — NO `StreamHandler` (conflicts with Rich TUI)
- Log format: `2026-03-30 14:23:01 | INFO | Authenticated successfully`
- Events to log: auth start/success/failure, enumeration count, each file download start/complete/fail with size and SHA-256, retry attempts, session expiry, completeness report summary
- Log level: INFO for normal events, WARNING for retries, ERROR for failures
- Append mode — re-runs append to existing log (supports resume audit trail)
- Create logger at download start, close at end — don't leave file handles open during idle

### Auto-Detect Root Folder (UX-01)
- `_resolve_sharing_link()` already exists in cli/main.py (used by interactive mode)
- For CLI `download` and `list` commands: make `--root-folder` optional (not required)
- If `-r` not provided: call `_resolve_sharing_link()` to follow the sharing URL redirect and extract the `id=` parameter
- If auto-detect fails AND `-r` not provided: print clear error asking user to specify `-r` manually
- Interactive mode already does this — just need to wire it into CLI subcommands
- Move `_resolve_sharing_link()` and `_resolve_folder_from_browser_url()` from cli/main.py to a shared utility (both CLI and interactive use them)

### Claude's Discretion
- Exact log message wording
- Logger configuration details (name, propagation)
- Whether to add log rotation (probably not for v1 — files won't get huge)
- Test fixture design for logging assertions

</decisions>

<specifics>
## Specific Ideas

- All three features are additive — no refactoring of existing code needed
- ETA is literally one line change (add TimeRemainingColumn to _make_progress)
- Log file is ~50 lines of logging setup + sprinkled log calls
- Auto-detect is moving existing code into CLI subcommands

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `sharepoint_dl/downloader/engine.py:_make_progress()` — add TimeRemainingColumn here
- `sharepoint_dl/cli/main.py:_resolve_sharing_link()` — already resolves sharing links via redirect
- `sharepoint_dl/cli/main.py:_resolve_folder_from_browser_url()` — extracts `id=` from URL
- Python stdlib `logging` — no new deps

### Established Patterns
- Rich Progress with multiple columns (engine.py)
- Typer CLI with optional flags (cli/main.py)
- File I/O to dest directory (state.json, manifest.json patterns)

### Integration Points
- `_make_progress()` → add column (ETA)
- `download()` and `list_files()` CLI commands → make `-r` optional, add auto-detect fallback
- Download flow → add logging calls at key points
- Interactive mode → already has auto-detect, just needs logging added

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-zero-risk-ux-wins*
*Context gathered: 2026-03-30*
