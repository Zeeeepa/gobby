"""Skills CLI commands.

This module provides CLI commands for managing skills:
- list: List all installed skills
- show: Show details of a specific skill
- install: Install a skill from a source
- remove: Remove an installed skill
"""

from pathlib import Path

import click

from gobby.storage.database import LocalDatabase
from gobby.storage.skills import LocalSkillManager


def get_skill_storage() -> LocalSkillManager:
    """Get skill storage manager."""
    db = LocalDatabase()
    return LocalSkillManager(db)


@click.group()
def skills() -> None:
    """Manage Gobby skills."""
    pass


@skills.command()
@click.option("--category", "-c", help="Filter by category")
@click.option("--enabled/--disabled", default=None, help="Filter by enabled status")
@click.option("--limit", "-n", default=50, help="Maximum skills to show")
@click.pass_context
def list(
    ctx: click.Context,
    category: str | None,
    enabled: bool | None,
    limit: int,
) -> None:
    """List installed skills."""
    storage = get_skill_storage()
    skills_list = storage.list_skills(
        category=category,
        enabled=enabled,
        limit=limit,
        include_global=True,
    )

    if not skills_list:
        click.echo("No skills found.")
        return

    for skill in skills_list:
        # Get category from metadata if available
        cat_str = ""
        if skill.metadata and isinstance(skill.metadata, dict):
            skillport = skill.metadata.get("skillport", {})
            if isinstance(skillport, dict) and skillport.get("category"):
                cat_str = f" [{skillport['category']}]"

        status = "✓" if skill.enabled else "✗"
        click.echo(f"{status} {skill.name}{cat_str} - {skill.description[:60]}")


@skills.command()
@click.argument("name")
@click.pass_context
def show(ctx: click.Context, name: str) -> None:
    """Show details of a specific skill."""
    storage = get_skill_storage()
    skill = storage.get_by_name(name)

    if skill is None:
        click.echo(f"Skill not found: {name}")
        return

    click.echo(f"Name: {skill.name}")
    click.echo(f"Description: {skill.description}")
    if skill.version:
        click.echo(f"Version: {skill.version}")
    if skill.license:
        click.echo(f"License: {skill.license}")
    click.echo(f"Enabled: {skill.enabled}")
    if skill.source_type:
        click.echo(f"Source: {skill.source_type}")
    if skill.source_path:
        click.echo(f"Path: {skill.source_path}")
    click.echo("")
    click.echo("Content:")
    click.echo("-" * 40)
    click.echo(skill.content)


@skills.command()
@click.argument("source")
@click.option("--project", "-p", help="Install scoped to project")
@click.pass_context
def install(ctx: click.Context, source: str, project: str | None) -> None:
    """Install a skill from a source.

    SOURCE can be:
    - A local directory path
    - A path to a SKILL.md file
    - A GitHub URL (owner/repo, github:owner/repo)
    - A ZIP archive path
    """
    from gobby.skills.loader import SkillLoader, SkillLoadError

    storage = get_skill_storage()
    loader = SkillLoader()

    try:
        # Determine source type and load
        source_path = Path(source)

        if source.startswith("github:") or source.startswith("https://github.com/"):
            # GitHub URL
            parsed_skill = loader.load_from_github(source)
            source_type = "github"
        elif source_path.suffix == ".zip":
            # ZIP archive
            parsed_skill = loader.load_from_zip(source_path)
            source_type = "zip"
        elif source_path.exists():
            # Local path
            parsed_skill = loader.load_skill(source_path)
            source_type = "local"
        else:
            # Try as GitHub shorthand (owner/repo)
            if "/" in source:
                parsed_skill = loader.load_from_github(source)
                source_type = "github"
            else:
                click.echo(f"Source not found: {source}")
                return

        # Store the skill
        skill = storage.create_skill(
            name=parsed_skill.name,
            description=parsed_skill.description,
            content=parsed_skill.content,
            version=parsed_skill.version,
            license=parsed_skill.license,
            compatibility=parsed_skill.compatibility,
            allowed_tools=parsed_skill.allowed_tools,
            metadata=parsed_skill.metadata,
            source_path=parsed_skill.source_path,
            source_type=source_type,
            source_ref=getattr(parsed_skill, "source_ref", None),
            project_id=project,
            enabled=True,
        )

        click.echo(f"Installed skill: {skill.name} ({source_type})")

    except SkillLoadError as e:
        click.echo(f"Error: {e}")
    except Exception as e:
        click.echo(f"Error installing skill: {e}")


@skills.command()
@click.argument("name")
@click.pass_context
def remove(ctx: click.Context, name: str) -> None:
    """Remove an installed skill."""
    storage = get_skill_storage()
    skill = storage.get_by_name(name)

    if skill is None:
        click.echo(f"Skill not found: {name}")
        return

    storage.delete_skill(skill.id)
    click.echo(f"Removed skill: {name}")
