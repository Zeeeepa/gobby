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


@skills.command()
@click.option("--project", "-p", "project_id", help="Project ID")
@click.option("--tag", "-t", help="Filter by tag")
@click.option("--limit", "-n", default=20, help="Max results")
@click.pass_context
def list(ctx: click.Context, project_id: str | None, tag: str | None, limit: int) -> None:
    """List skills."""
    storage = get_skill_storage(ctx)
    # Note: list_skills in storage.skills now supports tag filtering
    skills = storage.list_skills(project_id=project_id, tag=tag, limit=limit)
    if not skills:
        click.echo("No skills found.")
        return

    for skill in skills:
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
    skill = storage.get_skill(skill_id)
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
