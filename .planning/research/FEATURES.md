# Feature Research

**Domain:** CLI bulk download tool — forensic evidence collection from SharePoint
**Researched:** 2026-03-30 (v1.1 update; original v1.0 research 2026-03-27)
**Confidence:** HIGH

---

## v1.1 Feature Analysis

This section covers the 9 features being added in v1.1. v1.0 features (recursive traversal,
streaming downloads, SHA-256 manifest, resume, TUI, etc.) are validated — see the v1.0 section
below. The question this research answers: how do these 9 features rank by user expectation,
value, and build complexity?

### Table Stakes (Users Expect These in v1.1)

Features that power users of bulk download tools assume exist. Missing them makes the tool feel
unfinished compared to standard alternatives like wget, aria2c, or yt-dlp.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Download speed & ETA display | wget, curl, aria2 all show this. Users running 200+ GB downloads need to plan around it. A progress bar without ETA feels broken for long-running jobs. | LOW | Rich's `TimeRemainingColumn` and `TransferSpeedColumn` handle this natively. Wire into the existing `rich.Progress` instance in `engine.py`. Rolling average over last N chunks is more stable than instantaneous speed. |
| Timestamped log file | Any tool that touches forensic evidence is expected to produce a durable audit trail. Also essential for debugging failures that scroll off the terminal. | LOW | Python `logging` with `FileHandler` writing to `download.log` in the destination directory alongside `state.json`. Additive — no existing behavior changes. |
| Auto-detect folder from sharing link | The `-r` flag forces users to manually decode a URL parameter. This is the main friction point in CLI mode. Interactive mode already resolves the sharing link; CLI mode just doesn't. | LOW | Follow redirect in `cli/main.py`, extract `id=` from final URL. One function, no architecture change. Make `-r` optional — auto-detect when possible, fallback to `-r` when not. |
| Post-download verify command | SHA-256 hashes are computed at download time but there is no way to prove files on disk right now match what was originally downloaded. For forensic chain-of-custody, this is not optional. | LOW | `verify` Typer subcommand reads `manifest.json`, re-hashes each file, reports mismatches. All data is already in `manifest.json`. Pure consumer of existing infrastructure — no changes to how hashes are stored. |

### Differentiators (Competitive Advantage)

Features that go beyond what generic download tools provide and reinforce the forensic /
reliability identity of this tool.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Smart session refresh mid-download | No other SharePoint download tool handles mid-run token expiry gracefully. Multi-hour downloads (200+ GB) will hit session expiry. Without this, users must babysit and restart. With it, downloads run unattended to completion. | HIGH | Pause worker pool, reopen Playwright, harvest new cookies, inject into live `requests.Session`, resume workers. Thread-safety between the worker pool and auth layer is the hard part. Depends on existing `AuthExpiredError`, `JobState` resume logic, and `engine.py` concurrency model. |
| Multi-folder batch download | Forensic collections routinely cover multiple custodians. Queuing all folders in one session — one auth, one run — eliminates repeated TUI navigation and reduces total elapsed time significantly. | MEDIUM | Interactive-mode change: after folder selection, offer "Add another folder?" before starting downloads. Queue of `(folder_path, dest)` tuples processed sequentially. Each folder gets its own `state.json` and `manifest.json`. No changes to the download engine. |
| Config file for saved settings | Repeat users (forensic investigators who use the tool weekly) re-enter the same URL, destination, and worker count every session. A config removes friction without changing the interaction model for first-time users. | LOW | `~/.sharepoint-dl/config.json` using stdlib `json`. Pre-fill TUI prompts and CLI defaults. Tool must work without the file — config is entirely optional. The `~/.sharepoint-dl/` path already exists for `session.json`. |
| Bandwidth throttling | Corporate and VPN networks are shared. Saturating the link during a multi-hour download creates conflict with IT and other users. A `--throttle` flag makes the tool office-safe. | MEDIUM | Token-bucket or sleep-between-chunks in `engine.py`. Must coordinate across concurrent workers — total bandwidth is the constraint, not per-worker. Adds complexity to the download hot path. |
| Publish to PyPI as `spdl` | `pip install spdl` vs cloning a repo and running setup scripts is the difference between a tool and a project. Makes the tool accessible to non-developers and enables distribution outside the immediate team. | MEDIUM | `pyproject.toml` classifiers, license metadata, GitHub Actions for publishing via twine or trusted publishers. Main complexity: `playwright install chromium` must still run manually after install and must be clearly documented in the package README and `spdl --help`. Verify the `spdl` name is unclaimed on PyPI before starting. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Parallel batch execution (folders simultaneously) | Faster completion for multi-custodian collections | Multiplies concurrent HTTP load on SharePoint; more likely to trigger rate limiting. Also multiplies auth complexity — one session expiry now blocks multiple concurrent folder downloads. | Sequential batch execution: one folder at a time, one auth session. Simpler, predictable, rate-limit safe. |
| Per-worker bandwidth cap | Fine-grained throttle control | Users think in total bandwidth, not per-worker. A per-worker cap interacts badly with worker count changes. Creates false precision and confusing math. | Total bandwidth cap via shared token bucket across all workers. This is what `--throttle 50MB/s` should mean. |
| Silent auto re-auth without user confirmation | Seamless recovery from session expiry | Re-auth without user visibility can silently extend a session past what the user intended to authorize. For forensic chain-of-custody, the user should confirm the re-auth event happened at a known time. | Smart session refresh must pause and show the user what is happening (browser is reopening), then resume. Log the auth event with a timestamp. |
| Incremental sync mode | "Only download new files" for ongoing collection | SharePoint REST does not expose a reliable last-modified-since delta for external guest sessions. Implementing this correctly requires version tracking — significant complexity for an edge case. | Resume logic already handles interrupted downloads. Full re-enumeration with skip-if-exists covers the "re-run on same folder" adequately. |

