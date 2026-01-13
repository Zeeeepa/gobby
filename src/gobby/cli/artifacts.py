"""CLI commands for session artifacts."""

import json
from typing import Any

import click

from gobby.storage.artifacts import Artifact, LocalArtifactManager
from gobby.storage.database import LocalDatabase


def get_artifact_manager() -> LocalArtifactManager:
    """Get the artifact manager."""
    db = LocalDatabase()
    return LocalArtifactManager(db)


@click.group()
def artifacts() -> None:
    """Manage session artifacts (code, diffs, errors)."""
    pass


@artifacts.command()
@click.argument("query")
@click.option("--session", "-s", "session_id", help="Filter by session ID")
@click.option("--type", "-t", "artifact_type", help="Filter by artifact type (code, diff, error)")
@click.option("--limit", "-n", default=50, help="Maximum results")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def search(
    query: str,
    session_id: str | None,
    artifact_type: str | None,
    limit: int,
    output_json: bool,
) -> None:
    """Search artifacts by content.

    Uses full-text search to find matching artifacts.
    """
    manager = get_artifact_manager()
    artifacts_list = manager.search_artifacts(
        query_text=query,
        session_id=session_id,
        artifact_type=artifact_type,
        limit=limit,
    )

    if not artifacts_list:
        if output_json:
            click.echo(json.dumps({"artifacts": [], "count": 0}))
        else:
            click.echo("No artifacts found")
        return

    if output_json:
        click.echo(
            json.dumps(
                {
                    "artifacts": [a.to_dict() for a in artifacts_list],
                    "count": len(artifacts_list),
                },
                indent=2,
            )
        )
    else:
        _display_artifact_list(artifacts_list)


@artifacts.command("list")
@click.option("--session", "-s", "session_id", help="Filter by session ID")
@click.option("--type", "-t", "artifact_type", help="Filter by artifact type (code, diff, error)")
@click.option("--limit", "-n", default=100, help="Maximum results")
@click.option("--offset", "-o", default=0, help="Offset for pagination")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def list_artifacts(
    session_id: str | None,
    artifact_type: str | None,
    limit: int,
    offset: int,
    output_json: bool,
) -> None:
    """List artifacts with optional filters."""
    manager = get_artifact_manager()
    artifacts_list = manager.list_artifacts(
        session_id=session_id,
        artifact_type=artifact_type,
        limit=limit,
        offset=offset,
    )

    if output_json:
        click.echo(
            json.dumps(
                {
                    "artifacts": [a.to_dict() for a in artifacts_list],
                    "count": len(artifacts_list),
                },
                indent=2,
            )
        )
    else:
        if not artifacts_list:
            click.echo("No artifacts found")
            return
        _display_artifact_list(artifacts_list)


@artifacts.command()
@click.argument("artifact_id")
@click.option("--verbose", "-v", is_flag=True, help="Show full metadata")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def show(artifact_id: str, verbose: bool, output_json: bool) -> None:
    """Display a single artifact by ID."""
    manager = get_artifact_manager()
    artifact = manager.get_artifact(artifact_id)

    if artifact is None:
        if output_json:
            click.echo(json.dumps({"error": f"Artifact '{artifact_id}' not found"}))
        else:
            click.echo(f"Artifact not found: {artifact_id}", err=True)
        raise SystemExit(1)

    if output_json:
        click.echo(json.dumps(artifact.to_dict(), indent=2))
    else:
        _display_artifact_detail(artifact, verbose)


