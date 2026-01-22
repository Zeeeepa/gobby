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
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def show(ctx: click.Context, name: str, json_output: bool) -> None:
    """Show details of a specific skill."""
    storage = get_skill_storage()
    skill = storage.get_by_name(name)

    if skill is None:
        if json_output:
            click.echo(json.dumps({"error": "Skill not found", "name": name}))
        else:
            click.echo(f"Skill not found: {name}")
        return

    if json_output:
        output = {
            "name": skill.name,
            "description": skill.description,
            "version": skill.version,
            "license": skill.license,
            "enabled": skill.enabled,
            "source_type": skill.source_type,
            "source_path": skill.source_path,
            "compatibility": skill.compatibility if hasattr(skill, "compatibility") else None,
            "content": skill.content,
            "category": _get_skill_category(skill),
            "tags": _get_skill_tags(skill),
        }
        click.echo(json.dumps(output, indent=2))
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
    - A local directory path (e.g., ./my-skill or /path/to/skill)
    - A path to a SKILL.md file (e.g., ./SKILL.md)
    - A GitHub URL (owner/repo, github:owner/repo, https://github.com/owner/repo)
    - A ZIP archive path (e.g., ./skills.zip)

    Use --project to scope the skill to a specific project.
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
    """Remove an installed skill.

    NAME is the skill name to remove (e.g., 'commit-message').
    """
    storage = get_skill_storage()
    skill = storage.get_by_name(name)

    if skill is None:
        click.echo(f"Skill not found: {name}")
        return

    storage.delete_skill(skill.id)
    click.echo(f"Removed skill: {name}")


@skills.command()
@click.argument("name", required=False)
@click.option("--all", "update_all", is_flag=True, help="Update all installed skills")
@click.pass_context
def update(ctx: click.Context, name: str | None, update_all: bool) -> None:
    """Update an installed skill from its source.

    NAME is the skill name to update (e.g., 'commit-message').
    Use --all to update all skills that have remote sources.

    Only skills installed from GitHub can be updated (re-fetched from source).
    Local skills are skipped.
    """
    from gobby.skills.loader import SkillLoader, SkillLoadError

    storage = get_skill_storage()
    loader = SkillLoader()

    if not name and not update_all:
        click.echo("Error: Provide a skill name or use --all to update all skills")
        return

    if update_all:
        # Update all skills with remote sources
        skills_list = storage.list_skills(include_global=True)
        updated = 0
        skipped = 0

        for skill in skills_list:
            if skill.source_type == "github" and skill.source_path:
                try:
                    # Extract GitHub URL from source_path (e.g., "github:owner/repo")
                    source_url = skill.source_path
                    if source_url.startswith("github:"):
                        parsed_skill = loader.load_from_github(source_url)
                        storage.update_skill(
                            skill.id,
                            content=parsed_skill.content,
                            description=parsed_skill.description,
                            version=parsed_skill.version,
                            metadata=parsed_skill.metadata,
                        )
                        click.echo(f"Updated: {skill.name}")
                        updated += 1
                    else:
                        click.echo(f"Skipped: {skill.name} (invalid source)")
                        skipped += 1
                except SkillLoadError as e:
                    click.echo(f"Failed to update {skill.name}: {e}")
                    skipped += 1
            else:
                click.echo(f"Skipped: {skill.name} (local source)")
                skipped += 1

        click.echo(f"\nUpdated {updated} skill(s), skipped {skipped}")
        return

    # Update single skill
    skill = storage.get_by_name(name)

    if skill is None:
        click.echo(f"Skill not found: {name}")
        return

    if skill.source_type != "github" or not skill.source_path:
        click.echo(f"Cannot update {name}: local skills cannot be refreshed from remote")
        return

    try:
        source_url = skill.source_path
        if not source_url.startswith("github:"):
            click.echo(f"Cannot update {name}: unsupported source type")
            return

        parsed_skill = loader.load_from_github(source_url)
        storage.update_skill(
            skill.id,
            content=parsed_skill.content,
            description=parsed_skill.description,
            version=parsed_skill.version,
            metadata=parsed_skill.metadata,
        )
        click.echo(f"Updated skill: {name}")

    except SkillLoadError as e:
        click.echo(f"Error updating {name}: {e}")


@skills.command()
@click.argument("path")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def validate(ctx: click.Context, path: str, json_output: bool) -> None:
    """Validate a SKILL.md file against the Agent Skills specification.

    PATH is the path to a SKILL.md file or directory containing one.

    Validates:
    - name: max 64 chars, lowercase + hyphens only
    - description: max 1024 chars, non-empty
    - version: semver pattern (if provided)
    - category: lowercase alphanumeric + hyphens (if provided)
    - tags: list of strings, each max 64 chars (if provided)
    """
    from gobby.skills.loader import SkillLoader, SkillLoadError
    from gobby.skills.validator import SkillValidator

    source_path = Path(path)

    if not source_path.exists():
        if json_output:
            click.echo(json.dumps({"error": "Path not found", "path": path}))
        else:
            click.echo(f"Error: Path not found: {path}")
        return

    # Load the skill
    loader = SkillLoader()
    try:
        # Don't validate during load - we want to do it ourselves
        parsed_skill = loader.load_skill(source_path, validate=False, check_dir_name=False)
    except SkillLoadError as e:
        if json_output:
            click.echo(json.dumps({"error": str(e), "path": path}))
        else:
            click.echo(f"Error loading skill: {e}")
        return

    # Validate the skill
    validator = SkillValidator()
    result = validator.validate(parsed_skill)

    if json_output:
        output = result.to_dict()
        output["path"] = path
        output["skill_name"] = parsed_skill.name
        click.echo(json.dumps(output, indent=2))
        return

    # Human-readable output
    if result.valid:
        click.echo(f"✓ Valid: {parsed_skill.name}")
        if result.warnings:
            click.echo("\nWarnings:")
            for warning in result.warnings:
                click.echo(f"  - {warning}")
    else:
        click.echo(f"✗ Invalid: {parsed_skill.name}")
        click.echo("\nErrors:")
        for error in result.errors:
            click.echo(f"  - {error}")
        if result.warnings:
            click.echo("\nWarnings:")
            for warning in result.warnings:
                click.echo(f"  - {warning}")


# Meta subcommand group
@skills.group()
def meta() -> None:
    """Manage skill metadata fields."""
    pass


def _get_nested_value(data: dict[str, Any], key: str) -> Any:
    """Get a nested value from a dict using dot notation."""
    keys = key.split(".")
    current = data
    for k in keys:
        if not isinstance(current, dict) or k not in current:
            return None
        current = current[k]
    return current


def _set_nested_value(data: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    """Set a nested value in a dict using dot notation."""
    keys = key.split(".")
    result = data.copy() if data else {}
    current = result

    # Navigate to parent, creating dicts as needed
    for k in keys[:-1]:
        if k not in current or not isinstance(current[k], dict):
            current[k] = {}
        else:
            current[k] = current[k].copy()
        current = current[k]

    # Set the final key
    current[keys[-1]] = value
    return result


def _unset_nested_value(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Remove a nested value from a dict using dot notation."""
    if not data:
        return {}

    keys = key.split(".")
    result = data.copy()

    if len(keys) == 1:
        # Simple key
        result.pop(keys[0], None)
        return result

    # Navigate to parent
    current = result
    parents: list[tuple[dict[str, Any], str]] = []

    for k in keys[:-1]:
        if not isinstance(current, dict) or k not in current:
            return result  # Key doesn't exist, nothing to do
        parents.append((current, k))
        if isinstance(current[k], dict):
            current[k] = current[k].copy()
        current = current[k]

    # Remove the final key
    if isinstance(current, dict) and keys[-1] in current:
        del current[keys[-1]]

    return result


@meta.command("get")
@click.argument("name")
@click.argument("key")
@click.pass_context
def meta_get(ctx: click.Context, name: str, key: str) -> None:
    """Get a metadata field value.

    NAME is the skill name.
    KEY is the metadata field (supports dot notation for nested keys).

    Examples:
        gobby skills meta get my-skill author
        gobby skills meta get my-skill skillport.category
    """
    storage = get_skill_storage()
    skill = storage.get_by_name(name)

    if skill is None:
        click.echo(f"Skill not found: {name}")
        return

    if not skill.metadata:
        click.echo("null")
        return

    value = _get_nested_value(skill.metadata, key)
    if value is None:
        click.echo(f"Key not found: {key}")
    elif isinstance(value, (dict, list)):
        click.echo(json.dumps(value, indent=2))
    else:
        click.echo(str(value))


@meta.command("set")
@click.argument("name")
@click.argument("key")
@click.argument("value")
@click.pass_context
def meta_set(ctx: click.Context, name: str, key: str, value: str) -> None:
    """Set a metadata field value.

    NAME is the skill name.
    KEY is the metadata field (supports dot notation for nested keys).
    VALUE is the value to set.

    Examples:
        gobby skills meta set my-skill author "John Doe"
        gobby skills meta set my-skill skillport.category git
    """
    storage = get_skill_storage()
    skill = storage.get_by_name(name)

    if skill is None:
        click.echo(f"Skill not found: {name}")
        return

    # Try to parse value as JSON for complex types
    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    new_metadata = _set_nested_value(skill.metadata or {}, key, parsed_value)
    storage.update_skill(skill.id, metadata=new_metadata)
    click.echo(f"Set {key} = {value}")


@meta.command("unset")
@click.argument("name")
@click.argument("key")
@click.pass_context
def meta_unset(ctx: click.Context, name: str, key: str) -> None:
    """Remove a metadata field.

    NAME is the skill name.
    KEY is the metadata field (supports dot notation for nested keys).

    Examples:
        gobby skills meta unset my-skill author
        gobby skills meta unset my-skill skillport.tags
    """
    storage = get_skill_storage()
    skill = storage.get_by_name(name)

    if skill is None:
        click.echo(f"Skill not found: {name}")
        return

    if not skill.metadata:
        click.echo(f"Key not found: {key}")
        return

    new_metadata = _unset_nested_value(skill.metadata, key)
    storage.update_skill(skill.id, metadata=new_metadata)
    click.echo(f"Unset {key}")


@skills.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize skills directory for the current project.

    Creates .gobby/skills/ directory and config file for local skill management.
    This is idempotent - running init multiple times is safe.
    """
    import yaml

    skills_dir = Path(".gobby/skills")
    config_file = skills_dir / "config.yaml"

    # Create .gobby directory if needed
    gobby_dir = Path(".gobby")
    if not gobby_dir.exists():
        gobby_dir.mkdir(parents=True)

    # Create skills directory
    if not skills_dir.exists():
        skills_dir.mkdir(parents=True)
        click.echo(f"Created {skills_dir}/")
    else:
        click.echo(f"Skills directory already exists: {skills_dir}/")

    # Create config file if it doesn't exist
    if not config_file.exists():
        default_config = {
            "version": "1.0",
            "skills": {
                "enabled": True,
                "auto_discover": True,
                "search_paths": ["./skills", "./.gobby/skills"],
            },
        }
        with open(config_file, "w") as f:
            yaml.dump(default_config, f, default_flow_style=False)
        click.echo(f"Created {config_file}")
    else:
        click.echo(f"Config already exists: {config_file}")

    click.echo("\nSkills initialized successfully!")


@skills.command()
@click.argument("name")
@click.option("--description", "-d", default=None, help="Skill description")
@click.pass_context
def new(ctx: click.Context, name: str, description: str | None) -> None:
    """Create a new skill scaffold.

    NAME is the skill name (lowercase, hyphens allowed).

    Creates a new skill directory with:
    - SKILL.md with frontmatter template
    - scripts/ directory for helper scripts
    - assets/ directory for images and files
    - references/ directory for documentation
    """
    skill_dir = Path(name)

    # Check if directory already exists
    if skill_dir.exists():
        click.echo(f"Directory already exists: {name}")
        return

    # Create skill directory structure
    skill_dir.mkdir(parents=True)
    (skill_dir / "scripts").mkdir()
    (skill_dir / "assets").mkdir()
    (skill_dir / "references").mkdir()

    # Default description if not provided
    if description is None:
        description = f"Description for {name}"

    # Create SKILL.md with template
    skill_template = f"""---
name: {name}
description: {description}
version: 1.0.0
metadata:
  skillport:
    category: general
    tags: []
    alwaysApply: false
  gobby:
    triggers: []
---

# {name.replace("-", " ").title()}

## Overview

{description}

## Instructions

Add your skill instructions here.

## Examples

Provide usage examples here.
"""

    with open(skill_dir / "SKILL.md", "w") as f:
        f.write(skill_template)

    click.echo(f"Created skill scaffold: {name}/")
    click.echo(f"  - {name}/SKILL.md")
    click.echo(f"  - {name}/scripts/")
    click.echo(f"  - {name}/assets/")
    click.echo(f"  - {name}/references/")
