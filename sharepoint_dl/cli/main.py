"""Typer CLI app for SharePoint bulk file downloader."""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import requests as _requests
import typer
from rich.console import Console
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.table import Table

from sharepoint_dl.auth.browser import harvest_session
from sharepoint_dl.auth.reauth import ReauthController
from sharepoint_dl.cli.resolve import resolve_folder_from_browser_url, resolve_sharing_link
from sharepoint_dl.auth.session import load_session, validate_session
from sharepoint_dl.config import load_config, save_config
from sharepoint_dl.downloader.engine import _make_progress, download_all
from sharepoint_dl.downloader.log import setup_download_logger, shutdown_download_logger
from sharepoint_dl.downloader.throttle import TokenBucket, parse_throttle
from sharepoint_dl.enumerator.traversal import AuthExpiredError, enumerate_files
from sharepoint_dl.manifest import generate_manifest
from sharepoint_dl.manifest.verifier import verify_manifest
from sharepoint_dl.state.job_state import JobState

app = typer.Typer(
    no_args_is_help=False,
    invoke_without_command=True,
    help="SharePoint bulk file downloader for forensic evidence collection.",
)

console = Console()



def _list_subfolders(
    session: _requests.Session, site_url: str, folder_path: str
) -> list[dict[str, str]]:
    """List immediate subfolders of a SharePoint folder.

    Returns:
        List of dicts with 'name' and 'path' keys.
    """
    from sharepoint_dl.enumerator.traversal import _fetch_page

    encoded = _requests.utils.quote(folder_path, safe="")
    url = (
        f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{encoded}')"
        f"/Folders?$select=Name,ServerRelativeUrl"
    )
    folders = []
    next_url: str | None = url
    while next_url:
        results, next_url = _fetch_page(session, next_url)
        for item in results:
            name = item.get("Name", "")
            if name and not name.startswith("Forms"):
                folders.append({
                    "name": name,
                    "path": item["ServerRelativeUrl"],
                })
    return sorted(folders, key=lambda f: f["name"])


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    """Interactive mode — walks you through the entire download process."""
    if ctx.invoked_subcommand is not None:
        return
    _interactive_mode()


def _interactive_mode() -> None:
    """Interactive TUI that guides the user through auth, folder selection, and download."""
    import os

    exit_code = 0
    try:
        _interactive_mode_inner()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Cancelled.[/yellow]")
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else 1
    finally:
        # Force-exit to avoid long hangs from ThreadPoolExecutor atexit handlers
        os._exit(exit_code)


def _print_banner() -> None:
    """Print the title banner."""
    console.print()
    console.print("  [bold bright_cyan]SPDL[/bold bright_cyan] [dim]—[/dim] [bold]SharePoint Bulk Downloader[/bold]  [dim]v0.1[/dim]")
    console.print("  [dim]@unstatusthequo · Ctrl+C cancel · Re-run to resume[/dim]")
    console.print()


def _section_header(number: str, title: str) -> None:
    """Print a styled section header."""
    console.print()
    console.print(f"  [bright_magenta]>[/bright_magenta] [bold bright_cyan]{number}[/bold bright_cyan] [bold]{title}[/bold]")


def _success(text: str) -> None:
    console.print(f"    [bright_green]{text}[/bright_green]")


def _info(text: str) -> None:
    console.print(f"    [dim]{text}[/dim]")


def _warn(text: str) -> None:
    console.print(f"    [bright_yellow]{text}[/bright_yellow]")


def _error(text: str) -> None:
    console.print(f"    [bright_red]{text}[/bright_red]")


def _run_verify(dest_dir: Path) -> None:
    """Run manifest verification for a download folder and print results."""
    from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TextColumn
    import json as _json

    manifest_path_local = dest_dir / "manifest.json"
    if not manifest_path_local.exists():
        _warn("No manifest.json found — skipping verification.")
        return

    manifest_data = _json.loads(manifest_path_local.read_text(encoding="utf-8"))
    total_bytes = sum(
        f.get("size_bytes", 0) for f in manifest_data.get("files", [])
    )

    with Progress(
        SpinnerColumn(style="bright_magenta"),
        TextColumn("[bright_cyan]{task.description}[/bright_cyan]"),
        BarColumn(bar_width=None, complete_style="bright_magenta", finished_style="bright_green"),
        DownloadColumn(binary_units=True),
        console=console,
    ) as vp:
        task_id = vp.add_task("Verifying files", total=total_bytes)

        def on_progress(name: str, size_bytes: int) -> None:
            vp.update(task_id, advance=size_bytes)

        summary = verify_manifest(dest_dir, on_progress=on_progress)

    if summary.failed == 0 and summary.missing == 0:
        _success(f"{summary.passed}/{summary.total} files verified OK")
    else:
        parts = []
        if summary.failed > 0:
            parts.append(f"{summary.failed} FAIL")
        if summary.missing > 0:
            parts.append(f"{summary.missing} MISSING")
        _error(f"Verification issues: {', '.join(parts)}")


