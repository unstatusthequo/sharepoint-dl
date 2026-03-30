# Phase 9: Batch and Session Resilience - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-30
**Phase:** 09-batch-and-session-resilience
**Areas discussed:** Session refresh flow

---

## Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Session refresh flow | How does re-auth work mid-download? Playwright on main thread, worker pause/resume, session propagation | ✓ |
| Batch queue UX | TUI folder queuing, per-job subdirectories, auto-start behavior | |
| Per-job isolation | Subdirectory structure, config save across jobs, shared vs per-job session | |
| Failure & edge cases | Re-auth failure, enumeration vs download expiry, max attempts, batch continuation | |

---

## Session Refresh Flow

### Q1: Re-auth browser window behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Silent popup | Browser opens automatically with Rich message "Session expired -- re-authenticating..." | ✓ |
| User-prompted | Tool pauses and asks "Press Enter to open browser" | |
| Automatic retry first | Wait 30s and retry silently, only open browser if retry fails | |

**User's choice:** Silent popup
**Notes:** Automatic, unattended-friendly

### Q2: Handling in-flight files after re-auth

| Option | Description | Selected |
|--------|-------------|----------|
| Retry failed file from scratch | Re-download from byte 0 with fresh session | ✓ |
| Resume from last chunk | Use HTTP Range header to resume from interruption point | |
| Skip and continue | Mark as failed, continue with remaining files | |

**User's choice:** Retry failed file from scratch
**Notes:** Simple, avoids partial-write corruption, state.json handles retry naturally

### Q3: Re-auth attempt limit

| Option | Description | Selected |
|--------|-------------|----------|
| 3 attempts then abort | After 3 failed re-auths, abort with clear error | ✓ |
| Unlimited retries | Keep trying as long as user is willing | |
| 1 attempt then abort | Single chance, then save and exit | |

**User's choice:** 3 attempts then abort
**Notes:** Prevents infinite loop on unreachable auth

### Q4: Session propagation to workers

| Option | Description | Selected |
|--------|-------------|----------|
| Replace session in-place | Update cookies on existing shared Session object with lock | ✓ |
| Broadcast new session | Create new Session, distribute via shared mutable reference | |
| Restart ThreadPoolExecutor | Shut down executor, create new session, start fresh | |

**User's choice:** Replace session object in-place
**Notes:** Thread-safe with lock, no reference swapping needed

## Claude's Discretion

- Subdirectory naming for batch jobs
- Rich UI for batch queue prompt
- Threading synchronization details
- Re-auth module structure

## Deferred Ideas

None — discussion stayed within phase scope
