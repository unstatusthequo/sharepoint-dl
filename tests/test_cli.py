"""Tests for sharepoint_dl.cli.main — typer CLI subcommands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from sharepoint_dl.cli.main import app
from sharepoint_dl.enumerator.traversal import AuthExpiredError, FileEntry

runner = CliRunner()

SITE_URL = "https://contoso.sharepoint.com/sites/shared"
TEST_URL = "https://contoso.sharepoint.com/sites/shared/Shared%20Documents/Images"


class TestAuthCommand:
    """sharepoint-dl auth subcommand."""

    @patch("sharepoint_dl.cli.main.harvest_session")
    def test_auth_command_success(self, mock_harvest):
        """auth succeeds — exit 0, 'Session saved' in output."""
        mock_harvest.return_value = Path("/tmp/session.json")

        result = runner.invoke(app, ["auth", TEST_URL])

        assert result.exit_code == 0
        assert "Session saved" in result.output
        mock_harvest.assert_called_once_with(TEST_URL)

    @patch("sharepoint_dl.cli.main.harvest_session")
    def test_auth_command_timeout(self, mock_harvest):
        """auth times out — exit 1."""
        mock_harvest.side_effect = TimeoutError("timed out")

        result = runner.invoke(app, ["auth", TEST_URL])

        assert result.exit_code == 1


class TestListCommand:
    """sharepoint-dl list subcommand."""

    @patch("sharepoint_dl.cli.main.enumerate_files")
    @patch("sharepoint_dl.cli.main.validate_session")
    @patch("sharepoint_dl.cli.main.load_session")
    def test_list_command(self, mock_load, mock_validate, mock_enumerate):
        """list with valid session — shows file count."""
        mock_session = MagicMock()
        mock_load.return_value = mock_session
        mock_validate.return_value = True
        mock_enumerate.return_value = [
            FileEntry(name="file1.E01", server_relative_url="/a/file1.E01", size_bytes=1000, folder_path="/a"),
            FileEntry(name="file2.E01", server_relative_url="/a/file2.E01", size_bytes=2000, folder_path="/a"),
            FileEntry(name="file3.L01", server_relative_url="/b/file3.L01", size_bytes=3000, folder_path="/b"),
        ]

        result = runner.invoke(app, ["list", TEST_URL, "--root-folder", "/sites/shared/Images"])

        assert result.exit_code == 0
        assert "3 files" in result.output

    @patch("sharepoint_dl.cli.main.load_session")
    def test_list_no_session(self, mock_load):
        """list with no session — exit 1, helpful message."""
        mock_load.return_value = None

        result = runner.invoke(app, ["list", TEST_URL, "--root-folder", "/sites/shared/Images"])

        assert result.exit_code == 1
        assert "No active session" in result.output


class TestDownloadCommand:
    """sharepoint-dl download subcommand."""

    def test_download_stub(self):
        """download raises NotImplementedError or exits with Phase 2 message."""
        result = runner.invoke(app, ["download", TEST_URL, "/tmp/dest"])

        # Should indicate not implemented
        assert result.exit_code == 1
        assert "Phase 2" in result.output


class TestHelpOutput:
    """No args shows help."""

    def test_no_args_shows_help(self):
        """Invoking with no args shows help text."""
        result = runner.invoke(app, [])

        # Typer no_args_is_help exits with code 0 (shell) but CliRunner sees 2
        assert result.exit_code in (0, 2)
        assert "auth" in result.output
        assert "list" in result.output
        assert "download" in result.output
