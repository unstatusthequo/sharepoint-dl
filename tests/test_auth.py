"""Tests for the auth module (AUTH-01, AUTH-02)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestHarvestSession:
    """Tests for harvest_session (AUTH-01)."""

    def test_harvest_session_writes_file(self, tmp_path: Path, mock_storage_state: dict):
        """Mock Playwright context, verify session.json created with correct structure."""
        from sharepoint_dl.auth.browser import harvest_session

        storage_state_file = tmp_path / "storage_state.json"
        storage_state_file.write_text(json.dumps(mock_storage_state))

        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.cookies.return_value = mock_storage_state["cookies"]
        mock_context.storage_state.side_effect = lambda path: (
            Path(path).write_text(json.dumps(mock_storage_state))
        )
        mock_context.new_page.return_value = mock_page

        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_pw = MagicMock()
        mock_pw.chromium.launch.return_value = mock_browser

        mock_pw_cm = MagicMock()
        mock_pw_cm.__enter__ = MagicMock(return_value=mock_pw)
        mock_pw_cm.__exit__ = MagicMock(return_value=False)

        with patch("sharepoint_dl.auth.browser.sync_playwright", return_value=mock_pw_cm):
            with patch("sharepoint_dl.auth.browser.SESSION_DIR", tmp_path):
                result = harvest_session("https://contoso.sharepoint.com/sites/shared")

        assert result.exists()
        session_data = json.loads(result.read_text())
        assert "_host" in session_data
        assert session_data["_host"] == "contoso.sharepoint.com"


class TestLoadSession:
    """Tests for load_session and build_session (AUTH-02)."""

    def test_load_session_injects_cookies(self, mock_session_path: Path):
        """Load from mock session file, verify requests.Session has FedAuth cookie."""
        from sharepoint_dl.auth.session import load_session

        with patch("sharepoint_dl.auth.session.SESSION_DIR", mock_session_path.parent):
            with patch(
                "sharepoint_dl.auth.session._session_file",
                return_value=mock_session_path,
            ):
                session = load_session("https://contoso.sharepoint.com/sites/shared")

        assert session is not None
        cookie_names = [c.name for c in session.cookies]
        assert "FedAuth" in cookie_names

    def test_load_session_missing_file(self, tmp_path: Path):
        """Returns None when session file is absent."""
        from sharepoint_dl.auth.session import load_session

        nonexistent = tmp_path / "no_such_file.json"
        with patch(
            "sharepoint_dl.auth.session._session_file",
            return_value=nonexistent,
        ):
            result = load_session("https://contoso.sharepoint.com/sites/shared")

        assert result is None

    def test_host_mismatch_returns_none(self, mock_session_path: Path):
        """Returns None when stored host != requested host."""
        from sharepoint_dl.auth.session import load_session

        with patch(
            "sharepoint_dl.auth.session._session_file",
            return_value=mock_session_path,
        ):
            result = load_session("https://different-tenant.sharepoint.com/sites/other")

        assert result is None


class TestValidateSession:
    """Tests for validate_session."""

    def test_validate_session_active(self):
        """Mock 200 response, returns True."""
        from sharepoint_dl.auth.session import validate_session

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session.get.return_value = mock_response

        result = validate_session(
            mock_session, "https://contoso.sharepoint.com/sites/shared"
        )
        assert result is True

    def test_validate_session_expired(self):
        """Mock 401 response, returns False."""
        from sharepoint_dl.auth.session import validate_session

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_session.get.return_value = mock_response

        result = validate_session(
            mock_session, "https://contoso.sharepoint.com/sites/shared"
        )
        assert result is False
