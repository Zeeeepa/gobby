"""CLI commands for code indexing.

Bulk indexing operations run through the daemon's HTTP API,
giving unbounded execution time with streaming progress output.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import click

from gobby.config.app import DaemonConfig

if TYPE_CHECKING:
    from gobby.utils.daemon_client import DaemonClient


def _get_daemon_client(ctx: click.Context) -> DaemonClient:
    """Get a DaemonClient for calling daemon HTTP API."""
    from gobby.utils.daemon_client import DaemonClient

    config: DaemonConfig = ctx.obj["config"]
    return DaemonClient(host="localhost", port=config.daemon_port)


def _require_daemon(client: DaemonClient) -> None:
    """Check daemon is running, raise ClickException if not."""
    is_healthy, err = client.check_health()
    if not is_healthy:
        raise click.ClickException(f"Daemon not running: {err}")


@click.group("code-index")
def code_index() -> None:
    """Code indexing commands."""
    pass


@code_index.command("index")
@click.argument("path", default=".")
@click.option("--project-id", "-p", default="", help="Project ID (default: auto-detect)")
@click.option("--full", is_flag=True, help="Full re-index (skip incremental)")
@click.pass_context
def index_cmd(ctx: click.Context, path: str, project_id: str, full: bool) -> None:
    """Index a directory for code navigation.

    Indexes all supported source files in PATH, extracting symbols
    (functions, classes, methods) for code navigation and search.

    Incremental by default — only re-indexes changed files.

    Examples:

        gobby code-index index src/

        gobby code-index index . --full

        gobby code-index index /path/to/project -p my-project
    """
    abs_path = os.path.abspath(path)
    if not os.path.isdir(abs_path):
        raise click.ClickException(f"Not a directory: {abs_path}")

    client = _get_daemon_client(ctx)
    _require_daemon(client)

    incremental = not full
    click.echo(f"Indexing {abs_path} ({'incremental' if incremental else 'full'})...")

    response = client.call_http_api(
        "/api/code-index/index",
        method="POST",
        json_data={
            "path": abs_path,
            "project_id": project_id,
            "incremental": incremental,
        },
        timeout=600.0,
    )

    if not response.ok:
        raise click.ClickException(
            f"Indexing failed (HTTP {response.status_code}): {response.text}"
        )

    try:
        data = response.json()
    except ValueError as e:
        raise click.ClickException(f"Invalid response from daemon: {e}") from e

    files_indexed = data.get("files_indexed", 0)
    files_skipped = data.get("files_skipped", 0)
    symbols_found = data.get("symbols_found", 0)
    duration_ms = data.get("duration_ms", 0)
    errors = data.get("errors", [])

    click.echo(f"Done in {duration_ms}ms:")
    click.echo(f"  Files indexed: {files_indexed}")
    click.echo(f"  Files skipped: {files_skipped}")
    click.echo(f"  Symbols found: {symbols_found}")

    if errors:
        click.echo(f"  Errors: {len(errors)}")
        for err in errors[:5]:
            click.echo(f"    - {err}")


@code_index.command("status")
@click.option("--project-id", "-p", default="", help="Project ID")
@click.pass_context
def status_cmd(ctx: click.Context, project_id: str) -> None:
    """Show indexing status.

    Without --project-id, lists all indexed projects.
    With --project-id, shows detailed stats for that project.

    Examples:

        gobby code-index status

        gobby code-index status -p my-project
    """
    client = _get_daemon_client(ctx)
    _require_daemon(client)

    params = f"?project_id={project_id}" if project_id else ""
    response = client.call_http_api(
        f"/api/code-index/status{params}",
        method="GET",
    )

    if not response.ok:
        raise click.ClickException(
            f"Status check failed (HTTP {response.status_code}): {response.text}"
        )

    try:
        data = response.json()
    except ValueError as e:
        raise click.ClickException(f"Invalid response from daemon: {e}") from e

    if "projects" in data:
        projects = data["projects"]
        if not projects:
            click.echo("No indexed projects.")
            return
        click.echo(f"Indexed projects ({len(projects)}):")
        for proj in projects:
            click.echo(
                f"  {proj.get('id', '?')}: "
                f"{proj.get('total_files', 0)} files, "
                f"{proj.get('total_symbols', 0)} symbols"
            )
            if proj.get("last_indexed_at"):
                click.echo(f"    Last indexed: {proj['last_indexed_at']}")
    else:
        if not data.get("indexed"):
            click.echo(f"Project '{project_id}' is not indexed.")
            return
        click.echo(f"Project: {data.get('id', project_id)}")
        click.echo(f"  Root: {data.get('root_path', '?')}")
        click.echo(f"  Files: {data.get('total_files', 0)}")
        click.echo(f"  Symbols: {data.get('total_symbols', 0)}")
        if data.get("last_indexed_at"):
            click.echo(f"  Last indexed: {data['last_indexed_at']}")
        if data.get("index_duration_ms"):
            click.echo(f"  Duration: {data['index_duration_ms']}ms")


@code_index.command("invalidate")
@click.option("--project-id", "-p", default="", help="Project ID")
@click.pass_context
def invalidate_cmd(ctx: click.Context, project_id: str) -> None:
    """Clear index for a project, forcing full re-index next time.

    Examples:

        gobby code-index invalidate -p my-project
    """
    client = _get_daemon_client(ctx)
    _require_daemon(client)

    response = client.call_http_api(
        "/api/code-index/invalidate",
        method="POST",
        json_data={"project_id": project_id},
    )

    if not response.ok:
        raise click.ClickException(
            f"Invalidation failed (HTTP {response.status_code}): {response.text}"
        )

    try:
        data = response.json()
    except ValueError as e:
        raise click.ClickException(f"Invalid response from daemon: {e}") from e

    click.echo(f"Index invalidated for project: {data.get('project_id', project_id or 'default')}")
