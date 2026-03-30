"""Tests for sharepoint_dl.manifest.verifier."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_manifest(dest: Path, files: list[dict]) -> None:
    manifest = {
        "metadata": {
            "source_url": "https://example.sharepoint.com/sites/test",
            "root_folder": "/sites/test/Shared Documents",
            "total_files": len(files),
            "total_size_bytes": sum(f["size_bytes"] for f in files),
            "generated_at": "2026-03-30T00:00:00+00:00",
            "tool_version": "sharepoint-dl v1.0",
        },
        "files": files,
        "failed": [],
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2))


class TestVerifyManifestAllPass:
    def test_all_files_matching_returns_pass(self, tmp_path: Path) -> None:
        from sharepoint_dl.manifest.verifier import verify_manifest

        content_a = b"file content alpha"
        content_b = b"file content beta"

        (tmp_path / "file_a.txt").write_bytes(content_a)
        (tmp_path / "file_b.txt").write_bytes(content_b)

        files = [
            {
                "name": "file_a.txt",
                "server_relative_url": "/sites/test/Shared/file_a.txt",
                "local_path": "file_a.txt",
                "size_bytes": len(content_a),
                "sha256": _sha256(content_a),
                "downloaded_at": "2026-03-30T00:00:00+00:00",
            },
            {
                "name": "file_b.txt",
                "server_relative_url": "/sites/test/Shared/file_b.txt",
                "local_path": "file_b.txt",
                "size_bytes": len(content_b),
                "sha256": _sha256(content_b),
                "downloaded_at": "2026-03-30T00:00:00+00:00",
            },
        ]
        _write_manifest(tmp_path, files)

        summary = verify_manifest(tmp_path)

        assert summary.total == 2
        assert summary.passed == 2
        assert summary.failed == 0
        assert summary.missing == 0
        assert all(r.status == "PASS" for r in summary.results)

    def test_pass_result_fields(self, tmp_path: Path) -> None:
        from sharepoint_dl.manifest.verifier import verify_manifest

        content = b"hello world"
        (tmp_path / "hello.txt").write_bytes(content)

        files = [
            {
                "name": "hello.txt",
                "server_relative_url": "/sites/test/Shared/hello.txt",
                "local_path": "hello.txt",
                "size_bytes": len(content),
                "sha256": _sha256(content),
                "downloaded_at": "2026-03-30T00:00:00+00:00",
            }
        ]
        _write_manifest(tmp_path, files)

        summary = verify_manifest(tmp_path)
        result = summary.results[0]

        assert result.name == "hello.txt"
        assert result.local_path == "hello.txt"
        assert result.expected_sha256 == _sha256(content)
        assert result.actual_sha256 == _sha256(content)
        assert result.status == "PASS"


class TestVerifyManifestFail:
    def test_tampered_file_returns_fail(self, tmp_path: Path) -> None:
        from sharepoint_dl.manifest.verifier import verify_manifest

        original_content = b"original content"
        tampered_content = b"tampered content!"

        # Write the tampered version to disk
        (tmp_path / "file.txt").write_bytes(tampered_content)

        files = [
            {
                "name": "file.txt",
                "server_relative_url": "/sites/test/Shared/file.txt",
                "local_path": "file.txt",
                "size_bytes": len(original_content),
                "sha256": _sha256(original_content),
                "downloaded_at": "2026-03-30T00:00:00+00:00",
            }
        ]
        _write_manifest(tmp_path, files)

        summary = verify_manifest(tmp_path)

        assert summary.total == 1
        assert summary.failed == 1
        assert summary.passed == 0
        assert summary.missing == 0

        result = summary.results[0]
        assert result.status == "FAIL"
        assert result.expected_sha256 == _sha256(original_content)
        assert result.actual_sha256 == _sha256(tampered_content)

    def test_mixed_pass_and_fail(self, tmp_path: Path) -> None:
        from sharepoint_dl.manifest.verifier import verify_manifest

        good_content = b"good file"
        original_content = b"original"
        tampered_content = b"tampered"

        (tmp_path / "good.txt").write_bytes(good_content)
        (tmp_path / "bad.txt").write_bytes(tampered_content)

        files = [
            {
                "name": "good.txt",
                "server_relative_url": "/sites/test/Shared/good.txt",
                "local_path": "good.txt",
                "size_bytes": len(good_content),
                "sha256": _sha256(good_content),
                "downloaded_at": "2026-03-30T00:00:00+00:00",
            },
            {
                "name": "bad.txt",
                "server_relative_url": "/sites/test/Shared/bad.txt",
                "local_path": "bad.txt",
                "size_bytes": len(original_content),
                "sha256": _sha256(original_content),
                "downloaded_at": "2026-03-30T00:00:00+00:00",
            },
        ]
        _write_manifest(tmp_path, files)

        summary = verify_manifest(tmp_path)

        assert summary.total == 2
        assert summary.passed == 1
        assert summary.failed == 1
        assert summary.missing == 0


class TestVerifyManifestMissing:
    def test_missing_file_returns_missing(self, tmp_path: Path) -> None:
        from sharepoint_dl.manifest.verifier import verify_manifest

        content = b"file content"
        # Don't write the file to disk

        files = [
            {
                "name": "missing.txt",
                "server_relative_url": "/sites/test/Shared/missing.txt",
                "local_path": "missing.txt",
                "size_bytes": len(content),
                "sha256": _sha256(content),
                "downloaded_at": "2026-03-30T00:00:00+00:00",
            }
        ]
        _write_manifest(tmp_path, files)

        summary = verify_manifest(tmp_path)

        assert summary.total == 1
        assert summary.missing == 1
        assert summary.passed == 0
        assert summary.failed == 0

        result = summary.results[0]
        assert result.status == "MISSING"
        assert result.actual_sha256 is None

    def test_one_missing_one_present(self, tmp_path: Path) -> None:
        from sharepoint_dl.manifest.verifier import verify_manifest

        content_a = b"file a content"
        content_b = b"file b content"

        (tmp_path / "present.txt").write_bytes(content_a)
        # file_b.txt is NOT written

        files = [
            {
                "name": "present.txt",
                "server_relative_url": "/sites/test/Shared/present.txt",
                "local_path": "present.txt",
                "size_bytes": len(content_a),
                "sha256": _sha256(content_a),
                "downloaded_at": "2026-03-30T00:00:00+00:00",
            },
            {
                "name": "missing.txt",
                "server_relative_url": "/sites/test/Shared/missing.txt",
                "local_path": "missing.txt",
                "size_bytes": len(content_b),
                "sha256": _sha256(content_b),
                "downloaded_at": "2026-03-30T00:00:00+00:00",
            },
        ]
        _write_manifest(tmp_path, files)

        summary = verify_manifest(tmp_path)

        assert summary.total == 2
        assert summary.passed == 1
        assert summary.missing == 1
        assert summary.failed == 0


class TestVerifyManifestNoManifest:
    def test_no_manifest_raises_file_not_found(self, tmp_path: Path) -> None:
        from sharepoint_dl.manifest.verifier import verify_manifest

        with pytest.raises(FileNotFoundError):
            verify_manifest(tmp_path)


class TestVerifyManifestOnProgress:
    def test_on_progress_called_for_each_file(self, tmp_path: Path) -> None:
        from sharepoint_dl.manifest.verifier import verify_manifest

        content_a = b"alpha"
        content_b = b"beta"

        (tmp_path / "a.txt").write_bytes(content_a)
        (tmp_path / "b.txt").write_bytes(content_b)

        files = [
            {
                "name": "a.txt",
                "server_relative_url": "/sites/test/Shared/a.txt",
                "local_path": "a.txt",
                "size_bytes": len(content_a),
                "sha256": _sha256(content_a),
                "downloaded_at": "2026-03-30T00:00:00+00:00",
            },
            {
                "name": "b.txt",
                "server_relative_url": "/sites/test/Shared/b.txt",
                "local_path": "b.txt",
                "size_bytes": len(content_b),
                "sha256": _sha256(content_b),
                "downloaded_at": "2026-03-30T00:00:00+00:00",
            },
        ]
        _write_manifest(tmp_path, files)

        progress_calls: list[tuple[str, int]] = []

        def on_progress(name: str, size_bytes: int) -> None:
            progress_calls.append((name, size_bytes))

        verify_manifest(tmp_path, on_progress=on_progress)

        assert len(progress_calls) == 2
        names = [c[0] for c in progress_calls]
        assert "a.txt" in names
        assert "b.txt" in names
