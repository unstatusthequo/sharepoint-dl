---
phase: 10-tui-polish
verified: 2026-03-30T00:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 10: TUI Polish Verification Report

**Phase Goal:** Download reports are human-readable, all features are accessible through the interactive TUI, and progress display is accurate per file
**Verified:** 2026-03-30
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|---------|
| 1  | After download, manifest.csv exists alongside manifest.json with correct columns | VERIFIED | `_write_manifest_csv()` called in `generate_manifest()` at writer.py:106; columns defined in `_CSV_COLUMNS` at writer.py:111 |
| 2  | CSV contains ALL files (complete + failed) with Status column | VERIFIED | `files_list` rows get `status="COMPLETE"`, `failed_list` rows get `status="FAILED"`, both written via `DictWriter.writerows()` at writer.py:133-165 |
| 3  | Per-file progress bars show elapsed time since that specific file started, not session time | VERIFIED | `file_start = time.monotonic()` set per worker after task reset at engine.py:313; closure captures `_fs=_file_start` as default arg to avoid stale capture bug at engine.py:321 |
| 4  | Overall progress bar still shows session-wide elapsed time | VERIFIED | `overall_start = time.monotonic()` at engine.py:275; `on_chunk` updates overall task with `time.monotonic() - _os` at engine.py:325 |
| 5  | On startup, TUI shows numbered menu: 1. Download files  2. Verify a prior download | VERIFIED | main.py:173-174 prints both menu items; `Prompt.ask` with default="1" at main.py:176-179 |
| 6  | Selecting Verify prompts for folder path pre-filled from config.toml download_dest | VERIFIED | `cfg["download_dest"]` used as default at main.py:184; `Prompt.ask` with that default at main.py:185-188 |
| 7  | After worker count prompt, TUI asks for bandwidth limit with freeform input | VERIFIED | Throttle while-loop prompt at main.py:264-283 appears after `workers = IntPrompt.ask(...)` at main.py:254-258 |
| 8  | Throttle value is saved to config.toml for next session | VERIFIED | `"throttle": throttle_input` included in `save_config()` call at main.py:585; Config TypedDict has `throttle: str` field at config.py:21 |
| 9  | Invalid throttle input shows error and re-prompts | VERIFIED | `except ValueError as exc: _error(...)` inside `while True` loop at main.py:282-283; no `break` on error path so loop continues |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact | Provides | Level 1: Exists | Level 2: Substantive | Level 3: Wired | Status |
|----------|----------|-----------------|----------------------|-----------------|--------|
| `sharepoint_dl/manifest/writer.py` | CSV generation inside `generate_manifest()` | Yes | 168 lines; `import csv`, `_write_manifest_csv()`, `csv.DictWriter` | Called from `generate_manifest()` at line 106; `generate_manifest` called from `cli/main.py:450` | VERIFIED |
| `sharepoint_dl/downloader/engine.py` | Per-file elapsed timer in progress display | Yes | 448 lines; `_format_elapsed()`, `time.monotonic`, `TextColumn("{task.fields[elapsed]}")` | `TextColumn` used in `_make_progress()` at line 209; `_format_elapsed` called in `on_chunk` at lines 322, 325 | VERIFIED |
| `sharepoint_dl/cli/main.py` | Startup menu + throttle prompt in interactive flow | Yes | 678+ lines; "Download files", "Verify a prior download", "Bandwidth limit?" all present | Startup menu at line 173, throttle prompt at line 265, `_run_verify()` at lines 198, 608 | VERIFIED |
| `sharepoint_dl/config.py` | Config TypedDict with throttle field | Yes | 100 lines; `throttle: str` in TypedDict, in DEFAULT_CONFIG, in `_validate()` | Loaded via `load_config()` in main.py:167; saved via `save_config()` at main.py:580-587 | VERIFIED |

---

### Key Link Verification

