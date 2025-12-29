import asyncio
import logging
from pathlib import Path
from typing import Any

import click

from gobby.config.app import DaemonConfig
from gobby.llm import create_llm_service
from gobby.skills import SkillLearner
from gobby.storage.database import LocalDatabase
from gobby.storage.session_messages import LocalSessionMessageManager
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.skills import LocalSkillManager, Skill

logger = logging.getLogger(__name__)


def get_skill_storage(ctx: click.Context) -> LocalSkillManager:
    db = LocalDatabase()
    return LocalSkillManager(db)


def get_skill_learner(ctx: click.Context) -> SkillLearner | None:
    config: DaemonConfig = ctx.obj["config"]
    if not hasattr(config, "skills"):
        return None

    db = LocalDatabase()
    storage = LocalSkillManager(db)
    message_manager = LocalSessionMessageManager(db)
    try:
        llm_service = create_llm_service(config)
        return SkillLearner(storage, message_manager, llm_service, config.skills)
    except Exception as e:
        click.echo(f"Error initializing skill learner: {e}", err=True)
        return None


@click.group()
def skills() -> None:
    """Manage Gobby skills."""
    pass


def _read_safe_file(filepath: str, base_dir: Path | None = None) -> str:
    """
    Safely read a file, ensuring it's within the allowed base directory.
    Prevents path traversal attacks relative to the base directory.

    Args:
        filepath: The path to the file to read.
        base_dir: The base directory to restrict access to. Defaults to CWD.

    Returns:
        The content of the file.

    Raises:
        ValueError: If a path traversal attempt is detected.
        FileNotFoundError: If the file does not exist.
        IOError: For other IO errors.
    """
    # Use CWD if no base_dir provided
    if base_dir is None:
        base_dir = Path.cwd()

    # Resolve base directory to absolute path
    base_dir = base_dir.resolve()

    # Create path object from input
    candidate_path = Path(filepath)

    # Handle absolute paths:
    # If it's absolute, we check if it's within base_dir.
    # If it's relative, we join with base_dir and resolve.
    if not candidate_path.is_absolute():
        candidate_path = base_dir / candidate_path

    # Resolve the candidate path to eliminate .. components
    try:
        resolved_path = candidate_path.resolve()
    except FileNotFoundError:
        # If file doesn't exist, resolve() might fail or raise depending on python version/path strictness
        # In newer python resolve(strict=True) is default.
        # But we want to preserve FileNotFoundError from the operational open() if possible,
        # or raise it here if we can't resolve.
        # Let's try to resolve blindly or just check existence first.
        if not candidate_path.exists():
            raise FileNotFoundError(f"File not found: {filepath}") from None
        raise

    # Check traversal
    if not resolved_path.is_relative_to(base_dir):
        raise ValueError(
            f"Path traversal detected: {filepath} is outside base directory {base_dir}"
        )

    # Check existence to ensure correct error type
    if not resolved_path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    # Check if it is a file
    if not resolved_path.is_file():
        raise ValueError(f"Not a file: {filepath}")

    return resolved_path.read_text()


@skills.command("list")
@click.option("--project", "-p", "project_id", help="Project ID")
@click.option("--tag", "-t", help="Filter by tag")
@click.option("--limit", "-n", default=20, help="Max results")
@click.pass_context
def list_skills_cmd(
    ctx: click.Context, project_id: str | None, tag: str | None, limit: int
) -> None:
    """List skills."""
    storage = get_skill_storage(ctx)
    # Note: list_skills in storage.skills now supports tag filtering
    skill_list = storage.list_skills(project_id=project_id, tag=tag, limit=limit)
    if not skill_list:
        click.echo("No skills found.")
        return

    for skill in skill_list:
        click.echo(f"[{skill.id[:8]}] {skill.name}")
        click.echo(f"  {skill.description}")


