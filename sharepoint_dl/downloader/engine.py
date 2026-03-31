"""Download engine: single-file streaming + concurrent executor with Rich progress."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
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
    TimeRemainingColumn,
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
from sharepoint_dl.state.job_state import FileStatus, JobState, derive_local_relative_path

if TYPE_CHECKING:
    from sharepoint_dl.downloader.throttle import TokenBucket

logger = logging.getLogger(__name__)

CHUNK_SIZE = 8_388_608  # 8 MB


def _format_size_bytes(size_bytes: int) -> str:
    """Format bytes as human-readable size (local helper to avoid circular imports)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


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
    encoded = quote(server_relative_url, safe="/:@!$'()*,;=")
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
    throttle: "TokenBucket | None" = None,
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
                if throttle is not None:
                    throttle.consume(len(chunk))

    # Size verification
    expected = file_entry.size_bytes
    actual = part_path.stat().st_size
    if expected > 0 and actual != expected:
        if actual < expected:
            # Truncated download — file is incomplete, reject it
            part_path.unlink(missing_ok=True)
            raise ValueError(f"Size mismatch: expected {expected}, got {actual}")
        # File is larger than API reported — SharePoint sometimes recompresses
        # Office files on download. Keep the file but log the discrepancy.
        logger.warning(
            "Size discrepancy (kept): %s expected %d, got %d (+%d bytes)",
            file_entry.name, expected, actual, actual - expected,
        )

    part_path.rename(dest_path)
    return sha256.hexdigest()


_NAME_WIDTH = 20  # Fixed display width for filenames in progress bar


