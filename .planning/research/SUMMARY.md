# Project Research Summary

**Project:** SharePoint Bulk Downloader (SPDL) — v1.1 Milestone
**Domain:** CLI forensic evidence collection tool for SharePoint shared folders (guest/external auth)
**Researched:** 2026-03-30 (v1.1 update; original v1.0 research 2026-03-27)
**Confidence:** HIGH (architecture and features based on direct codebase inspection; auth layer MEDIUM due to active Microsoft OTP→Entra B2B migration)

## Executive Summary

SPDL is a forensic-grade CLI tool for bulk downloading SharePoint shared folders using guest/external authentication. The v1.0 foundation — two-phase Playwright session harvest plus requests streaming plus SHA-256 manifest — is validated and shipped. v1.1 adds nine features that bring the tool to parity with generic download tools (wget, aria2c, yt-dlp) on ETA display, timestamped logging, config file, and bandwidth throttling, while extending its forensic lead with a local verify command and first-class multi-folder batch mode. One new runtime dependency (`tomli-w`) covers all config file needs. Everything else is stdlib or already installed.

The recommended build order for v1.1 follows a clear dependency and risk gradient. Four zero-risk wins (ETA display, log file, auto-detect folder from sharing link, PyPI publish) require no new modules and carry no regression risk to the existing download path — these ship first. A second tier of contained new modules (config file, throttle, verify command) adds functionality without touching the core engine. The highest-complexity features (multi-folder batch, smart session refresh) come last because they interact with the existing TUI loop and the auth-halt concurrency model respectively. Session refresh is the highest-leverage reliability feature for multi-hour 200+ GB downloads, and the hardest to test; it must be built last with adequate test coverage of thread coordination.

The critical risk for the entire v1.1 milestone is the PyPI package name `spdl` — it is already registered by Meta's data loading library (`pip install spdl` installs the wrong package). This must be resolved before any packaging work begins; `sharepoint-dl` is the natural fallback given the existing GitHub slug. The second major risk is the Microsoft OTP retirement (effective July 2026): the Playwright session-harvest architecture is already flow-agnostic and handles Entra B2B guest auth with no code changes, but this must be empirically verified during the session refresh phase against a post-migration tenant.

## Key Findings

### Recommended Stack

The v1.0 stack (Python 3.11+, playwright 1.58, requests 2.33, rich 14.1, typer 0.15, tenacity 9.x) is validated and unchanged. v1.1 adds exactly one new runtime dependency: `tomli-w` (>=1.2.0) to write TOML config files — stdlib `tomllib` handles reads, and `tomli-w` (by the same author, hukkin) handles writes. All other v1.1 features use Rich columns, stdlib logging, and stdlib threading that are already installed or built-in. A dev-only `twine` addition supports PyPI publishing via `uv run twine upload dist/*`.

**Core technologies:**
- `playwright` 1.58: browser automation for session harvest — the only reliable way to capture full Microsoft identity session state (cookies + localStorage) in one call via `storageState()`; works identically for OTP and Entra B2B guest flows
- `requests` 2.33: sync HTTP streaming downloads — `stream=True` + `iter_content()` keeps 2 GB files off-heap; synchronous is correct for sequential large-file downloads
- `rich` 14.1: terminal progress display — `TransferSpeedColumn`, `DownloadColumn`, `TimeRemainingColumn` available natively; no new dep needed for ETA or speed display
- `tenacity` 9.x: retry with exponential backoff — handles 429/5xx; auth expiry (401/403) is a hard halt, not a retry target
- `tomli-w` 1.2.0: config file writes — the only new v1.1 runtime dep; 15 KB, MIT, Python 3.9+

**Explicit exclusions for v1.1:** `pydantic-settings` (overkill for ~6 flat config keys), `requests-ratelimiter` (limits by request count, not bytes/sec), `tomlkit` (style-preserving, unnecessary since config is always written fresh), `structlog` (overkill for a human-readable audit trail), `platformdirs` (defer unless config path logic grows complex).

### Expected Features

