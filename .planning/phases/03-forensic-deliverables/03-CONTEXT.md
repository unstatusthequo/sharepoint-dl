# Phase 3: Forensic Deliverables - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Generate a forensic manifest and completeness report from completed downloads. The SHA-256 hashes are already computed during Phase 2's download stream — this phase reads them from state.json and formats them as a manifest.json that can be handed to a third party as proof of completeness and integrity.

</domain>

<decisions>
## Implementation Decisions

### Manifest Format
- JSON file: `manifest.json` in the download destination directory (alongside state.json)
- Per-file entry: filename, remote server-relative path, local path, size_bytes, sha256, downloaded_at timestamp
- Top-level metadata: source SharePoint URL, root folder path, total file count, total size, manifest generation timestamp, tool version
- Sorted by remote path for consistent ordering

### Manifest Generation
- Generated at the end of a successful download run (all files complete or explicitly failed)
- Also generated on re-runs where all files reach terminal state (complete or failed)
- Reads SHA-256 hashes from state.json — does NOT re-read files from disk (single I/O pass guarantee from Phase 2)
- Only includes files with status=complete in the manifest (failed files listed separately)

### Completeness Report
- Printed to console at end of run as part of the success summary
- Shows: expected count (from enumeration), downloaded count, failed count, match status
- If counts don't match: explicit warning with list of missing/failed files
- Non-zero exit if expected != downloaded (already handled by Phase 2's error path)

### CLI Integration
- No new subcommands — manifest generation is automatic at end of download
- `--no-manifest` flag to skip manifest generation (for testing/debugging only)
- Manifest path printed in success summary: "Manifest written to: /path/to/manifest.json"

### Claude's Discretion
- Exact JSON schema structure
- Whether to include a summary section in manifest.json
- Error handling for edge cases (partial state.json, missing hashes)
- Test fixture design

</decisions>

<specifics>
## Specific Ideas

- state.json already has all the data needed: per-file name, size, sha256, status, downloaded_at, folder_path
- The manifest is a formatted view of state.json's complete files — no new computation needed
- This is the forensic deliverable — the user hands this file to prove they got everything

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `sharepoint_dl/state/job_state.py`: `JobState` class with per-file tracking, SHA-256 already stored
- `sharepoint_dl/downloader/engine.py`: `download_all()` returns `(completed, failed)` lists
- `sharepoint_dl/cli/main.py`: download command already prints success/failure summary

### Established Patterns
- JSON file I/O with atomic writes (state/job_state.py pattern)
- Rich console output for summaries (cli/main.py)
- typer options for flags

### Integration Points
- `sharepoint_dl/manifest/` — empty module, ready for implementation
- `download_all()` return value provides completed/failed lists
- CLI download command needs manifest generation added after download completes
- state.json in dest dir is the data source

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-forensic-deliverables*
*Context gathered: 2026-03-27*
