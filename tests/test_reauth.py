"""Tests for ReauthController (REL-01) — check-lock-check session refresh coordinator."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import requests


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(cookies: list[dict] | None = None) -> requests.Session:
    """Create a requests.Session with optional cookies pre-loaded."""
    session = requests.Session()
    for c in cookies or []:
        session.cookies.set(
            c["name"],
            c["value"],
            domain=c.get("domain", ""),
            path=c.get("path", "/"),
        )
    return session


def _make_controller(
    session: requests.Session | None = None,
    on_reauth=None,
    sharepoint_url: str = "https://contoso.sharepoint.com/sites/shared",
):
    """Construct a ReauthController with sensible defaults."""
    from sharepoint_dl.auth.reauth import ReauthController

    if session is None:
        session = _make_session()
    if on_reauth is None:
        on_reauth = MagicMock()
    return ReauthController(session, sharepoint_url, on_reauth), session, on_reauth


# ---------------------------------------------------------------------------
# TestReauthController
# ---------------------------------------------------------------------------


class TestReauthController:
    """Unit tests for ReauthController."""

    # ------------------------------------------------------------------
    # Existence and interface
    # ------------------------------------------------------------------

    def test_class_exists(self):
        """ReauthController can be imported from sharepoint_dl.auth.reauth."""
        from sharepoint_dl.auth.reauth import ReauthController  # noqa: F401

    def test_max_attempts_constant(self):
        """MAX_ATTEMPTS class constant is 3."""
        from sharepoint_dl.auth.reauth import ReauthController

        assert ReauthController.MAX_ATTEMPTS == 3

    def test_init_stores_attributes(self):
        """__init__ stores session, sharepoint_url, and on_reauth."""
        from sharepoint_dl.auth.reauth import ReauthController

        session = _make_session()
        on_reauth = MagicMock()
        url = "https://contoso.sharepoint.com/sites/shared"
        ctrl = ReauthController(session, url, on_reauth)

        assert ctrl._session is session
        assert ctrl._sharepoint_url == url
        assert ctrl._on_reauth is on_reauth
        assert ctrl._attempts == 0

    # ------------------------------------------------------------------
    # First worker: acquires lock and runs re-auth
    # ------------------------------------------------------------------

    def test_first_worker_acquires_lock(self, mock_session_path: Path):
        """First worker calling trigger() runs on_reauth callback once."""
        ctrl, session, on_reauth = _make_controller()

        with patch(
            "sharepoint_dl.auth.reauth.build_session",
            return_value=_make_session(),
        ), patch(
            "sharepoint_dl.auth.reauth._session_file",
            return_value=mock_session_path,
        ):
            result = ctrl.trigger()

        assert result is True
        on_reauth.assert_called_once()

    def test_trigger_returns_true_on_success(self, mock_session_path: Path):
        """trigger() returns True when on_reauth succeeds."""
        ctrl, _, _ = _make_controller()

        with patch(
            "sharepoint_dl.auth.reauth.build_session",
            return_value=_make_session(),
        ), patch(
            "sharepoint_dl.auth.reauth._session_file",
            return_value=mock_session_path,
        ):
            result = ctrl.trigger()

        assert result is True

    def test_trigger_increments_attempt_counter(self, mock_session_path: Path):
        """Each successful trigger() increments _attempts by 1."""
        ctrl, _, _ = _make_controller()

        with patch(
            "sharepoint_dl.auth.reauth.build_session",
            return_value=_make_session(),
        ), patch(
            "sharepoint_dl.auth.reauth._session_file",
            return_value=mock_session_path,
        ):
            ctrl.trigger()

        assert ctrl._attempts == 1

    # ------------------------------------------------------------------
    # Concurrent workers: wait on Event
    # ------------------------------------------------------------------

    def test_only_one_reauth_runs_concurrently(self, mock_session_path: Path):
        """With 5 concurrent workers all calling trigger(), on_reauth is called exactly once."""
        # Simulate a slow re-auth so workers definitely overlap
        call_order = []

        def slow_reauth(url: str) -> None:
            call_order.append("reauth_start")
            time.sleep(0.1)
            call_order.append("reauth_end")

        ctrl, session, on_reauth = _make_controller(on_reauth=slow_reauth)
        on_reauth.side_effect = slow_reauth  # won't apply since on_reauth is slow_reauth itself

        results: list[bool] = []

        def worker():
            with patch(
                "sharepoint_dl.auth.reauth.build_session",
                return_value=_make_session(),
            ), patch(
                "sharepoint_dl.auth.reauth._session_file",
                return_value=mock_session_path,
            ):
                results.append(ctrl.trigger())

        # Build a fresh controller with slow_reauth directly
        from sharepoint_dl.auth.reauth import ReauthController

        ctrl = ReauthController(session, "https://contoso.sharepoint.com/sites/shared", slow_reauth)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # on_reauth (slow_reauth) called once
        assert call_order.count("reauth_start") == 1
        # All workers get True
        assert all(r is True for r in results)
        assert len(results) == 5

    def test_concurrent_workers_all_get_same_result_on_failure(self, mock_session_path: Path):
        """When re-auth fails, all concurrent waiting workers also get False."""
        call_count = 0

        def failing_reauth(url: str) -> None:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("browser closed")

        from sharepoint_dl.auth.reauth import ReauthController

        session = _make_session()
        ctrl = ReauthController(
            session, "https://contoso.sharepoint.com/sites/shared", failing_reauth
        )

        results: list[bool] = []

        def worker():
            with patch(
                "sharepoint_dl.auth.reauth.build_session",
                return_value=_make_session(),
            ), patch(
                "sharepoint_dl.auth.reauth._session_file",
                return_value=mock_session_path,
            ):
                results.append(ctrl.trigger())

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert call_count == 1  # only one browser attempt
        assert all(r is False for r in results)

    # ------------------------------------------------------------------
    # Max attempts enforcement
    # ------------------------------------------------------------------

    def test_max_attempts_enforced(self, mock_session_path: Path):
        """After MAX_ATTEMPTS (3) calls, trigger() returns False without calling on_reauth."""
        ctrl, session, on_reauth = _make_controller()

        with patch(
            "sharepoint_dl.auth.reauth.build_session",
            return_value=_make_session(),
        ), patch(
            "sharepoint_dl.auth.reauth._session_file",
            return_value=mock_session_path,
        ):
            # Exhaust all attempts
            for _ in range(ctrl.MAX_ATTEMPTS):
                ctrl._done_event.clear()  # allow each call to proceed
                result = ctrl.trigger()
            # 4th call must return False without calling on_reauth again
            ctrl._done_event.clear()
            extra_result = ctrl.trigger()

        assert extra_result is False
        assert on_reauth.call_count == ctrl.MAX_ATTEMPTS

    def test_max_attempts_returns_false_immediately(self, mock_session_path: Path):
        """After exhausting attempts, subsequent trigger() calls return False fast."""
        ctrl, _, on_reauth = _make_controller()

        with patch(
            "sharepoint_dl.auth.reauth.build_session",
            return_value=_make_session(),
        ), patch(
            "sharepoint_dl.auth.reauth._session_file",
            return_value=mock_session_path,
        ):
            for _ in range(ctrl.MAX_ATTEMPTS):
                ctrl._done_event.clear()
                ctrl.trigger()
            ctrl._done_event.clear()
            result = ctrl.trigger()

        assert result is False

    # ------------------------------------------------------------------
    # Cookie refresh (in-place update)
    # ------------------------------------------------------------------

    def test_cookies_updated_in_place(self, mock_session_path: Path):
        """After trigger(), new cookies from session.json are on the SAME session object."""
        old_session = _make_session(
            [{"name": "FedAuth", "value": "old_token", "domain": "contoso.sharepoint.com"}]
        )
        new_session = _make_session(
            [{"name": "FedAuth", "value": "new_token", "domain": "contoso.sharepoint.com"}]
        )

        ctrl, session, on_reauth = _make_controller(session=old_session)

        with patch(
            "sharepoint_dl.auth.reauth.build_session",
            return_value=new_session,
        ), patch(
            "sharepoint_dl.auth.reauth._session_file",
            return_value=mock_session_path,
        ):
            ctrl.trigger()

        # Identity check — still the SAME object
        assert ctrl._session is old_session
        # Value check — cookies are updated
        cookie_dict = {c.name: c.value for c in old_session.cookies}
        assert cookie_dict.get("FedAuth") == "new_token"

    def test_old_cookies_cleared_before_refresh(self, mock_session_path: Path):
        """Stale cookies that don't exist in the new session are removed."""
        old_session = _make_session(
            [
                {"name": "FedAuth", "value": "old", "domain": "contoso.sharepoint.com"},
                {"name": "stale_cookie", "value": "stale", "domain": "contoso.sharepoint.com"},
            ]
        )
        new_session = _make_session(
            [{"name": "FedAuth", "value": "fresh", "domain": "contoso.sharepoint.com"}]
        )

        ctrl, _, _ = _make_controller(session=old_session)

        with patch(
            "sharepoint_dl.auth.reauth.build_session",
            return_value=new_session,
        ), patch(
            "sharepoint_dl.auth.reauth._session_file",
            return_value=mock_session_path,
        ):
            ctrl.trigger()

        cookie_names = {c.name for c in old_session.cookies}
        assert "stale_cookie" not in cookie_names
        assert "FedAuth" in cookie_names

    # ------------------------------------------------------------------
    # Failure / exception handling
    # ------------------------------------------------------------------

    def test_trigger_returns_false_when_on_reauth_raises(self):
        """trigger() returns False when on_reauth raises an exception."""

        def bad_reauth(url: str) -> None:
            raise RuntimeError("network error")

        ctrl, _, _ = _make_controller(on_reauth=bad_reauth)
        result = ctrl.trigger()
        assert result is False

    def test_exception_sets_last_result_false(self):
        """After on_reauth raises, _last_result is False."""

        def bad_reauth(url: str) -> None:
            raise RuntimeError("timeout")

        ctrl, _, _ = _make_controller(on_reauth=bad_reauth)
        ctrl.trigger()
        assert ctrl._last_result is False

    def test_done_event_set_even_on_failure(self):
        """After on_reauth raises, _done_event is set so waiting workers unblock."""

        def bad_reauth(url: str) -> None:
            raise RuntimeError("timeout")

        ctrl, _, _ = _make_controller(on_reauth=bad_reauth)
        ctrl.trigger()
        assert ctrl._done_event.is_set()

    # ------------------------------------------------------------------
    # reset_for_retry
    # ------------------------------------------------------------------

    def test_reset_for_retry_clears_done_event(self, mock_session_path: Path):
        """reset_for_retry() clears _done_event so next round can re-block workers."""
        ctrl, _, _ = _make_controller()

        with patch(
            "sharepoint_dl.auth.reauth.build_session",
            return_value=_make_session(),
        ), patch(
            "sharepoint_dl.auth.reauth._session_file",
            return_value=mock_session_path,
        ):
            ctrl.trigger()

        assert ctrl._done_event.is_set()
        ctrl.reset_for_retry()
        assert not ctrl._done_event.is_set()

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def test_reauth_logged_on_success(self, mock_session_path: Path, caplog):
        """trigger() logs attempt number, 'succeeded', and elapsed time on success."""
        import logging

        ctrl, _, _ = _make_controller()

        with patch(
            "sharepoint_dl.auth.reauth.build_session",
            return_value=_make_session(),
        ), patch(
            "sharepoint_dl.auth.reauth._session_file",
            return_value=mock_session_path,
        ), caplog.at_level(logging.INFO, logger="sharepoint_dl.auth.reauth"):
            ctrl.trigger()

        assert any("succeeded" in r.message for r in caplog.records)
        assert any("1" in r.message for r in caplog.records)  # attempt number

    def test_reauth_logged_on_failure(self, caplog):
        """trigger() logs attempt number, 'failed', and elapsed time on failure."""
        import logging

        def bad_reauth(url: str) -> None:
            raise RuntimeError("timeout")

        ctrl, _, _ = _make_controller(on_reauth=bad_reauth)

        with caplog.at_level(logging.ERROR, logger="sharepoint_dl.auth.reauth"):
            ctrl.trigger()

        assert any("failed" in r.message for r in caplog.records)
        assert any("1" in r.message for r in caplog.records)

    # ------------------------------------------------------------------
    # No playwright import
    # ------------------------------------------------------------------

    def test_no_playwright_import_in_reauth_module(self):
        """reauth.py must not import playwright — Playwright stays in browser.py."""
        import importlib
        import sys

        # Remove from cache to get clean inspect
        mod_name = "sharepoint_dl.auth.reauth"
        if mod_name in sys.modules:
            del sys.modules[mod_name]

        import ast
        import importlib.util

        spec = importlib.util.find_spec(mod_name)
        assert spec is not None, "sharepoint_dl.auth.reauth module not found"
        source = Path(spec.origin).read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                else:
                    names = [node.module or ""]
                for name in names:
                    assert "playwright" not in (name or ""), (
                        f"reauth.py must not import playwright, found: {name}"
                    )
