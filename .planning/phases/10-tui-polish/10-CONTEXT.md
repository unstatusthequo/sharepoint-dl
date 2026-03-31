# Phase 10: TUI Polish - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Three independent improvements identified during v1.1 UAT: (1) human-readable CSV manifest report alongside JSON, (2) TUI-first startup menu with verify and throttle prompts, (3) accurate per-file elapsed timer in progress bars.

</domain>

<decisions>
## Implementation Decisions

### CSV Manifest Report (FOR-02)
- **D-01:** Filename: `manifest.csv` — lives alongside `manifest.json` in the download folder
- **D-02:** Includes ALL files (complete + failed + missing) with a Status column for filtering
- **D-03:** Columns: filename, local_path, size_bytes, sha256 (full, not truncated), status (COMPLETE/FAILED/MISSING), error (blank for complete files), downloaded_at
- **D-04:** Generated automatically after `manifest.json` is written — no user prompt needed
- **D-05:** Uses Python stdlib `csv` module — no new dependencies

### TUI Startup Flow (UX-05)
- **D-06:** Numbered menu on startup: `1. Download files  2. Verify a prior download`
- **D-07:** Menu appears after the banner, before the sharing URL prompt
- **D-08:** Selecting "Verify" prompts for folder path, pre-filled from `config.toml` `download_dest` value
- **D-09:** Throttle prompt appears after workers prompt: `Bandwidth limit? (e.g. 5MB, Enter to skip)`
- **D-10:** Throttle value saved to config.toml for next session (new `throttle` field)
- **D-11:** Verify path uses existing `verify_manifest()` from `sharepoint_dl/manifest/verifier.py` — same logic as CLI `verify` command

### Per-File Elapsed Timer (UX-06)
- **D-12:** Replace `TimeElapsedColumn` for worker tasks with a custom field that resets when a worker picks up a new file
- **D-13:** Overall task keeps the session-wide `TimeElapsedColumn` (that's correct for overall)
- **D-14:** Implementation: record `time.monotonic()` when worker starts a file, compute elapsed in the progress update callback, display via `TextColumn("{task.fields[elapsed]}")`

### Claude's Discretion
- CSV quoting strategy (stdlib csv handles this)
- Exact Rich prompt styling for the startup menu
- Whether throttle default shows "none" or is blank when no prior value

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Manifest & CSV
- `sharepoint_dl/manifest/writer.py` — `generate_manifest()` creates manifest.json; CSV generation plugs in here
- `sharepoint_dl/manifest/verifier.py` — `verify_manifest()` for TUI verify flow

### TUI & CLI
- `sharepoint_dl/cli/main.py` — `_interactive_mode_inner()` is the main TUI flow; startup menu goes at top, throttle prompt after workers
- `sharepoint_dl/config.py` — `Config` TypedDict, `load_config()`, `save_config()`; add `throttle` field

### Progress Bar
- `sharepoint_dl/downloader/engine.py` — `_make_progress()` creates Rich Progress; `download_all()` worker closure updates per-file tasks

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `generate_manifest()` in `writer.py` already builds the full files/failed lists — CSV generation reads the same data
- `verify_manifest()` in `verifier.py` — TUI verify calls this directly
- `parse_throttle()` in `throttle.py` — already parses "5MB" strings; reuse for TUI prompt
- `_make_progress()` in `engine.py` — modify columns for per-file timer
- `load_config()` / `save_config()` — extend Config TypedDict with optional `throttle` field

### Established Patterns
- Rich `Prompt.ask()` with `default=` for pre-filled values
- `IntPrompt.ask()` for numeric input with validation
- `_section_header()` for TUI section markers
- Config save at end of batch loop (already wired)

### Integration Points
- `generate_manifest()` → add CSV write call after JSON write
- `_interactive_mode_inner()` → add startup menu before sharing URL prompt
- `_interactive_mode_inner()` → add throttle prompt after workers prompt, pass to `download_all()`
- `_make_progress()` → replace `TimeElapsedColumn` with custom field for worker tasks
- `download_all()` worker closure → record file start time, update elapsed field

</code_context>

<specifics>
## Specific Ideas

- CSV should be generated in the same `generate_manifest()` call — write both files atomically
- Startup menu should be a simple numbered list (not AskUserQuestion — this is the app's own UI)
- Throttle prompt can accept freeform input and validate with `parse_throttle()`, showing error and re-prompting on invalid input

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 10-tui-polish*
*Context gathered: 2026-03-31*
