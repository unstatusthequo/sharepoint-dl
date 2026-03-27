# Roadmap: SharePoint Bulk Downloader

## Overview

Three phases, each a hard dependency on the previous. Phase 1 proves the authenticated session and file enumeration are correct before any download code is written — this is the forensic constraint, not a preference. Phase 2 builds the download engine with all reliability mechanisms from day one (streaming, retry, resume, explicit error tracking). Phase 3 produces the forensic deliverables: the manifest, completeness report, and CLI polish. The tool cannot be trusted until all three phases are complete.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - Authenticated session + verified complete file enumeration (completed 2026-03-27)
- [x] **Phase 2: Download Engine** - Streaming, retry, resume, concurrency, and explicit error tracking (completed 2026-03-27)
- [ ] **Phase 3: Forensic Deliverables** - Manifest, completeness report, and CLI polish

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
**Plans**: TBD

Plans:
- [ ] 03-01: Manifest writer (append-only JSON manifest, SHA-256 from download stream, finalization at run end)
- [ ] 03-02: Completeness report and CLI polish (expected vs downloaded count, clean end-of-run summary, non-zero exit wiring)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/3 | Complete    | 2026-03-27 |
| 2. Download Engine | 2/3 | Complete    | 2026-03-27 |
| 3. Forensic Deliverables | 0/2 | Not started | - |
