import click
from gobby.config.app import DaemonConfig
from gobby.memory.manager import MemoryManager
from gobby.storage.database import LocalDatabase


def get_memory_manager(ctx: click.Context) -> MemoryManager:
    config: DaemonConfig = ctx.obj["config"]
    db = LocalDatabase()
    return MemoryManager(db, config.memory)


@click.group()
def memory() -> None:
    """Manage Gobby memories."""
    pass


@memory.command()
@click.argument("content")
@click.option(
    "--type", "-t", "memory_type", default="fact", help="Type of memory (fact, preference, etc.)"
)
@click.option("--importance", "-i", type=float, default=0.5, help="Importance (0.0 - 1.0)")
@click.option("--project", "-p", "project_id", help="Project ID")
@click.pass_context
def remember(
    ctx: click.Context, content: str, memory_type: str, importance: float, project_id: str | None
) -> None:
    """Store a new memory."""
    manager = get_memory_manager(ctx)
    memory = manager.remember(
        content=content,
        memory_type=memory_type,
        importance=importance,
        project_id=project_id,
        source_type="cli",
    )
    click.echo(f"Stored memory: {memory.id} - {memory.content}")


@memory.command()
@click.argument("query", required=False)
@click.option("--project", "-p", "project_id", help="Project ID")
@click.option("--limit", "-n", default=10, help="Max results")
@click.pass_context
def recall(ctx: click.Context, query: str | None, project_id: str | None, limit: int) -> None:
    """Retrieve memories."""
    manager = get_memory_manager(ctx)
    memories = manager.recall(
        query=query,
        project_id=project_id,
        limit=limit,
    )
    if not memories:
        click.echo("No memories found.")
        return

    for mem in memories:
        click.echo(f"[{mem.id[:8]}] ({mem.memory_type}, {mem.importance}) {mem.content}")


@memory.command()
@click.argument("memory_id")
@click.pass_context
def forget(ctx: click.Context, memory_id: str) -> None:
    """Delete a memory."""
    manager = get_memory_manager(ctx)
    success = manager.forget(memory_id)
    if success:
        click.echo(f"Forgot memory: {memory_id}")
    else:
        click.echo(f"Memory not found: {memory_id}")
