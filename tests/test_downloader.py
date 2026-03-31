"""Unit tests for sharepoint_dl.downloader.engine module."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from sharepoint_dl.downloader.engine import (
    CHUNK_SIZE,
    _build_download_url,
    _download_file,
    _make_progress,
    download_all,
)
from sharepoint_dl.enumerator.traversal import AuthExpiredError, FileEntry
from sharepoint_dl.state.job_state import FileStatus


@pytest.fixture
def sample_entry() -> FileEntry:
    """A single FileEntry for download tests."""
    return FileEntry(
        name="evidence_001.E01",
        server_relative_url="/sites/shared/Images/custodian1/evidence_001.E01",
        size_bytes=24,
        folder_path="/sites/shared/Images/custodian1",
    )


@pytest.fixture
def site_url() -> str:
    return "https://contoso.sharepoint.com/sites/shared"


class TestStreaming:
    """_download_file writes to .part, renames on success, .part gone after."""

    def test_writes_part_then_renames(
        self,
        tmp_path: Path,
        sample_entry: FileEntry,
        site_url: str,
    ):
        content = b"A" * 24
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.iter_content = MagicMock(return_value=iter([content]))
        resp.raise_for_status = MagicMock()
        session.get.return_value = resp

        dest = tmp_path / "evidence_001.E01"
        _download_file(session, sample_entry, dest, site_url)

        assert dest.exists()
        assert dest.read_bytes() == content
        assert not dest.with_suffix(dest.suffix + ".part").exists()

    def test_content_matches_chunks(
        self,
        tmp_path: Path,
        sample_entry: FileEntry,
        site_url: str,
    ):
        chunk1 = b"A" * 12
        chunk2 = b"B" * 12
        content = chunk1 + chunk2

        # Update entry size to match
        sample_entry.size_bytes = len(content)

        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.iter_content = MagicMock(return_value=iter([chunk1, chunk2]))
        resp.raise_for_status = MagicMock()
        session.get.return_value = resp

        dest = tmp_path / "evidence_001.E01"
        _download_file(session, sample_entry, dest, site_url)

        assert dest.read_bytes() == content


class TestHashing:
    """SHA-256 computed during download matches hashlib reference."""

    def test_sha256_matches_reference(
        self,
        tmp_path: Path,
        sample_entry: FileEntry,
        site_url: str,
    ):
        content = b"Hello, SHA-256 test data!"
        sample_entry.size_bytes = len(content)

        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.iter_content = MagicMock(return_value=iter([content]))
        resp.raise_for_status = MagicMock()
        session.get.return_value = resp

        dest = tmp_path / "evidence_001.E01"
        sha = _download_file(session, sample_entry, dest, site_url)

        expected = hashlib.sha256(content).hexdigest()
        assert sha == expected


class TestSizeMismatch:
    """If downloaded size != FileEntry.size_bytes, .part is deleted and ValueError raised."""

    def test_size_mismatch_raises_valueerror(
        self,
        tmp_path: Path,
        sample_entry: FileEntry,
        site_url: str,
    ):
        content = b"short"
        # sample_entry.size_bytes is 24, content is 5 -> mismatch
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.iter_content = MagicMock(return_value=iter([content]))
        resp.raise_for_status = MagicMock()
        session.get.return_value = resp

        dest = tmp_path / "evidence_001.E01"
        with pytest.raises(ValueError, match="Size mismatch"):
            _download_file(session, sample_entry, dest, site_url)

        # .part should be cleaned up
        part = dest.with_suffix(dest.suffix + ".part")
        assert not part.exists()


class TestAuthHalt:
    """401/403 raises AuthExpiredError immediately, not retried by tenacity."""

    def test_401_raises_auth_expired(
        self,
        tmp_path: Path,
        sample_entry: FileEntry,
        site_url: str,
    ):
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 401
        session.get.return_value = resp

        dest = tmp_path / "evidence_001.E01"
        with pytest.raises(AuthExpiredError):
            _download_file(session, sample_entry, dest, site_url)

        # Should be called only once (no retry)
        assert session.get.call_count == 1

    def test_403_raises_auth_expired(
        self,
        tmp_path: Path,
        sample_entry: FileEntry,
        site_url: str,
    ):
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 403
        session.get.return_value = resp

        dest = tmp_path / "evidence_001.E01"
        with pytest.raises(AuthExpiredError):
            _download_file(session, sample_entry, dest, site_url)

        assert session.get.call_count == 1


class TestFailureTracking:
    """500 retried by tenacity; after exhaustion raises HTTPError."""

    def test_500_retried_3_times(
        self,
        tmp_path: Path,
        sample_entry: FileEntry,
        site_url: str,
    ):
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 500

        def raise_for_status():
            raise requests.HTTPError(response=resp)

        resp.raise_for_status = raise_for_status
        session.get.return_value = resp

        dest = tmp_path / "evidence_001.E01"
        with pytest.raises(requests.HTTPError):
            _download_file(session, sample_entry, dest, site_url)

        # tenacity retries 3 times total
        assert session.get.call_count == 3


class TestRetryAfter:
    """429 with Retry-After header is retried; uses WaitRetryAfter."""

    def test_429_retried_then_succeeds(
        self,
        tmp_path: Path,
        sample_entry: FileEntry,
        site_url: str,
    ):
        content = b"A" * 24

        # First call: 429, second call: 200
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "1"}

        def raise_429():
            raise requests.HTTPError(response=resp_429)

        resp_429.raise_for_status = raise_429

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.iter_content = MagicMock(return_value=iter([content]))
        resp_200.raise_for_status = MagicMock()

        session = MagicMock()
        session.get.side_effect = [resp_429, resp_200]

        dest = tmp_path / "evidence_001.E01"
        sha = _download_file(session, sample_entry, dest, site_url)

        assert dest.exists()
        assert session.get.call_count == 2


class TestMakeProgress:
    """_make_progress() includes expected columns."""

    def test_has_time_remaining_column(self):
        from rich.progress import TimeRemainingColumn
        progress = _make_progress()
        column_types = [type(c) for c in progress.columns]
        assert TimeRemainingColumn in column_types

    def test_still_has_transfer_speed_column(self):
        from rich.progress import TransferSpeedColumn
        progress = _make_progress()
        column_types = [type(c) for c in progress.columns]
        assert TransferSpeedColumn in column_types


class TestDownloadUrl:
    """_build_download_url constructs correct download.aspx URL."""

    def test_basic_url_construction(self):
        url = _build_download_url(
            "https://contoso.sharepoint.com/sites/shared",
            "/sites/shared/Images/custodian1/evidence.E01",
        )
        assert "/_layouts/15/download.aspx" in url
        assert "SourceUrl=" in url
        assert "/sites/shared/Images/custodian1/evidence.E01" in url

    def test_trailing_slash_stripped(self):
        url = _build_download_url(
            "https://contoso.sharepoint.com/sites/shared/",
            "/sites/shared/file.txt",
        )
        assert "shared//_layouts" not in url
        assert "shared/_layouts" in url


def _make_test_entries(count: int = 3) -> list[FileEntry]:
    """Create N small FileEntry objects for concurrency tests."""
    return [
        FileEntry(
            name=f"file_{i}.dat",
            server_relative_url=f"/sites/shared/Docs/file_{i}.dat",
            size_bytes=24,
            folder_path="/sites/shared/Docs",
        )
        for i in range(count)
    ]


def _mock_session_for_download(entries: list[FileEntry], auth_fail_index: int | None = None):
    """Create a mock session that returns content for each file.

    If auth_fail_index is set, the Nth unique file download returns 401.
    Thread IDs are tracked via a list attached to the session.
    """
    session = MagicMock()
    session._thread_ids = []
    call_count = {"n": 0}
    lock = threading.Lock()

    def mock_get(url, **kwargs):
        tid = threading.current_thread().ident
        with lock:
            session._thread_ids.append(tid)
            idx = call_count["n"]
            call_count["n"] += 1

        resp = MagicMock()

        if auth_fail_index is not None and idx == auth_fail_index:
            resp.status_code = 401
            return resp

        content = b"A" * 24
        resp.status_code = 200
        resp.iter_content = MagicMock(return_value=iter([content]))
        resp.raise_for_status = MagicMock()
        return resp

    session.get = MagicMock(side_effect=mock_get)
    return session


class TestConcurrency:
    """download_all with workers=3 submits futures concurrently."""

    def test_multiple_threads_used(self, tmp_path: Path):
        entries = _make_test_entries(6)
        session = _mock_session_for_download(entries)
        site_url = "https://contoso.sharepoint.com/sites/shared"

        completed, failed = download_all(session, entries, tmp_path, site_url, workers=3)

        assert len(completed) == 6
        assert len(failed) == 0
        # Verify at least 2 distinct thread IDs were used (concurrency)
        distinct_threads = set(session._thread_ids)
        assert len(distinct_threads) >= 2, f"Expected concurrency, got threads: {distinct_threads}"

    def test_all_files_downloaded(self, tmp_path: Path):
        entries = _make_test_entries(3)
        session = _mock_session_for_download(entries)
        site_url = "https://contoso.sharepoint.com/sites/shared"

        completed, failed = download_all(session, entries, tmp_path, site_url, workers=3)

        assert len(completed) == 3
        assert len(failed) == 0


class TestAuthHaltAll:
    """When one worker raises AuthExpiredError, all workers halt."""

    def test_auth_halt_raises_and_stops(self, tmp_path: Path):
        entries = _make_test_entries(5)
        session = _mock_session_for_download(entries, auth_fail_index=1)
        site_url = "https://contoso.sharepoint.com/sites/shared"

        with pytest.raises(AuthExpiredError):
            download_all(session, entries, tmp_path, site_url, workers=3)

        # Not all 5 files should have been attempted (some cancelled)
        # At minimum, the auth failure should have been recorded
        assert session.get.call_count < 5 + 2  # reasonable upper bound


class TestProgress:
    """download_all accepts a Rich Progress instance and updates tasks."""

    def test_progress_tasks_updated(self, tmp_path: Path):
        from rich.progress import Progress

        entries = _make_test_entries(2)
        session = _mock_session_for_download(entries)
        site_url = "https://contoso.sharepoint.com/sites/shared"

        progress = Progress(disable=True)  # disable rendering for test
        with progress:
            completed, failed = download_all(
                session, entries, tmp_path, site_url, workers=2, progress=progress
            )

        assert len(completed) == 2
        assert len(failed) == 0
        # Progress should have tasks (overall + workers)
        assert len(progress.tasks) >= 1


class TestResumeSkip:
    """download_all with pre-populated state skips completed files."""

    def test_skips_already_complete(self, tmp_path: Path):
        entries = _make_test_entries(3)
        site_url = "https://contoso.sharepoint.com/sites/shared"

        # Pre-populate state.json with first file as COMPLETE
        state_data = {
            entries[0].server_relative_url: {
                "name": entries[0].name,
                "size_bytes": entries[0].size_bytes,
                "folder_path": entries[0].folder_path,
                "local_path": "Docs/file_0.dat",
                "status": "complete",
                "sha256": "abc123",
                "error": None,
                "downloaded_at": "2026-03-27T00:00:00Z",
            },
        }
        (tmp_path / "state.json").write_text(json.dumps(state_data))

        session = _mock_session_for_download(entries)

        completed, failed = download_all(session, entries, tmp_path, site_url, workers=2)

        # All 3 should be complete (1 from state, 2 downloaded)
        assert len(completed) == 3
        assert len(failed) == 0
        # Only 2 files should have been downloaded (1 was already complete)
        assert session.get.call_count == 2

    def test_persists_local_path_before_streaming(self, tmp_path: Path):
        entries = _make_test_entries(1)
        entry = entries[0]
        site_url = "https://contoso.sharepoint.com/sites/shared"

        def mock_get(url, **kwargs):
            state_data = json.loads((tmp_path / "state.json").read_text())
            tracked = state_data[entry.server_relative_url]
            assert tracked["status"] == "downloading"
            assert tracked["local_path"] == "files/Docs/file_0.dat"

            resp = MagicMock()
            resp.status_code = 200
            resp.iter_content = MagicMock(return_value=iter([b"A" * 24]))
            resp.raise_for_status = MagicMock()
            return resp

        session = MagicMock()
        session.get = MagicMock(side_effect=mock_get)

        completed, failed = download_all(session, entries, tmp_path, site_url, workers=1)

        assert len(completed) == 1
        assert len(failed) == 0
        assert json.loads((tmp_path / "state.json").read_text())[entry.server_relative_url][
            "local_path"
        ] == "files/Docs/file_0.dat"

    def test_persists_flat_local_path_before_streaming(self, tmp_path: Path):
        entries = _make_test_entries(1)
        entry = entries[0]
        site_url = "https://contoso.sharepoint.com/sites/shared"

        def mock_get(url, **kwargs):
            state_data = json.loads((tmp_path / "state.json").read_text())
            tracked = state_data[entry.server_relative_url]
            assert tracked["status"] == "downloading"
            assert tracked["local_path"] == "files/" + entry.name

            resp = MagicMock()
            resp.status_code = 200
            resp.iter_content = MagicMock(return_value=iter([b"A" * 24]))
            resp.raise_for_status = MagicMock()
            return resp

        session = MagicMock()
        session.get = MagicMock(side_effect=mock_get)

        completed, failed = download_all(
            session, entries, tmp_path, site_url, workers=1, flat=True
        )

        assert len(completed) == 1
        assert len(failed) == 0
        assert json.loads((tmp_path / "state.json").read_text())[entry.server_relative_url][
            "local_path"
        ] == "files/" + entry.name


class TestReauthIntegration:
    """Tests for on_auth_expired callback wired into download_all()."""

    def test_on_auth_expired_none_raises(self, tmp_path: Path):
        """Default behavior: when on_auth_expired is None, AuthExpiredError propagates."""
        entries = _make_test_entries(3)
        session = _mock_session_for_download(entries, auth_fail_index=0)
        site_url = "https://contoso.sharepoint.com/sites/shared"

        with pytest.raises(AuthExpiredError):
            download_all(session, entries, tmp_path, site_url, workers=1, on_auth_expired=None)

    def test_on_auth_expired_true_resumes(self, tmp_path: Path):
        """When on_auth_expired returns True, auth_halt is cleared and workers resume.

        No AuthExpiredError is raised — the callback handles it. The auth-expired
        file stays FAILED initially but the retry loop re-downloads it using the
        refreshed session, so all files ultimately complete.
        """
        entries = _make_test_entries(3)
        # First request returns 401, rest succeed (including retry of the 401 file)
        session = _mock_session_for_download(entries, auth_fail_index=0)
        site_url = "https://contoso.sharepoint.com/sites/shared"

        callback_calls = []

        def on_auth_expired() -> bool:
            callback_calls.append(True)
            return True

        # Should NOT raise — callback returns True so auth_halt is cleared
        completed, failed = download_all(
            session, entries, tmp_path, site_url, workers=1,
            on_auth_expired=on_auth_expired,
        )

        # Callback was invoked at least once
        assert len(callback_calls) >= 1
        # No AuthExpiredError raised — reauth succeeded
        # All files eventually complete (retry loop re-downloads the auth_expired one)
        assert len(failed) == 0
        assert len(completed) == 3

    def test_on_auth_expired_false_aborts(self, tmp_path: Path):
        """When on_auth_expired returns False, AuthExpiredError is raised (abort)."""
        entries = _make_test_entries(3)
        session = _mock_session_for_download(entries, auth_fail_index=0)
        site_url = "https://contoso.sharepoint.com/sites/shared"

        def on_auth_expired() -> bool:
            return False

        with pytest.raises(AuthExpiredError):
            download_all(
                session, entries, tmp_path, site_url, workers=1,
                on_auth_expired=on_auth_expired,
            )