**Must have — v1.1 table stakes (users expect parity with wget/aria2c/yt-dlp):**
- ETA and download speed display — conspicuous absence for multi-hour runs; effectively free via existing Rich columns
- Timestamped log file — forensic identity requires a durable audit trail; additive, no regression risk to existing behaviour
- Auto-detect root folder from sharing link — removes the single biggest friction point in CLI mode; interactive mode already does this
- Post-download verify command — completes the forensic chain-of-custody story; pure consumer of existing `manifest.json`

**Should have — v1.1 differentiators and quality-of-life (P1 and P2):**
- Multi-folder batch download (P1) — primary use case for multi-custodian forensic collections; sequential, not parallel
- PyPI publish as `sharepoint-dl` (P1) — unlocks distribution beyond the immediate team; complexity is packaging, not application logic
- Smart session refresh mid-download (P2) — no other SharePoint download tool handles token expiry gracefully; critical for unattended 200+ GB runs
- Bandwidth throttling `--throttle` flag (P2) — required for office and VPN environments where link saturation creates IT conflicts
- Config file for saved settings (P2) — quality-of-life for repeat forensic investigators who re-enter the same URL and destination weekly

**Defer to v1.2+:**
- Incremental sync mode — SharePoint REST lacks a reliable last-modified-since delta for external guest sessions; full re-enumeration with skip-if-exists already handles re-runs adequately
- Parallel batch execution — multiplies concurrent HTTP load and auth complexity; sequential batch is safe, predictable, and rate-limit-safe
- Per-worker bandwidth cap — users think in total bandwidth, not per-worker; per-worker creates false precision and confusing math

### Architecture Approach

v1.1 adds four new modules to the existing codebase without restructuring it: `auth/refresh.py` (mid-download re-auth trigger), `downloader/throttle.py` (token-bucket rate limiter), `manifest/verifier.py` (disk re-hash vs manifest comparison), and `cli/config.py` (load/save config). Three existing modules receive targeted modifications: `engine.py` gets throttle and refresh hooks plus the ETA column; `cli/main.py` gets the verify command, batch loop, and config pre-fill; `pyproject.toml` gets PyPI metadata. Six modules remain completely untouched (browser.py, session.py, traversal.py, job_state.py, manifest/writer.py, `__main__.py`).

**Major components (v1.1 target state):**
1. `cli/main.py` — TUI orchestration and all commands (download/verify/list/auth); modified to add verify command, batch loop, and config pre-fill
2. `downloader/engine.py` — concurrent download orchestration with throttle and refresh hooks; modified to accept `TokenBucket | None` and `sharing_url` parameters
3. `auth/refresh.py` (NEW) — mid-download re-auth; called from the main thread after workers drain, never from inside a worker thread (Playwright GUI constraint)
4. `downloader/throttle.py` (NEW) — single shared token-bucket rate limiter; one instance per download run, passed to all workers via `on_chunk` callback
5. `manifest/verifier.py` (NEW) — pure local disk re-hash; no session, no network, no side effects; reads `manifest.json`, re-hashes each file, reports mismatches
6. `cli/config.py` (NEW) — load/save `~/.sharepoint-dl/config.json`; defaults layer only, never overrides explicit CLI flags

**Key architectural constraints from research:**
- Session refresh must run on the main thread, not inside a worker thread (Playwright opens a real browser window; calling from a non-main thread risks GUI issues on some platforms)
- Token bucket must be a single shared instance across all workers, not instantiated per worker (per-worker means effective bandwidth = `workers × limit`)
- Each batch job must have its own destination subdirectory, `state.json`, `manifest.json`, and log file (shared state.json causes collision and destroys forensic per-custodian evidence boundaries)
- Config file precedence is strictly: explicit CLI arg > config file > hardcoded default (config file is never mandatory; saves only on successful completion)
- No `StreamHandler` competing with Rich's terminal control (log output routes to file-only handler)

### Critical Pitfalls