def _truncate_name(name: str, max_len: int = _NAME_WIDTH) -> str:
    """Truncate a filename for progress display, keeping extension visible."""
    if len(name) <= max_len:
        return name.ljust(max_len)
    stem, _, ext = name.rpartition(".")
    if ext and len(ext) <= 5:
        available = max_len - len(ext) - 2  # 2 for "…."
        return f"{stem[:available]}….{ext}"
    return name[: max_len - 1] + "…"


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as a human-readable string.

    Args:
        seconds: Elapsed time in seconds.

    Returns:
        Formatted string: "0s" for under 1s, "12s" for under 60s, "2m 15s" for 60s+.
    """
    if seconds < 1:
        return "0s"
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    return f"{minutes}m {secs}s"


def _make_progress() -> Progress:
    """Create a Rich Progress instance with cyberpunk-styled download columns."""
    return Progress(
        SpinnerColumn(style="bright_magenta"),
        TextColumn("[bright_cyan]{task.description}[/bright_cyan]"),
        BarColumn(bar_width=None, complete_style="bright_magenta", finished_style="bright_green"),
        DownloadColumn(binary_units=True),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        TextColumn("{task.fields[elapsed]}"),
        TextColumn("{task.fields[status]}"),
    )


def download_all(
    session: requests.Session,
    files: list[FileEntry],
    dest_dir: Path,
    site_url: str,
    workers: int = 3,
    progress: Progress | None = None,
    flat: bool = False,
    throttle: "TokenBucket | None" = None,
    on_auth_expired: "Callable[[], bool] | None" = None,
    files_dir: Path | None = None,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Orchestrate concurrent file downloads with progress and auth halt.

    Creates a JobState, initializes it with files, cleans up interrupted
    downloads, then uses ThreadPoolExecutor to download pending files
    concurrently. If any worker encounters an auth error (401/403), all
    workers are halted via a threading.Event.

    Args:
        session: Authenticated requests.Session.
        files: List of FileEntry objects to download.
        dest_dir: Root directory for metadata (state.json).
        site_url: SharePoint site URL.
        workers: Number of concurrent download workers (default 3).
        progress: Optional Rich Progress instance for visual feedback.
        throttle: Optional shared TokenBucket for bandwidth limiting.
        on_auth_expired: Optional callback invoked on 401. If it returns True,
            auth_halt is cleared and workers resume (file stays FAILED for
            retry loop). If it returns False or is None, existing abort
            behavior is preserved.
        files_dir: Directory for downloaded files. Defaults to dest_dir/files
            if not specified.

    Returns:
        Tuple of (completed_urls, failed_entries) where failed_entries
        is a list of (server_relative_url, error_reason) tuples.

    Raises:
        AuthExpiredError: If any worker encounters 401/403 and on_auth_expired
            is None or returns False.
    """
    actual_files_dir = files_dir if files_dir is not None else dest_dir / "files"
    state = JobState(dest_dir)
    state.initialize(files)
    state.cleanup_interrupted(dest_dir, files_dir=actual_files_dir)

    file_map = {f.server_relative_url: f for f in files}
    pending = state.pending_files()

    if not pending:
        return state.complete_files(), state.failed_files()

    auth_halt = threading.Event()
    auth_error: list[AuthExpiredError] = []

    # Set up progress tasks
    overall_task = None
    worker_tasks: list = []
    completed_count = 0
    total_pending = len(pending)
    overall_start = time.monotonic()
    if progress is not None:
        total_size = sum(file_map[url].size_bytes for url in pending if url in file_map)
        overall_task = progress.add_task(
            "Overall".ljust(_NAME_WIDTH), total=total_size,
            status=f"[cyan]0/{total_pending} files[/cyan]",
            elapsed="0s",
        )
        for i in range(workers):
            wt = progress.add_task(f"[worker {i}]", total=0, visible=False, status="", elapsed="0s")
            worker_tasks.append(wt)

    def worker(url: str, worker_id: int) -> None:
        if auth_halt.is_set():
            return

        file_entry = file_map[url]
        dest_path = _local_path(actual_files_dir, file_entry, flat=flat)
        local_path = dest_path.relative_to(dest_dir).as_posix()

        state.set_status(url, FileStatus.DOWNLOADING, local_path=local_path)

        # Each worker gets its own dedicated progress task (by worker_id)
        my_task = None
        if progress is not None and worker_tasks:
            my_task = worker_tasks[worker_id % len(worker_tasks)]
            # Reset: set completed to 0 and total to this file's size; reset elapsed to "0s"
            progress.update(
                my_task,
                description=_truncate_name(file_entry.name),
                total=file_entry.size_bytes,
                completed=0,
                visible=True,
                status="",
                elapsed="0s",
            )

            # Record per-file start time AFTER resetting the task
            file_start = time.monotonic()

            # Capture my_task in closure to avoid stale references
            _task = my_task
            _overall = overall_task
            _file_start = file_start
            _overall_start = overall_start

            def on_chunk(n: int, _t=_task, _o=_overall, _fs=_file_start, _os=_overall_start) -> None:
                file_elapsed = _format_elapsed(time.monotonic() - _fs)
                progress.update(_t, advance=n, elapsed=file_elapsed)
                if _o is not None:
                    overall_elapsed = _format_elapsed(time.monotonic() - _os)
                    progress.update(_o, advance=n, elapsed=overall_elapsed)
        else:
            on_chunk = None  # type: ignore[assignment]

        try:
            logger.info("Downloading: %s (%s)", file_entry.name, _format_size_bytes(file_entry.size_bytes))
            sha = _download_file(
                session, file_entry, dest_path, site_url, on_chunk=on_chunk, throttle=throttle
            )
            state.set_status(
                url,
                FileStatus.COMPLETE,
                sha256=sha,
                downloaded_at=datetime.now(timezone.utc).isoformat(),
            )
            logger.info("Complete: %s (SHA-256: %s...)", file_entry.name, sha[:16])
            nonlocal completed_count
            completed_count += 1
            if progress is not None and my_task is not None:
                progress.update(my_task, visible=False)
                if overall_task is not None:
                    progress.update(
                        overall_task,
                        status=f"[cyan]{completed_count}/{total_pending} files[/cyan]",
                    )
        except AuthExpiredError as e:
            state.set_status(url, FileStatus.FAILED, error="auth_expired")
            logger.error("Failed: %s -- auth expired", file_entry.name)
            if on_auth_expired is not None:
                auth_halt.set()  # Pause new submissions
                refreshed = on_auth_expired()
                if refreshed:
                    auth_halt.clear()  # Resume workers
                    return  # File stays FAILED — retry loop picks it up
            # No callback or refresh failed — original abort behavior
            auth_halt.set()
            auth_error.append(e)
            raise
        except Exception as e:
            state.set_status(url, FileStatus.FAILED, error=str(e))
            logger.error("Failed: %s -- %s", file_entry.name, str(e))
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

    # Retry failed files (up to 2 additional rounds)
    for retry_round in range(1, 3):
        failed_urls = [url for url, _reason in state.failed_files()]
        if not failed_urls:
            break

        if progress is not None and overall_task is not None:
            progress.update(
                overall_task,
                status=f"[yellow]Retry round {retry_round}: {len(failed_urls)} files[/yellow]",
            )

        # Reset failed files to pending for retry
        for url in failed_urls:
            state.set_status(url, FileStatus.PENDING, error=None)

        retry_halt = threading.Event()
        retry_auth_error: list[AuthExpiredError] = []

        with ThreadPoolExecutor(max_workers=workers) as retry_executor:
            retry_futures = {}
            for i, url in enumerate(failed_urls):
                if retry_halt.is_set():
                    break
                future = retry_executor.submit(worker, url, i % workers)
                retry_futures[future] = url

            for future in as_completed(retry_futures):
                try:
                    future.result()
                except AuthExpiredError:
                    for f in retry_futures:
                        f.cancel()
                    retry_auth_error.append(future.exception())
                    break
                except Exception:
                    pass

        if retry_auth_error:
            raise retry_auth_error[0]

    return state.complete_files(), state.failed_files()


def _local_path(files_dir: Path, file_entry: FileEntry, flat: bool = False) -> Path:
    """Construct local path for a downloaded file.

    Args:
        files_dir: Directory where downloaded files are stored.
        file_entry: FileEntry with folder_path and name.
        flat: If True, put all files directly in files_dir (no subdirectories).

    Returns:
        Path to the local file destination.
    """
    relative = derive_local_relative_path(file_entry.folder_path, file_entry.name, flat=flat)
    return files_dir / relative