| From | To | Via | Status | Evidence |
|------|----|-----|--------|---------|
| `sharepoint_dl/manifest/writer.py` | `manifest.csv` | `csv.writer` inside `generate_manifest()` | WIRED | `_write_manifest_csv(dest_dir, ...)` at writer.py:106; writes to `dest_dir / "manifest.csv"` at writer.py:159 with atomic .tmp rename at writer.py:167 |
| `sharepoint_dl/downloader/engine.py` | Rich Progress | `TextColumn` with `task.fields[elapsed]` | WIRED | `TextColumn("{task.fields[elapsed]}")` at engine.py:209; all tasks initialized with `elapsed="0s"` at lines 282, 284 |
| `sharepoint_dl/cli/main.py` | `sharepoint_dl/manifest/verifier.py` | `verify_manifest()` call from TUI verify flow | WIRED | `from sharepoint_dl.manifest.verifier import verify_manifest` at line 26; called inside `_run_verify()` at line 149, which is called from verify flow at line 198 and post-download at line 608 |
| `sharepoint_dl/cli/main.py` | `sharepoint_dl/downloader/throttle.py` | `parse_throttle()` for TUI throttle input validation | WIRED | `from sharepoint_dl.downloader.throttle import TokenBucket, parse_throttle` at line 23; `parse_throttle(raw)` called inside throttle validation loop at line 274 |
| `sharepoint_dl/cli/main.py` | `sharepoint_dl/config.py` | `save_config` with throttle field | WIRED | `save_config({..., "throttle": throttle_input})` at main.py:580-587; `cfg.get("throttle", "")` at main.py:261 loads it back |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `writer.py` CSV output | `files_list`, `failed_list` | Built from `state.all_entries()` at writer.py:44 — live JobState populated during download | Yes — DB-equivalent: JobState reads from state.json on disk, contains real per-file SHA-256, sizes, timestamps | FLOWING |
| `engine.py` elapsed display | `elapsed` field per task | `time.monotonic()` calls at lines 275, 313 inside live worker execution | Yes — real wall-clock elapsed, resets per file | FLOWING |
| `cli/main.py` throttle persistence | `throttle_input` | User input validated through `parse_throttle()`, stored in `save_config()` at line 585 | Yes — round-trips through TOML file | FLOWING |
| `cli/main.py` verify flow | `summary` from `verify_manifest()` | `verify_manifest(dest_dir, on_progress=on_progress)` at main.py:149 — reads manifest.json + re-hashes files on disk | Yes — real file I/O and hash comparison | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Check | Result | Status |
|----------|-------|--------|--------|
| All 96 tests pass | `uv run --no-sync pytest tests/test_manifest.py tests/test_downloader.py tests/test_cli.py tests/test_config.py -q` | `96 passed in 3.31s` | PASS |
| CSV columns correct | `grep "_CSV_COLUMNS" sharepoint_dl/manifest/writer.py` | `["filename", "local_path", "size_bytes", "sha256", "status", "error", "downloaded_at"]` — 7 columns | PASS |
| TimeElapsedColumn removed | `grep -c "TimeElapsedColumn" sharepoint_dl/downloader/engine.py` | `0` — fully removed | PASS |
| `_format_elapsed` callable | `grep -c "_format_elapsed" sharepoint_dl/downloader/engine.py` | `3` (def + 2 call sites) | PASS |
| Throttle saved in config | `grep "throttle_input" sharepoint_dl/cli/main.py` | Referenced in save_config call at line 585 | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| FOR-02 | 10-01-PLAN.md | After download, a manifest.csv file is generated with full SHA-256 hashes and per-file metadata, openable in Excel/Sheets | SATISFIED | `_write_manifest_csv()` in writer.py produces 7-column CSV with full sha256, COMPLETE/FAILED status, atomic write; 6 dedicated CSV tests all pass |
| UX-06 | 10-01-PLAN.md | Per-file progress bars show elapsed time since that file started downloading, not overall session time | SATISFIED | `file_start = time.monotonic()` per worker task at engine.py:313; resets to "0s" on new file at engine.py:309; `TimeElapsedColumn` fully removed |
| UX-05 | 10-02-PLAN.md | On startup, TUI offers "Download or Verify?" — verify and throttle are accessible through interactive prompts, not just CLI flags | SATISFIED | Startup menu at main.py:173-179; verify flow at main.py:181-201; throttle prompt at main.py:261-283; both `parse_throttle` and `verify_manifest` wired via import and active call paths |

**No orphaned requirements.** REQUIREMENTS.md traceability table maps UX-05, UX-06, FOR-02 all to Phase 10, and all three are claimed by plans in this phase.

---

### Anti-Patterns Found

No anti-patterns detected in modified files.

| File | Pattern scanned | Result |
|------|-----------------|--------|
| `sharepoint_dl/manifest/writer.py` | TODO/FIXME, empty returns, stubs | Clean |
| `sharepoint_dl/downloader/engine.py` | TODO/FIXME, empty returns, stubs, hardcoded empty state | Clean |
| `sharepoint_dl/cli/main.py` | TODO/FIXME, placeholder, empty handlers | Clean |
| `sharepoint_dl/config.py` | TODO/FIXME, stubs | Clean |

---

### Human Verification Required

#### 1. TUI startup menu visual layout

**Test:** Launch the app interactively (`python -m sharepoint_dl` or `spdl`) and observe the startup screen.
**Expected:** Banner prints, then immediately below it two numbered options appear: "1. Download files" and "2. Verify a prior download" with Rich markup applied (bright_magenta numbers, bold text), followed by a prompt.
**Why human:** Rich markup rendering in an actual terminal cannot be verified by grep; visual alignment and color require a live TTY.

#### 2. Throttle re-prompt behavior on invalid input

**Test:** At the bandwidth limit prompt, enter an invalid value such as "abc" or "5x".
**Expected:** Error message prints in bright_red ("Invalid throttle value: ...") and the prompt re-appears without advancing the flow.
**Why human:** The while-loop control flow with `_error()` output requires an interactive session to confirm the re-prompt actually appears and the error text is readable.

#### 3. CSV file opens correctly in Excel/Sheets

**Test:** Run a real download, then open `manifest.csv` in Excel or Google Sheets.
**Expected:** File opens without import dialog; columns align correctly; filenames with commas or quotes appear as single cells (not split across columns); UTF-8 characters in filenames render correctly.
**Why human:** Excel import behavior requires manual testing; `csv.DictWriter` QUOTE_MINIMAL behavior with edge-case filenames is best confirmed by visual inspection of the output file.

---

### Gaps Summary

No gaps. All 9 observable truths verified, all 4 artifacts pass all four levels (exists, substantive, wired, data flowing), all 5 key links confirmed wired, all 3 requirement IDs satisfied, 96/96 tests pass, zero anti-patterns found.

The three items flagged for human verification are cosmetic/environmental concerns (terminal rendering, interactive re-prompt UX, spreadsheet compatibility) and do not block goal achievement — the underlying code is correctly implemented and tested.

---

_Verified: 2026-03-30_
_Verifier: Claude (gsd-verifier)_
