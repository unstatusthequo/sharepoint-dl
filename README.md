# SPDL -- SharePoint Bulk Downloader

Reliable bulk download tool for SharePoint shared folders. Built for forensic evidence collection but works for any SharePoint external sharing link.

Authenticates via browser (email + OTP code), lets you browse and select folders interactively, downloads all files with concurrent workers, and produces a verification manifest with SHA-256 hashes.

## Features

- **Interactive TUI** -- Just run it, paste a link, browse folders, download. No flags to memorize.
- **Browser-based auth** -- Playwright opens Chromium, you log in, session is cached for reuse
- **Folder browser** -- Navigate the SharePoint folder tree interactively to pick your target
- **Streaming downloads** -- 8 MB chunks handle 2 GB+ files without memory issues
- **SHA-256 hashes** -- Computed during download (single I/O pass, no re-read)
- **Resume on re-run** -- Completed files are skipped, failed files auto-retried (2 extra rounds)
- **Forensic manifest** -- `manifest.json` with per-file path, size, hash, and timestamp
- **Completeness report** -- Expected vs downloaded vs failed count after every run
- **Concurrent downloads** -- 1-8 parallel workers (default 3) with per-file progress bars
- **Graceful cancel** -- Ctrl+C saves progress, re-run picks up where you left off
- **Never silently skips** -- Every failure is tracked, reported, and retried
- **Cross-platform** -- macOS, Linux, Windows

## Installation

Requires [uv](https://docs.astral.sh/uv/) (installed automatically by setup scripts) and Python 3.11-3.13.

### macOS / Linux

```bash
git clone git@github.com:unstatusthequo/sharepoint-dl.git
cd sharepoint-dl
./setup.sh
```

### Windows

> **Important:** All commands must be run from **PowerShell**, not Command Prompt (CMD). Right-click the Start menu and select "Windows PowerShell" or "Terminal".

```powershell
git clone https://github.com/unstatusthequo/sharepoint-dl.git
cd sharepoint-dl
powershell -ExecutionPolicy Bypass -File setup.ps1
```

To run after setup:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

### Manual Installation

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh   # macOS/Linux
# or: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

git clone git@github.com:unstatusthequo/sharepoint-dl.git
cd sharepoint-dl
uv lock && uv sync
uv run playwright install chromium
```

## Quick Start (Interactive Mode)

The easiest way to use SPDL -- just launch it and follow the prompts:

```bash
./run.sh                                              # macOS/Linux
powershell -ExecutionPolicy Bypass -File .\run.ps1    # Windows (from PowerShell)
```

The interactive mode will:

1. Ask you to paste the SharePoint sharing link
2. Open a browser for authentication (or reuse a cached session)
3. Let you browse folders and select which one to download
4. Ask where to save the files and how many parallel workers to use
5. Download everything flat into one folder with progress bars
6. Generate `manifest.json` with SHA-256 hashes for every file

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

    Navigate or select: 1

    Found 165 files (237.1 GB total)

  > 04 CONFIGURATION
    Download destination [~/Downloads/sharepoint-dl]: /evidence/custodian-a
    Parallel workers (1-8) [3]: 3

  Start download? [Y/n]: y
```

## CLI Mode (Advanced)

All commands are also available as direct CLI flags for scripting or automation.

### `auth` -- Authenticate

```bash
./run.sh auth '<sharepoint-sharing-url>'
```

Opens Chromium, you complete the login, session is saved to `~/.sharepoint-dl/session.json`. Reused automatically on future runs until it expires.

### `list` -- Enumerate Files

```bash
./run.sh list '<url>' -r '/sites/Team/Shared Documents/Folder'
```

| Option | Description |
|--------|-------------|
| `-r, --root-folder` | **(Required)** Server-relative path to the folder to enumerate |

### `download` -- Download Files

```bash
./run.sh download '<url>' /path/to/dest -r '/sites/Team/Shared Documents/Folder'
```

| Option | Description |
|--------|-------------|
| `-r, --root-folder` | **(Required)** Server-relative path to the folder to download |
| `-w, --workers N` | Concurrent download workers, 1-8 (default: 3) |
| `-y, --yes` | Skip confirmation prompt |
| `--flat` | All files directly in dest folder (no subdirectories) |
| `--no-manifest` | Skip manifest.json generation |

#### CLI Examples

```bash
# Download flat with 5 workers, skip confirmation
./run.sh download '<url>' ./evidence \
  -r '/sites/Team/Shared Documents/Images/Custodian/LAPTOP-ABC' \
  --flat -w 5 -y

# Resume an interrupted download (just re-run the same command)
./run.sh download '<url>' ./evidence \
  -r '/sites/Team/Shared Documents/Images/Custodian/LAPTOP-ABC' \
  --flat
# Completed files are skipped automatically
```

> **Windows:** Run all commands from **PowerShell** (not CMD). Use `powershell -ExecutionPolicy Bypass -File .\run.ps1` instead of `./run.sh`, and double quotes `"` instead of single quotes `'`.

## Finding the Root Folder Path (CLI Mode)

The `-r` flag requires the server-relative path. To find it:

1. Open the SharePoint sharing link in your browser
2. Navigate to the target folder
3. Look at the browser URL for the `id=` parameter
4. URL-decode it (`%2F` = `/`, `%20` = space)

Example URL:
```
...?id=%2Fsites%2FTeam%2FShared%20Documents%2FImages%2FCustodian
```

Root folder path:
```
/sites/Team/Shared Documents/Images/Custodian
```

> **Tip:** In interactive mode you don't need this -- just browse and select.

## Output Files

After a download, the destination folder contains:

| File | Description |
|------|-------------|
| Your downloaded files | All files from the SharePoint folder |
| `state.json` | Per-file tracking (status, hash). Used for resume on re-run |
| `manifest.json` | Forensic manifest -- proof of completeness |

### manifest.json

The manifest contains:

- **Per file:** filename, remote path, local path, size in bytes, SHA-256 hash, download timestamp
- **Metadata:** source URL, root folder, total file count, total size, generation timestamp, tool version

SHA-256 hashes are computed during the download stream -- files are never re-read from disk.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Run `rm -rf .venv && uv lock && uv sync` |
| `No active session` | Run auth again, or use interactive mode (handles it automatically) |
| `Session expired` | Re-run -- interactive mode re-authenticates automatically |
| Browser closes before login completes | Make sure you complete the full login flow (email + OTP code) |
| Size mismatch errors | Fixed in latest version. Re-run to retry failed files automatically |
| `Ctrl+C` during download | Progress is saved. Re-run to resume |
| Python 3.14 errors | Use Python 3.11-3.13. Setup scripts handle this automatically |

## Requirements

- [uv](https://docs.astral.sh/uv/) (installed automatically by setup scripts)
- Python 3.11-3.13 (installed automatically by uv if needed)
- Chromium (installed automatically by Playwright)
- Access to a SharePoint site via external sharing link

## License

MIT
