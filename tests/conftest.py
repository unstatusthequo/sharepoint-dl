"""Shared test fixtures for sharepoint_dl tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sharepoint_dl.enumerator.traversal import FileEntry


@pytest.fixture
def mock_storage_state() -> dict:
    """Return a dict matching Playwright storageState JSON with FedAuth and rtFa cookies."""
    return {
        "cookies": [
            {
                "name": "FedAuth",
                "value": "77u/PD94bWwgdmVyc2lvbj0iMS4wIi...",
                "domain": "contoso.sharepoint.com",
                "path": "/",
                "expires": -1,
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            },
            {
                "name": "rtFa",
                "value": "someRtFaTokenValue123==",
                "domain": "contoso.sharepoint.com",
                "path": "/",
                "expires": -1,
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            },
        ],
        "origins": [],
    }


@pytest.fixture
def mock_session_path(tmp_path: Path, mock_storage_state: dict) -> Path:
    """Write mock_storage_state to a tmp_path file, return the path."""
    session_file = tmp_path / "session.json"
    data = {**mock_storage_state, "_host": "contoso.sharepoint.com"}
    session_file.write_text(json.dumps(data))
    return session_file


@pytest.fixture
def mock_sharepoint_responses() -> dict:
    """Return a dict of URL patterns to JSON response bodies for SharePoint REST API."""
    return {
        "files_page1": {
            "d": {
                "results": [
                    {
                        "Name": "evidence_001.E01",
                        "ServerRelativeUrl": "/sites/shared/Images/custodian1/evidence_001.E01",
                        "Length": "2147483648",
                        "TimeLastModified": "2026-01-15T10:30:00Z",
                    },
                    {
                        "Name": "evidence_002.E01",
                        "ServerRelativeUrl": "/sites/shared/Images/custodian1/evidence_002.E01",
                        "Length": "1073741824",
                        "TimeLastModified": "2026-01-15T11:00:00Z",
                    },
                ],
                "__next": "https://contoso.sharepoint.com/_api/web/GetFolderByServerRelativeUrl('/sites/shared/Images/custodian1')/Files?$skiptoken=2",
            }
        },
        "files_page2": {
            "d": {
                "results": [
                    {
                        "Name": "evidence_003.L01",
                        "ServerRelativeUrl": "/sites/shared/Images/custodian1/evidence_003.L01",
                        "Length": "536870912",
                        "TimeLastModified": "2026-01-15T11:30:00Z",
                    },
                ]
            }
        },
        "folders": {
            "d": {
                "results": [
                    {
                        "Name": "custodian1",
                        "ServerRelativeUrl": "/sites/shared/Images/custodian1",
                        "ItemCount": 3,
                    },
                    {
                        "Name": "custodian2",
                        "ServerRelativeUrl": "/sites/shared/Images/custodian2",
                        "ItemCount": 5,
                    },
                ]
            }
        },
    }


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


@pytest.fixture
def mock_download_response():
    """Factory fixture returning a mock requests.Response with configurable chunks.

    Usage:
        resp = mock_download_response(content=b"file data", chunk_size=4)
    """
    from unittest.mock import MagicMock

    def _factory(
        content: bytes = b"test file content",
        status_code: int = 200,
        chunk_size: int = 8_388_608,
        headers: dict | None = None,
    ) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.headers = headers or {}

        # Split content into chunks
        chunks = [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]
        resp.iter_content = MagicMock(return_value=iter(chunks))

        def raise_for_status():
            if 400 <= status_code < 600:
                from requests.exceptions import HTTPError

                raise HTTPError(response=resp)

        resp.raise_for_status = raise_for_status
        return resp

    return _factory
