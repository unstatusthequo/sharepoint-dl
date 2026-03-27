"""Manifest writer for forensic-grade JSON download manifests.

Reads completed download state from JobState and produces a standalone
JSON manifest with per-file metadata (including SHA-256 hashes from the
download stream) and top-level summary information.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sharepoint_dl.state.job_state import FileStatus, JobState

TOOL_VERSION = "sharepoint-dl v1.0"


def generate_manifest(
    state: JobState,
    dest_dir: Path,
    source_url: str,
    root_folder: str,
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
                "local_path": entry["folder_path"] + "/" + entry["name"],
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

    # Atomic write: .tmp then rename
    manifest_path = dest_dir / "manifest.json"
    tmp_path = manifest_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(manifest, indent=2))
    tmp_path.replace(manifest_path)

    return manifest_path
