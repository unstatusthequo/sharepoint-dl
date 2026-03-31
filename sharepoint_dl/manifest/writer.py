"""Manifest writer for forensic-grade JSON download manifests.

Reads completed download state from JobState and produces a standalone
JSON manifest with per-file metadata (including SHA-256 hashes from the
download stream) and top-level summary information. Also produces a
manifest.csv for Excel-openable forensic review.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from sharepoint_dl.state.job_state import FileStatus, JobState, entry_local_relative_path

TOOL_VERSION = "sharepoint-dl v1.0"


def generate_manifest(
    state: JobState,
    dest_dir: Path,
    source_url: str,
    root_folder: str,
    *,
    flat: bool = False,
) -> Path:
    """Generate a forensic manifest JSON file from download state.

    Reads all entries from JobState, partitions them by status, and writes
    a manifest.json to dest_dir. SHA-256 hashes come from state (computed
    during download), not from re-reading files on disk.

    Args:
        state: The JobState containing all tracked file entries.
        dest_dir: Directory where manifest.json will be written.
        source_url: Original SharePoint sharing URL.
        root_folder: Name of the root folder that was downloaded.

    Returns:
        Path to the written manifest.json file.
    """
    entries = state.all_entries()

    # Partition by status
    complete = []
    failed = []
    for url, entry in entries.items():
        status = entry["status"]
        if status == FileStatus.COMPLETE:
            complete.append((url, entry))
        elif status == FileStatus.FAILED:
            failed.append((url, entry))

    # Build files list (complete only), sorted by server_relative_url
    files_list = sorted(
        [
            {
                "name": entry["name"],
                "server_relative_url": url,
                "local_path": entry.get("local_path") or entry_local_relative_path(entry, flat=flat),
                "size_bytes": entry["size_bytes"],
                "sha256": entry["sha256"],
                "downloaded_at": entry["downloaded_at"],
            }
            for url, entry in complete
        ],
        key=lambda f: f["server_relative_url"],
    )

    # Build failed list, sorted by server_relative_url
    failed_list = sorted(
        [
            {
                "name": entry["name"],
                "server_relative_url": url,
                "error": entry.get("error", "unknown"),
            }
            for url, entry in failed
        ],
        key=lambda f: f["server_relative_url"],
    )

    # Build manifest
    manifest = {
        "metadata": {
            "source_url": source_url,
            "root_folder": root_folder,
            "total_files": len(files_list),
            "total_size_bytes": sum(f["size_bytes"] for f in files_list),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tool_version": TOOL_VERSION,
        },
        "files": files_list,
        "failed": failed_list,
    }

    # Atomic write: .tmp then rename (JSON)
    manifest_path = dest_dir / "manifest.json"
    tmp_path = manifest_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(manifest, indent=2))
    tmp_path.replace(manifest_path)

    # Write manifest.csv alongside manifest.json (atomic .tmp + rename)
    _write_manifest_csv(dest_dir, files_list, failed_list)

    return manifest_path


_CSV_COLUMNS = ["filename", "local_path", "size_bytes", "sha256", "status", "error", "downloaded_at"]


def _write_manifest_csv(
    dest_dir: Path,
    files_list: list[dict],
    failed_list: list[dict],
) -> None:
    """Write manifest.csv atomically to dest_dir.

    Combines complete files (files_list) and failed files (failed_list),
    sorted by server_relative_url. Uses csv.writer with QUOTE_MINIMAL so
    commas and quotes in filenames are safely escaped.

    Args:
        dest_dir: Directory where manifest.csv will be written.
        files_list: List of complete file dicts (from generate_manifest).
        failed_list: List of failed file dicts (from generate_manifest).
    """
    # Build combined rows sorted by server_relative_url
    rows: list[dict] = []

    for f in files_list:
        rows.append({
            "filename": f["name"],
            "local_path": f.get("local_path", ""),
            "size_bytes": str(f["size_bytes"]),
            "sha256": f.get("sha256", ""),
            "status": "COMPLETE",
            "error": "",
            "downloaded_at": f.get("downloaded_at", ""),
            "_sort_key": f["server_relative_url"],
        })

    for f in failed_list:
        rows.append({
            "filename": f["name"],
            "local_path": "",
            "size_bytes": "0",
            "sha256": "",
            "status": "FAILED",
            "error": f.get("error", ""),
            "downloaded_at": "",
            "_sort_key": f["server_relative_url"],
        })

    rows.sort(key=lambda r: r["_sort_key"])

    csv_path = dest_dir / "manifest.csv"
    tmp_csv = csv_path.with_suffix(".csv.tmp")

    with tmp_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    tmp_csv.replace(csv_path)
