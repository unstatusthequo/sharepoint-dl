"""Playwright-based session harvest for SharePoint authentication."""

from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from sharepoint_dl.auth.session import SESSION_DIR, save_session

def harvest_session(sharepoint_url: str, timeout_seconds: int = 180) -> Path:
    """Open a headed Chromium browser, wait for auth cookies, save session.

    Waits for the FedAuth cookie specifically — this is only set after
    successful authentication, not during intermediate redirects.

    Args:
        sharepoint_url: The SharePoint site URL to authenticate against.
        timeout_seconds: Maximum time to wait for authentication (default 180s).

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
            page.goto(sharepoint_url, wait_until="domcontentloaded")

            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                cookies = context.cookies()
                cookie_names = {c["name"] for c in cookies}
                # FedAuth is the definitive auth cookie — only set after
                # successful SharePoint authentication, not during redirects
                if "FedAuth" in cookie_names:
                    # Wait a moment for all cookies to settle
                    time.sleep(3)
                    context.storage_state(path=str(tmp_storage))
                    return save_session(tmp_storage, sharepoint_url)
                time.sleep(2)

            raise TimeoutError(
                f"Authentication not detected within {timeout_seconds}s. "
                f"Open {sharepoint_url} manually to check the login flow."
            )
        finally:
            browser.close()