def _interactive_mode_inner() -> None:
    """Inner interactive flow — separated so KeyboardInterrupt is caught cleanly."""
    import os

    # Load saved config to pre-fill prompts
    cfg = load_config()

    os.system("cls" if os.name == "nt" else "clear")
    _print_banner()
    console.print()

    # Step 1: Get sharing URL
    sharing_url = Prompt.ask(
        "  [bright_magenta]>[/bright_magenta] [bold]Paste the SharePoint sharing link[/bold]"
    ).strip()
    if not sharing_url:
        _error("No URL provided.")
        raise typer.Exit(code=1)

    # Step 2: Authenticate
    site_url, _ = _parse_sharepoint_url(sharing_url)
    session = load_session(sharing_url)

    if session is not None and validate_session(session, site_url):
        _success("Session active — using saved credentials.")
    else:
        _warn("Opening browser for authentication...")
        _info("Complete the login (email + code), then the browser will close automatically.")
        try:
            harvest_session(sharing_url)
        except TimeoutError:
            _error("Authentication timed out. Please try again.")
            raise typer.Exit(code=1)
        session = load_session(sharing_url)
        if session is None:
            _error("Failed to load session after auth.")
            raise typer.Exit(code=1)
        _success("Authenticated successfully.")

    # Step 3: Resolve the shared folder
    _section_header("02", "SELECT TARGET FOLDER")

    with console.status("    [dim]Resolving sharing link...[/dim]", spinner="dots"):
        root_path = resolve_sharing_link(session, sharing_url)

    if root_path:
        _info(f"Shared root: {root_path}")
    else:
        _warn("Could not auto-resolve folder from sharing link.")

    # Step 4 (once): Download destination and workers
    _section_header("04", "CONFIGURATION")

    default_dest = cfg["download_dest"] or str(Path.home() / "Downloads" / "sharepoint-dl")
    dest_str = Prompt.ask(
        "    [bold]Download destination[/bold]",
        default=default_dest,
    ).strip()
    batch_root = Path(dest_str)

    workers = IntPrompt.ask(
        "    [bold]Parallel workers[/bold] (1-8)",
        default=cfg["workers"],
    )
    workers = max(1, min(8, workers))

    # Throttle prompt
    throttle_default = cfg.get("throttle", "") or ""
    throttle_input = ""
    throttle_bucket = None
    while True:
        raw = Prompt.ask(
            "    [bold]Bandwidth limit?[/bold] (e.g. 5MB, Enter to skip)",
            default=throttle_default or "skip",
        ).strip()
        if raw == "skip" or raw == "":
            throttle_input = ""
            throttle_bucket = None
            break
        try:
            rate = parse_throttle(raw)
            if rate is not None:
                throttle_bucket = TokenBucket(rate)
                throttle_input = raw
            else:
                throttle_input = ""
                throttle_bucket = None
            break
        except ValueError as exc:
            _error(f"Invalid throttle value: {exc}")

    # Batch loop — each iteration downloads one folder
    batch_results: list[dict] = []
    current_path = root_path

    while True:
        # --- FOLDER SELECTION ---
        _section_header("02", "SELECT TARGET FOLDER")

        while True:
            if current_path is None:
                folder_url = Prompt.ask(
                    "    [bold]Paste the browser URL of the target folder[/bold]"
                ).strip()
                current_path = resolve_folder_from_browser_url(folder_url)
                if current_path is None:
                    _error("Could not extract folder path from that URL. Try again.")
                    continue

            # Show current folder and subfolders
            console.print(f"\n    [bright_cyan]Current:[/bright_cyan] {current_path}")

            with console.status("    [dim]Loading subfolders...[/dim]", spinner="dots"):
                try:
                    subfolders = _list_subfolders(session, site_url, current_path)
                except Exception:
                    subfolders = []

            if subfolders:
                console.print()
                for i, sf in enumerate(subfolders, 1):
                    console.print(
                        f"    [bright_magenta]{i:>3}.[/bright_magenta] [bright_cyan]{sf['name']}[/bright_cyan]"
                    )
                console.print(
                    f"    [bright_yellow]  0.[/bright_yellow] [bold bright_green]>> DOWNLOAD THIS FOLDER <<[/bold bright_green]"
                )
                console.print()

                choice = Prompt.ask(
                    "    Navigate or select",
                    default="0",
                ).strip()

                if choice == "0" or choice == "":
                    break
                try:
                    idx = int(choice)
                    if 1 <= idx <= len(subfolders):
                        current_path = subfolders[idx - 1]["path"]
                        continue
                    else:
                        _error("Invalid number.")
                        continue
                except ValueError:
                    resolved = resolve_folder_from_browser_url(choice)
                    if resolved:
                        current_path = resolved
                        continue
                    _error("Invalid input. Enter a number or paste a folder URL.")
                    continue
            else:
                _info("No subfolders — this is a leaf folder.")
                break

        server_relative_path = current_path
        folder_display = server_relative_path.rsplit("/", 1)[-1] if "/" in server_relative_path else server_relative_path

        # --- FILE ENUMERATION ---
        _section_header("03", "SCANNING FILES")

        with console.status("    [bright_cyan]Enumerating...[/bright_cyan]", spinner="dots"):
            try:
                files = enumerate_files(session, site_url, server_relative_path)
            except AuthExpiredError:
                _error("Session expired. Please restart.")
                raise typer.Exit(code=1)

        if not files:
            _warn("No files found in that folder.")
            raise typer.Exit(code=0)

        total_size = sum(f.size_bytes for f in files)
        _success(f"Found {len(files)} files ({_format_size(total_size)} total)")

        # Check if files span multiple folders
        unique_folders = {f.folder_path for f in files}
        has_subfolders = len(unique_folders) > 1

        # Prompt for layout if subfolders exist
        if has_subfolders:
            # Check for duplicate filenames that would collide in flat mode
            from collections import Counter
            name_counts = Counter(f.name for f in files)
            dupes = sum(1 for c in name_counts.values() if c > 1)

            console.print()
            console.print(f"    [bright_yellow]Files span {len(unique_folders)} folders.[/bright_yellow]")
            if dupes > 0:
                console.print(f"    [bright_red]Warning: {dupes} filenames appear in multiple folders — flat mode will overwrite duplicates![/bright_red]")
            console.print(f"    [bright_magenta]1.[/bright_magenta] [bold]Keep source folders[/bold] (recommended) [dim]— preserves original folder structure[/dim]")
            console.print(f"    [bright_magenta]2.[/bright_magenta] [bold]Flat[/bold] [dim]— all files in one folder{' ⚠ collisions!' if dupes > 0 else ''}[/dim]")
            layout_choice = Prompt.ask(
                "    [bold]File layout[/bold]",
                default="1",
            ).strip()
            flat = layout_choice == "2"
        else:
            flat = True  # Single folder — flat is fine

        layout_label = "flat (all files in one folder)" if flat else "keep source folders"

        # Confirm
        console.print()
        console.print(f"  [dim]{'─' * 44}[/dim]")
        console.print(f"  [bright_cyan]Folder:[/bright_cyan]  {folder_display}")
        console.print(f"  [bright_cyan]Files:[/bright_cyan]   {len(files)} ({_format_size(total_size)})")
        console.print(f"  [bright_cyan]Dest:[/bright_cyan]    {batch_root}")
        console.print(f"  [bright_cyan]Workers:[/bright_cyan] {workers}")
        console.print(f"  [bright_cyan]Layout:[/bright_cyan]  {layout_label}")
        console.print(f"  [dim]{'─' * 44}[/dim]")
        console.print()

        if not Confirm.ask("  [bold bright_yellow]>> Start download?[/bold bright_yellow]", default=True):
            _warn("Aborted.")
            batch_results.append({
                "folder": folder_display,
                "files": 0,
                "failed": 0,
                "elapsed": 0.0,
                "status": "CANCELLED",
            })
            break

        # --- PER-JOB SETUP ---
        # Metadata (state.json, manifest.json, download.log) at batch_root
        # Downloaded files go into timestamped subdirectory
        batch_root.mkdir(parents=True, exist_ok=True)
        job_files_dir = _job_dest(batch_root)
        dl_logger = setup_download_logger(batch_root)
        dl_logger.info("Session validated for %s", site_url)
        dl_logger.info("Enumerated %d files (%s total)", len(files), _format_size(total_size))
        dl_logger.info(
            "Starting download: %d files, %d workers, dest=%s, files=%s, flat=%s",
            len(files), workers, batch_root, job_files_dir, flat,
        )

        start_time = time.time()
        auth_expired = False
        completed: list[str] = []
        failed: list[tuple[str, str]] = []
        state: JobState | None = None

        cancelled = False
        try:
            def _do_reauth(url: str) -> None:
                console.print("  [bright_yellow]Session expired -- re-authenticating...[/bright_yellow]")
                harvest_session(url)

            reauth = ReauthController(session, site_url, on_reauth=_do_reauth)
            progress = _make_progress()
            with progress:
                completed, failed = download_all(
                    session, files, batch_root, site_url,
                    workers=workers, progress=progress, flat=flat,
                    on_auth_expired=reauth.trigger,
                    files_dir=job_files_dir,
                    throttle=throttle_bucket,
                )
        except AuthExpiredError:
            auth_expired = True
            state = JobState(batch_root)
            completed = state.complete_files()
            failed = state.failed_files()
            dl_logger.error(
                "Session expired during download -- %d completed, %d failed",
                len(completed), len(failed),
            )
        except KeyboardInterrupt:
            cancelled = True
            console.print("\n\n[yellow]Cancelled — saving progress...[/yellow]")
            state = JobState(batch_root)
            completed = state.complete_files()
            failed = state.failed_files()
            dl_logger.warning("Download cancelled by user -- %d completed", len(completed))
        else:
            state = JobState(batch_root)
        finally:
            elapsed = time.time() - start_time

        # Manifest (even on cancel -- captures what completed so far)
        manifest_path = None
        if state is not None and completed:
            manifest_path = generate_manifest(state, batch_root, sharing_url, server_relative_path, flat=flat)
            if manifest_path:
                dl_logger.info("Manifest written: %s", manifest_path)

        # Log completeness and failures
        dl_logger.info(
            "Completeness: %d expected, %d downloaded, %d failed",
            len(files), len(completed), len(failed),
        )
        if not auth_expired and not cancelled and not failed:
            dl_logger.info(
                "Download complete: %d files (%s) in %.1fs",
                len(completed), _format_size(total_size), elapsed,
            )
        for file_url, reason in failed:
            dl_logger.error("Failed: %s -- %s", file_url, reason)
        shutdown_download_logger()

        # Determine job status
        if cancelled:
            job_status = "CANCELLED"
        elif auth_expired:
            job_status = "AUTH_EXPIRED"
        elif failed:
            job_status = "FAILED"
        else:
            job_status = "OK"

        batch_results.append({
            "folder": folder_display,
            "files": len(completed),
            "failed": len(failed),
            "elapsed": elapsed,
            "status": job_status,
        })

        # Report for this job
        remaining = len(files) - len(completed) - len(failed)
        if cancelled:
            status_text = f"[bright_yellow]CANCELLED[/bright_yellow] — {len(completed)} complete, {remaining} remaining"
        elif auth_expired:
            status_text = f"[bright_red]SESSION EXPIRED[/bright_red] — {len(completed)} complete, {remaining} remaining"
        elif failed:
            status_text = f"[bright_red]INCOMPLETE[/bright_red] — {len(failed)} failed"
        else:
            status_text = "[bold bright_green]COMPLETE[/bold bright_green]"

        console.print()
        console.print(f"  [dim]{'═' * 44}[/dim]")
        console.print(f"  [bold bright_cyan]COMPLETENESS REPORT[/bold bright_cyan]")
        console.print(f"  [dim]{'─' * 44}[/dim]")
        console.print(f"  [bright_cyan]Expected:[/bright_cyan]   {len(files)}")
        console.print(f"  [bright_green]Downloaded:[/bright_green] {len(completed)}")
        if failed:
            console.print(f"  [bright_red]Failed:[/bright_red]     {len(failed)}")
        else:
            console.print(f"  [dim]Failed:[/dim]     0")
        console.print(f"  [bright_cyan]Status:[/bright_cyan]     {status_text}")

        if manifest_path:
            console.print(f"  [bright_magenta]Manifest:[/bright_magenta]   {manifest_path}")
        console.print(f"  [dim]{'═' * 44}[/dim]")

        if failed:
            console.print()
            error_table = Table(
                title="[bright_red]Failed Downloads[/bright_red]",
                border_style="bright_red",
                title_style="bold bright_red",
            )
            error_table.add_column("File", style="bright_yellow")
            error_table.add_column("Error", style="bright_red")
            for file_url, reason in failed:
                fname = file_url.rsplit("/", 1)[-1] if "/" in file_url else file_url
                error_table.add_row(fname, reason)
            console.print(error_table)

        if cancelled:
            console.print(
                "\n  [bright_yellow]Re-run to resume — completed files will be skipped.[/bright_yellow]"
            )
            break

        if auth_expired:
            console.print(
                "\n  [bright_red]Session expired. Re-run to resume — completed files skipped.[/bright_red]"
            )
            raise typer.Exit(code=1)

        # Offer to queue another folder
        console.print()
        if not Confirm.ask("  [bold]Queue another folder?[/bold]", default=False):
            break

        # Reset navigation to shared root for next job
        current_path = root_path

    # --- BATCH SUMMARY (shown when 2+ jobs completed) ---
    if len(batch_results) > 1:
        console.print()
        summary_table = Table(
            title="[bold bright_cyan]BATCH SUMMARY[/bold bright_cyan]",
            border_style="bright_cyan",
        )
        summary_table.add_column("Folder", style="bright_cyan")
        summary_table.add_column("Files", justify="right", style="bright_green")
        summary_table.add_column("Status", justify="center")
        summary_table.add_column("Time", justify="right", style="dim")
        for r in batch_results:
            status_style = "[bright_green]OK[/bright_green]" if r["status"] == "OK" else f"[bright_red]{r['status']}[/bright_red]"
            summary_table.add_row(
                r["folder"],
                str(r["files"]),
                status_style,
                f"{r['elapsed']:.0f}s",
            )
        console.print(summary_table)

    # Determine overall exit status
    any_auth_expired = any(r["status"] == "AUTH_EXPIRED" for r in batch_results)
    any_failed = any(r["status"] == "FAILED" for r in batch_results)

    # Determine if any jobs actually downloaded files
    ok_results = [r for r in batch_results if r["status"] == "OK"]
    total_downloaded = sum(r["files"] for r in batch_results)

    # Save config after any download attempt — captures user preferences
    # (URL, dest, workers) regardless of whether all files succeeded
    if batch_results:
        try:
            save_config({
                "sharepoint_url": sharing_url,
                "download_dest": str(batch_root),
                "workers": workers,
                "flat": flat,
                "throttle": throttle_input,
            })
        except Exception as exc:
            console.print(f"  [dim]Config save failed: {exc}[/dim]")

    if any_auth_expired:
        raise typer.Exit(code=1)

    if any_failed:
        raise typer.Exit(code=1)

    # Only show success summary and verify prompt when all jobs succeeded
    if ok_results and not any_failed and not any_auth_expired:
        last_ok = ok_results[-1]
        console.print(
            f"\n  [bold bright_green]Done![/bold bright_green] {total_downloaded} files "
            f"in {last_ok['elapsed']:.1f}s"
        )

    # Offer post-download verification only on clean completion
    if ok_results and not any_failed and not any_auth_expired and Confirm.ask("  [bold]Verify downloaded files?[/bold]", default=False):
        _section_header("06", "VERIFICATION")
        try:
            _run_verify(batch_root)
        except Exception as exc:
            _warn(f"Verification error: {exc}")


