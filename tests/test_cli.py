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
    """sharepoint-dl download subcommand calls enumerate then download_all."""

    @patch("sharepoint_dl.cli.main.download_all")
    @patch("sharepoint_dl.cli.main._make_progress")
    @patch("sharepoint_dl.cli.main.enumerate_files")
    @patch("sharepoint_dl.cli.main.validate_session")
    @patch("sharepoint_dl.cli.main.load_session")
    def test_download_calls_with_correct_args(
        self, mock_load, mock_validate, mock_enum, mock_progress, mock_dl
    ):
        """download calls enumerate_files then download_all with correct args."""
        mock_session = MagicMock()
        mock_load.return_value = mock_session
        mock_validate.return_value = True
        mock_enum.return_value = [
            FileEntry(name="f1.dat", server_relative_url="/a/f1.dat", size_bytes=100, folder_path="/a"),
        ]
        mock_progress_inst = MagicMock()
        mock_progress_inst.__enter__ = MagicMock(return_value=mock_progress_inst)
        mock_progress_inst.__exit__ = MagicMock(return_value=False)
        mock_progress.return_value = mock_progress_inst
        mock_dl.return_value = (["/a/f1.dat"], [])

        result = runner.invoke(
            app,
            ["download", TEST_URL, "/tmp/dest", "--root-folder", "/sites/shared/Docs", "--yes"],
        )

        assert result.exit_code == 0
        mock_enum.assert_called_once()
        mock_dl.assert_called_once()

    @patch("sharepoint_dl.cli.main.download_all")
    @patch("sharepoint_dl.cli.main._make_progress")
    @patch("sharepoint_dl.cli.main.enumerate_files")
    @patch("sharepoint_dl.cli.main.validate_session")
    @patch("sharepoint_dl.cli.main.load_session")
    def test_workers_flag_passed(
        self, mock_load, mock_validate, mock_enum, mock_progress, mock_dl
    ):
        """--workers flag is passed through to download_all."""
        mock_session = MagicMock()
        mock_load.return_value = mock_session
        mock_validate.return_value = True
        mock_enum.return_value = [
            FileEntry(name="f1.dat", server_relative_url="/a/f1.dat", size_bytes=100, folder_path="/a"),
        ]
        mock_progress_inst = MagicMock()
        mock_progress_inst.__enter__ = MagicMock(return_value=mock_progress_inst)
        mock_progress_inst.__exit__ = MagicMock(return_value=False)
        mock_progress.return_value = mock_progress_inst
        mock_dl.return_value = (["/a/f1.dat"], [])

        result = runner.invoke(
            app,
            ["download", TEST_URL, "/tmp/dest", "--root-folder", "/sites/shared/Docs", "--yes", "--workers", "5"],
        )

        assert result.exit_code == 0
        _, kwargs = mock_dl.call_args
        assert kwargs.get("workers") == 5 or mock_dl.call_args[0][4] == 5 if len(mock_dl.call_args[0]) > 4 else kwargs.get("workers") == 5


