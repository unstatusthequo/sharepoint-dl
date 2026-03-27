"""Single-file streaming download with retry, auth guard, and incremental SHA-256."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from urllib.parse import quote

import requests
from tenacity import (
    RetryCallState,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
)
from tenacity.wait import wait_base

from sharepoint_dl.enumerator.traversal import AuthExpiredError, FileEntry

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

CHUNK_SIZE = 8_388_608  # 8 MB


def _build_download_url(site_url: str, server_relative_url: str) -> str:
    """Build the download.aspx URL for a file.

    Uses download.aspx instead of /$value due to confirmed large-file bug
    (sp-dev-docs#5247).

    Args:
        site_url: SharePoint site URL (e.g. https://contoso.sharepoint.com/sites/shared).
        server_relative_url: Server-relative path to the file.

    Returns:
        Full download.aspx URL with SourceUrl parameter.
    """
    encoded = quote(server_relative_url, safe="/:@!$&'()*+,;=")
    return f"{site_url.rstrip('/')}/_layouts/15/download.aspx?SourceUrl={encoded}"


class WaitRetryAfter(wait_base):
    """Custom tenacity wait that respects Retry-After headers on 429 responses.

    Falls back to exponential backoff min(2 ** attempt, 16) when no
    Retry-After header is present.
    """

    def __call__(self, retry_state: RetryCallState) -> float:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        if exc and isinstance(exc, requests.HTTPError) and exc.response is not None:
            retry_after = exc.response.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    return float(retry_after)
                except (ValueError, TypeError):
                    pass
        # Exponential backoff fallback
        attempt = retry_state.attempt_number
        return min(2**attempt, 16)


@retry(
    retry=retry_if_exception_type(requests.HTTPError),
    stop=stop_after_attempt(3),
    wait=WaitRetryAfter(),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _download_file(
    session: requests.Session,
    file_entry: FileEntry,
    dest_path: Path,
    site_url: str,
    on_chunk: Callable[[int], None] | None = None,
) -> str:
    """Download one file, stream to .part, compute SHA-256, rename on success.

    Args:
        session: Authenticated requests.Session.
        file_entry: FileEntry from the enumerator.
        dest_path: Final destination path for the downloaded file.
        site_url: SharePoint site URL for URL construction.
        on_chunk: Optional callback receiving chunk byte count for progress updates.

    Returns:
        Hex SHA-256 digest of the downloaded file.

    Raises:
        AuthExpiredError: On 401/403 (not retried by tenacity).
        requests.HTTPError: On 429/5xx (retried by tenacity up to 3 attempts).
        ValueError: On size mismatch after download.
    """
    download_url = _build_download_url(site_url, file_entry.server_relative_url)
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")
    part_path.parent.mkdir(parents=True, exist_ok=True)

    resp = session.get(download_url, stream=True, timeout=(30, 600))

    # Auth check BEFORE raise_for_status — prevents tenacity from retrying dead sessions
    if resp.status_code in (401, 403):
        raise AuthExpiredError("Session expired during download.")

    resp.raise_for_status()  # 429, 5xx become HTTPError -> retried by tenacity

    sha256 = hashlib.sha256()
    with part_path.open("wb") as fh:
        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                fh.write(chunk)
                sha256.update(chunk)
                if on_chunk:
                    on_chunk(len(chunk))

    # Size verification
    expected = file_entry.size_bytes
    actual = part_path.stat().st_size
    if expected > 0 and actual != expected:
        part_path.unlink(missing_ok=True)
        raise ValueError(f"Size mismatch: expected {expected}, got {actual}")

    part_path.rename(dest_path)
    return sha256.hexdigest()


def _local_path(dest_dir: Path, file_entry: FileEntry) -> Path:
    """Construct local path preserving folder structure relative to root folder.

    Strips the common site prefix from folder_path to create subdirectories
    under dest_dir.

    Args:
        dest_dir: Root download destination directory.
        file_entry: FileEntry with folder_path and name.

    Returns:
        Path to the local file destination.
    """
    # folder_path is like /sites/shared/Images/custodian1
    # Strip leading slash and take the last component(s) as relative path
    parts = file_entry.folder_path.strip("/").split("/")
    # Skip site-level prefix (sites/sitename/library) — keep from the 3rd segment onward
    # This matches the SharePoint URL structure: /sites/{site}/{library}/{folders...}
    if len(parts) > 3:
        relative = Path(*parts[3:])
    elif len(parts) > 2:
        relative = Path(parts[-1])
    else:
        relative = Path(".")
    return dest_dir / relative / file_entry.name
