"""Unit tests for sharepoint_dl.state.job_state module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sharepoint_dl.enumerator.traversal import FileEntry
from sharepoint_dl.state.job_state import FileStatus, JobState


@pytest.fixture
def file_entries() -> list[FileEntry]:
    """Return 3 FileEntry objects matching mock_sharepoint_responses data."""
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


class TestResume:
    """initialize() populates state; complete files excluded from pending_files()."""

    def test_initialize_populates_state(self, tmp_path: Path, file_entries: list[FileEntry]):
        state = JobState(tmp_path)
        state.initialize(file_entries)

        # All 3 files should be in state
        assert len(state.pending_files()) == 3

    def test_complete_files_excluded_from_pending(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        state = JobState(tmp_path)
        state.initialize(file_entries)

        # Mark one file as complete
        state.set_status(
            file_entries[0].server_relative_url,
            FileStatus.COMPLETE,
            sha256="abc123",
        )

        pending = state.pending_files()
        assert file_entries[0].server_relative_url not in pending
        assert len(pending) == 2

    def test_failed_files_appear_in_pending(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        state = JobState(tmp_path)
        state.initialize(file_entries)

        state.set_status(
            file_entries[1].server_relative_url,
            FileStatus.FAILED,
            error="network timeout",
        )

        pending = state.pending_files()
        assert file_entries[1].server_relative_url in pending

    def test_downloading_files_appear_in_pending(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        state = JobState(tmp_path)
        state.initialize(file_entries)

        state.set_status(file_entries[2].server_relative_url, FileStatus.DOWNLOADING)

        pending = state.pending_files()
        assert file_entries[2].server_relative_url in pending


class TestPartCleanup:
    """cleanup_interrupted() deletes .part files and resets status to pending."""

    def test_cleanup_deletes_only_tracked_part_file(
        self, tmp_path: Path
    ):
        tracked = FileEntry(
            name="duplicate.bin",
            server_relative_url="/sites/shared/Images/custodian1/duplicate.bin",
            size_bytes=10,
            folder_path="/sites/shared/Images/custodian1",
        )
        unrelated = FileEntry(
            name="duplicate.bin",
            server_relative_url="/sites/shared/Images/custodian2/duplicate.bin",
            size_bytes=10,
            folder_path="/sites/shared/Images/custodian2",
        )

        state = JobState(tmp_path)
        state.initialize([tracked, unrelated])

        tracked_local_path = "custodian1/duplicate.bin"
        state.set_status(
            tracked.server_relative_url,
            FileStatus.DOWNLOADING,
            local_path=tracked_local_path,
        )

        tracked_part = tmp_path / "files" / tracked_local_path
        tracked_part = tracked_part.with_suffix(tracked_part.suffix + ".part")
        tracked_part.parent.mkdir(parents=True, exist_ok=True)
        tracked_part.write_bytes(b"partial data")

        unrelated_part = tmp_path / "files" / "custodian2" / "duplicate.bin.part"
        unrelated_part.parent.mkdir(parents=True, exist_ok=True)
        unrelated_part.write_bytes(b"other partial data")

        state.cleanup_interrupted(tmp_path)

        assert not tracked_part.exists()
        assert unrelated_part.exists()

    def test_cleanup_handles_flat_output_when_local_path_is_tracked(
        self, tmp_path: Path
    ):
        entry = FileEntry(
            name="evidence_001.E01",
            server_relative_url="/sites/shared/Images/custodian1/evidence_001.E01",
            size_bytes=10,
            folder_path="/sites/shared/Images/custodian1",
        )

        state = JobState(tmp_path)
        state.initialize([entry])

        state.set_status(
            entry.server_relative_url,
            FileStatus.DOWNLOADING,
            local_path=entry.name,
        )

        part_file = tmp_path / "files" / "evidence_001.E01.part"
        part_file.parent.mkdir(parents=True, exist_ok=True)
        part_file.write_bytes(b"partial data")

        state.cleanup_interrupted(tmp_path)

        state_entry = state.get_entry(entry.server_relative_url)
        assert state_entry is not None
        assert state_entry["status"] == FileStatus.PENDING
        assert not part_file.exists()


class TestAtomicWrite:
    """set_status() writes via temp-rename pattern; survives simulated crash."""

    def test_state_json_written_on_set_status(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        state = JobState(tmp_path)
        state.initialize(file_entries)

        state_file = tmp_path / "state.json"
        assert state_file.exists()

        data = json.loads(state_file.read_text())
        assert file_entries[0].server_relative_url in data

    def test_state_json_valid_after_save(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        state = JobState(tmp_path)
        state.initialize(file_entries)

        # Simulate a "crash" scenario: write a .tmp file to pretend atomic write interrupted
        tmp_file = tmp_path / "state.json.tmp"
        tmp_file.write_text('{"corrupted": true}')

        # state.json should still be valid (the .tmp is abandoned)
        state2 = JobState(tmp_path)
        assert len(state2.pending_files()) == 3

    def test_state_persists_across_reload(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        state = JobState(tmp_path)
        state.initialize(file_entries)
        state.set_status(
            file_entries[0].server_relative_url,
            FileStatus.COMPLETE,
            sha256="abc123",
        )

        # Reload from disk
        state2 = JobState(tmp_path)
        complete = state2.complete_files()
        assert file_entries[0].server_relative_url in complete


class TestInitializeIdempotent:
    """Calling initialize() twice does not overwrite already-complete entries."""

    def test_initialize_preserves_complete_entries(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        state = JobState(tmp_path)
        state.initialize(file_entries)

        # Complete a file
        state.set_status(
            file_entries[0].server_relative_url,
            FileStatus.COMPLETE,
            sha256="abc123",
        )

        # Re-initialize with same files
        state.initialize(file_entries)

        entry = state.get_entry(file_entries[0].server_relative_url)
        assert entry is not None
        assert entry["status"] == FileStatus.COMPLETE
        assert entry["sha256"] == "abc123"

    def test_legacy_downloading_entries_use_exact_fallback_path(
        self, tmp_path: Path
    ):
        tracked = FileEntry(
            name="duplicate.bin",
            server_relative_url="/sites/shared/Images/custodian1/duplicate.bin",
            size_bytes=10,
            folder_path="/sites/shared/Images/custodian1",
        )
        sibling = FileEntry(
            name="duplicate.bin",
            server_relative_url="/sites/shared/Images/custodian2/duplicate.bin",
            size_bytes=10,
            folder_path="/sites/shared/Images/custodian2",
        )

        legacy_state = {
            tracked.server_relative_url: {
                "name": tracked.name,
                "size_bytes": tracked.size_bytes,
                "folder_path": tracked.folder_path,
                "status": "downloading",
                "sha256": None,
                "error": None,
                "downloaded_at": None,
            }
        }
        (tmp_path / "state.json").write_text(json.dumps(legacy_state))

        state = JobState(tmp_path)
        state.initialize([tracked, sibling])

        tracked_part = tmp_path / "files" / "custodian1" / "duplicate.bin.part"
        tracked_part.parent.mkdir(parents=True, exist_ok=True)
        tracked_part.write_bytes(b"partial data")

        sibling_part = tmp_path / "files" / "custodian2" / "duplicate.bin.part"
        sibling_part.parent.mkdir(parents=True, exist_ok=True)
        sibling_part.write_bytes(b"other partial data")

        state.cleanup_interrupted(tmp_path)

        entry = state.get_entry(tracked.server_relative_url)
        assert entry is not None
        assert entry["status"] == FileStatus.PENDING
        assert not tracked_part.exists()
        assert sibling_part.exists()


class TestFailedFiles:
    """failed_files() returns list of (url, error_reason) tuples for all failed entries."""

    def test_failed_files_returns_tuples(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        state = JobState(tmp_path)
        state.initialize(file_entries)

        state.set_status(
            file_entries[0].server_relative_url,
            FileStatus.FAILED,
            error="network timeout",
        )
        state.set_status(
            file_entries[1].server_relative_url,
            FileStatus.FAILED,
            error="size mismatch",
        )

        failed = state.failed_files()
        assert len(failed) == 2
        urls = [url for url, _ in failed]
        assert file_entries[0].server_relative_url in urls
        assert file_entries[1].server_relative_url in urls

    def test_failed_files_empty_when_none_failed(
        self, tmp_path: Path, file_entries: list[FileEntry]
    ):
        state = JobState(tmp_path)
        state.initialize(file_entries)

        assert state.failed_files() == []
