"""Unit tests for sharepoint_dl.downloader.log module."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from sharepoint_dl.downloader.log import setup_download_logger, shutdown_download_logger


class TestSetupDownloadLogger:
    """setup_download_logger creates a file-only logger."""

    def test_creates_logger_with_file_handler(self, tmp_path: Path):
        logger = setup_download_logger(tmp_path)
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1

    def test_file_handler_points_to_download_log(self, tmp_path: Path):
        logger = setup_download_logger(tmp_path)
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert file_handlers[0].baseFilename == str(tmp_path / "download.log")
        shutdown_download_logger()

    def test_no_stream_handler_attached(self, tmp_path: Path):
        logger = setup_download_logger(tmp_path)
        stream_handlers = [
            h for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 0
        shutdown_download_logger()

    def test_file_opened_in_append_mode(self, tmp_path: Path):
        logger = setup_download_logger(tmp_path)
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert file_handlers[0].mode == "a"
        shutdown_download_logger()

    def test_log_format_matches_spec(self, tmp_path: Path):
        logger = setup_download_logger(tmp_path)
        logger.info("test message")
        shutdown_download_logger()

        log_content = (tmp_path / "download.log").read_text()
        # Format: "YYYY-MM-DD HH:MM:SS | LEVEL | message"
        import re
        pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| INFO \| test message"
        assert re.search(pattern, log_content), f"Log content did not match expected format: {log_content!r}"

    def test_calling_twice_does_not_duplicate_handlers(self, tmp_path: Path):
        setup_download_logger(tmp_path)
        logger = setup_download_logger(tmp_path)
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        shutdown_download_logger()

    def test_propagate_is_false(self, tmp_path: Path):
        logger = setup_download_logger(tmp_path)
        assert logger.propagate is False
        shutdown_download_logger()


class TestShutdownDownloadLogger:
    """shutdown_download_logger removes and closes file handlers."""

    def test_removes_file_handler(self, tmp_path: Path):
        logger = setup_download_logger(tmp_path)
        shutdown_download_logger()
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0

    def test_handler_is_closed(self, tmp_path: Path):
        logger = setup_download_logger(tmp_path)
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        handler = file_handlers[0]
        shutdown_download_logger()
        # After close, the stream should be closed
        assert handler.stream.closed