def _job_dest(batch_root: Path) -> Path:
    """Create a timestamped subdirectory for a download job.

    Naming: {YYYY-MM-DD_HHMMSS}
    Metadata (state.json, manifest.json, download.log) lives at batch_root.
    Downloaded files go into this timestamped subdirectory.
    """
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    job_dir = batch_root / ts
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def _parse_sharepoint_url(url: str) -> tuple[str, str]:
    """Extract site_url from a SharePoint URL.

    Args:
        url: SharePoint URL (sharing link or direct folder URL).

    Returns:
        Tuple of (site_url, server_relative_path).
        For sharing links, server_relative_path may not be extractable
        and will be empty (use --root-folder instead).
    """
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path_parts = parsed.path.strip("/").split("/")

    # SharePoint sharing links use /:f:/s/SiteName/... or /:f:/r/sites/SiteName/...
    # The /s/ is shorthand for /sites/, /p/ for /personal/
    shorthand_map = {"s": "sites", "p": "personal"}

    # Detect sharing link pattern: /:type:/shorthand/SiteName/...
    # Format 1 (OTP):  /:f:/s/SiteName/...  → shorthand s = sites
    # Format 2 (auth): /:f:/r/sites/SiteName/... → r is literal, sites/SiteName follows
    if len(path_parts) >= 3 and path_parts[0].startswith(":") and path_parts[0].endswith(":"):
        shorthand = path_parts[1]
        if shorthand == "r" and len(path_parts) >= 4 and path_parts[2] in ("sites", "personal"):
            # Format 2: /:f:/r/sites/SiteName/... — r is literal, next two are prefix/name
            site_url = f"{base}/{path_parts[2]}/{path_parts[3]}"
        else:
            # Format 1: /:f:/s/SiteName/... — shorthand maps to prefix
            site_name = path_parts[2]
            prefix = shorthand_map.get(shorthand, shorthand)
            site_url = f"{base}/{prefix}/{site_name}"
        return site_url, ""

    # Standard patterns: /sites/{name}/... or /personal/{name}/...
    if len(path_parts) >= 2 and path_parts[0] in ("sites", "personal"):
        site_url = f"{base}/{path_parts[0]}/{path_parts[1]}"
        remaining = "/".join(path_parts[2:])
        if remaining:
            server_relative_path = f"/{'/'.join(path_parts)}"
        else:
            server_relative_path = ""
    else:
        site_url = base
        server_relative_path = parsed.path if parsed.path != "/" else ""

    return site_url, server_relative_path


