# Roadmap: SharePoint Bulk Downloader

## Overview

Three phases, each a hard dependency on the previous. Phase 1 proves the authenticated session and file enumeration are correct before any download code is written - this is the forensic constraint, not a preference. Phase 2 builds the download engine with all reliability mechanisms from day one (streaming, retry, resume, explicit error tracking). Phase 3 produces the forensic deliverables: the manifest, completeness report, and CLI polish. The tool cannot be trusted until all three phases are complete.

The v1.0 milestone audit found four blocker gaps and one planning normalization pass still needed before archival. Phases 4-6 close those gaps in dependency order: first harden resume/reporting behavior, then correct manifest evidence, then normalize the planning artifacts so a re-audit can pass cleanly.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - Authenticated session + verified complete file enumeration (completed 2026-03-27)
- [x] **Phase 2: Download Engine** - Streaming, retry, resume, concurrency, and explicit error tracking (completed 2026-03-27)
- [x] **Phase 3: Forensic Deliverables** - Manifest, completeness report, and CLI polish (completed 2026-03-27)
- [x] **Phase 4: Resume Safety and Failure Reporting** - Path-safe resume cleanup, pre-download visibility, and auth-expiry summaries (completed 2026-03-27)
- [x] **Phase 5: Manifest Path Accuracy** - Manifest local_path matches the real on-disk output path in every download mode (completed 2026-03-27)
- [ ] **Phase 6: Audit Evidence Normalization** - Planning artifacts reconciled so milestone re-audit can pass cleanly

## Phase Details

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
- [ ] 01-01-PLAN.md — Project scaffold + auth module (session harvest, persistence, validation)
- [ ] 01-02-PLAN.md — Enumerator module (recursive traversal, pagination) + CLI wiring (typer subcommands, rich output)
- [ ] 01-03-PLAN.md — Manual verification checkpoint (real auth flow + file count accuracy vs browser UI)

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
- [ ] 02-01-PLAN.md — Job state module (atomic persistence, resume logic) + single-file download function (streaming, SHA-256, auth guard, retry)
- [ ] 02-02-PLAN.md — Concurrent executor (ThreadPoolExecutor, auth halt) + Rich progress + CLI download command + error summary
- [ ] 02-03-PLAN.md — Manual verification checkpoint (real SharePoint download, resume, progress display)

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
- [ ] 03-01-PLAN.md — Manifest writer module (JobState accessor, JSON manifest generation with per-file metadata and SHA-256 from state)
- [ ] 03-02-PLAN.md — Completeness report and CLI integration (expected vs downloaded count, manifest auto-generation, --no-manifest flag)

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
- [ ] 06-01-PLAN.md — Verification-doc normalization for Phases 1-3 + roadmap plan-count/progress reconciliation

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 3/3 | Complete    | 2026-03-27 |
| 2. Download Engine | 3/3 | Complete    | 2026-03-27 |
| 3. Forensic Deliverables | 2/2 | Complete    | 2026-03-27 |
| 4. Resume Safety and Failure Reporting | 2/2 | Complete   | 2026-03-27 |
| 5. Manifest Path Accuracy | 1/1 | Complete | 2026-03-27 |
| 6. Audit Evidence Normalization | 0/1 | Planned | - |
