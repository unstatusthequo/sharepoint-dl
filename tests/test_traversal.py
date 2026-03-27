"""Tests for sharepoint_dl.enumerator.traversal — file enumeration with pagination."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from sharepoint_dl.enumerator.traversal import (
    AuthExpiredError,
    FileEntry,
    enumerate_files,
)

SITE_URL = "https://contoso.sharepoint.com/sites/shared"
ROOT_PATH = "/sites/shared/Images"


def _make_files_response(files: list[dict], next_url: str | None = None) -> dict:
    """Build a SharePoint REST API files response."""
    resp = {"d": {"results": files}}
    if next_url:
        resp["d"]["__next"] = next_url
    return resp


def _make_folders_response(folders: list[dict], next_url: str | None = None) -> dict:
    """Build a SharePoint REST API folders response."""
    resp = {"d": {"results": folders}}
    if next_url:
        resp["d"]["__next"] = next_url
    return resp


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """Create a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status.return_value = None
    return resp


def _mock_401_response() -> MagicMock:
    """Create a mock 401 response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 401
    resp.json.return_value = {}
    return resp


class TestRecursionIntoSubfolders:
    """enumerate_files discovers and traverses subfolders."""

    def test_recursion_into_subfolders(self):
        """Root folder has 2 subfolders, each with files — all files returned."""
        session = MagicMock(spec=requests.Session)

        # Build responses keyed by URL pattern
        root_files = _make_files_response([])
        root_folders = _make_folders_response([
            {"ServerRelativeUrl": "/sites/shared/Images/custodian1"},
            {"ServerRelativeUrl": "/sites/shared/Images/custodian2"},
        ])
        c1_files = _make_files_response([
            {"Name": "file1.E01", "ServerRelativeUrl": "/sites/shared/Images/custodian1/file1.E01", "Length": "100"},
        ])
        c1_folders = _make_folders_response([])
        c2_files = _make_files_response([
            {"Name": "file2.E01", "ServerRelativeUrl": "/sites/shared/Images/custodian2/file2.E01", "Length": "200"},
            {"Name": "file3.L01", "ServerRelativeUrl": "/sites/shared/Images/custodian2/file3.L01", "Length": "300"},
        ])
        c2_folders = _make_folders_response([])

        def side_effect(url, **kwargs):
            if "Images')/Files" in url or "Images%2F" in url and "Files" in url:
                # Root files or encoded root files
                if "custodian1" in url and "Files" in url:
                    return _mock_response(json_data=c1_files)
                elif "custodian2" in url and "Files" in url:
                    return _mock_response(json_data=c2_files)
                else:
                    return _mock_response(json_data=root_files)
            elif "Folders" in url:
                if "custodian1" in url:
                    return _mock_response(json_data=c1_folders)
                elif "custodian2" in url:
                    return _mock_response(json_data=c2_folders)
                else:
                    return _mock_response(json_data=root_folders)
            return _mock_response(json_data=_make_files_response([]))

        session.get.side_effect = side_effect

        result = enumerate_files(session, SITE_URL, ROOT_PATH)

        assert len(result) == 3
        names = {f.name for f in result}
        assert names == {"file1.E01", "file2.E01", "file3.L01"}


class TestPagination:
    """enumerate_files follows __next pagination links."""

    def test_pagination_follows_next_link(self):
        """Page 1 has __next pointing to page 2; files from both pages returned."""
        session = MagicMock(spec=requests.Session)

        page1 = _make_files_response(
            [{"Name": "file1.E01", "ServerRelativeUrl": "/sites/shared/Images/file1.E01", "Length": "100"}],
            next_url="https://contoso.sharepoint.com/_api/next-page",
        )
        page2 = _make_files_response(
            [{"Name": "file2.E01", "ServerRelativeUrl": "/sites/shared/Images/file2.E01", "Length": "200"}],
        )
        folders = _make_folders_response([])

        call_count = 0

        def side_effect(url, **kwargs):
            nonlocal call_count
            if "next-page" in url:
                return _mock_response(json_data=page2)
            elif "Files" in url:
                return _mock_response(json_data=page1)
            elif "Folders" in url:
                return _mock_response(json_data=folders)
            return _mock_response(json_data=_make_files_response([]))

        session.get.side_effect = side_effect

        result = enumerate_files(session, SITE_URL, ROOT_PATH)

        assert len(result) == 2
        names = [f.name for f in result]
        assert "file1.E01" in names
        assert "file2.E01" in names

    def test_no_pagination_needed(self):
        """Single-page response returns correct file count."""
        session = MagicMock(spec=requests.Session)

        files = _make_files_response([
            {"Name": f"file{i}.E01", "ServerRelativeUrl": f"/sites/shared/Images/file{i}.E01", "Length": str(i * 100)}
            for i in range(5)
        ])
        folders = _make_folders_response([])

        def side_effect(url, **kwargs):
            if "Files" in url:
                return _mock_response(json_data=files)
            elif "Folders" in url:
                return _mock_response(json_data=folders)
            return _mock_response(json_data=_make_files_response([]))

        session.get.side_effect = side_effect

        result = enumerate_files(session, SITE_URL, ROOT_PATH)
        assert len(result) == 5


class TestFileCountAccuracy:
    """File count matches expected across multiple folders and pages."""

    def test_file_count_accuracy(self):
        """Total file count correct across multiple folders with pagination."""
        session = MagicMock(spec=requests.Session)

        # Root: 0 files, 2 subfolders
        # Subfolder1: 3 files (2 pages), 0 subfolders
        # Subfolder2: 2 files (1 page), 0 subfolders
        root_files = _make_files_response([])
        root_folders = _make_folders_response([
            {"ServerRelativeUrl": "/sites/shared/Images/sub1"},
            {"ServerRelativeUrl": "/sites/shared/Images/sub2"},
        ])
        sub1_page1 = _make_files_response(
            [
                {"Name": "a.E01", "ServerRelativeUrl": "/sites/shared/Images/sub1/a.E01", "Length": "100"},
                {"Name": "b.E01", "ServerRelativeUrl": "/sites/shared/Images/sub1/b.E01", "Length": "200"},
            ],
            next_url="https://contoso.sharepoint.com/_api/sub1-next",
        )
        sub1_page2 = _make_files_response([
            {"Name": "c.E01", "ServerRelativeUrl": "/sites/shared/Images/sub1/c.E01", "Length": "300"},
        ])
        sub1_folders = _make_folders_response([])
        sub2_files = _make_files_response([
            {"Name": "d.E01", "ServerRelativeUrl": "/sites/shared/Images/sub2/d.E01", "Length": "400"},
            {"Name": "e.L01", "ServerRelativeUrl": "/sites/shared/Images/sub2/e.L01", "Length": "500"},
        ])
        sub2_folders = _make_folders_response([])

        def side_effect(url, **kwargs):
            if "sub1-next" in url:
                return _mock_response(json_data=sub1_page2)
            elif "sub1" in url and "Files" in url:
                return _mock_response(json_data=sub1_page1)
            elif "sub1" in url and "Folders" in url:
                return _mock_response(json_data=sub1_folders)
            elif "sub2" in url and "Files" in url:
                return _mock_response(json_data=sub2_files)
            elif "sub2" in url and "Folders" in url:
                return _mock_response(json_data=sub2_folders)
            elif "Files" in url:
                return _mock_response(json_data=root_files)
            elif "Folders" in url:
                return _mock_response(json_data=root_folders)
            return _mock_response(json_data=_make_files_response([]))

        session.get.side_effect = side_effect

        result = enumerate_files(session, SITE_URL, ROOT_PATH)
        assert len(result) == 5
        names = {f.name for f in result}
        assert names == {"a.E01", "b.E01", "c.E01", "d.E01", "e.L01"}


class TestAuthExpiry:
    """401/403 raises AuthExpiredError immediately — no retry, no silent skip."""

    def test_auth_expiry_halts(self):
        """401 response mid-traversal raises AuthExpiredError."""
        session = MagicMock(spec=requests.Session)

        session.get.return_value = _mock_401_response()

        with pytest.raises(AuthExpiredError, match="Session expired"):
            enumerate_files(session, SITE_URL, ROOT_PATH)


class TestUrlEncoding:
    """Folder paths with special characters are URL-encoded."""

    def test_url_encoding_spaces(self):
        """Folder path with spaces gets encoded in API URL."""
        session = MagicMock(spec=requests.Session)

        files = _make_files_response([
            {"Name": "report.pdf", "ServerRelativeUrl": "/sites/shared/My Documents/report.pdf", "Length": "1000"},
        ])
        folders = _make_folders_response([])

        def side_effect(url, **kwargs):
            if "Files" in url:
                return _mock_response(json_data=files)
            elif "Folders" in url:
                return _mock_response(json_data=folders)
            return _mock_response(json_data=_make_files_response([]))

        session.get.side_effect = side_effect

        path_with_spaces = "/sites/shared/My Documents"
        result = enumerate_files(session, SITE_URL, path_with_spaces)

        assert len(result) == 1
        # Verify URL encoding was applied — the space should be %20
        calls = session.get.call_args_list
        first_url = calls[0][0][0]
        assert "My%20Documents" in first_url
        assert "My Documents" not in first_url