---

## Feature Dependencies

```
[Auto-detect folder from sharing link]
    └──enables──> [Multi-folder batch download]
        (batch UX is cleaner when URL entry is frictionless)

[Timestamped log file]
    └──enhances──> [Smart session refresh]
        (auth events must be logged with timestamps for chain-of-custody)
    └──enhances──> [Post-download verify command]
        (verify results should be logged with timestamps)

[Post-download verify command]
    └──requires──> [SHA-256 manifest]  [EXISTS in v1.0]

[Smart session refresh]
    └──requires──> [AuthExpiredError exception flow]  [EXISTS in v1.0]
    └──requires──> [JobState resume logic]  [EXISTS in v1.0]
    └──requires──> [Playwright auth browser]  [EXISTS in v1.0]

[Bandwidth throttling]
    └──requires──> [Streaming chunk download loop]  [EXISTS in v1.0]
    └──conflicts-by-design──> [Maximum download speed]

[Config file]
    └──uses-location──> [~/.sharepoint-dl/ directory]  [EXISTS in v1.0 for session.json]

[ETA display]
    └──requires──> [Rich Progress integration]  [EXISTS in v1.0]

[PyPI publish]
    └──requires──> [Post-install docs: playwright install chromium]  (new documentation obligation)
    └──independent of──> [all other v1.1 features]
```

### Dependency Notes

- **Post-download verify is a pure consumer of v1.0 infrastructure.** No changes to hash computation or manifest format. Lowest-risk feature in the set.
- **Smart session refresh is the only feature with cross-cutting thread-state concerns.** Coordinate with the worker pool model in `engine.py`. Build this after ETA display and log file (simpler, lower-risk) so the downloader infrastructure is stable before adding thread-coordination complexity.
- **Auto-detect and multi-folder are naturally sequenced.** Auto-detect removes the friction of URL entry, which makes the multi-folder "add another" flow feel polished. Implement auto-detect first.
- **Config file and session.json share a directory.** Extending `~/.sharepoint-dl/` is straightforward given the existing pattern.
- **PyPI publish is packaging-only.** It is orthogonal to all other v1.1 features and can be done in any order. The main risk is the post-install Playwright step — document it prominently.

---

## MVP Definition for v1.1

### Ship First (P1 — High Value, Low-Medium Cost)

- [ ] **ETA display** — Effectively free with Rich; absence is conspicuous for multi-hour runs
- [ ] **Timestamped log file** — Forensic identity requires it; additive, no regression risk
- [ ] **Auto-detect folder from sharing link** — Removes the single biggest friction point in CLI mode
- [ ] **Post-download verify command** — Completes the forensic story; all data already exists in `manifest.json`
- [ ] **Multi-folder batch download** — High value for primary use case (multi-custodian forensic collections)
- [ ] **PyPI publish** — Unlocks distribution; complexity is packaging, not application logic

### Ship If Estimates Hold (P2 — Medium-High Value, Medium-High Cost)

- [ ] **Smart session refresh** — Highly valuable but highest implementation complexity in v1.1; requires solid test coverage of worker pool coordination before shipping
- [ ] **Bandwidth throttling** — Genuinely needed for office/VPN use; moderate complexity in the download hot path
- [ ] **Config file** — Good quality-of-life for repeat users; lower urgency than reliability features

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| ETA display | HIGH | LOW | P1 |
| Timestamped log file | HIGH | LOW | P1 |
| Auto-detect folder from sharing link | HIGH | LOW | P1 |
| Post-download verify command | HIGH | LOW | P1 |
| Multi-folder batch download | HIGH | MEDIUM | P1 |
| PyPI publish | HIGH | MEDIUM | P1 |
| Smart session refresh | HIGH | HIGH | P2 |
| Bandwidth throttling | MEDIUM | MEDIUM | P2 |
| Config file for saved settings | MEDIUM | LOW | P2 |

