"""Download logging: file-only logger for audit trail.

Creates a timestamped log file in the download destination directory.
Uses FileHandler only -- no StreamHandler -- to avoid corrupting the Rich TUI.
"""

from __future__ import annotations

import logging
from pathlib import Path

LOGGER_NAME = "sharepoint_dl"


def setup_download_logger(dest_dir: Path) -> logging.Logger:
    """Create or reconfigure the download logger with a FileHandler.

    Idempotent: removes any existing FileHandlers before adding a new one,
    so calling twice does not duplicate handlers.

    Args:
        dest_dir: Directory where download.log will be created/appended.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(LOGGER_NAME)

    # Remove existing FileHandlers (idempotent setup)
    for handler in logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            handler.close()
            logger.removeHandler(handler)

    file_handler = logging.FileHandler(dest_dir / "download.log", mode="a")
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    return logger


def shutdown_download_logger() -> None:
    """Remove and close all FileHandlers on the download logger.

    Ensures file handles are released after download completes.
    """
    logger = logging.getLogger(LOGGER_NAME)
    for handler in logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            handler.close()
            logger.removeHandler(handler)