1. **PyPI name `spdl` is taken by Meta's data loading library** — `pip install spdl` installs the wrong package. Use `sharepoint-dl` (matches existing GitHub slug). Verify at pypi.org before any packaging work. This is a hard blocker that must be resolved as the first task of Phase 1.

2. **Multiple workers trigger concurrent re-auth races** — when a session expires with 3-8 workers active, all workers detect 401 nearly simultaneously. Without a `threading.Lock` around the refresh operation, multiple Playwright browser windows open concurrently and may corrupt `session.json`. Use check-lock-check (double-checked locking): first thread to acquire the lock performs re-auth; subsequent threads re-check session validity before attempting another browser launch.

3. **Token bucket scope: per-worker multiplies bandwidth** — instantiating a `TokenBucket` inside the worker function gives each worker its own independent rate limit. With 4 workers each capped at 1 MB/s, actual throughput is 4 MB/s. The bucket must be a single shared instance created before the `ThreadPoolExecutor`, passed to all workers. Use `time.monotonic()` not `time.time()` for refill calculations.

4. **Throttle sleep inside the chunk loop breaks streaming** — sleeping inside `on_chunk` to enforce a rate limit stalls the active HTTP response; SharePoint's server-side read timeout fires and produces `ChunkedEncodingError`. Throttle at the pre-request level, or use a leaky bucket that absorbs burst without stalling the active stream.

5. **Playwright browsers not installed after `pip install`** — `playwright install chromium` is a required manual post-install step that `pip` cannot automate. Without a startup check that detects missing binaries and prints an actionable error, users see an opaque Playwright traceback. Add the check to `__main__.py` before publishing.

6. **Log file `StreamHandler` competing with Rich TUI** — adding `logging.StreamHandler(sys.stderr)` while Rich's live progress is active garbles the progress bar rendering. Route all audit output to a file-only `FileHandler`; let Rich own the terminal entirely.

7. **Batch state.json collision** — two batch jobs pointing to the same destination directory will collide in `state.json` and the second job may report all files as already complete. Each batch job must write to a distinct subdirectory of the user-specified destination.

## Implications for Roadmap

Based on the combined dependency analysis from ARCHITECTURE.md and the pitfall-to-phase mapping from PITFALLS.md, a three-phase structure is recommended. The build order follows the risk gradient: low-risk isolated changes first, new contained modules second, cross-cutting concurrency changes last.

### Phase 1: Zero-Risk Wins
**Rationale:** Four features that require no new modules, carry no regression risk to the existing download path, and can be shipped and verified independently. Resolving the PyPI name conflict must be the first task — it is a hard blocker for the publish feature and costs nothing to resolve early. Getting these four done first clears them from the risk register and delivers visible value immediately.
**Delivers:** ETA and download speed display in the progress bar; timestamped audit log written to `~/.sharepoint-dl/logs/`; `--root-folder` made optional in CLI `list` and `download` commands via auto-detect; PyPI package published as `sharepoint-dl` with post-install Playwright startup check
**Addresses:** ETA display (table stakes), log file (table stakes), auto-detect folder (table stakes), PyPI publish (distribution)
**Avoids:** Pitfall A (PyPI name — verify and claim `sharepoint-dl` before writing any packaging code); Pitfall G (Playwright post-install — add startup check before publishing); Pitfall K (log + Rich — file-only handler, no StreamHandler)
**Research flag:** None — all four features use documented stdlib and Rich patterns. ETA is a single-line change to `_make_progress()`. Log file is standard Python `logging.FileHandler`. Auto-detect is a redirect follow using existing `_resolve_sharing_link()`. PyPI publish follows the standard `pyproject.toml` + twine workflow.

