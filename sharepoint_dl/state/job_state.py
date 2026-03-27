"""Thread-safe job state with atomic persistence for download resume."""

from __future__ import annotations

import json
import threading
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sharepoint_dl.enumerator.traversal import FileEntry


class FileStatus(str, Enum):
    """Lifecycle status for a tracked file."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    FAILED = "failed"


class JobState:
    """Thread-safe job state persisted as state.json in destination directory.

    State is keyed by server_relative_url. Writes use an atomic temp-rename
    pattern so state.json always contains a complete, valid JSON document
    (even if the process crashes mid-write).
    """

    def __init__(self, dest_dir: Path) -> None:
        self._path = dest_dir / "state.json"
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        """Load existing state from disk if available."""
        if self._path.exists():
            self._data = json.loads(self._path.read_text())
            # Reconstitute FileStatus enums from stored strings
            for entry in self._data.values():
                if isinstance(entry.get("status"), str):
                    entry["status"] = FileStatus(entry["status"])

    def _save(self) -> None:
        """Atomic write: write to .tmp then rename (POSIX atomic on same fs)."""
        tmp = self._path.with_suffix(".tmp")
        # Serialize FileStatus enums as their string values
        serializable = {}
        for key, entry in self._data.items():
            serializable[key] = {
                k: (v.value if isinstance(v, FileStatus) else v) for k, v in entry.items()
            }
        tmp.write_text(json.dumps(serializable, indent=2))
        tmp.replace(self._path)

    def initialize(self, files: list[FileEntry]) -> None:
        """Populate state for files not already present. Idempotent.

        Args:
            files: List of FileEntry objects from the enumerator.
        """
        with self._lock:
            for f in files:
                key = f.server_relative_url
                if key not in self._data:
                    self._data[key] = {
                        "name": f.name,
                        "size_bytes": f.size_bytes,
                        "folder_path": f.folder_path,
                        "status": FileStatus.PENDING,
                        "sha256": None,
                        "error": None,
                        "downloaded_at": None,
                    }
            self._save()

    def set_status(self, server_relative_url: str, status: FileStatus, **kwargs) -> None:
        """Update file status and optional extra fields. Thread-safe.

        Args:
            server_relative_url: The file key.
            status: New FileStatus value.
            **kwargs: Additional fields to update (sha256, error, downloaded_at).
        """
        with self._lock:
            self._data[server_relative_url]["status"] = status
            for k, v in kwargs.items():
                self._data[server_relative_url][k] = v
            self._save()

    def pending_files(self) -> list[str]:
        """Return keys where status is PENDING, FAILED, or DOWNLOADING (for retry)."""
        with self._lock:
            return [
                k
                for k, v in self._data.items()
                if v["status"] in (FileStatus.PENDING, FileStatus.FAILED, FileStatus.DOWNLOADING)
            ]

    def complete_files(self) -> list[str]:
        """Return keys where status is COMPLETE."""
        with self._lock:
            return [k for k, v in self._data.items() if v["status"] == FileStatus.COMPLETE]

    def failed_files(self) -> list[tuple[str, str]]:
        """Return (server_relative_url, error_reason) for all FAILED entries."""
        with self._lock:
            return [
                (k, v.get("error", "unknown"))
                for k, v in self._data.items()
                if v["status"] == FileStatus.FAILED
            ]

    def cleanup_interrupted(self, dest_dir: Path) -> None:
        """Delete .part files for DOWNLOADING entries and reset to PENDING.

        Called on resume to clean up artifacts from interrupted downloads.

        Args:
            dest_dir: The root download destination directory.
        """
        with self._lock:
            for key, entry in self._data.items():
                if entry["status"] == FileStatus.DOWNLOADING:
                    # Reconstruct local path from folder_path and name
                    folder = entry.get("folder_path", "")
                    name = entry["name"]
                    # Strip the common prefix to get relative folder
                    # folder_path is like /sites/shared/Images/custodian1
                    # We need to find the part after the root folder
                    parts = folder.strip("/").split("/")
                    # Skip site-level path components (sites/shared/Images)
                    # Use everything after the root to build local dir
                    # For cleanup, search for the .part file by name pattern
                    self._find_and_delete_part(dest_dir, name)
                    entry["status"] = FileStatus.PENDING
            self._save()

    @staticmethod
    def _find_and_delete_part(dest_dir: Path, filename: str) -> None:
        """Find and delete .part file for a given filename under dest_dir."""
        part_name = filename + ".part"
        for part_file in dest_dir.rglob(part_name):
            part_file.unlink(missing_ok=True)

    def all_entries(self) -> dict[str, dict]:
        """Return a shallow copy of all tracked entries keyed by server_relative_url."""
        with self._lock:
            return dict(self._data)

    def get_entry(self, server_relative_url: str) -> dict | None:
        """Return the state dict for a file, or None if not tracked."""
        with self._lock:
            return self._data.get(server_relative_url)
