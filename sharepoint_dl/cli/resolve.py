"""Shared URL resolution utilities for SharePoint sharing links."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

import requests


def resolve_folder_from_browser_url(url: str) -> str | None:
    """Extract the server-relative folder path from a SharePoint browser URL.

    SharePoint folder URLs contain an ``id=`` query parameter with the
    URL-encoded server-relative path.

    Args:
        url: A SharePoint browser URL (from the address bar).

    Returns:
        Server-relative path, or ``None`` if it can't be extracted.
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if "id" in params:
        return unquote(params["id"][0])
    # Try fragment
    if parsed.fragment:
        frag_params = parse_qs(parsed.fragment)
        if "id" in frag_params:
            return unquote(frag_params["id"][0])
    return None


def resolve_sharing_link(session: requests.Session, sharing_url: str) -> str | None:
    """Follow a SharePoint sharing link redirect to find the folder path.

    Args:
        session: Authenticated requests.Session.
        sharing_url: The sharing link URL.

    Returns:
        Server-relative folder path, or ``None`` if it can't be resolved.
    """
    try:
        resp = session.get(sharing_url, allow_redirects=True, timeout=30)
        if resp.status_code == 200:
            return resolve_folder_from_browser_url(str(resp.url))
    except Exception:
        pass
    return None
