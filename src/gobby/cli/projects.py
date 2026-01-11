"""
Project management CLI commands.
"""

import json

import click

from gobby.storage.database import LocalDatabase
from gobby.storage.projects import LocalProjectManager


def get_project_manager() -> LocalProjectManager:
    """Get initialized project manager."""
    db = LocalDatabase()
    return LocalProjectManager(db)


@click.group()
def projects() -> None:
    """Manage Gobby projects."""
    pass


@projects.command("list")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def list_projects(json_format: bool) -> None:
    """List all known projects."""
    manager = get_project_manager()
    projects_list = manager.list()

    if json_format:
        click.echo(json.dumps([p.to_dict() for p in projects_list], indent=2, default=str))
        return

    if not projects_list:
        click.echo("No projects found.")
        click.echo("Use 'gobby init' in a project directory to register it.")
        return

    click.echo(f"Found {len(projects_list)} project(s):\n")
    for project in projects_list:
        path_info = f"  {project.repo_path}" if project.repo_path else ""
        click.echo(f"  {project.name:<20} {project.id[:12]}{path_info}")


@projects.command("show")
@click.argument("project_ref")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def show_project(project_ref: str, json_format: bool) -> None:
    """Show details for a project.

    PROJECT_REF can be a project name or UUID.
    """
    manager = get_project_manager()

    # Try as UUID first, then as name
    project = manager.get(project_ref)
    if not project:
        project = manager.get_by_name(project_ref)

    if not project:
        click.echo(f"Project not found: {project_ref}", err=True)
        raise SystemExit(1)

    if json_format:
        click.echo(json.dumps(project.to_dict(), indent=2, default=str))
        return

    click.echo(f"Project: {project.name}")
    click.echo(f"  ID: {project.id}")
    if project.repo_path:
        click.echo(f"  Path: {project.repo_path}")
    if project.github_url:
        click.echo(f"  GitHub: {project.github_url}")
    if project.github_repo:
        click.echo(f"  Repo: {project.github_repo}")
    click.echo(f"  Created: {project.created_at}")
    click.echo(f"  Updated: {project.updated_at}")
