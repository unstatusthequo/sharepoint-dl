# Phase 8: New Contained Modules - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Three independent new modules: config file persistence, bandwidth throttling, and post-download integrity verification. Each is self-contained with a clean interface to existing code.

</domain>

<decisions>
## Implementation Decisions

### Config File (UX-03)
- Location: `~/.sharepoint-dl/config.toml` (same directory as session.json)
- Format: TOML — read with stdlib `tomllib`, write with `tomli-w`
- Saved settings: `sharepoint_url`, `download_dest`, `workers`, `flat` (boolean)
- Auto-save after successful download (update config with the values used)
- Pre-fill in interactive mode: prompt shows config values as defaults
- CLI args always override config — config is never mandatory
- New module: `sharepoint_dl/config.py`
- If config file doesn't exist or is corrupt: silently use defaults, don't error

### Bandwidth Throttling (REL-02)
- Flag: `--throttle` accepting values like `10MB` or `50MB` (megabytes per second)
- Implementation: shared token bucket across all workers (single instance, mutex-protected)
- Throttle point: after each chunk write, sleep to maintain target rate — NOT inside iter_content
- New module: `sharepoint_dl/downloader/throttle.py`
- Token bucket refills at target rate; each chunk write consumes tokens equal to chunk size
- If throttle not specified: no overhead (no sleeps, no token checks)
- Log throttle setting at download start: "Throttling to 10 MB/s"
- Interactive mode: don't prompt for throttle (keep it simple) — CLI-only flag

### Verify Command (FOR-01)
- New CLI command: `sharepoint-dl verify <dest_dir>` or `./run.sh verify <dest_dir>`
- Reads `manifest.json` from dest_dir
- For each file in manifest: re-read from disk, compute SHA-256, compare against manifest hash
- Report: per-file PASS/FAIL, summary count, exit code 1 on any mismatch
- New module: `sharepoint_dl/manifest/verifier.py`
- Handle missing files (file in manifest but not on disk): report as FAIL with "file not found"
- Handle extra files (on disk but not in manifest): ignore (user may have added files)
- Progress bar during verification (files can be large)
- Also available in interactive mode: after download completes, offer "Verify downloaded files?"

### Claude's Discretion
- Token bucket implementation details (refill interval, bucket size)
- TOML schema field names
- Verify command output formatting
- Test fixture design

</decisions>

<specifics>
## Specific Ideas

- All three modules are independent — can be built and tested in isolation
- Config and throttle plug into existing download flow; verify is a new standalone command
- `tomli-w` is the only new runtime dependency (already identified in research)

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `~/.sharepoint-dl/` directory already exists (session.json lives there)
- `sharepoint_dl/downloader/engine.py:_download_file()` — throttle plugs into the chunk write loop
- `sharepoint_dl/manifest/writer.py:generate_manifest()` — verify reads the same manifest format
- `sharepoint_dl/downloader/log.py` — log throttle setting
- `sharepoint_dl/cli/main.py` — add verify command, add --throttle flag, add config loading

### Established Patterns
- Typer CLI commands (auth, list, download, verify)
- Rich progress bars for long operations
- Module-per-feature in sharepoint_dl/ package

### Integration Points
- `config.py` → `cli/main.py` (load config, pre-fill prompts, save after download)
- `throttle.py` → `engine.py:_download_file()` (call throttle.consume after each chunk write)
- `throttle.py` → `engine.py:download_all()` (create shared bucket, pass to workers)
- `verifier.py` → `cli/main.py` (new verify command)

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-new-contained-modules*
*Context gathered: 2026-03-30*
