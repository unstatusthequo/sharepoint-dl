"""Post-download manifest verification — re-hashes files on disk and compares to manifest.

Public API:
    verify_manifest(dest_dir, on_progress=None) -> VerifySummary
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable, NamedTuple

CHUNK_SIZE = 8_388_608  # 8 MB — matches download engine


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class VerifyResult(NamedTuple):
    """Per-file verification outcome."""

    name: str
    local_path: str
    expected_sha256: str
    actual_sha256: str | None  # None when file is MISSING
    status: str  # "PASS", "FAIL", or "MISSING"


class VerifySummary(NamedTuple):
    """Aggregate result of manifest verification."""

    results: list[VerifyResult]
    total: int
    passed: int
    failed: int
    missing: int


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def verify_manifest(
    dest_dir: Path,
    on_progress: Callable[[str, int], None] | None = None,
) -> VerifySummary:
    """Verify all files listed in dest_dir/manifest.json against their SHA-256 hashes.

    Re-reads each file from disk in 8 MB chunks and compares the computed SHA-256
    to the value recorded in the manifest at download time.

    Extra files on disk that are not listed in the manifest are ignored.

    Args:
        dest_dir: Directory containing manifest.json and downloaded files.
        on_progress: Optional callback invoked after each file with
            (name, size_bytes) so callers can update a progress bar.

    Returns:
        VerifySummary with per-file results and summary counts.

    Raises:
        FileNotFoundError: If manifest.json does not exist in dest_dir.
    """
    manifest_path = dest_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest.json found in {dest_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    file_entries = manifest.get("files", [])

    results: list[VerifyResult] = []
    passed = 0
    failed = 0
    missing = 0

    for entry in file_entries:
        name: str = entry["name"]
        local_path_rel: str = entry["local_path"]
        expected_sha256: str = entry["sha256"]
        size_bytes: int = entry.get("size_bytes", 0)

        # Resolve local path relative to dest_dir
        file_path = dest_dir / local_path_rel

        if not file_path.exists():
            results.append(
                VerifyResult(
                    name=name,
                    local_path=local_path_rel,
                    expected_sha256=expected_sha256,
                    actual_sha256=None,
                    status="MISSING",
                )
            )
            missing += 1
        else:
            actual_sha256 = _hash_file(file_path)
            if actual_sha256 == expected_sha256:
                status = "PASS"
                passed += 1
            else:
                status = "FAIL"
                failed += 1

            results.append(
                VerifyResult(
                    name=name,
                    local_path=local_path_rel,
                    expected_sha256=expected_sha256,
                    actual_sha256=actual_sha256,
                    status=status,
                )
            )

        if on_progress is not None:
            on_progress(name, size_bytes)

    return VerifySummary(
        results=results,
        total=len(results),
        passed=passed,
        failed=failed,
        missing=missing,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _hash_file(path: Path) -> str:
    """Compute SHA-256 of a file by reading in 8 MB chunks.

    Args:
        path: Path to the file on disk.

    Returns:
        Hex-encoded SHA-256 digest.
    """
    sha256 = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(CHUNK_SIZE)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()
