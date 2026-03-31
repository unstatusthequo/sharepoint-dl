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


def validate_local_relative_path(local_path: str | None) -> str | None:
    """Return a normalized relative local path when it is safe to use."""
    if not local_path:
        return None

    relative = Path(local_path)
    if relative.is_absolute() or ".." in relative.parts:
        return None

    return relative.as_posix()


def derive_local_relative_path(folder_path: str, name: str, *, flat: bool = False) -> str:
    """Derive the relative output path for a SharePoint file."""
    if flat:
        return name

    parts = Path(folder_path.strip("/")).parts
    if len(parts) > 3:
        relative = Path(*parts[3:])
    elif len(parts) > 2:
        relative = Path(parts[-1])
    else:
        relative = Path(".")

    if relative == Path("."):
        return name
    return (relative / name).as_posix()


def entry_local_relative_path(entry: dict, *, flat: bool = False) -> str | None:
    """Return the best relative local path for a state entry."""
    stored = validate_local_relative_path(entry.get("local_path"))
    if stored is not None:
        return stored

    folder = entry.get("folder_path")
    name = entry.get("name")
    if not folder or not name:
        return None

    return derive_local_relative_path(folder, name, flat=flat)


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
                        "local_path": None,
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
            for entry in self._data.values():
                if entry["status"] != FileStatus.DOWNLOADING:
                    continue

                part_path = self._resolve_interrupted_part_path(dest_dir, entry)
                if part_path is not None:
                    part_path.unlink(missing_ok=True)

                entry["status"] = FileStatus.PENDING
            self._save()

    @staticmethod
    def _resolve_interrupted_part_path(dest_dir: Path, entry: dict) -> Path | None:
        """Resolve the exact .part path for one interrupted entry."""
        local_path = entry_local_relative_path(entry)
        if local_path is None:
            return None

        local = dest_dir / "files" / local_path
        return local.with_suffix(local.suffix + ".part")

    def all_entries(self) -> dict[str, dict]:
        """Return a shallow copy of all tracked entries keyed by server_relative_url."""
        with self._lock:
            return dict(self._data)

    def get_entry(self, server_relative_url: str) -> dict | None:
        """Return the state dict for a file, or None if not tracked."""
        with self._lock:
            return self._data.get(server_relative_url)