@artifacts.command()
@click.argument("session_id")
@click.option("--type", "-t", "artifact_type", help="Filter by artifact type")
@click.option("--limit", "-n", default=100, help="Maximum results")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def timeline(
    session_id: str,
    artifact_type: str | None,
    limit: int,
    output_json: bool,
) -> None:
    """Show artifacts for a session in chronological order.

    Displays artifacts from oldest to newest.
    """
    manager = get_artifact_manager()
    artifacts_list = manager.list_artifacts(
        session_id=session_id,
        artifact_type=artifact_type,
        limit=limit,
        offset=0,
    )

    # Reverse to get chronological order (oldest first)
    artifacts_list = list(reversed(artifacts_list))

    if output_json:
        click.echo(
            json.dumps(
                {
                    "session_id": session_id,
                    "artifacts": [a.to_dict() for a in artifacts_list],
                    "count": len(artifacts_list),
                },
                indent=2,
            )
        )
    else:
        if not artifacts_list:
            click.echo(f"No artifacts found for session: {session_id}")
            return
        click.echo(f"Timeline for session: {session_id}")
        click.echo("-" * 60)
        for artifact in artifacts_list:
            _display_timeline_entry(artifact)


def _display_artifact_list(artifacts_list: list[Any]) -> None:
    """Display a list of artifacts in table format."""
    # Header
    click.echo(f"{'ID':<12} {'Type':<8} {'Source':<20} {'Created':<20}")
    click.echo("-" * 60)

    for artifact in artifacts_list:
        artifact_id = artifact.id[:12] if len(artifact.id) > 12 else artifact.id
        source = artifact.source_file or "-"
        if len(source) > 18:
            source = "..." + source[-15:]
        created = artifact.created_at[:19] if artifact.created_at else "-"
        click.echo(f"{artifact_id:<12} {artifact.artifact_type:<8} {source:<20} {created:<20}")


def _display_artifact_detail(artifact: Artifact, verbose: bool) -> None:
    """Display a single artifact with optional verbosity."""
    click.echo(f"ID: {artifact.id}")
    click.echo(f"Type: {artifact.artifact_type}")
    click.echo(f"Session: {artifact.session_id}")

    if artifact.source_file:
        location = artifact.source_file
        if artifact.line_start:
            location += f":{artifact.line_start}"
            if artifact.line_end and artifact.line_end != artifact.line_start:
                location += f"-{artifact.line_end}"
        click.echo(f"Source: {location}")

    click.echo(f"Created: {artifact.created_at}")

    if verbose and artifact.metadata:
        click.echo(f"Metadata: {json.dumps(artifact.metadata, indent=2)}")

    click.echo("")
    click.echo("-" * 60)

    # Display content with syntax highlighting for code
    _display_content(artifact.content, artifact.artifact_type, artifact.metadata)


def _display_content(content: str, artifact_type: str, metadata: dict[str, Any] | None) -> None:
    """Display content with appropriate formatting."""
    # Try to use rich for syntax highlighting if available
    try:
        from rich.console import Console
        from rich.syntax import Syntax

        console = Console()

        # Determine language for syntax highlighting
        language = None
        if metadata and "language" in metadata:
            language = metadata["language"]
        elif artifact_type == "code":
            # Default to python if no language specified
            language = "python"
        elif artifact_type == "diff":
            language = "diff"
        elif artifact_type == "error":
            language = "text"

        if language:
            syntax = Syntax(content, language, theme="monokai", line_numbers=True)
            console.print(syntax)
        else:
            click.echo(content)

    except ImportError:
        # Fall back to plain text
        click.echo(content)


def _display_timeline_entry(artifact: Artifact) -> None:
    """Display a single timeline entry."""
    click.echo(f"[{artifact.created_at[:19]}] {artifact.artifact_type.upper()}: {artifact.id}")
    if artifact.source_file:
        click.echo(f"  Source: {artifact.source_file}")

    # Show a preview of the content (first 2 lines)
    lines = artifact.content.split("\n")[:2]
    for line in lines:
        if len(line) > 60:
            line = line[:57] + "..."
        click.echo(f"  | {line}")

    if len(artifact.content.split("\n")) > 2:
        click.echo(f"  | ... ({len(artifact.content.split(chr(10)))} lines total)")
    click.echo("")
