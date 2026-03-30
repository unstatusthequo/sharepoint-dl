"""ReauthController — check-lock-check session refresh coordinator.

Coordinates automatic mid-download re-authentication when workers encounter
401/403 responses. Uses check-lock-check pattern with threading.Lock and
threading.Event to ensure exactly one browser window opens per re-auth round.

Per D-06: Playwright re-auth runs on the main thread. Worker threads block on
a threading.Event until re-auth completes or fails.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable
from urllib.parse import urlparse

import requests

from sharepoint_dl.auth.session import _session_file, build_session

logger = logging.getLogger(__name__)


class ReauthController:
    """Coordinates automatic session re-authentication for download workers.

    Uses check-lock-check pattern: first worker to call trigger() acquires
    the lock and runs the re-auth callback on the main thread. Subsequent
    callers wait on a threading.Event until re-auth completes or fails.

    Max attempts enforced per controller instance (one download run).

    Args:
        session: The shared requests.Session used by all download workers.
            Cookies are updated IN-PLACE on this object after re-auth.
        sharepoint_url: The SharePoint URL for the current download run.
        on_reauth: Callable[[str], None] that triggers harvest_session.
            Receives sharepoint_url as the single argument.
            Must be called on the main thread (Playwright GUI constraint).
    """

    MAX_ATTEMPTS = 3

    def __init__(
        self,
        session: requests.Session,
        sharepoint_url: str,
        on_reauth: Callable[[str], None],
    ) -> None:
        self._session = session
        self._sharepoint_url = sharepoint_url
        self._on_reauth = on_reauth
        self._lock = threading.Lock()
        self._done_event = threading.Event()
        self._attempts = 0
        self._last_result: bool = False

    def trigger(self) -> bool:
        """Called by a worker thread on 401/403. Returns True if session refreshed.

        Check-lock-check pattern:
        - Fast path: if _done_event is set, return _last_result immediately.
        - Lock winner: runs re-auth, updates cookies in-place, sets event.
        - Lock losers: block on _done_event.wait(), return _last_result.

        After MAX_ATTEMPTS failures, returns False without calling on_reauth.

        Returns:
            True if re-authentication succeeded, False otherwise.
        """
        # Fast path: a previous re-auth attempt is already complete
        if self._done_event.is_set():
            return self._last_result

        acquired = self._lock.acquire(blocking=False)
        if acquired:
            try:
                # Check again inside the lock (second check in check-lock-check)
                if self._done_event.is_set():
                    return self._last_result

                if self._attempts >= self.MAX_ATTEMPTS:
                    self._last_result = False
                    self._done_event.set()
                    return False

                self._attempts += 1
                # Clear event so concurrent workers block until this round completes
                self._done_event.clear()
                t0 = time.monotonic()
                try:
                    self._on_reauth(self._sharepoint_url)
                    self._refresh_cookies()
                    elapsed = time.monotonic() - t0
                    logger.info(
                        "Re-auth attempt %d succeeded in %.1fs",
                        self._attempts,
                        elapsed,
                    )
                    self._last_result = True
                except Exception as exc:
                    elapsed = time.monotonic() - t0
                    logger.error(
                        "Re-auth attempt %d failed in %.1fs: %s",
                        self._attempts,
                        elapsed,
                        exc,
                    )
                    self._last_result = False
                finally:
                    self._done_event.set()
            finally:
                self._lock.release()
        else:
            # Another thread holds the lock — wait for re-auth to complete
            self._done_event.wait()

        return self._last_result

    def reset_for_retry(self) -> None:
        """Clear completion event so the next download round can re-block workers.

        Must be called between re-auth rounds (e.g., after engine's retry loop
        completes and a new wave of workers is about to start).
        """
        self._done_event.clear()

    def _refresh_cookies(self) -> None:
        """Update cookies on the shared session in-place from saved session.json.

        Per D-03: updates the EXISTING shared requests.Session object — no object
        swapping. All worker threads continue holding the same session reference.
        """
        host = urlparse(self._sharepoint_url).netloc
        new_session = build_session(_session_file(), host)

        # Clear old cookies and copy fresh ones in-place
        self._session.cookies.clear()
        for cookie in new_session.cookies:
            self._session.cookies.set(
                cookie.name,
                cookie.value,
                domain=cookie.domain,
                path=cookie.path,
            )