**Priority key:**
- P1: Ship in v1.1 core phases
- P2: Ship in v1.1 if time holds; defer to v1.2 if they don't

---

## Competitor Feature Analysis

Tools like wget, aria2c, and yt-dlp establish baseline expectations for bulk CLI downloaders.

| Feature | wget / curl | aria2c | yt-dlp | SPDL v1.0 | SPDL v1.1 target |
|---------|-------------|--------|--------|-----------|------------------|
| Speed + ETA display | Yes | Yes | Yes | No | Yes |
| Log file with timestamps | Yes (`--output-file`) | Yes | Yes | No | Yes |
| Config file | Yes (`.wgetrc`) | Yes (`aria2.conf`) | Yes (`~/.config/yt-dlp/config`) | No | Yes |
| Bandwidth throttle | Yes (`--limit-rate`) | Yes (`--max-download-limit`) | Yes (`--limit-rate`) | No | Yes |
| Resume interrupted | Yes | Yes | Yes | Yes | Yes (existing) |
| Batch / queue | Yes (input file) | Yes | Yes (playlist) | No | Yes (multi-folder) |
| Post-download hash verify | No (separate tool) | No | No | No | Yes |
| Forensic manifest (JSON, per-file) | No | No | No | Yes | Yes (existing) |
| SharePoint guest auth | No | No | No | Yes | Yes (existing) |
| Session refresh mid-run | N/A | N/A | N/A | No | Yes |

SPDL's differentiation is the combination of forensic manifest + live verify + SharePoint-aware
session auth. ETA, logging, config, and throttling are catch-up items to reach parity with
generic download tools — they are expected, not differentiating.

---

## v1.0 Feature Research (Retained for Reference)

*Original research 2026-03-27. v1.0 features are validated and shipped.*

### Table Stakes (v1.0)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Recursive folder traversal | Any bulk downloader must walk the tree | LOW | SharePoint REST API with `$skiptoken` pagination |
| Preserve folder structure locally | Users expect local layout to mirror remote | LOW | Create directory tree from folder path segments |
| User-specified download destination | Hardcoded paths are never acceptable | LOW | CLI argument or interactive prompt |
| Progress indication | Large downloads need feedback | LOW | Per-file and overall; Rich progress bars |
| Error reporting per file | Silent skip is the original failure mode | LOW | Surface every error; never swallow exceptions |
| Resume / skip completed files | Re-downloading everything after interruption is a non-starter | MEDIUM | Check file existence + size match before downloading |
| Handle large files (2GB+) | EnCase `.E01`/`.L01` files are routinely 1-2GB | MEDIUM | Stream in chunks; avoid full in-memory buffering |
| Authentication via existing session | No admin credentials or app registration available | HIGH | Playwright session cookie extraction |

### Differentiators (v1.0)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Verification manifest (filename, size, SHA-256) | Forensic use requires provable completeness | MEDIUM | JSON manifest; remote size AND local post-download hash |
| Expected vs. actual count report | Immediately shows missing files without manual auditing | LOW | Count before; compare at end |
| Configurable concurrency with back-off | SharePoint throttles aggressively; blind parallel downloads cause 429s | MEDIUM | Semaphore-bounded; exponential back-off with `Retry-After` |
| Dry-run / list-only mode | Scope a collection before committing to a long download | LOW | Walk tree, print list, exit without downloading |

### Anti-Features (v1.0)

| Feature | Why Avoid | Alternative |
|---------|-----------|-------------|
| Incremental sync | Forensic requires discrete timestamped captures, not living sync | One-time full download with dated output directory |
| GUI | Heavyweight, irrelevant to forensic CLI workflow | Clean CLI output with structured logs |
| Upload capability | Out of scope; risks accidentally modifying evidence | Explicitly rejected |
| Parallel chunked byte-range splitting | SharePoint guest sessions do not reliably support multi-range | Single-connection streaming with retry |
| File filtering | Forensic collection must be complete; filters create accidental exclusions | Download everything; filter locally after verification |

---

## Sources

- [yt-dlp GitHub repository](https://github.com/yt-dlp/yt-dlp) — config file location, batch mode patterns, speed/ETA display
- [aria2c download manager](https://nixsanctuary.com/how-to-manage-and-speed-up-your-large-file-downloads-with-aria2/) — bandwidth throttling, multi-connection patterns
- [playwright PyPI](https://pypi.org/project/playwright/) — post-install browser setup requirement (must run `playwright install chromium` separately)
- Rich Progress documentation — `TimeRemainingColumn`, `TransferSpeedColumn` available natively (HIGH confidence, verified against existing `engine.py` usage)
- [surge download manager](https://www.freshports.org/www/surge/) — TUI download tool feature set baseline
- Existing codebase: `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STACK.md`
- All 9 v1.1 todo files in `.planning/todos/pending/`

---

*Feature research for: SharePoint Bulk Downloader (SPDL) — v1.0 original + v1.1 update*
*Last updated: 2026-03-30*
