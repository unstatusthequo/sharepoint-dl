"""Session persistence, loading, and validation for SharePoint auth."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

import requests

SESSION_DIR = Path.home() / ".sharepoint-dl"


def _session_file() -> Path:
    """Return the path to the session JSON file."""
    return SESSION_DIR / "session.json"


def save_session(storage_state_path: Path, sharepoint_url: str) -> Path:
    """Read Playwright storageState, add host binding, write session.json with 0o600.

    Args:
        storage_state_path: Path to the Playwright storageState JSON file.
        sharepoint_url: The SharePoint URL this session was created for.

    Returns:
        Path to the written session.json.
    """
    data = json.loads(storage_state_path.read_text())
    data["_host"] = urlparse(sharepoint_url).netloc

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    dest = _session_file()
    dest.write_text(json.dumps(data, indent=2))
    os.chmod(dest, 0o600)
    return dest


def load_session(sharepoint_url: str) -> requests.Session | None:
    """Load a saved session if it exists and matches the requested host.

    Args:
        sharepoint_url: The SharePoint URL to load a session for.

    Returns:
        A requests.Session with cookies injected, or None if no valid session exists.
    """
    session_path = _session_file()
    if not session_path.exists():
        return None

    data = json.loads(session_path.read_text())
    stored_host = data.get("_host", "")
    requested_host = urlparse(sharepoint_url).netloc

    if stored_host != requested_host:
        return None

    return build_session(session_path, requested_host)


def build_session(session_path: Path, sharepoint_host: str) -> requests.Session:
    """Read session JSON and inject matching-domain cookies into a requests.Session.

    Args:
        session_path: Path to the session JSON file.
        sharepoint_host: The SharePoint host to filter cookies for.

    Returns:
        A requests.Session with cookies set.
    """
    data = json.loads(session_path.read_text())
    session = requests.Session()

    for cookie in data.get("cookies", []):
        domain = cookie.get("domain", "")
        if sharepoint_host in domain:
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=domain,
                path=cookie.get("path", "/"),
            )

    return session


def validate_session(session: requests.Session, site_url: str) -> bool:
    """Probe the SharePoint REST API to check if the session is still valid.

    Args:
        session: A requests.Session with auth cookies.
        site_url: The SharePoint site URL to validate against.

    Returns:
        True if the session is active (HTTP 200), False otherwise.
    """
    url = f"{site_url.rstrip('/')}/_api/web/title"
    headers = {"Accept": "application/json;odata=verbose"}

    try:
        resp = session.get(url, headers=headers, timeout=(10, 30))
        return resp.status_code == 200
    except requests.RequestException:
        return False