class TestDownloadConfirmation:
    """Confirmation prompt before downloading."""

    @patch("sharepoint_dl.cli.main.download_all")
    @patch("sharepoint_dl.cli.main._make_progress")
    @patch("sharepoint_dl.cli.main.enumerate_files")
    @patch("sharepoint_dl.cli.main.validate_session")
    @patch("sharepoint_dl.cli.main.load_session")
    def test_confirmation_prompt_shown(
        self, mock_load, mock_validate, mock_enum, mock_progress, mock_dl
    ):
        """Without --yes, confirmation prompt is shown."""
        mock_load.return_value = MagicMock()
        mock_validate.return_value = True
        mock_enum.return_value = [
            FileEntry(name="f1.dat", server_relative_url="/a/f1.dat", size_bytes=1024, folder_path="/a"),
        ]
        mock_progress_inst = MagicMock()
        mock_progress_inst.__enter__ = MagicMock(return_value=mock_progress_inst)
        mock_progress_inst.__exit__ = MagicMock(return_value=False)
        mock_progress.return_value = mock_progress_inst
        mock_dl.return_value = (["/a/f1.dat"], [])

        # Answer 'y' to the prompt
        result = runner.invoke(
            app,
            ["download", TEST_URL, "/tmp/dest", "--root-folder", "/sites/shared/Docs"],
            input="y\n",
        )

        assert "1 file" in result.output or "1.0 KB" in result.output

    @patch("sharepoint_dl.cli.main.download_all")
    @patch("sharepoint_dl.cli.main._make_progress")
    @patch("sharepoint_dl.cli.main.enumerate_files")
    @patch("sharepoint_dl.cli.main.validate_session")
    @patch("sharepoint_dl.cli.main.load_session")
    def test_yes_skips_prompt(
        self, mock_load, mock_validate, mock_enum, mock_progress, mock_dl
    ):
        """--yes flag skips the confirmation prompt."""
        mock_load.return_value = MagicMock()
        mock_validate.return_value = True
        mock_enum.return_value = [
            FileEntry(name="f1.dat", server_relative_url="/a/f1.dat", size_bytes=1024, folder_path="/a"),
        ]
        mock_progress_inst = MagicMock()
        mock_progress_inst.__enter__ = MagicMock(return_value=mock_progress_inst)
        mock_progress_inst.__exit__ = MagicMock(return_value=False)
        mock_progress.return_value = mock_progress_inst
        mock_dl.return_value = (["/a/f1.dat"], [])

        result = runner.invoke(
            app,
            ["download", TEST_URL, "/tmp/dest", "--root-folder", "/sites/shared/Docs", "--yes"],
        )

        assert result.exit_code == 0


class TestDownloadExitCode:
    """Exit code 1 on failures, 0 on success."""

    @patch("sharepoint_dl.cli.main.download_all")
    @patch("sharepoint_dl.cli.main._make_progress")
    @patch("sharepoint_dl.cli.main.enumerate_files")
    @patch("sharepoint_dl.cli.main.validate_session")
    @patch("sharepoint_dl.cli.main.load_session")
    def test_exit_code_0_on_success(
        self, mock_load, mock_validate, mock_enum, mock_progress, mock_dl
    ):
        mock_load.return_value = MagicMock()
        mock_validate.return_value = True
        mock_enum.return_value = [
            FileEntry(name="f1.dat", server_relative_url="/a/f1.dat", size_bytes=100, folder_path="/a"),
        ]
        mock_progress_inst = MagicMock()
        mock_progress_inst.__enter__ = MagicMock(return_value=mock_progress_inst)
        mock_progress_inst.__exit__ = MagicMock(return_value=False)
        mock_progress.return_value = mock_progress_inst
        mock_dl.return_value = (["/a/f1.dat"], [])

        result = runner.invoke(
            app,
            ["download", TEST_URL, "/tmp/dest", "--root-folder", "/sites/shared/Docs", "--yes"],
        )
        assert result.exit_code == 0

    @patch("sharepoint_dl.cli.main.download_all")
    @patch("sharepoint_dl.cli.main._make_progress")
    @patch("sharepoint_dl.cli.main.enumerate_files")
    @patch("sharepoint_dl.cli.main.validate_session")
    @patch("sharepoint_dl.cli.main.load_session")
    def test_exit_code_1_on_failures(
        self, mock_load, mock_validate, mock_enum, mock_progress, mock_dl
    ):
        mock_load.return_value = MagicMock()
        mock_validate.return_value = True
        mock_enum.return_value = [
            FileEntry(name="f1.dat", server_relative_url="/a/f1.dat", size_bytes=100, folder_path="/a"),
            FileEntry(name="f2.dat", server_relative_url="/a/f2.dat", size_bytes=200, folder_path="/a"),
        ]
        mock_progress_inst = MagicMock()
        mock_progress_inst.__enter__ = MagicMock(return_value=mock_progress_inst)
        mock_progress_inst.__exit__ = MagicMock(return_value=False)
        mock_progress.return_value = mock_progress_inst
        mock_dl.return_value = (["/a/f1.dat"], [("/a/f2.dat", "Connection reset")])

        result = runner.invoke(
            app,
            ["download", TEST_URL, "/tmp/dest", "--root-folder", "/sites/shared/Docs", "--yes"],
        )
        assert result.exit_code == 1


