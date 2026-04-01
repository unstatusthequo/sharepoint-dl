# SPDL -- SharePoint Bulk Downloader

Reliable bulk download tool for SharePoint shared folders. Built for forensic evidence collection but works for any SharePoint sharing link.

Authenticates via browser (OTP email codes or SSO login), lets you browse and select folders interactively, downloads all files with concurrent workers, and produces verification manifests (JSON + CSV) with SHA-256 hashes.

## Features

- **Interactive TUI** -- Just run it, paste a link, browse folders, download. No flags to memorize.
- **Browser-based auth** -- Playwright opens Chromium, you log in, session is cached for reuse
- **Both SharePoint link types** -- OTP sharing links (`/:f:/s/`) and authenticated SSO links (`/:f:/r/`)
- **Folder browser** -- Navigate the SharePoint folder tree interactively to pick your target
- **Folder layout choice** -- Keep source folder structure (recommended) or flat. Warns about filename collisions.
- **Streaming downloads** -- 8 MB chunks handle 2 GB+ files without memory issues
- **SHA-256 hashes** -- Computed during download (single I/O pass, no re-read)
- **Resume on re-run** -- Completed files are skipped, failed files auto-retried (2 extra rounds)
- **Forensic manifests** -- `manifest.json` + `manifest.csv` with per-file path, size, hash, and timestamp
- **Completeness report** -- Expected vs downloaded vs failed count after every run
- **Post-download verification** -- `verify` command re-hashes files on disk and compares to manifest
- **Concurrent downloads** -- 1-8 parallel workers (default 3) with per-file progress bars, ETA, and speed
- **Bandwidth throttle** -- Limit download speed (e.g. `5MB`) to avoid saturating the network
- **Batch mode** -- Queue multiple folders for download in one session without re-authenticating
- **Auto re-auth** -- If session expires mid-download, browser opens automatically to re-authenticate. Workers pause and resume.
- **Config persistence** -- Saves your preferences (URL, destination, workers, throttle) across sessions
- **Graceful cancel** -- Ctrl+C saves progress, re-run picks up where you left off
- **Audit log** -- Timestamped `download.log` with all events for forensic audit trail
- **Never silently skips** -- Every failure is tracked, reported, and retried
- **Self-healing launcher** -- `run.sh` auto-installs uv, repairs Playwright, handles everything
- **Cross-platform** -- macOS, Linux, Windows

## Quick Start

```bash
git clone git@github.com:unstatusthequo/sharepoint-dl.git
cd sharepoint-dl
./run.sh
```

That's it. `run.sh` handles everything: installs uv if missing, creates the virtual environment, installs dependencies, downloads Chromium for authentication, and launches the app.

### What happens

1. Paste the SharePoint sharing link
2. Browser opens for authentication (or reuses a cached session)
3. Browse folders and select which one to download
4. Choose download destination, worker count, and optional bandwidth limit
5. If multiple subfolders exist, choose "Keep source folders" (recommended) or "Flat"
6. Download runs with per-file progress bars showing speed, ETA, and elapsed time
7. After download: `manifest.json`, `manifest.csv`, `download.log`, and `state.json` in the destination folder
8. Downloaded files go into a timestamped subdirectory (e.g. `2026-03-31_143000/`)
9. Optionally verify downloaded files against their SHA-256 hashes
10. Queue another folder for batch download, or exit

```
  SPDL — SharePoint Bulk Downloader  v0.1
  @unstatusthequo · Ctrl+C cancel · Re-run to resume

  > Paste the SharePoint sharing link: https://company.sharepoint.com/...
    Session active — using saved credentials.

  > 02 SELECT TARGET FOLDER
    Shared root: /sites/Team/Shared Documents/General/Images

      1. Custodian A
      2. Custodian B
      3. Custodian C
      0. >> DOWNLOAD THIS FOLDER <<

    Navigate or select: 0
    Found 174 files (405.6 MiB total)

    Files span 12 folders.
    1. Keep source folders (recommended)
    2. Flat — all files in one folder
    File layout (1): 1

  >> Start download? [y/n] (y): y
  Overall              ━━━━━━━━━━━━━━━━━━━━━ 405.6/405.6 MiB 14.8 MB/s 0:00:00 28s 174/174 files

  Done! 174 files in 28.1s
  Verify downloaded files? [y/n] (n): y
    174/174 files verified OK

  Queue another folder? [y/n] (n): n
```

### Windows

> **Important:** All commands must be run from **PowerShell**, not Command Prompt (CMD).

```powershell
git clone https://github.com/unstatusthequo/sharepoint-dl.git
cd sharepoint-dl
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

## Output Files

After a download, the destination folder contains:

```
your-download-folder/
├── state.json          # Per-file tracking (status, hash). Used for resume
├── manifest.json       # Forensic manifest — machine-readable
├── manifest.csv        # Forensic manifest — human-readable (Excel/Sheets)
├── download.log        # Timestamped event log for audit trail
└── 2026-03-31_143000/  # Downloaded files (timestamped subdirectory)
    ├── document1.pdf
    ├── subfolder/
    │   └── report.xlsx
    └── ...
```

### manifest.csv

Opens directly in Excel or Google Sheets. Columns:

| filename | local_path | size_bytes | sha256 | status | error | downloaded_at |
|----------|------------|------------|--------|--------|-------|---------------|
| report.pdf | 2026-03-31/report.pdf | 445013 | a1b2c3... | COMPLETE | | 2026-03-31T... |
| broken.zip | | 0 | | FAILED | Size mismatch | |

Full SHA-256 hashes (not truncated) for forensic chain-of-custody documentation.

## CLI Mode (Advanced)

All commands are also available as direct CLI flags for scripting or automation.

### `auth` -- Authenticate

```bash
./run.sh auth '<sharepoint-sharing-url>'
```

### `list` -- Enumerate Files

```bash
./run.sh list '<url>'
```

### `download` -- Download Files

```bash
./run.sh download '<url>' /path/to/dest
```

| Option | Description |
|--------|-------------|
| `-r, --root-folder` | Server-relative path (auto-detected if omitted) |
| `-w, --workers N` | Concurrent download workers, 1-8 (default: 3) |
| `-y, --yes` | Skip confirmation prompt |
| `--flat` | All files directly in dest folder (no subdirectories) |
| `--throttle RATE` | Bandwidth limit (e.g. `5MB`, `500KB`) |
| `--no-manifest` | Skip manifest generation |

### `verify` -- Verify Downloaded Files

```bash
./run.sh verify /path/to/download-folder
```

Re-reads every file from disk, recomputes SHA-256, and compares against `manifest.json`. Reports per-file PASS/FAIL. Exits with code 1 on any mismatch.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Run `rm -rf .venv && ./run.sh` (auto-rebuilds) |
| `No active session` | Run auth again, or use interactive mode (handles it automatically) |
| `Session expired` | Re-run -- auto re-auth opens browser if session expires mid-download |
| Browser closes before login | Complete the full login flow (email + OTP code, or SSO) |
| Playwright driver error | `run.sh` auto-repairs this. Or: `rm -rf .venv && ./run.sh` |
| `Ctrl+C` during download | Progress is saved. Re-run to resume |

## Requirements

- [uv](https://docs.astral.sh/uv/) (installed automatically by `run.sh`)
- Python 3.11-3.13 (installed automatically by uv if needed)
- Chromium (installed automatically by Playwright)
- Access to a SharePoint site via sharing link

## License

MIT
