"""Unit tests for sharepoint_dl.downloader.engine module."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from sharepoint_dl.downloader.engine import (
    CHUNK_SIZE,
    _build_download_url,
    _download_file,
)
from sharepoint_dl.enumerator.traversal import AuthExpiredError, FileEntry


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
