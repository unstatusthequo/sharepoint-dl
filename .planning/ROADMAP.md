# Roadmap: SharePoint Bulk Downloader

## Milestones

- ✅ **v1.0 MVP** - Phases 1-6 (shipped 2026-03-27)
- 🚧 **v1.1 Feature Expansion** - Phases 7-9 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-6) — SHIPPED 2026-03-27</summary>

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - Authenticated session + verified complete file enumeration (completed 2026-03-27)
- [x] **Phase 2: Download Engine** - Streaming, retry, resume, concurrency, and explicit error tracking (completed 2026-03-27)
- [x] **Phase 3: Forensic Deliverables** - Manifest, completeness report, and CLI polish (completed 2026-03-27)
- [x] **Phase 4: Resume Safety and Failure Reporting** - Path-safe resume cleanup, pre-download visibility, and auth-expiry summaries (completed 2026-03-27)
- [x] **Phase 5: Manifest Path Accuracy** - Manifest local_path matches the real on-disk output path in every download mode (completed 2026-03-27)
- [x] **Phase 6: Audit Evidence Normalization** - Planning artifacts reconciled so milestone re-audit can pass cleanly (completed 2026-03-27)

### Phase 1: Foundation
**Goal**: User can authenticate against the real SharePoint link and get a verified, complete file listing before any download code exists
**Depends on**: Nothing (first phase)
**Requirements**: AUTH-01, AUTH-02, AUTH-03, ENUM-01, ENUM-02, ENUM-03, CLI-01
**Success Criteria** (what must be TRUE):
  1. User runs the tool, completes the browser auth flow (OTP or Entra B2B — whichever the real link triggers), and the tool confirms the session is active
  2. Tool reports total file count for the target folder, and that count matches the count visible in the SharePoint browser UI
  3. Tool detects an expired session and prompts the user to re-authenticate rather than proceeding silently
  4. User can specify the download destination folder at launch via CLI argument
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — Project scaffold + auth module (session harvest, persistence, validation)
- [x] 01-02-PLAN.md — Enumerator module (recursive traversal, pagination) + CLI wiring (typer subcommands, rich output)
- [x] 01-03-PLAN.md — Manual verification checkpoint (real auth flow + file count accuracy vs browser UI)

### Phase 2: Download Engine
**Goal**: Every file downloads correctly — 2GB files stream without memory issues, interrupted runs resume cleanly, and no file is ever silently skipped
**Depends on**: Phase 1
**Requirements**: DWNL-01, DWNL-02, DWNL-03, DWNL-04, DWNL-05, CLI-02, CLI-03
**Success Criteria** (what must be TRUE):
  1. A 2GB forensic evidence file downloads completely without memory error or timeout, and its local size matches the remote size
  2. If the tool is killed mid-run and restarted, already-completed files are skipped and only failures/incomplete files are retried
  3. If any file fails to download after retries, it appears explicitly in the error summary — the tool never silently proceeds past a failure
  4. Tool exits with a non-zero exit code when any file fails
  5. Per-file and overall progress bars are visible during the download run
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — Job state module (atomic persistence, resume logic) + single-file download function (streaming, SHA-256, auth guard, retry)
- [x] 02-02-PLAN.md — Concurrent executor (ThreadPoolExecutor, auth halt) + Rich progress + CLI download command + error summary
- [x] 02-03-PLAN.md — Manual verification checkpoint (real SharePoint download, resume, progress display)

### Phase 3: Forensic Deliverables
**Goal**: User can hand a completed manifest to a third party as proof that every file in the SharePoint folder was downloaded and is intact
**Depends on**: Phase 2
**Requirements**: VRFY-01, VRFY-02, VRFY-03
**Success Criteria** (what must be TRUE):
  1. After a completed run, a manifest.json exists containing filename, remote path, size, SHA-256 hash, and download timestamp for every downloaded file
  2. The file count in the manifest matches the file count the enumerator reported before downloading began
  3. The SHA-256 hash in the manifest was computed from the streamed bytes during download — no second I/O pass, no server-provided hash accepted
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md — Manifest writer module (JobState accessor, JSON manifest generation with per-file metadata and SHA-256 from state)
- [x] 03-02-PLAN.md — Completeness report and CLI integration (expected vs downloaded count, manifest auto-generation, --no-manifest flag)

### Phase 4: Resume Safety and Failure Reporting
**Goal**: Resume logic is path-safe, download runs always show pre-transfer scope, and auth-expiry failures still produce explicit end-of-run reporting
**Depends on**: Phase 3
**Requirements**: DWNL-02, ENUM-03, CLI-03
**Gap Closure**: Closes the v1.0 audit gaps around duplicate filename resume cleanup, `download --yes` visibility, and auth-expiry reporting
**Success Criteria** (what must be TRUE):
  1. Interrupted-run cleanup targets the exact tracked `.part` file for each entry, even when two folders contain the same filename
  2. `sharepoint-dl download` prints total file count and total size before transfers begin, including when `--yes` bypasses confirmation
  3. If auth expires during download, the tool still emits a completeness report and explicit failure summary while preserving completed work for resume
**Plans**: 2 plans

Plans:
- [x] 04-01-PLAN.md — Path-safe interrupted cleanup + exact local-path state persistence
- [x] 04-02-PLAN.md — Pre-download scope visibility + auth-expiry reporting tail normalization

