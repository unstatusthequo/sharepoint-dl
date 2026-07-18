"""Playwright-based session harvest for SharePoint authentication."""

from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from sharepoint_dl.auth.session import SESSION_DIR, save_session

EDGE_PROFILE_DIR = SESSION_DIR / "edge-profile"

_CLOSED_EARLY_MESSAGE = (
    "The browser closed before the session could be captured. Please try again."
)


def harvest_session(sharepoint_url: str, timeout_seconds: int = 180) -> Path:
    """Open a headed Edge browser, wait for auth cookies, save session.

    Uses a persistent Edge profile (EDGE_PROFILE_DIR) rather than a
    throwaway context. Some tenants' Conditional Access policies require
    the Edge *browser profile* itself to be signed in (device identity),
    not just a valid web session cookie — a fresh, never-signed-in profile
    fails that check outright. A persistent profile lets that one-time
    "sign in to Edge" step carry over between runs.

    Waits for the FedAuth cookie specifically — this is only set after
    successful authentication, not during intermediate redirects. A blank
    keep-alive tab is kept open for the whole flow so that the auth tab
    self-closing doesn't take down the entire browser process (which
    happens when the last window closes) before the session can be read
    out.

    Args:
        sharepoint_url: The SharePoint site URL to authenticate against.
        timeout_seconds: Maximum time to wait for authentication (default 180s).

    Returns:
        Path to the saved session.json file.

    Raises:
        TimeoutError: If authentication is not detected within timeout_seconds.
        RuntimeError: If the browser closes before the session can be captured.
    """
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    EDGE_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_storage = SESSION_DIR / "storage_state_tmp.json"

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            str(EDGE_PROFILE_DIR), channel="msedge", headless=False
        )
        try:
            # Keeps the browser process alive even if the auth tab below
            # closes itself right after login completes.
            context.new_page()

            auth_page = context.new_page()
            auth_page.goto(sharepoint_url, wait_until="domcontentloaded")

            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                try:
                    cookie_names = {c["name"] for c in context.cookies()}
                except PlaywrightError as exc:
                    raise RuntimeError(_CLOSED_EARLY_MESSAGE) from exc
                if "FedAuth" in cookie_names:
                    context.storage_state(path=str(tmp_storage))
                    return save_session(tmp_storage, sharepoint_url)
                time.sleep(0.5)

            raise TimeoutError(
                f"Authentication not detected within {timeout_seconds}s. "
                f"Open {sharepoint_url} manually to check the login flow."
            )
        finally:
            try:
                context.close()
            except PlaywrightError:
                pass