@skills.command()
@click.argument("session_id")
@click.pass_context
def learn(ctx: click.Context, session_id: str) -> None:
    """Learn skills from a session."""
    learner = get_skill_learner(ctx)
    if not learner:
        click.echo("Skill learning not verified/configured.", err=True)
        return

    async def _run(learner: SkillLearner) -> list[Skill]:
        db = LocalDatabase()
        session_manager = LocalSessionManager(db)
        session = session_manager.get(session_id)
        if not session:
            # Try to fetch current session if "current" passed? No, keep it simple for now.
            # But the user might want "last" or "current".
            # For now, just explicit ID.
            click.echo(f"Session not found: {session_id}", err=True)
            return []

        return await learner.learn_from_session(session)

    skills = asyncio.run(_run(learner))
    if skills:
        click.echo(f"Learned {len(skills)} new skills:")
        for s in skills:
            click.echo(f"  - {s.name}: {s.description}")
    else:
        click.echo("No new skills learned.")


@skills.command()
@click.argument("skill_id")
@click.pass_context
def delete(ctx: click.Context, skill_id: str) -> None:
    """Delete a skill."""
    import shutil
    from pathlib import Path

    storage = get_skill_storage(ctx)

    # Get skill first to know its name for cleanup
    skill: Skill | None = None
    try:
        skill = storage.get_skill(skill_id)
        skill_name = skill.name if skill else None
    except ValueError:
        skill_name = None

    success = storage.delete_skill(skill_id)
    if success:
        click.echo(f"Deleted skill: {skill_id}")

        # Also remove from exported directory if it exists
        if skill_name:
            safe_name = "".join(c for c in skill_name if c.isalnum() or c in "-_").lower()
            if not safe_name and skill and skill.id:
                # Fallback to sanitized ID if name yields empty string
                safe_name = "".join(c for c in skill.id if c.isalnum() or c in "-_").lower()

            if safe_name:
                skill_dir = Path(".claude/skills") / safe_name
                # Ensure it is actually a subdirectory of .claude/skills
                try:
                    # Resolve to absolute paths for safety check
                    root_skills = Path(".claude/skills").resolve()
                    target_dir = skill_dir.resolve()
                    if (
                        target_dir.is_relative_to(root_skills)
                        and target_dir.exists()
                        and target_dir.is_dir()
                    ):
                        shutil.rmtree(target_dir)
                        click.echo(f"Removed exported skill directory: {skill_dir}")
                except (ValueError, FileNotFoundError):
                    # Path resolution failed or not relative (traversal attempt?), ignore
                    pass
            else:
                click.echo(
                    "Warning: Could not determine safe name for skill directory cleanup.", err=True
                )
    else:
        click.echo(f"Skill not found: {skill_id}")


@skills.command()
@click.argument("skill_id")
@click.pass_context
def get(ctx: click.Context, skill_id: str) -> None:
    """Get skill details."""
    storage = get_skill_storage(ctx)
    try:
        skill = storage.get_skill(skill_id)
    except ValueError:
        click.echo(f"Skill not found: {skill_id}")
        return
    if not skill:
        click.echo(f"Skill not found: {skill_id}")
        return

    click.echo(f"Name: {skill.name}")
    click.echo(f"ID: {skill.id}")
    click.echo(f"Created: {skill.created_at}")
    click.echo(f"Updated: {skill.updated_at}")
    click.echo(f"Description: {skill.description}")
    click.echo(f"Trigger Pattern: {skill.trigger_pattern}")
    click.echo("Instructions:")
    click.echo(skill.instructions)
    click.echo("Usage Count: " + str(skill.usage_count))
    if skill.tags:
        click.echo(f"Tags: {', '.join(skill.tags)}")


