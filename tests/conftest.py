"""Shared test fixtures for sharepoint_dl tests."""

import json
from pathlib import Path

import pytest


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
