"""Recursive SharePoint folder traversal with pagination and auth expiry detection."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
from requests.utils import quote
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class AuthExpiredError(Exception):
    """Raised when SharePoint returns 401/403, indicating session expiry."""

    pass


@dataclass
class FileEntry:
    """A single file discovered during SharePoint folder enumeration."""

    name: str
    server_relative_url: str
    size_bytes: int
    folder_path: str
    sharepoint_created_at: str | None = None
    sharepoint_modified_at: str | None = None
    sharepoint_created_by: str | None = None
    sharepoint_created_by_email: str | None = None
    sharepoint_modified_by: str | None = None
    sharepoint_modified_by_email: str | None = None


def _user_field(item: dict, field: str, key: str) -> str | None:
    """Extract a SharePoint user field from expanded REST data."""
    user = item.get(field)
    if not isinstance(user, dict):
        return None
    variants = (key, key.upper(), key.lower(), "EMail" if key.lower() == "email" else key)
    value = next((user.get(variant) for variant in variants if user.get(variant)), None)
    return str(value) if value else None


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(requests.HTTPError),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _fetch_page(session: requests.Session, url: str) -> tuple[list[dict], str | None]:
    """Fetch a single page of SharePoint REST API results.

    Args:
        session: Authenticated requests.Session.
        url: The API URL to fetch.

    Returns:
        Tuple of (results list, next_url or None).

    Raises:
        AuthExpiredError: If response is 401 or 403.
        requests.HTTPError: For other HTTP errors (retried by tenacity).
    """
    headers = {"Accept": "application/json;odata=verbose"}
    resp = session.get(url, headers=headers, timeout=(10, 60))

    if resp.status_code in (401, 403):
        raise AuthExpiredError(
            "Session expired. Run 'sharepoint-dl auth <url>' to re-authenticate."
        )

    resp.raise_for_status()

    data = resp.json()["d"]
    results = data.get("results", [])
    next_url = data.get("__next")
    return results, next_url


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(requests.HTTPError),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def fetch_single_file(
    session: requests.Session,
    site_url: str,
    server_relative_path: str,
) -> FileEntry:
    """Fetch metadata for a single SharePoint file (no folder traversal).

    Args:
        session: Authenticated requests.Session with SharePoint cookies.
        site_url: SharePoint site URL (e.g. https://contoso.sharepoint.com/sites/shared).
        server_relative_path: Server-relative path to the file.

    Returns:
        A FileEntry for the file, with folder_path set to its parent directory.

    Raises:
        AuthExpiredError: If session expires (401/403).
        requests.HTTPError: For other HTTP errors (retried by tenacity).
    """
    site_url = site_url.rstrip("/")
    encoded = quote(server_relative_path, safe="")
    url = (
        f"{site_url}/_api/web/GetFileByServerRelativeUrl('{encoded}')"
        "?$select=Name,ServerRelativeUrl,Length,TimeCreated,TimeLastModified,"
        "Author/Title,Author/Email,Author/EMail,"
        "ModifiedBy/Title,ModifiedBy/Email,ModifiedBy/EMail"
        "&$expand=Author,ModifiedBy"
    )
    headers = {"Accept": "application/json;odata=verbose"}
    resp = session.get(url, headers=headers, timeout=(10, 60))

    if resp.status_code in (401, 403):
        raise AuthExpiredError(
            "Session expired. Run 'sharepoint-dl auth <url>' to re-authenticate."
        )

    resp.raise_for_status()

    item = resp.json()["d"]
    folder_path = server_relative_path.rsplit("/", 1)[0] if "/" in server_relative_path else ""
    return FileEntry(
        name=item["Name"],
        server_relative_url=item["ServerRelativeUrl"],
        size_bytes=int(item.get("Length", 0)),
        folder_path=folder_path,
        sharepoint_created_at=item.get("TimeCreated"),
        sharepoint_modified_at=item.get("TimeLastModified"),
        sharepoint_created_by=_user_field(item, "Author", "Title"),
        sharepoint_created_by_email=_user_field(item, "Author", "Email"),
        sharepoint_modified_by=_user_field(item, "ModifiedBy", "Title"),
        sharepoint_modified_by_email=_user_field(item, "ModifiedBy", "Email"),
    )


def enumerate_files(
    session: requests.Session,
    site_url: str,
    server_relative_path: str,
) -> list[FileEntry]:
    """Recursively enumerate all files under a SharePoint folder.

    Uses an explicit stack for depth-first traversal. Follows __next pagination
    links until exhausted. Filters out SharePoint system folders (/Forms).

    Args:
        session: Authenticated requests.Session with SharePoint cookies.
        site_url: SharePoint site URL (e.g. https://contoso.sharepoint.com/sites/shared).
        server_relative_path: Server-relative path to the root folder.

    Returns:
        List of FileEntry for every file found across all subfolders.

    Raises:
        AuthExpiredError: If session expires during traversal (401/403).
    """
    site_url = site_url.rstrip("/")
    files: list[FileEntry] = []
    stack: list[str] = [server_relative_path]

    while stack:
        folder_path = stack.pop()
        encoded = quote(folder_path, safe="")

        # Fetch files in this folder (with pagination)
        files_url = (
            f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{encoded}')"
            "/Files?"
            "$select=Name,ServerRelativeUrl,Length,TimeCreated,TimeLastModified,"
            "Author/Title,Author/Email,Author/EMail,"
            "ModifiedBy/Title,ModifiedBy/Email,ModifiedBy/EMail"
            "&$expand=Author,ModifiedBy"
        )
        next_url: str | None = files_url
        while next_url:
            results, next_url = _fetch_page(session, next_url)
            for item in results:
                files.append(
                    FileEntry(
                        name=item["Name"],
                        server_relative_url=item["ServerRelativeUrl"],
                        size_bytes=int(item.get("Length", 0)),
                        folder_path=folder_path,
                        sharepoint_created_at=item.get("TimeCreated"),
                        sharepoint_modified_at=item.get("TimeLastModified"),
                        sharepoint_created_by=_user_field(item, "Author", "Title"),
                        sharepoint_created_by_email=_user_field(item, "Author", "Email"),
                        sharepoint_modified_by=_user_field(item, "ModifiedBy", "Title"),
                        sharepoint_modified_by_email=_user_field(item, "ModifiedBy", "Email"),
                    )
                )

        # Fetch subfolders (with pagination)
        folders_url = (
            f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{encoded}')"
            f"/Folders?$select=ServerRelativeUrl"
        )
        next_url = folders_url
        while next_url:
            results, next_url = _fetch_page(session, next_url)
            for item in results:
                sub_path = item["ServerRelativeUrl"]
                # Skip SharePoint system folders
                if "/Forms" not in sub_path:
                    stack.append(sub_path)

    return files
