"""Shared URL resolution utilities for SharePoint sharing links."""

from __future__ import annotations


def resolve_folder_from_browser_url(url: str) -> str | None:
    """Extract the server-relative folder path from a SharePoint browser URL.

    Stub — not yet implemented.
    """
    raise NotImplementedError


def resolve_sharing_link(session: object, sharing_url: str) -> str | None:
    """Follow a SharePoint sharing link redirect to find the folder path.

    Stub — not yet implemented.
    """
    raise NotImplementedError
