"""Download engine: single-file streaming + concurrent executor with Rich progress."""

from __future__ import annotations

import hashlib
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from urllib.parse import quote

import requests
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)
from tenacity import (
    RetryCallState,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
)
from tenacity.wait import wait_base

from sharepoint_dl.enumerator.traversal import AuthExpiredError, FileEntry
from sharepoint_dl.state.job_state import FileStatus, JobState

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


def _make_progress() -> Progress:
    """Create a Rich Progress instance with download-appropriate columns."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeElapsedColumn(),
    )


def download_all(
    session: requests.Session,
    files: list[FileEntry],
    dest_dir: Path,
    site_url: str,
    workers: int = 3,
    progress: Progress | None = None,
    flat: bool = False,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Orchestrate concurrent file downloads with progress and auth halt.

    Creates a JobState, initializes it with files, cleans up interrupted
    downloads, then uses ThreadPoolExecutor to download pending files
    concurrently. If any worker encounters an auth error (401/403), all
    workers are halted via a threading.Event.

    Args:
        session: Authenticated requests.Session.
        files: List of FileEntry objects to download.
        dest_dir: Root download destination directory.
        site_url: SharePoint site URL.
        workers: Number of concurrent download workers (default 3).
        progress: Optional Rich Progress instance for visual feedback.

    Returns:
        Tuple of (completed_urls, failed_entries) where failed_entries
        is a list of (server_relative_url, error_reason) tuples.

    Raises:
        AuthExpiredError: If any worker encounters 401/403.
    """
    state = JobState(dest_dir)
    state.initialize(files)
    state.cleanup_interrupted(dest_dir)

    file_map = {f.server_relative_url: f for f in files}
    pending = state.pending_files()

    if not pending:
        return state.complete_files(), state.failed_files()

    auth_halt = threading.Event()
    auth_error: list[AuthExpiredError] = []

    # Set up progress tasks
    overall_task = None
    worker_tasks: list = []
    if progress is not None:
        total_size = sum(file_map[url].size_bytes for url in pending if url in file_map)
        overall_task = progress.add_task("Overall", total=total_size)
        for i in range(workers):
            wt = progress.add_task(f"[worker {i}]", total=0, visible=False)
            worker_tasks.append(wt)

    def worker(url: str, worker_id: int) -> None:
        if auth_halt.is_set():
            return

        file_entry = file_map[url]
        dest_path = _local_path(dest_dir, file_entry, flat=flat)
        local_path = dest_path.relative_to(dest_dir).as_posix()

        state.set_status(url, FileStatus.DOWNLOADING, local_path=local_path)

        # Set up progress for this worker
        if progress is not None and worker_tasks:
            wt = worker_tasks[worker_id % len(worker_tasks)]
            progress.update(wt, description=file_entry.name, total=file_entry.size_bytes, completed=0, visible=True)

            def on_chunk(n: int) -> None:
                progress.update(wt, advance=n)
                if overall_task is not None:
                    progress.update(overall_task, advance=n)
        else:
            on_chunk = None  # type: ignore[assignment]

        try:
            sha = _download_file(session, file_entry, dest_path, site_url, on_chunk=on_chunk)
            state.set_status(
                url,
                FileStatus.COMPLETE,
                sha256=sha,
                downloaded_at=datetime.now(timezone.utc).isoformat(),
            )
            if progress is not None and worker_tasks:
                wt = worker_tasks[worker_id % len(worker_tasks)]
                progress.update(wt, visible=False)
        except AuthExpiredError as e:
            auth_halt.set()
            auth_error.append(e)
            state.set_status(url, FileStatus.FAILED, error="auth_expired")
            raise
        except Exception as e:
            state.set_status(url, FileStatus.FAILED, error=str(e))
            raise

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for i, url in enumerate(pending):
            if auth_halt.is_set():
                break
            future = executor.submit(worker, url, i % workers)
            futures[future] = url

        for future in as_completed(futures):
            try:
                future.result()
            except AuthExpiredError:
                # Cancel remaining futures
                for f in futures:
                    f.cancel()
                break
            except Exception:
                pass  # Already recorded in state

    if auth_error:
        raise auth_error[0]

    return state.complete_files(), state.failed_files()


def _local_path(dest_dir: Path, file_entry: FileEntry, flat: bool = False) -> Path:
    """Construct local path for a downloaded file.

    Args:
        dest_dir: Root download destination directory.
        file_entry: FileEntry with folder_path and name.
        flat: If True, put all files directly in dest_dir (no subdirectories).

    Returns:
        Path to the local file destination.
    """
    if flat:
        return dest_dir / file_entry.name

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
