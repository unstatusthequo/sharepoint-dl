"""Shared URL resolution utilities for SharePoint sharing links."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

import requests


def resolve_folder_from_browser_url(url: str) -> str | None:
    """Extract the server-relative folder path from a SharePoint browser URL.

    Supports multiple SharePoint URL formats:
    - ``id=`` query parameter (classic sharing links)
    - ``RootFolder=`` query parameter (classic document-library views)
    - ``/:f:/r/`` path prefix (direct resource links, e.g. authenticated shares)
    - Direct document-library URLs, including ``/Forms/AllItems.aspx`` views

    Args:
        url: A SharePoint browser URL (from the address bar or sharing link).

    Returns:
        Server-relative path, or ``None`` if it can't be extracted.
    """
    parsed = urlparse(url)

    # Format 1: id= query parameter (classic)
    params = parse_qs(parsed.query)
    if "id" in params:
        return unquote(params["id"][0])
    if "RootFolder" in params:
        return unquote(params["RootFolder"][0])
    # Try fragment
    if parsed.fragment:
        frag_params = parse_qs(parsed.fragment)
        if "id" in frag_params:
            return unquote(frag_params["id"][0])
        if "RootFolder" in frag_params:
            return unquote(frag_params["RootFolder"][0])

    # Format 2: /:f:/r/ or /:f:/s/ path prefix (direct resource links)
    # Pattern: /:f:/r/sites/SiteName/Shared Documents/folder → /sites/SiteName/Shared Documents/folder
    decoded_path = unquote(parsed.path)
    match = re.match(r"/:f:/[rs](/sites/.+)", decoded_path)
    if match:
        return match.group(1)

    # Format 3: direct SharePoint browser URLs.
    # Document-library views use /Forms/AllItems.aspx under the library root,
    # while copied folder URLs can point directly at a server-relative folder.
    parts = [part for part in decoded_path.strip("/").split("/") if part]
    if len(parts) >= 3 and parts[0] in ("sites", "personal"):
        if "_layouts" in parts:
            return None

        for index, part in enumerate(parts):
            if (
                part == "Forms"
                and index + 1 < len(parts)
                and parts[index + 1].endswith(".aspx")
            ):
                return "/" + "/".join(parts[:index])

        return "/" + "/".join(parts)

    return None


def resolve_sharing_link(session: requests.Session, sharing_url: str) -> str | None:
    """Resolve a SharePoint sharing link to a server-relative folder path.

    Supports both link formats:
    - OTP sharing links (/:f:/s/...) — follows redirect, extracts id= from final URL
    - Authenticated resource links (/:f:/r/...) — path embedded directly in URL

    Args:
        session: Authenticated requests.Session.
        sharing_url: The sharing link URL.

    Returns:
        Server-relative folder path, or ``None`` if it can't be resolved.
    """
    # Try extracting directly from the URL first (handles /:f:/r/ format)
    direct = resolve_folder_from_browser_url(sharing_url)
    if direct:
        return direct

    # Fall back to following redirects (handles /:f:/s/ OTP format)
    try:
        resp = session.get(sharing_url, allow_redirects=True, timeout=30)
        if resp.status_code == 200:
            return resolve_folder_from_browser_url(str(resp.url))
    except Exception:
        pass
    return None
