# SharePoint Bulk Downloader

Reliable bulk download tool for SharePoint shared folders, designed for forensic evidence collection. Authenticates via browser session (email + OTP code), downloads all files with concurrent workers, and produces a verification manifest with SHA-256 hashes to prove completeness.

## Features

- **Browser-based auth** -- Playwright opens Chromium, you log in, cookies are captured automatically
- **Recursive enumeration** -- Walks all folders/subfolders with full pagination (no silent truncation)
- **Streaming downloads** -- 8 MB chunks handle 2 GB+ files without memory issues
- **SHA-256 hashes** -- Computed during download (single I/O pass, no re-read)
- **Resume on re-run** -- Completed files are skipped, only failures retried
- **Forensic manifest** -- JSON file with per-file path, size, hash, and timestamp
- **Completeness report** -- Expected vs downloaded vs failed count
- **Concurrent downloads** -- 1-8 parallel workers (default 3)
- **Never silently skips** -- Every failure is tracked and reported

## Installation

### macOS / Linux

```bash
git clone git@github.com:unstatusthequo/sharepoint-dl.git
cd sharepoint-dl
./setup.sh
source .venv/bin/activate
```

### Windows (PowerShell)

```powershell
git clone git@github.com:unstatusthequo/sharepoint-dl.git
cd sharepoint-dl
powershell -ExecutionPolicy Bypass -File setup.ps1
.venv\Scripts\Activate.ps1
```

### Manual Installation

Requires Python 3.11-3.13 (not 3.14).

```bash
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\Activate.ps1     # Windows

pip install -e .
playwright install chromium
```

## Quick Start

```bash
# 1. Authenticate (browser opens, complete login)
sharepoint-dl auth '<sharepoint-sharing-url>'

# 2. List files to see what's there
sharepoint-dl list '<url>' -r '/sites/SiteName/Shared Documents/Path/To/Folder'

# 3. Download everything
sharepoint-dl download '<url>' /path/to/dest -r '/sites/SiteName/Shared Documents/Path/To/Folder'
```

> **Windows note:** Use double quotes `"` instead of single quotes `'` for URLs.

## Commands

### `auth` -- Authenticate

Opens a Chromium browser to the SharePoint URL. Complete the login (email + OTP code), and the session cookies are saved automatically. The browser closes when auth is detected.

```bash
sharepoint-dl auth '<sharepoint-url>'
```

Session is saved to `~/.sharepoint-dl/session.json` and reused across runs until it expires.

### `list` -- Enumerate Files

Lists all files in a SharePoint folder without downloading. Shows per-folder breakdown with file counts and sizes.

```bash
sharepoint-dl list '<url>' -r '/sites/SiteName/Shared Documents/Folder'
```

| Option | Description |
|--------|-------------|
| `-r, --root-folder` | **(Required)** Server-relative path to the folder to enumerate |

Example output:

```
                     Enumeration Results
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┓
┃ Folder                              ┃ Files ┃     Size ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━┩
│ /sites/.../LAPTOP-5V7K1CJ4          │   165 │ 237.1 GB │
└─────────────────────────────────────┴───────┴──────────┘

Found 165 files (237.1 GB total) across 1 folders
```

### `download` -- Download Files

Downloads all files from a SharePoint folder with progress bars, resume capability, and manifest generation.

```bash
sharepoint-dl download '<url>' /path/to/destination -r '/sites/SiteName/Shared Documents/Folder'
```

| Option | Description |
|--------|-------------|
| `-r, --root-folder` | **(Required)** Server-relative path to the folder to download |
| `-w, --workers N` | Number of concurrent download workers, 1-8 (default: 3) |
| `-y, --yes` | Skip confirmation prompt |
| `--flat` | Download all files directly into dest folder (no subdirectories) |
| `--no-manifest` | Skip manifest.json generation |

#### Examples

**Download with default settings (asks for confirmation):**

```bash
sharepoint-dl download '<url>' ./evidence -r '/sites/Team/Shared Documents/Images/Custodian1/LAPTOP-ABC'
```

**Download flat (no nested folders) with 5 workers, skip confirmation:**

```bash
sharepoint-dl download '<url>' ./evidence -r '/sites/Team/Shared Documents/Images/Custodian1/LAPTOP-ABC' --flat -w 5 -y
```

**Resume an interrupted download (just re-run the same command):**

```bash
# Ctrl+C during download, then re-run:
sharepoint-dl download '<url>' ./evidence -r '/sites/Team/Shared Documents/Images/Custodian1/LAPTOP-ABC' --flat
# Completed files are skipped automatically
```

## Output Files

After a download completes, the destination folder contains:

| File | Description |
|------|-------------|
| `*.E01, *.L01, ...` | Downloaded evidence files |
| `state.json` | Internal tracking file (per-file status, used for resume) |
| `manifest.json` | Forensic manifest with SHA-256 hashes for every file |

### manifest.json

The manifest is the forensic deliverable. It contains:

- **Per file:** filename, remote path, local path, size in bytes, SHA-256 hash, download timestamp
- **Metadata:** source URL, root folder, total file count, total size, generation timestamp, tool version

SHA-256 hashes are computed during the download stream -- files are never re-read from disk.

## Finding the Root Folder Path

The `--root-folder` (`-r`) flag requires the server-relative path to the SharePoint folder. To find it:

1. Open the SharePoint sharing link in your browser
2. Navigate to the folder you want to download
3. Look at the browser URL -- it contains an `id=` parameter with the path
4. URL-decode it (replace `%2F` with `/`, `%20` with spaces)

Example: if the browser shows:

```
...?id=%2Fsites%2FTeam%2FShared%20Documents%2FImages%2FCustodian
```

The root folder path is:

```
/sites/Team/Shared Documents/Images/Custodian
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `No active session` | Run `sharepoint-dl auth '<url>'` first |
| `Session expired` | Re-run `sharepoint-dl auth '<url>'` |
| Browser closes before login completes | Auth waits for the `FedAuth` cookie -- make sure you complete the full login flow |
| `Cannot determine folder path` | Use `-r` to specify the server-relative path (see section above) |
| Files silently missing | This tool fixes that -- pagination is handled correctly. Compare `list` count to browser count |
| Python 3.14 errors | Use Python 3.11-3.13. The `setup.sh`/`setup.ps1` scripts handle this |

## Requirements

- Python 3.11-3.13
- Chromium (installed automatically by Playwright)
- Access to the SharePoint site via sharing link (email + OTP code)
