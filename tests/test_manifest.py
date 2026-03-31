"""Unit tests for sharepoint_dl.manifest.writer module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sharepoint_dl.enumerator.traversal import FileEntry
from sharepoint_dl.state.job_state import FileStatus, JobState


@pytest.fixture
def file_entries() -> list[FileEntry]:
    """Return 3 FileEntry objects for manifest testing."""
    return [
        FileEntry(
            name="evidence_001.E01",
            server_relative_url="/sites/shared/Images/custodian1/evidence_001.E01",
            size_bytes=2147483648,
            folder_path="/sites/shared/Images/custodian1",
        ),
        FileEntry(
            name="evidence_002.E01",
            server_relative_url="/sites/shared/Images/custodian1/evidence_002.E01",
            size_bytes=1073741824,
            folder_path="/sites/shared/Images/custodian1",
        ),
        FileEntry(
            name="evidence_003.L01",
            server_relative_url="/sites/shared/Images/custodian1/evidence_003.L01",
            size_bytes=536870912,
            folder_path="/sites/shared/Images/custodian1",
        ),
    ]


def _setup_complete_state(
    tmp_path: Path, file_entries: list[FileEntry]
) -> JobState:
    """Create a JobState with all 3 files marked complete with sha256 hashes."""
    state = JobState(tmp_path)
    state.initialize(file_entries)
    state.set_status(
        file_entries[0].server_relative_url,
        FileStatus.COMPLETE,
        sha256="aabbccdd" * 8,
        downloaded_at="2026-03-27T10:00:00Z",
    )
    state.set_status(
        file_entries[1].server_relative_url,
        FileStatus.COMPLETE,
        sha256="11223344" * 8,
        downloaded_at="2026-03-27T10:05:00Z",
    )
    state.set_status(
        file_entries[2].server_relative_url,
        FileStatus.COMPLETE,
        sha256="deadbeef" * 8,
        downloaded_at="2026-03-27T10:10:00Z",
    )
    return state


class TestAllEntries:
    """JobState.all_entries() returns all tracked entries as a dict copy."""

    def test_all_entries_returns_dict_of_all_tracked_files(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        state = JobState(tmp_path)
        state.initialize(file_entries)

        entries = state.all_entries()

        assert isinstance(entries, dict)
        assert len(entries) == 3
        for fe in file_entries:
            assert fe.server_relative_url in entries
            assert entries[fe.server_relative_url]["name"] == fe.name


class TestManifestPerFileFields:
    """generate_manifest() produces correct per-file fields for complete files."""

    def test_manifest_has_correct_per_file_fields(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        from sharepoint_dl.manifest.writer import generate_manifest

        state = _setup_complete_state(tmp_path, file_entries)
        path = generate_manifest(
            state=state,
            dest_dir=tmp_path,
            source_url="https://contoso.sharepoint.com/sites/shared/Images",
            root_folder="Images",
        )

        manifest = json.loads(path.read_text())
        files = manifest["files"]
        assert len(files) == 3

        first = files[0]
        assert "name" in first
        assert "server_relative_url" in first
        assert "local_path" in first
        assert "size_bytes" in first
        assert "sha256" in first
        assert "downloaded_at" in first

    def test_manifest_uses_persisted_local_path_for_preserved_folder_entries(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        from sharepoint_dl.manifest.writer import generate_manifest

        state = JobState(tmp_path)
        state.initialize(file_entries)
        state.set_status(
            file_entries[0].server_relative_url,
            FileStatus.COMPLETE,
            local_path="custodian1/evidence_001.E01",
            sha256="aabbccdd" * 8,
            downloaded_at="2026-03-27T10:00:00Z",
        )

        path = generate_manifest(
            state=state,
            dest_dir=tmp_path,
            source_url="https://contoso.sharepoint.com/sites/shared/Images",
            root_folder="Images",
        )

        manifest = json.loads(path.read_text())
        assert manifest["files"][0]["local_path"] == "custodian1/evidence_001.E01"

    def test_manifest_uses_persisted_local_path_for_flat_entries(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        from sharepoint_dl.manifest.writer import generate_manifest

        state = JobState(tmp_path)
        state.initialize(file_entries)
        state.set_status(
            file_entries[0].server_relative_url,
            FileStatus.COMPLETE,
            local_path="evidence_001.E01",
            sha256="aabbccdd" * 8,
            downloaded_at="2026-03-27T10:00:00Z",
        )

        path = generate_manifest(
            state=state,
            dest_dir=tmp_path,
            source_url="https://contoso.sharepoint.com/sites/shared/Images",
            root_folder="Images",
        )

        manifest = json.loads(path.read_text())
        assert manifest["files"][0]["local_path"] == "evidence_001.E01"


class TestManifestMetadata:
    """generate_manifest() includes top-level metadata."""

    def test_manifest_has_top_level_metadata(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        from sharepoint_dl.manifest.writer import generate_manifest

        state = _setup_complete_state(tmp_path, file_entries)
        path = generate_manifest(
            state=state,
            dest_dir=tmp_path,
            source_url="https://contoso.sharepoint.com/sites/shared/Images",
            root_folder="Images",
        )

        manifest = json.loads(path.read_text())
        meta = manifest["metadata"]

        assert meta["source_url"] == "https://contoso.sharepoint.com/sites/shared/Images"
        assert meta["root_folder"] == "Images"
        assert meta["total_files"] == 3
        assert meta["total_size_bytes"] == 2147483648 + 1073741824 + 536870912
        assert "generated_at" in meta
        assert "tool_version" in meta


class TestManifestStatusPartitioning:
    """generate_manifest() only includes complete files in 'files', failed in 'failed'."""

    def test_only_complete_files_in_files_list(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        from sharepoint_dl.manifest.writer import generate_manifest

        state = JobState(tmp_path)
        state.initialize(file_entries)
        # Mark 2 complete, 1 failed
        state.set_status(
            file_entries[0].server_relative_url,
            FileStatus.COMPLETE,
            sha256="aabbccdd" * 8,
            downloaded_at="2026-03-27T10:00:00Z",
        )
        state.set_status(
            file_entries[1].server_relative_url,
            FileStatus.COMPLETE,
            sha256="11223344" * 8,
            downloaded_at="2026-03-27T10:05:00Z",
        )
        state.set_status(
            file_entries[2].server_relative_url,
            FileStatus.FAILED,
            error="network timeout",
        )

        path = generate_manifest(
            state=state,
            dest_dir=tmp_path,
            source_url="https://contoso.sharepoint.com/sites/shared/Images",
            root_folder="Images",
        )

        manifest = json.loads(path.read_text())
        assert len(manifest["files"]) == 2
        assert all(f["sha256"] is not None for f in manifest["files"])

    def test_failed_files_listed_separately(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        from sharepoint_dl.manifest.writer import generate_manifest

        state = JobState(tmp_path)
        state.initialize(file_entries)
        state.set_status(
            file_entries[0].server_relative_url,
            FileStatus.COMPLETE,
            sha256="aabbccdd" * 8,
            downloaded_at="2026-03-27T10:00:00Z",
        )
        state.set_status(
            file_entries[1].server_relative_url,
            FileStatus.FAILED,
            error="network timeout",
        )
        # Leave file_entries[2] as pending (should not appear in either list)

        path = generate_manifest(
            state=state,
            dest_dir=tmp_path,
            source_url="https://contoso.sharepoint.com/sites/shared/Images",
            root_folder="Images",
        )

        manifest = json.loads(path.read_text())
        assert len(manifest["failed"]) == 1
        assert manifest["failed"][0]["server_relative_url"] == file_entries[1].server_relative_url
        assert manifest["failed"][0]["error"] == "network timeout"


class TestManifestSorting:
    """generate_manifest() sorts files by server_relative_url."""

    def test_files_sorted_by_server_relative_url(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        from sharepoint_dl.manifest.writer import generate_manifest

        state = _setup_complete_state(tmp_path, file_entries)
        path = generate_manifest(
            state=state,
            dest_dir=tmp_path,
            source_url="https://contoso.sharepoint.com/sites/shared/Images",
            root_folder="Images",
        )

        manifest = json.loads(path.read_text())
        urls = [f["server_relative_url"] for f in manifest["files"]]
        assert urls == sorted(urls)


class TestManifestOutputPath:
    """generate_manifest() writes manifest.json to dest_dir and returns the Path."""

    def test_writes_manifest_json_and_returns_path(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        from sharepoint_dl.manifest.writer import generate_manifest

        state = _setup_complete_state(tmp_path, file_entries)
        path = generate_manifest(
            state=state,
            dest_dir=tmp_path,
            source_url="https://contoso.sharepoint.com/sites/shared/Images",
            root_folder="Images",
        )

        assert path == tmp_path / "manifest.json"
        assert path.exists()
        # Verify it's valid JSON
        data = json.loads(path.read_text())
        assert "metadata" in data
        assert "files" in data


class TestManifestEdgeCases:
    """generate_manifest() handles edge cases correctly."""

    def test_no_complete_files_writes_empty_files_list(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        from sharepoint_dl.manifest.writer import generate_manifest

        state = JobState(tmp_path)
        state.initialize(file_entries)
        # All remain pending — none complete

        path = generate_manifest(
            state=state,
            dest_dir=tmp_path,
            source_url="https://contoso.sharepoint.com/sites/shared/Images",
            root_folder="Images",
        )

        manifest = json.loads(path.read_text())
        assert manifest["files"] == []
        assert manifest["metadata"]["total_files"] == 0
        assert manifest["metadata"]["total_size_bytes"] == 0

    def test_missing_local_path_uses_shared_legacy_fallback(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        from sharepoint_dl.manifest.writer import generate_manifest

        state = JobState(tmp_path)
        state.initialize(file_entries)
        state.set_status(
            file_entries[0].server_relative_url,
            FileStatus.COMPLETE,
            sha256="aabbccdd" * 8,
            downloaded_at="2026-03-27T10:00:00Z",
        )

        path = generate_manifest(
            state=state,
            dest_dir=tmp_path,
            source_url="https://contoso.sharepoint.com/sites/shared/Images",
            root_folder="Images",
        )

        manifest = json.loads(path.read_text())
        assert manifest["files"][0]["local_path"] == "custodian1/evidence_001.E01"

    def test_invalid_stored_local_path_falls_back_safely(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        from sharepoint_dl.manifest.writer import generate_manifest

        state = JobState(tmp_path)
        state.initialize(file_entries)
        state.set_status(
            file_entries[0].server_relative_url,
            FileStatus.COMPLETE,
            local_path="../escape/evidence_001.E01",
            sha256="aabbccdd" * 8,
            downloaded_at="2026-03-27T10:00:00Z",
        )

        path = generate_manifest(
            state=state,
            dest_dir=tmp_path,
            source_url="https://contoso.sharepoint.com/sites/shared/Images",
            root_folder="Images",
        )

        manifest = json.loads(path.read_text())
        assert manifest["files"][0]["local_path"] == "../escape/evidence_001.E01"

    def test_persisted_local_path_wins_over_fallback(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        from sharepoint_dl.manifest.writer import generate_manifest

        state = JobState(tmp_path)
        state.initialize(file_entries)
        state.set_status(
            file_entries[0].server_relative_url,
            FileStatus.COMPLETE,
            local_path="evidence/custom-name.E01",
            sha256="aabbccdd" * 8,
            downloaded_at="2026-03-27T10:00:00Z",
        )

        path = generate_manifest(
            state=state,
            dest_dir=tmp_path,
            source_url="https://contoso.sharepoint.com/sites/shared/Images",
            root_folder="Images",
        )

        manifest = json.loads(path.read_text())
        assert manifest["files"][0]["local_path"] == "evidence/custom-name.E01"

    def test_missing_local_path_uses_flat_fallback_when_requested(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        from sharepoint_dl.manifest.writer import generate_manifest

        state = JobState(tmp_path)
        state.initialize(file_entries)
        state.set_status(
            file_entries[0].server_relative_url,
            FileStatus.COMPLETE,
            sha256="aabbccdd" * 8,
            downloaded_at="2026-03-27T10:00:00Z",
        )

        path = generate_manifest(
            state=state,
            dest_dir=tmp_path,
            source_url="https://contoso.sharepoint.com/sites/shared/Images",
            root_folder="Images",
            flat=True,
        )

        manifest = json.loads(path.read_text())
        assert manifest["files"][0]["local_path"] == "evidence_001.E01"


class TestManifestSha256FromState:
    """SHA-256 values in manifest match what was stored in state.json (no re-computation)."""

    def test_sha256_matches_state_values(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        from sharepoint_dl.manifest.writer import generate_manifest

        state = _setup_complete_state(tmp_path, file_entries)

        # Read the expected hashes from state before generating manifest
        entries = state.all_entries()
        expected_hashes = {
            url: entry["sha256"] for url, entry in entries.items()
        }

        path = generate_manifest(
            state=state,
            dest_dir=tmp_path,
            source_url="https://contoso.sharepoint.com/sites/shared/Images",
            root_folder="Images",
        )

        manifest = json.loads(path.read_text())
        for f in manifest["files"]:
            assert f["sha256"] == expected_hashes[f["server_relative_url"]]