### Phase 2: New Contained Modules
**Rationale:** Three features that each add one new module with clean, independently testable interfaces and no changes to the core download engine concurrency model. Medium complexity, contained blast radius.
**Delivers:** `~/.sharepoint-dl/config.json` saved on successful run and pre-filling TUI prompts; `--throttle <limit>` flag enforcing aggregate bandwidth across all workers; `spdl verify <dest_dir>` command re-hashing all downloaded files against `manifest.json`
**Addresses:** Config file (P2 quality-of-life), bandwidth throttling (P2 office/VPN), verify command (P1 forensic completeness)
**Avoids:** Pitfall E (shared token bucket, not per-worker); Pitfall F (throttle at pre-request level, not mid-stream sleep — test with 500 MB file at low limit); Pitfall J (config precedence strictly CLI > config > defaults; use `.get()` with defaults throughout; warn on unrecognised keys, don't crash)
**Research flag:** Throttle interaction with the existing Retry-After backoff needs empirical testing — download a large file at a low throttle limit (100 KB/s) with 3+ workers and confirm no `ChunkedEncodingError` and no measured bandwidth exceeding the limit. No external research needed.

### Phase 3: Cross-Module and Concurrency Features
**Rationale:** Two features that touch the TUI interaction loop (batch) and the auth-halt concurrency model (session refresh). These are the highest-complexity, highest-regression-risk changes in v1.1. Building them last ensures the download infrastructure is stable and that Phase 1 logging is in place to capture auth events for chain-of-custody before adding automated re-auth.
**Delivers:** Interactive "Add another folder?" TUI loop queuing multiple `(folder_path, dest_dir)` jobs sequentially with per-job summaries; `auth/refresh.py` automatically re-harvesting the session mid-download on 401, pausing the progress display cleanly, then resuming from the failed file
**Addresses:** Multi-folder batch (P1 — primary forensic use case), session refresh (P2 — highest-leverage reliability feature for long unattended runs)
**Avoids:** Pitfall B (concurrent reauth race — check-lock-check pattern, one browser window even with 4+ workers hitting 401 simultaneously); Pitfall C (session object mutation race — pause all workers, replace session, resume); Pitfall D (Playwright blocks progress — call `progress.stop()` before browser launch, restart with correct `completed` values after); Pitfall H (batch state collision — each job gets its own subdirectory); Pitfall I (batch partial failure — per-job result table printed at end, auth expiry halts and offers to resume from failed job)
**Research flag:** Session refresh requires testing against a real SharePoint session expiry — difficult to automate in CI and must be validated manually with an actual expiring guest session. Critically, the refresh path must be verified against an Entra B2B guest account (not just legacy OTP), since the July 2026 retirement deadline means OTP may not be available during testing on some tenants.

### Phase Ordering Rationale

- **Dependency chain enforces the order:** Auto-detect (Phase 1) makes the multi-folder batch UX clean and must precede batch (Phase 3). Log file (Phase 1) must precede session refresh (Phase 3) because auth events must be logged with timestamps for chain-of-custody. Config file (Phase 2) should precede batch (Phase 3) to allow pre-filling repeated URL entry in the batch loop.
- **Risk gradient drives sequencing within tiers:** Phase 1 has zero regression risk. Phase 2 adds new isolated modules. Phase 3 modifies the auth-halt flow and TUI loop — the most critical existing paths.
- **Pitfall resolution sequencing:** Resolving the PyPI name conflict (Pitfall A) as the first task of Phase 1 prevents wasted packaging work. The shared token bucket design (Pitfall E) and concurrency lock pattern (Pitfall B) must be explicitly designed before any code is written in Phases 2 and 3 respectively.
- **Forensic verify placement:** The verify command is technically low-cost but is placed in Phase 2 rather than Phase 1 because the four Phase 1 features are more urgent table-stakes gaps, and Phase 2 is still well before the v1.1 milestone ship date.

### Research Flags

Phases likely needing empirical validation during implementation (no additional external research needed):
- **Phase 2 (throttle):** Test a 500 MB file at 100 KB/s with 3 workers. Confirm measured bandwidth is approximately the configured limit, not `workers × limit`. Confirm no `ChunkedEncodingError`. Confirm throttle interacts correctly with the existing `Retry-After` backoff.
- **Phase 3 (session refresh):** Real SharePoint session expiry is hard to automate in CI. Requires manual validation with an actual expiring Entra B2B guest session (not just OTP). Confirm only one browser window opens with 4+ concurrent workers. Confirm progress display pauses and restarts cleanly with correct byte counts.

Phases with standard, well-documented patterns (research-phase not needed):
- **Phase 1:** ETA column is a one-line change; log file is standard Python `logging`; auto-detect follows existing `_resolve_sharing_link()` call; PyPI publish is standard `pyproject.toml` + twine.
- **Phase 2 (config, verify):** Config is a plain dataclass with `tomllib`/`tomli-w`; verify is a read-only SHA-256 re-hash with all infrastructure already in `manifest.json`.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | One new dep (`tomli-w`); all others validated in v1.0. Official PyPI, Python docs, and Rich source as sources. |
| Features | HIGH | Based on direct codebase inspection plus competitor feature analysis (wget, aria2c, yt-dlp). Priority split between P1 and P2 is clear and well-reasoned. |
| Architecture | HIGH | Based on direct inspection of `engine.py`, `main.py`, `session.py`, `job_state.py`, `manifest/writer.py`. All new module interfaces and modification points are precisely identified with integration patterns. |
| Pitfalls | HIGH (v1.1 implementation) / MEDIUM (auth layer behaviour) | v1.1 pitfalls grounded in codebase analysis and confirmed community concurrency patterns. Auth layer MEDIUM because Entra B2B guest session cookie names and lifetimes under the new flow are not yet empirically verified for this tool. |

**Overall confidence:** HIGH for implementation decisions. MEDIUM for auth-layer behaviour under Entra B2B migration.

### Gaps to Address

- **PyPI package name:** `spdl` is taken. `sharepoint-dl` is the recommended alternative and must be verified as unclaimed at pypi.org before Phase 1 begins. This is the only external dependency that could block Phase 1 delivery.
- **Entra B2B session refresh validation:** The Playwright session-harvest architecture is flow-agnostic by design, but the specific cookie names, session lifetime, and re-auth UX for Entra B2B guest accounts have not been verified empirically against a post-migration tenant. Validate in Phase 3 before shipping session refresh.
- **SharePoint read timeout under throttling:** The exact threshold at which SharePoint's server-side read timeout fires when chunk consumption is deliberately slowed is not documented. The Phase 2 throttle test (500 MB at 100 KB/s) will establish this empirically and inform whether a leaky-bucket or pre-request throttle approach is needed.

## Sources

### Primary (HIGH confidence)
- Python `tomllib` stdlib docs — read-only TOML, Python 3.11+ built-in
- `tomli-w` PyPI version 1.2.0 — write TOML, Python 3.9+, MIT license, by hukkin
- Rich `progress.py` source — confirms `TransferSpeedColumn`, `DownloadColumn`, `TimeRemainingColumn` available natively
- Python Packaging User Guide — `pyproject.toml` metadata, entry points, classifiers
- Playwright Python auth docs — `storageState()` API, session harvest pattern
- Microsoft Learn — SharePoint REST API folder/file operations
- Python `logging.FileHandler` stdlib docs
- Direct codebase inspection — `engine.py`, `main.py`, `auth/session.py`, `state/job_state.py`, `manifest/writer.py`
- PyPI `spdl` (Meta FAIR) — name conflict directly verified at pypi.org/project/spdl/

### Secondary (MEDIUM confidence)
- Steve Chen Blog + office365itpros.com — OTP retirement timeline, Entra B2B guest account replacement (community authors, corroborated by Microsoft notices)
- uv build + twine publish workflow — community-confirmed pattern
- OAuth token refresh race condition patterns — nango.dev and anthropics/claude-code GitHub issue; standard concurrency problem with established solutions
- Token bucket thread-safe implementation — oneuptime.com; standard algorithm confirmed by multiple independent sources
- Playwright post-install browser requirement — playwright.dev/python/docs/intro

### Tertiary (LOW confidence)
- httpx vs requests 2025 comparison — third-party blog; used only to confirm that requests is sufficient for sequential large-file downloads; conclusion is independently well-supported

---
*Research completed: 2026-03-30*
*Ready for roadmap: yes*