@app.command()
def auth(
    url: str = typer.Argument(..., help="SharePoint sharing URL"),
) -> None:
    """Authenticate against SharePoint and save session cookies."""
    try:
        harvest_session(url)
        console.print(f"[green]Session saved. You can now run 'sharepoint-dl list {url}'[/green]")
    except TimeoutError:
        console.print(
            "[red]Authentication timed out. Please try again and complete login "
            "within the timeout window.[/red]"
        )
        raise typer.Exit(code=1)


@app.command()
def verify(
    dest: Path = typer.Argument(..., help="Download destination directory containing manifest.json"),
) -> None:
    """Verify downloaded files against their manifest SHA-256 hashes."""
    from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TextColumn
    from rich.table import Table

    try:
        with Progress(
            SpinnerColumn(style="bright_magenta"),
            TextColumn("[bright_cyan]{task.description}[/bright_cyan]"),
            BarColumn(bar_width=None, complete_style="bright_magenta", finished_style="bright_green"),
            DownloadColumn(binary_units=True),
            console=console,
        ) as progress:
            task_id = None

            def on_progress(name: str, size_bytes: int) -> None:
                nonlocal task_id
                if task_id is not None:
                    progress.update(task_id, advance=size_bytes)

            # First pass: get total size for progress bar
            import json as _json
            manifest_path = dest / "manifest.json"
            if not manifest_path.exists():
                console.print("[red]No manifest.json found in the specified directory.[/red]")
                raise typer.Exit(code=1)

            manifest_data = _json.loads(manifest_path.read_text(encoding="utf-8"))
            total_bytes = sum(
                f.get("size_bytes", 0) for f in manifest_data.get("files", [])
            )

            task_id = progress.add_task("Verifying files", total=total_bytes)
            summary = verify_manifest(dest, on_progress=on_progress)

    except FileNotFoundError:
        console.print("[red]No manifest.json found in the specified directory.[/red]")
        raise typer.Exit(code=1)

    # Print results table
    table = Table(
        title="[bold bright_cyan]Verification Results[/bold bright_cyan]",
        border_style="bright_cyan",
    )
    table.add_column("File", style="bright_cyan")
    table.add_column("Status", justify="center")
    table.add_column("Expected SHA-256", style="dim")
    table.add_column("Actual SHA-256", style="dim")

    for result in summary.results:
        if result.status == "PASS":
            status_text = "[bold bright_green]PASS[/bold bright_green]"
        elif result.status == "FAIL":
            status_text = "[bold bright_red]FAIL[/bold bright_red]"
        else:
            status_text = "[bold bright_yellow]MISSING[/bold bright_yellow]"

        expected_short = result.expected_sha256[:16] + "..."
        actual_short = (result.actual_sha256[:16] + "...") if result.actual_sha256 else "—"

        table.add_row(result.name, status_text, expected_short, actual_short)

    console.print(table)

    # Print summary
    console.print()
    if summary.failed == 0 and summary.missing == 0:
        console.print(
            f"  [bold bright_green]{summary.passed}/{summary.total} files verified OK[/bold bright_green]"
        )
    else:
        parts = []
        if summary.passed > 0:
            parts.append(f"[bright_green]{summary.passed} OK[/bright_green]")
        if summary.failed > 0:
            parts.append(f"[bright_red]{summary.failed} failed[/bright_red]")
        if summary.missing > 0:
            parts.append(f"[bright_yellow]{summary.missing} missing[/bright_yellow]")
        console.print(f"  {' · '.join(parts)}")
        raise typer.Exit(code=1)


