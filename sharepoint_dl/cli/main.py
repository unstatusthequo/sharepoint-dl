"""Typer CLI app for SharePoint bulk file downloader."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import typer
from rich.console import Console
from rich.table import Table

from sharepoint_dl.auth.browser import harvest_session
from sharepoint_dl.auth.session import load_session, validate_session
from sharepoint_dl.enumerator.traversal import AuthExpiredError, enumerate_files

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
    site_url = f"{parsed.scheme}://{parsed.netloc}"

    # Try to extract site path (e.g. /sites/shared)
    path_parts = parsed.path.strip("/").split("/")

    # Common patterns: /sites/{name}/... or /personal/{name}/...
    if len(path_parts) >= 2 and path_parts[0] in ("sites", "personal"):
        site_url = f"{site_url}/{path_parts[0]}/{path_parts[1]}"
        remaining = "/".join(path_parts[2:])
        if remaining:
            server_relative_path = f"/{'/'.join(path_parts)}"
        else:
            server_relative_path = ""
    else:
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
        "",
        "--root-folder",
        help="Server-relative path to the root folder (e.g. /sites/shared/Shared Documents/Images). "
        "Required if the URL is a sharing link that cannot be parsed automatically.",
    ),
) -> None:
    """List all files in a SharePoint folder with summary table."""
    session = load_session(url)
    if session is None:
        console.print(
            "[red]No active session. Run 'sharepoint-dl auth <url>' first.[/red]"
        )
        raise typer.Exit(code=1)

    site_url, auto_path = _parse_sharepoint_url(url)
    server_relative_path = root_folder or auto_path

    if not validate_session(session, site_url):
        console.print(
            "[red]Session expired. Run 'sharepoint-dl auth <url>' to re-authenticate.[/red]"
        )
        raise typer.Exit(code=1)

    if not server_relative_path:
        console.print(
            "[red]Cannot determine folder path from URL. "
            "Please specify --root-folder.[/red]"
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
) -> None:
    """Download all files from a SharePoint folder. (Coming in Phase 2)"""
    console.print("[yellow]Download not yet implemented. Coming in Phase 2.[/yellow]")
    raise typer.Exit(code=1)
