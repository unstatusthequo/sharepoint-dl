"""Shared URL resolution utilities for SharePoint sharing links."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

import requests

# Extensions used to recognize a bare browser URL as pointing at a file
# rather than a folder. Deliberately an allowlist (not "contains a dot")
# so folder names with dots in them (e.g. "Q1.2024 Reports") aren't
# misclassified as files.
_FILE_EXTENSIONS = (
    ".docx", ".doc", ".docm", ".dotm", ".dotx", ".dot",
    ".xlsx", ".xls", ".xlsm", ".xlsb", ".xltm", ".xltx", ".xlam",
    ".pptx", ".ppt", ".pptm", ".potm", ".potx", ".ppam", ".ppsm", ".ppsx",
    ".pdf", ".txt", ".csv", ".msg", ".eml", ".zip", ".png", ".jpg", ".jpeg",
    ".gif", ".mp4", ".mov", ".one", ".vsdx", ".rtf", ".json", ".xml",
    ".accdb", ".mdb",
)


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


def resolve_file_from_browser_url(url: str) -> str | None:
    """Extract the server-relative file path from a SharePoint browser URL.

    Mirrors ``resolve_folder_from_browser_url`` but for links to a single
    file rather than a folder:

    - ``/:X:/r/`` path prefix, where ``X`` is any sharing-link type letter
      other than ``f`` (folder) — e.g. ``w`` (Word), ``x`` (Excel),
      ``p`` (PowerPoint), ``b`` (PDF/binary).
    - Direct browser URLs whose last path segment has a recognized
      document extension.

    Args:
        url: A SharePoint browser URL (from the address bar or sharing link).

    Returns:
        Server-relative path, or ``None`` if it can't be extracted.
    """
    parsed = urlparse(url)

    # Format 0: id=/RootFolder= query (or fragment) param pointing at a file
    # rather than a folder — e.g. a custom-view Forms/*.aspx?id=... link.
    # Only treated as a file when the value has a recognized extension;
    # otherwise it's left for resolve_folder_from_browser_url to handle.
    param_sources = [parse_qs(parsed.query)]
    if parsed.fragment:
        param_sources.append(parse_qs(parsed.fragment))
    for params in param_sources:
        for key in ("id", "RootFolder"):
            if key in params:
                value = unquote(params[key][0])
                if value.lower().endswith(_FILE_EXTENSIONS):
                    return value

    decoded_path = unquote(parsed.path)

    # Format 1: /:X:/r/sites/... or /:X:/s/sites/... direct resource link,
    # where X != f (folder link prefix)
    match = re.match(r"/:([a-zA-Z]{1,3}):/[rs](/(?:sites|personal)/.+)", decoded_path)
    if match and match.group(1).lower() != "f":
        return match.group(2)

    # Format 2: direct browser URL already pointing at the file itself
    parts = [part for part in decoded_path.strip("/").split("/") if part]
    if len(parts) >= 3 and parts[0] in ("sites", "personal"):
        if "_layouts" in parts:
            return None
        last = parts[-1].lower()
        if last.endswith(_FILE_EXTENSIONS):
            # Custom SharePoint views sometimes append the filename directly
            # after the view page instead of using an id= query param, e.g.
            # .../Forms/Underwriting.aspx/File.xlsm. "Forms/<view>.aspx" is
            # always a system view page, never a real path component, so
            # strip it out (mirrors resolve_folder_from_browser_url's
            # handling of Forms/AllItems.aspx).
            for index, part in enumerate(parts[:-1]):
                if part == "Forms" and parts[index + 1].lower().endswith(".aspx"):
                    parts = parts[:index] + parts[index + 2 :]
                    break
            return "/" + "/".join(parts)

    return None


def _site_collection_url(url: str) -> str | None:
    """Best-effort site-collection REST base URL for an arbitrary SharePoint URL."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    parts = [part for part in unquote(parsed.path).strip("/").split("/") if part]
    if len(parts) >= 2 and parts[0] in ("sites", "personal"):
        return f"{base}/{parts[0]}/{parts[1]}"
    return None


def resolve_file_by_sourcedoc(session: requests.Session, url: str) -> str | None:
    """Resolve a Doc.aspx/WopiFrame-style URL's sourcedoc GUID to a file path.

    This is the common landing page for OTP single-file sharing links
    (e.g. ``/:x:/s/...``) after redirect — it carries a ``sourcedoc``
    query param (a file GUID) rather than an embedded path.

    Args:
        session: Authenticated requests.Session.
        url: The (already-redirected) browser URL to inspect.

    Returns:
        Server-relative path, or ``None`` if it can't be resolved.
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    sourcedoc = params.get("sourcedoc", [None])[0]
    if not sourcedoc:
        return None

    guid = unquote(sourcedoc).strip("{}")
    site_url = _site_collection_url(url)
    if site_url is None:
        return None

    try:
        resp = session.get(
            f"{site_url}/_api/web/GetFileById('{guid}')?$select=ServerRelativeUrl",
            headers={"Accept": "application/json;odata=verbose"},
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()["d"]["ServerRelativeUrl"]
    except Exception:
        pass
    return None


def resolve_file_sharing_link(session: requests.Session, sharing_url: str) -> str | None:
    """Resolve a SharePoint sharing link to a server-relative FILE path.

    Mirrors ``resolve_sharing_link`` but for single-file links: tries a
    direct parse first, then follows the redirect for OTP-style links
    (``/:X:/s/...``), then falls back to resolving a ``sourcedoc`` GUID
    from the final landing page.

    Args:
        session: Authenticated requests.Session.
        sharing_url: The sharing link URL.

    Returns:
        Server-relative file path, or ``None`` if it can't be resolved.
    """
    direct = resolve_file_from_browser_url(sharing_url)
    if direct:
        return direct

    try:
        resp = session.get(sharing_url, allow_redirects=True, timeout=30)
        if resp.status_code != 200:
            return None
    except Exception:
        return None

    final_url = str(resp.url)
    direct2 = resolve_file_from_browser_url(final_url)
    if direct2:
        return direct2

    return resolve_file_by_sourcedoc(session, final_url)


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
