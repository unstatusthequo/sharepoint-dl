"""Playwright-based session harvest for SharePoint authentication."""

from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from sharepoint_dl.auth.session import SESSION_DIR, save_session

AUTH_COOKIE_NAMES = {"FedAuth", "rtFa"}


def harvest_session(sharepoint_url: str, timeout_seconds: int = 120) -> Path:
    """Open a headed Chromium browser, wait for auth cookies, save session.

    Args:
        sharepoint_url: The SharePoint site URL to authenticate against.
        timeout_seconds: Maximum time to wait for authentication (default 120s).

    Returns:
        Path to the saved session.json file.

    Raises:
        TimeoutError: If authentication is not detected within timeout_seconds.
    """
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    tmp_storage = SESSION_DIR / "storage_state_tmp.json"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(sharepoint_url)

            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                cookies = context.cookies()
                cookie_names = {c["name"] for c in cookies}
                if cookie_names & AUTH_COOKIE_NAMES:
                    context.storage_state(path=str(tmp_storage))
                    return save_session(tmp_storage, sharepoint_url)
                time.sleep(2)

            raise TimeoutError(
                f"Authentication not detected within {timeout_seconds}s. "
                f"Open {sharepoint_url} manually to check the login flow."
            )
        finally:
            browser.close()