@skills.command()
@click.argument("name")
@click.option(
    "--instructions", "-i", required=True, help="Skill instructions (or @file to read from file)"
)
@click.option("--description", "-d", help="Skill description")
@click.option("--trigger", "-t", "trigger_pattern", help="Trigger pattern (regex)")
@click.option("--tags", help="Comma-separated tags")
@click.option("--project", "-p", "project_id", help="Project ID")
@click.pass_context
def add(
    ctx: click.Context,
    name: str,
    instructions: str,
    description: str | None,
    trigger_pattern: str | None,
    tags: str | None,
    project_id: str | None,
) -> None:
    """Create a new skill directly."""
    storage = get_skill_storage(ctx)

    # Support @file syntax to read instructions from file
    if instructions.startswith("@"):
        filepath = instructions[1:]
        try:
            instructions = _read_safe_file(filepath)
        except (ValueError, FileNotFoundError) as e:
            click.echo(f"Error reading file: {e}", err=True)
            return

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    try:
        skill = storage.create_skill(
            name=name,
            instructions=instructions,
            project_id=project_id,
            description=description,
            trigger_pattern=trigger_pattern,
            tags=tag_list,
        )
        click.echo(f"Created skill: {skill.id}")
        click.echo(f"  Name: {skill.name}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@skills.command()
@click.argument("skill_id")
@click.option("--name", "-n", help="New name")
@click.option("--instructions", "-i", help="New instructions (or @file)")
@click.option("--description", "-d", help="New description")
@click.option("--trigger", "-t", "trigger_pattern", help="New trigger pattern")
@click.option("--tags", help="New tags (comma-separated)")
@click.pass_context
def update(
    ctx: click.Context,
    skill_id: str,
    name: str | None,
    instructions: str | None,
    description: str | None,
    trigger_pattern: str | None,
    tags: str | None,
) -> None:
    """Update an existing skill."""
    storage = get_skill_storage(ctx)

    # Support @file syntax for instructions
    if instructions and instructions.startswith("@"):
        filepath = instructions[1:]
        try:
            instructions = _read_safe_file(filepath)
        except (ValueError, FileNotFoundError) as e:
            click.echo(f"Error reading file: {e}", err=True)
            return

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    try:
        skill = storage.update_skill(
            skill_id=skill_id,
            name=name,
            instructions=instructions,
            description=description,
            trigger_pattern=trigger_pattern,
            tags=tag_list,
        )
        click.echo(f"Updated skill: {skill.id}")
        click.echo(f"  Name: {skill.name}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)


@skills.command()
@click.argument("skill_id")
@click.pass_context
def apply(ctx: click.Context, skill_id: str) -> None:
    """Apply a skill - shows instructions and marks as used."""
    storage = get_skill_storage(ctx)

    try:
        skill = storage.get_skill(skill_id)
    except ValueError:
        click.echo(f"Skill not found: {skill_id}", err=True)
        return

    if not skill:
        click.echo(f"Skill not found: {skill_id}", err=True)
        return

    # Increment usage
    storage.increment_usage(skill_id)

    click.echo(f"=== Applying Skill: {skill.name} ===")
    if skill.description:
        click.echo(f"Description: {skill.description}")
    click.echo("")
    click.echo("Instructions:")
    click.echo(skill.instructions)
    click.echo("")
    click.echo(f"(Usage count: {skill.usage_count + 1})")


@skills.command()
@click.option("--output", "-o", type=click.Path(), help="Output directory (default: .gobby)")
@click.option(
    "--format",
    "-f",
    "fmt",
    type=click.Choice(["claude", "legacy"]),
    default="claude",
    help="Export format: 'claude' (plugin format) or 'legacy' (flat files)",
)
@click.pass_context
def export(ctx: click.Context, output: str | None, fmt: str) -> None:
    """Export skills to Claude Code plugin format.

    Creates a .gobby plugin directory structure that Claude Code auto-discovers:

    \b
    .gobby/
    ├── .claude-plugin/
    │   └── plugin.json
    └── skills/
        └── <skill-name>/
            └── SKILL.md
    """
    import json
    from pathlib import Path

    import yaml

    storage = get_skill_storage(ctx)
    skills_list = storage.list_skills(limit=1000)

    if not skills_list:
        click.echo("No skills to export.")
        return

    # Determine output directory
    gobby_dir = Path(output) if output else Path(".gobby")
    skills_dir = gobby_dir / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "claude":
        # Create plugin manifest
        plugin_dir = gobby_dir / ".claude-plugin"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        manifest_file = plugin_dir / "plugin.json"
        if not manifest_file.exists():
            manifest = {
                "name": "gobby-skills",
                "version": "1.0.0",
                "description": "Skills learned and managed by Gobby",
            }
            with open(manifest_file, "w") as f:
                json.dump(manifest, f, indent=2)
            click.echo(f"Created plugin manifest: {manifest_file}")

    count = 0
    skipped = 0
    for skill in skills_list:
        try:
            # Create safe name
            safe_name = "".join(c for c in skill.name if c.isalnum() or c in "-_").lower()
            if not safe_name:
                safe_name = skill.id

            if fmt == "claude":
                # Claude Code format: skills/<name>/SKILL.md
                skill_dir = skills_dir / safe_name
                skill_dir.mkdir(parents=True, exist_ok=True)

                # Build trigger description
                description = _build_trigger_description(skill)

                frontmatter = {
                    "name": skill.name,
                    "description": description,
                }

                content = "---\n"
                content += yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
                content += "---\n\n"
                content += skill.instructions

                skill_file = skill_dir / "SKILL.md"
                with open(skill_file, "w") as f:
                    f.write(content)

                # Write Gobby metadata
                meta_file = skill_dir / ".gobby-meta.json"
                meta = {
                    "id": skill.id,
                    "trigger_pattern": skill.trigger_pattern or "",
                    "tags": skill.tags or [],
                    "usage_count": skill.usage_count,
                }
                with open(meta_file, "w") as f:
                    json.dump(meta, f, indent=2)
            else:
                # Legacy format: skills/<name>.md
                filename = skills_dir / f"{safe_name}.md"
                legacy_frontmatter: dict[str, Any] = {
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description or "",
                    "trigger_pattern": skill.trigger_pattern or "",
                    "tags": skill.tags or [],
                }

                content = "---\n"
                content += yaml.dump(legacy_frontmatter)
                content += "---\n\n"
                content += skill.instructions

                with open(filename, "w") as f:
                    f.write(content)

            count += 1
        except Exception as e:
            logger.error(f"Failed to export skill {skill.id} ({skill.name}): {e}")
            skipped += 1
            continue

    if fmt == "claude":
        click.echo(f"Exported {count} skills to {gobby_dir}/ (Claude Code plugin format)")
        if skipped > 0:
            click.echo(f"Skipped {skipped} skills due to errors (check logs for details)")
        click.echo("Skills will be auto-discovered by Claude Code.")
    else:
        click.echo(f"Exported {count} skills to {skills_dir}/ (legacy format)")
        if skipped > 0:
            click.echo(f"Skipped {skipped} skills due to errors (check logs for details)")


def _build_trigger_description(skill: Skill) -> str:
    """Build Claude Code compatible trigger description."""
    base_desc = skill.description or f"Provides guidance for {skill.name}"

    trigger_phrases = []
    if skill.trigger_pattern:
        parts = skill.trigger_pattern.split("|")
        for part in parts:
            phrase = part.strip()
            phrase = phrase.replace(".*", " ")
            phrase = phrase.replace("\\s+", " ")
            phrase = phrase.replace("\\b", "")
            phrase = phrase.replace("^", "").replace("$", "")
            phrase = phrase.strip()
            if phrase and len(phrase) > 1:
                trigger_phrases.append(f'"{phrase}"')

    if trigger_phrases:
        triggers = ", ".join(trigger_phrases[:5])
        return f"This skill should be used when the user asks to {triggers}. {base_desc}"
    else:
        return f"This skill should be used when working with {skill.name}. {base_desc}"