@app.command(name="list")
def list_files(
    url: str = typer.Argument(..., help="SharePoint folder URL"),
    root_folder: str | None = typer.Option(
        None,
        "--root-folder", "-r",
        help="Server-relative path to the folder to enumerate. "
        "If omitted, auto-detected from the sharing link URL.",
    ),
) -> None:
    """List all files in a SharePoint folder with summary table."""
    session = load_session(url)
    if session is None:
        console.print(
            "[red]No active session. Run 'sharepoint-dl auth <url>' first.[/red]"
        )
        raise typer.Exit(code=1)

    site_url, _auto_path = _parse_sharepoint_url(url)

    if not validate_session(session, site_url):
        console.print(
            "[red]Session expired. Run 'sharepoint-dl auth <url>' to re-authenticate.[/red]"
        )
        raise typer.Exit(code=1)

    if root_folder is None:
        with console.status("[bold green]Resolving folder from sharing link...", spinner="dots"):
            root_folder = resolve_sharing_link(session, url)
        if root_folder is None:
            console.print(
                "[red]Could not auto-detect folder from URL. "
                "Please specify --root-folder (-r) manually.[/red]"
            )
            raise typer.Exit(code=1)
        console.print(f"[green]Auto-detected folder:[/green] {root_folder}")

    server_relative_path = root_folder

    try:
        with console.status("[bold green]Scanning folders...", spinner="dots"):
            files = enumerate_files(session, site_url, server_relative_path)
    except AuthExpiredError:
        console.print(
            "[red]Session expired during enumeration. "
            "Run 'sharepoint-dl auth <url>' to re-authenticate.[/red]"
        )
        raise typer.Exit(code=1)

    # Build summary table grouped by folder
    folder_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "size": 0})
    for f in files:
        folder_stats[f.folder_path]["count"] += 1
        folder_stats[f.folder_path]["size"] += f.size_bytes

    table = Table(title="Enumeration Results")
    table.add_column("Folder", style="cyan")
    table.add_column("Files", justify="right", style="green")
    table.add_column("Size", justify="right", style="yellow")

    total_size = 0
    for folder_path in sorted(folder_stats.keys()):
        stats = folder_stats[folder_path]
        table.add_row(folder_path, str(stats["count"]), _format_size(stats["size"]))
        total_size += stats["size"]

    console.print(table)
    console.print(
        f"\nFound [bold]{len(files)} files[/bold] "
        f"({_format_size(total_size)} total) "
        f"across [bold]{len(folder_stats)} folders[/bold]"
    )


