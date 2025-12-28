import asyncio

import click

from gobby.config.app import DaemonConfig
from gobby.llm import create_llm_service
from gobby.memory.skills import SkillLearner
from gobby.storage.database import LocalDatabase
from gobby.storage.messages import LocalMessageManager
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.skills import LocalSkillManager, Skill


def get_skill_storage(ctx: click.Context) -> LocalSkillManager:
    db = LocalDatabase()
    return LocalSkillManager(db)


def get_skill_learner(ctx: click.Context) -> SkillLearner | None:
    config: DaemonConfig = ctx.obj["config"]
    if not hasattr(config, "skills"):
        return None

    db = LocalDatabase()
    storage = LocalSkillManager(db)
    message_manager = LocalMessageManager(db)
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

    async def _run() -> list[Skill]:
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

    skills = asyncio.run(_run())
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
    storage = get_skill_storage(ctx)
    success = storage.delete_skill(skill_id)
    if success:
        click.echo(f"Deleted skill: {skill_id}")
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
            with open(filepath) as f:
                instructions = f.read()
        except FileNotFoundError:
            click.echo(f"File not found: {filepath}", err=True)
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
            with open(filepath) as f:
                instructions = f.read()
        except FileNotFoundError:
            click.echo(f"File not found: {filepath}", err=True)
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
@click.option("--output", "-o", type=click.Path(), help="Output directory (default: .gobby/skills)")
@click.pass_context
def export(ctx: click.Context, output: str | None) -> None:
    """Export skills to markdown files."""
    from pathlib import Path

    import yaml

    storage = get_skill_storage(ctx)
    skills_list = storage.list_skills(limit=1000)

    if not skills_list:
        click.echo("No skills to export.")
        return

    # Determine output directory
    output_dir = Path(output) if output else Path(".gobby/skills")
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for skill in skills_list:
        # Create safe filename
        safe_name = "".join(c for c in skill.name if c.isalnum() or c in "-_").lower()
        if not safe_name:
            safe_name = skill.id  # Fallback to ID if name has no safe characters
        filename = output_dir / f"{safe_name}.md"

        # Build frontmatter
        frontmatter = {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description or "",
            "trigger_pattern": skill.trigger_pattern or "",
            "tags": skill.tags or [],
        }

        content = "---\n"
        content += yaml.dump(frontmatter)
        content += "---\n\n"
        content += skill.instructions

        with open(filename, "w") as f:
            f.write(content)
        count += 1

    click.echo(f"Exported {count} skills to {output_dir}/")