class TestErrorSummary:
    """Failed files shown in error summary table."""

    @patch("sharepoint_dl.cli.main.download_all")
    @patch("sharepoint_dl.cli.main._make_progress")
    @patch("sharepoint_dl.cli.main.enumerate_files")
    @patch("sharepoint_dl.cli.main.validate_session")
    @patch("sharepoint_dl.cli.main.load_session")
    def test_error_table_shows_failures(
        self, mock_load, mock_validate, mock_enum, mock_progress, mock_dl
    ):
        mock_load.return_value = MagicMock()
        mock_validate.return_value = True
        mock_enum.return_value = [
            FileEntry(name="f1.dat", server_relative_url="/a/f1.dat", size_bytes=100, folder_path="/a"),
            FileEntry(name="f2.dat", server_relative_url="/a/f2.dat", size_bytes=200, folder_path="/a"),
        ]
        mock_progress_inst = MagicMock()
        mock_progress_inst.__enter__ = MagicMock(return_value=mock_progress_inst)
        mock_progress_inst.__exit__ = MagicMock(return_value=False)
        mock_progress.return_value = mock_progress_inst
        mock_dl.return_value = (["/a/f1.dat"], [("/a/f2.dat", "Connection reset")])

        result = runner.invoke(
            app,
            ["download", TEST_URL, "/tmp/dest", "--root-folder", "/sites/shared/Docs", "--yes"],
        )

        assert "f2.dat" in result.output or "/a/f2.dat" in result.output
        assert "Connection reset" in result.output


class TestDownloadAuthExpired:
    """AuthExpiredError during download prints re-auth message."""

    @patch("sharepoint_dl.cli.main.download_all")
    @patch("sharepoint_dl.cli.main._make_progress")
    @patch("sharepoint_dl.cli.main.enumerate_files")
    @patch("sharepoint_dl.cli.main.validate_session")
    @patch("sharepoint_dl.cli.main.load_session")
    def test_auth_expired_message(
        self, mock_load, mock_validate, mock_enum, mock_progress, mock_dl
    ):
        mock_load.return_value = MagicMock()
        mock_validate.return_value = True
        mock_enum.return_value = [
            FileEntry(name="f1.dat", server_relative_url="/a/f1.dat", size_bytes=100, folder_path="/a"),
        ]
        mock_progress_inst = MagicMock()
        mock_progress_inst.__enter__ = MagicMock(return_value=mock_progress_inst)
        mock_progress_inst.__exit__ = MagicMock(return_value=False)
        mock_progress.return_value = mock_progress_inst
        mock_dl.side_effect = AuthExpiredError("Session expired")

        result = runner.invoke(
            app,
            ["download", TEST_URL, "/tmp/dest", "--root-folder", "/sites/shared/Docs", "--yes"],
        )

        assert result.exit_code == 1
        assert "re-authenticate" in result.output.lower() or "Re-authenticate" in result.output


class TestDownloadCompleteSummary:
    """On success, prints total files, size, and elapsed time."""

    @patch("sharepoint_dl.cli.main.download_all")
    @patch("sharepoint_dl.cli.main._make_progress")
    @patch("sharepoint_dl.cli.main.enumerate_files")
    @patch("sharepoint_dl.cli.main.validate_session")
    @patch("sharepoint_dl.cli.main.load_session")
    def test_success_summary(
        self, mock_load, mock_validate, mock_enum, mock_progress, mock_dl
    ):
        mock_load.return_value = MagicMock()
        mock_validate.return_value = True
        mock_enum.return_value = [
            FileEntry(name="f1.dat", server_relative_url="/a/f1.dat", size_bytes=1024, folder_path="/a"),
            FileEntry(name="f2.dat", server_relative_url="/a/f2.dat", size_bytes=2048, folder_path="/a"),
        ]
        mock_progress_inst = MagicMock()
        mock_progress_inst.__enter__ = MagicMock(return_value=mock_progress_inst)
        mock_progress_inst.__exit__ = MagicMock(return_value=False)
        mock_progress.return_value = mock_progress_inst
        mock_dl.return_value = (["/a/f1.dat", "/a/f2.dat"], [])

        result = runner.invoke(
            app,
            ["download", TEST_URL, "/tmp/dest", "--root-folder", "/sites/shared/Docs", "--yes"],
        )

        assert result.exit_code == 0
        assert "2" in result.output  # file count


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
