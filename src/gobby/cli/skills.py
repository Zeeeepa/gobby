"""Skills CLI commands.

This module provides CLI commands for managing skills:
- list: List all installed skills
- show: Show details of a specific skill
- install: Install a skill from a source
- remove: Remove an installed skill
"""

import json
from pathlib import Path
from typing import Any

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


@skills.command("list")
@click.option("--category", "-c", help="Filter by category")
@click.option("--tags", "-t", help="Filter by tags (comma-separated)")
@click.option("--enabled/--disabled", default=None, help="Filter by enabled status")
@click.option("--limit", "-n", default=50, help="Maximum skills to show")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def list_skills(
    ctx: click.Context,
    category: str | None,
    tags: str | None,
    enabled: bool | None,
    limit: int,
    json_output: bool,
) -> None:
    """List installed skills."""
    storage = get_skill_storage()
    skills_list = storage.list_skills(
        category=category,
        enabled=enabled,
        limit=limit,
        include_global=True,
    )

    # Filter by tags if specified
    if tags:
        tags_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tags_list:
            filtered_skills = []
            for skill in skills_list:
                skill_tags = _get_skill_tags(skill)
                if any(tag in skill_tags for tag in tags_list):
                    filtered_skills.append(skill)
            skills_list = filtered_skills

    if json_output:
        _output_json(skills_list)
        return

    if not skills_list:
        click.echo("No skills found.")
        return

    for skill in skills_list:
        # Get category from metadata if available
        cat_str = ""
        skill_category = _get_skill_category(skill)
        if skill_category:
            cat_str = f" [{skill_category}]"

        status = "✓" if skill.enabled else "✗"
        desc = skill.description[:60] if skill.description else ""
        click.echo(f"{status} {skill.name}{cat_str} - {desc}")


def _get_skill_tags(skill: Any) -> list[str]:
    """Extract tags from skill metadata."""
    if skill.metadata and isinstance(skill.metadata, dict):
        skillport = skill.metadata.get("skillport", {})
        if isinstance(skillport, dict):
            return skillport.get("tags", [])
    return []


def _get_skill_category(skill: Any) -> str | None:
    """Extract category from skill metadata."""
    if skill.metadata and isinstance(skill.metadata, dict):
        skillport = skill.metadata.get("skillport", {})
        if isinstance(skillport, dict):
            return skillport.get("category")
    return None


def _output_json(skills_list: list[Any]) -> None:
    """Output skills as JSON."""
    output = []
    for skill in skills_list:
        item = {
            "name": skill.name,
            "description": skill.description,
            "enabled": skill.enabled,
            "version": skill.version,
            "category": _get_skill_category(skill),
            "tags": _get_skill_tags(skill),
        }
        output.append(item)
    click.echo(json.dumps(output, indent=2))


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