@app.command()
def download(
    url: str = typer.Argument(..., help="SharePoint folder URL"),
    dest: Path = typer.Argument(..., help="Local download destination"),
    root_folder: str | None = typer.Option(
        None,
        "--root-folder",
        "-r",
        help="Server-relative path to the folder to download. "
        "If omitted, auto-detected from the sharing link URL.",
    ),
    workers: int = typer.Option(
        3,
        "--workers",
        "-w",
        min=1,
        max=8,
        help="Number of concurrent download workers (default: 3)",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt",
    ),
    flat: bool = typer.Option(
        False,
        "--flat",
        help="Download all files directly into dest folder (no subdirectories)",
    ),
    no_manifest: bool = typer.Option(
        False,
        "--no-manifest",
        help="Skip manifest.json generation (for testing/debugging only)",
    ),
    throttle_str: str | None = typer.Option(
        None,
        "--throttle",
        help="Bandwidth limit (e.g. 10MB, 50MB, 500KB). Shared across all workers.",
        show_default=False,
    ),
) -> None:
    """Download all files from a SharePoint folder."""
    # Load config to pre-fill defaults
    cfg = load_config()

    # Apply config defaults for options not explicitly set by the user
    # Typer uses the declared defaults (3 for workers, False for flat) so compare to those
    if workers == 3 and cfg["workers"] != 3:
        workers = cfg["workers"]
    if not flat and cfg["flat"]:
        flat = cfg["flat"]

    # Parse throttle
    throttle_bucket: TokenBucket | None = None
    if throttle_str is not None:
        try:
            rate_bps = parse_throttle(throttle_str)
        except ValueError as exc:
            console.print(f"[red]Invalid --throttle value: {exc}[/red]")
            raise typer.Exit(code=1)
        if rate_bps is not None:
            throttle_bucket = TokenBucket(rate_bps)

    # 1. Load session
    session = load_session(url)
    if session is None:
        console.print(
            "[red]No active session. Run 'sharepoint-dl auth <url>' first.[/red]"
        )
        raise typer.Exit(code=1)

    # 2. Parse URL
    site_url, _auto_path = _parse_sharepoint_url(url)

    # 3. Validate session
    if not validate_session(session, site_url):
        console.print(
            "[red]Session expired. Run 'sharepoint-dl auth <url>' to re-authenticate.[/red]"
        )
        raise typer.Exit(code=1)

    # 3b. Auto-detect root folder if not provided
    if root_folder is None:
        with console.status("[bold green]Resolving folder from sharing link...", spinner="dots"):
            root_folder = resolve_sharing_link(session, url)
        if root_folder is None:
            console.print(
                "[red]Could not auto-detect folder from URL. "
                "Please specify --root-folder (-r) manually.[/red]"
            )
            raise typer.Exit(code=1)
        console.print(f"[green]Auto-detected folder:[/green] {root_folder}")

    server_relative_path = root_folder

    # 4. Enumerate files
    try:
        with console.status("[bold green]Scanning folders...", spinner="dots"):
            files = enumerate_files(session, site_url, server_relative_path)
    except AuthExpiredError:
        console.print(
            "[red]Session expired during enumeration. "
            "Run 'sharepoint-dl auth <url>' to re-authenticate.[/red]"
        )
        raise typer.Exit(code=1)

    if not files:
        console.print("[yellow]No files found in the specified folder.[/yellow]")
        raise typer.Exit(code=0)

    # 5. Confirmation prompt
    total_size = sum(f.size_bytes for f in files)
    count = len(files)
    console.print(
        f"\nDownload [bold]{count} file{'s' if count != 1 else ''}[/bold] "
        f"({_format_size(total_size)}) to [bold]{dest}[/bold]?"
    )
    if not yes:
        if not typer.confirm("Proceed?", default=True):
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(code=0)

    # 6. Create destination directory
    dest.mkdir(parents=True, exist_ok=True)
    dl_logger = setup_download_logger(dest)
    dl_logger.info("Session validated for %s", site_url)
    dl_logger.info("Enumerated %d files (%s total)", len(files), _format_size(total_size))
    dl_logger.info(
        "Starting download: %d files, %d workers, dest=%s, flat=%s",
        count, workers, dest, flat,
    )
    if throttle_bucket is not None:
        dl_logger.info("Throttling to %s", throttle_str)

    # 7-8. Download with progress
    start_time = time.time()
    auth_expired = False
    cancelled = False
    completed: list[str] = []
    failed: list[tuple[str, str]] = []
    state: JobState | None = None
    try:
        def _do_reauth(url: str) -> None:
            console.print("  [bright_yellow]Session expired -- re-authenticating...[/bright_yellow]")
            harvest_session(url)

        reauth = ReauthController(session, site_url, on_reauth=_do_reauth)
        progress = _make_progress()
        with progress:
            completed, failed = download_all(
                session,
                files,
                dest,
                site_url,
                workers=workers,
                progress=progress,
                flat=flat,
                throttle=throttle_bucket,
                on_auth_expired=reauth.trigger,
            )
    except AuthExpiredError:
        auth_expired = True
        state = JobState(dest)
        completed = state.complete_files()
        failed = state.failed_files()
        dl_logger.error(
            "Session expired during download -- %d completed, %d failed",
            len(completed), len(failed),
        )
    except KeyboardInterrupt:
        cancelled = True
        console.print("\n\n[yellow]Cancelled — saving progress...[/yellow]")
        state = JobState(dest)
        completed = state.complete_files()
        failed = state.failed_files()
        dl_logger.warning("Download cancelled by user -- %d completed", len(completed))
    else:
        state = JobState(dest)
    finally:
        elapsed = time.time() - start_time

    # 9. Manifest generation
    manifest_path = None
    if not no_manifest and state is not None:
        manifest_path = generate_manifest(state, dest, url, root_folder, flat=flat)
        if manifest_path:
            dl_logger.info("Manifest written: %s", manifest_path)

    # Log completeness and failures
    dl_logger.info(
        "Completeness: %d expected, %d downloaded, %d failed",
        len(files), len(completed), len(failed),
    )
    if not auth_expired and not cancelled and not failed:
        dl_logger.info(
            "Download complete: %d files (%s) in %.1fs",
            len(completed), _format_size(total_size), elapsed,
        )
    for file_url, reason in failed:
        dl_logger.error("Failed: %s -- %s", file_url, reason)
    shutdown_download_logger()

    # 10. Completeness report
    status_ok = not auth_expired and len(failed) == 0
    status_text = (
        "[green]COMPLETE[/green]"
        if status_ok
        else f"[red]INCOMPLETE — {len(failed)} file{'s' if len(failed) != 1 else ''} failed[/red]"
    )
    console.print("\nCompleteness Report")
    console.print("-------------------")
    console.print(f"Expected:   {len(files)}")
    console.print(f"Downloaded: {len(completed)}")
    console.print(f"Failed:     {len(failed)}")
    console.print(f"Status:     {status_text}")

    if manifest_path is not None:
        console.print(f"\nManifest written to: {manifest_path}")

    # 11. Error summary
    if failed:
        error_table = Table(title="Failed Downloads", style="red")
        error_table.add_column("File", style="red")
        error_table.add_column("Error", style="red")
        for file_url, reason in failed:
            # Show just the filename from the URL
            fname = file_url.rsplit("/", 1)[-1] if "/" in file_url else file_url
            error_table.add_row(fname, reason)
        console.print(error_table)

        console.print(
            f"\n[green]{len(completed)} file{'s' if len(completed) != 1 else ''} "
            f"downloaded successfully.[/green]"
        )
        console.print(
            f"[red]{len(failed)} file{'s' if len(failed) != 1 else ''} failed.[/red]"
        )
        if auth_expired:
            console.print(
                "\n[red]Session expired during download. "
                "Re-authenticate with 'sharepoint-dl auth <url>' and re-run. "
                "Completed files will be skipped on resume.[/red]"
            )
        raise typer.Exit(code=1)

    if auth_expired:
        console.print(
            "\n[red]Session expired during download. "
            "Re-authenticate with 'sharepoint-dl auth <url>' and re-run. "
            "Completed files will be skipped on resume.[/red]"
        )
        raise typer.Exit(code=1)

    # Save config after successful download
    try:
        save_config({
            "sharepoint_url": url,
            "download_dest": str(dest),
            "workers": workers,
            "flat": flat,
            "throttle": throttle_str or "",
        })
    except Exception:
        pass  # Config save is best-effort; don't fail the download

    # 12. Success summary
    avg_speed = total_size / elapsed if elapsed > 0 else 0
    console.print(
        f"\n[green]Downloaded {len(completed)} file{'s' if len(completed) != 1 else ''} "
        f"({_format_size(total_size)}) in {elapsed:.1f}s "
        f"({_format_size(int(avg_speed))}/s)[/green]"
    )
