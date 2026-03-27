"""Typer CLI app for SharePoint bulk file downloader."""

from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import typer
from rich.console import Console
from rich.table import Table

from sharepoint_dl.auth.browser import harvest_session
from sharepoint_dl.auth.session import load_session, validate_session
from sharepoint_dl.downloader.engine import _make_progress, download_all
from sharepoint_dl.enumerator.traversal import AuthExpiredError, enumerate_files
from sharepoint_dl.manifest import generate_manifest
from sharepoint_dl.state.job_state import JobState

app = typer.Typer(
    no_args_is_help=True,
    help="SharePoint bulk file downloader for forensic evidence collection.",
)

console = Console()


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
    if len(path_parts) >= 3 and path_parts[0].startswith(":") and path_parts[0].endswith(":"):
        shorthand = path_parts[1]
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


@app.command(name="list")
def list_files(
    url: str = typer.Argument(..., help="SharePoint folder URL"),
    root_folder: str = typer.Option(
        ...,
        "--root-folder", "-r",
        help="Server-relative path to the folder to enumerate "
        "(e.g. '/sites/CyberSecurityTeam/Shared Documents/Images'). "
        "REQUIRED — prevents accidentally scanning the entire site.",
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
    server_relative_path = root_folder

    if not validate_session(session, site_url):
        console.print(
            "[red]Session expired. Run 'sharepoint-dl auth <url>' to re-authenticate.[/red]"
        )
        raise typer.Exit(code=1)

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
    root_folder: str = typer.Option(
        ...,
        "--root-folder",
        "-r",
        help="Server-relative path to the folder to download",
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
) -> None:
    """Download all files from a SharePoint folder."""
    # 1. Load session
    session = load_session(url)
    if session is None:
        console.print(
            "[red]No active session. Run 'sharepoint-dl auth <url>' first.[/red]"
        )
        raise typer.Exit(code=1)

    # 2. Parse URL
    site_url, _auto_path = _parse_sharepoint_url(url)
    server_relative_path = root_folder

    # 3. Validate session
    if not validate_session(session, site_url):
        console.print(
            "[red]Session expired. Run 'sharepoint-dl auth <url>' to re-authenticate.[/red]"
        )
        raise typer.Exit(code=1)

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

    # 7-8. Download with progress
    start_time = time.time()
    auth_expired = False
    completed: list[str] = []
    failed: list[tuple[str, str]] = []
    state: JobState | None = None
    try:
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
            )
    except AuthExpiredError:
        auth_expired = True
        state = JobState(dest)
        completed = state.complete_files()
        failed = state.failed_files()
    else:
        state = JobState(dest)

    elapsed = time.time() - start_time

    # 9. Manifest generation
    manifest_path = None
    if not no_manifest and state is not None:
        manifest_path = generate_manifest(state, dest, url, root_folder)

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

    # 12. Success summary
    avg_speed = total_size / elapsed if elapsed > 0 else 0
    console.print(
        f"\n[green]Downloaded {len(completed)} file{'s' if len(completed) != 1 else ''} "
        f"({_format_size(total_size)}) in {elapsed:.1f}s "
        f"({_format_size(int(avg_speed))}/s)[/green]"
    )