### Phase 5: Manifest Path Accuracy
**Goal**: Manifest evidence reflects the actual local filesystem path written for every completed file
**Depends on**: Phase 4
**Requirements**: VRFY-02
**Gap Closure**: Closes the v1.0 audit gap where `manifest.json` reports SharePoint-style paths instead of the real local output path
**Success Criteria** (what must be TRUE):
  1. `manifest.json` stores the actual on-disk path for each completed file, not the remote SharePoint folder path
  2. Manifest path evidence is correct for both preserved-folder downloads and `--flat` downloads
  3. Manifest generation and downloader/state reuse one source of truth for local file placement
**Plans**: 1 plan

Plans:
- [x] 05-01-PLAN.md — Persisted local_path manifest evidence + flat-mode CLI integration + legacy fallback validation

### Phase 6: Audit Evidence Normalization
**Goal**: Planning artifacts match the real verification evidence so milestone re-audit reflects the actual project state
**Depends on**: Phases 4 and 5
**Requirements**: None - planning normalization
**Gap Closure**: Closes the v1.0 audit tech debt around stale roadmap counts and inconsistent human-verification claims
**Success Criteria** (what must be TRUE):
  1. Phase verification docs distinguish real human verification from "verified by design" accurately
  2. `ROADMAP.md` progress counts match completed plans and the new gap-closure phases
  3. After Phases 4-5 complete, a re-audit can pass without planning-state contradictions
**Plans**: 1 plan

Plans:
- [x] 06-01-PLAN.md — Verification-doc normalization for Phases 1-3 + roadmap plan-count/progress reconciliation

</details>

### 🚧 v1.1 Feature Expansion (In Progress)

**Milestone Goal:** Make SPDL easier to use (auto-detect folder, config file, batch mode), more reliable during long downloads (session refresh, throttle), verifiable after download (verify command), and observable throughout (ETA, log file).

- [ ] **Phase 7: Zero-Risk UX Wins** - ETA/speed display, timestamped log file, and auto-detect folder from sharing link
- [ ] **Phase 8: New Contained Modules** - Config file, bandwidth throttle, and post-download verify command
- [ ] **Phase 9: Batch and Session Resilience** - Multi-folder batch download and automatic mid-download session refresh

## Phase Details

### Phase 7: Zero-Risk UX Wins
**Goal**: Users get visible download progress (speed and ETA), a durable audit log, and no longer need to manually specify the root folder from a sharing link
**Depends on**: Phase 6
**Requirements**: UX-01, UX-04, REL-03
**Success Criteria** (what must be TRUE):
  1. Progress bar shows current download speed and estimated time remaining during any active download run
  2. After a completed run, a timestamped `download.log` file exists containing all events from that run in human-readable form
  3. User can pass a SharePoint sharing link directly to `download` and the tool resolves the root folder path automatically, without a `--root-folder` flag
  4. Log file output does not corrupt or interleave with the Rich TUI progress display
**Plans**: TBD
**UI hint**: yes

### Phase 8: New Contained Modules
**Goal**: Users can save settings so repeat runs need less input, cap bandwidth to avoid saturating the network, and re-verify downloaded files against the manifest without re-downloading
**Depends on**: Phase 7
**Requirements**: UX-03, REL-02, FOR-01
**Success Criteria** (what must be TRUE):
  1. After a successful run, `~/.sharepoint-dl/config.toml` is written with the SharePoint URL, destination, and worker count used; these values pre-fill on the next run
  2. Explicit CLI arguments always override config file values; the config file is never mandatory
  3. Running `spdl verify <dest_dir>` re-reads every file from disk, recomputes its SHA-256, and reports any hash mismatches or missing files against `manifest.json`
  4. Running `spdl download --throttle 2MB` limits aggregate bandwidth across all workers to approximately 2 MB/s without causing `ChunkedEncodingError`
**Plans**: TBD

### Phase 9: Batch and Session Resilience
**Goal**: Users can queue multiple custodian folders in one session without restarting, and unattended multi-hour runs survive session expiry automatically
**Depends on**: Phase 8
**Requirements**: UX-02, REL-01
**Success Criteria** (what must be TRUE):
  1. After a download completes, the TUI offers to queue another folder; the user can add a second folder path and it downloads sequentially in the same session without re-authenticating
  2. Each batch job writes to its own subdirectory with its own `manifest.json`, `state.json`, and log file — no cross-job state collision
  3. When the session expires mid-download (401), the tool pauses workers, opens a browser window for re-authentication on the main thread, then resumes from the failed file — all without user re-running the command
  4. With 4+ concurrent workers all receiving 401, only one browser window opens; subsequent workers wait for the single re-auth to complete before retrying
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 3/3 | Complete | 2026-03-27 |
| 2. Download Engine | v1.0 | 3/3 | Complete | 2026-03-27 |
| 3. Forensic Deliverables | v1.0 | 2/2 | Complete | 2026-03-27 |
| 4. Resume Safety and Failure Reporting | v1.0 | 2/2 | Complete | 2026-03-27 |
| 5. Manifest Path Accuracy | v1.0 | 1/1 | Complete | 2026-03-27 |
| 6. Audit Evidence Normalization | v1.0 | 1/1 | Complete | 2026-03-27 |
| 7. Zero-Risk UX Wins | v1.1 | 0/TBD | Not started | - |
| 8. New Contained Modules | v1.1 | 0/TBD | Not started | - |
| 9. Batch and Session Resilience | v1.1 | 0/TBD | Not started | - |
