import asyncio

import click

from gobby.cli.utils import resolve_project_ref
from gobby.config.app import DaemonConfig
from gobby.memory.manager import MemoryManager
from gobby.storage.database import LocalDatabase


def get_memory_manager(ctx: click.Context) -> MemoryManager:
    """Get memory manager."""
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
@click.option("--project", "-p", "project_ref", help="Project (name or UUID)")
@click.pass_context
def create(
    ctx: click.Context, content: str, memory_type: str, importance: float, project_ref: str | None
) -> None:
    """Create a new memory."""
    project_id = resolve_project_ref(project_ref) if project_ref else None
    manager = get_memory_manager(ctx)
    memory = asyncio.run(
        manager.remember(
            content=content,
            memory_type=memory_type,
            importance=importance,
            project_id=project_id,
            source_type="cli",
        )
    )
    click.echo(f"Created memory: {memory.id} - {memory.content}")


@memory.command()
@click.argument("query", required=False)
@click.option("--project", "-p", "project_ref", help="Project (name or UUID)")
@click.option("--limit", "-n", default=10, help="Max results")
@click.option("--tags-all", "tags_all", help="Require ALL tags (comma-separated)")
@click.option("--tags-any", "tags_any", help="Require ANY tag (comma-separated)")
@click.option("--tags-none", "tags_none", help="Exclude memories with these tags (comma-separated)")
@click.pass_context
def recall(
    ctx: click.Context,
    query: str | None,
    project_ref: str | None,
    limit: int,
    tags_all: str | None,
    tags_any: str | None,
    tags_none: str | None,
) -> None:
    """Retrieve memories with optional tag filtering."""
    project_id = resolve_project_ref(project_ref) if project_ref else None
    manager = get_memory_manager(ctx)

    # Parse comma-separated tags
    tags_all_list = [t.strip() for t in tags_all.split(",") if t.strip()] if tags_all else None
    tags_any_list = [t.strip() for t in tags_any.split(",") if t.strip()] if tags_any else None
    tags_none_list = [t.strip() for t in tags_none.split(",") if t.strip()] if tags_none else None

    memories = manager.recall(
        query=query,
        project_id=project_id,
        limit=limit,
        tags_all=tags_all_list,
        tags_any=tags_any_list,
        tags_none=tags_none_list,
    )
    if not memories:
        click.echo("No memories found.")
        return

    for mem in memories:
        tags_str = f" [{', '.join(mem.tags)}]" if mem.tags else ""
        click.echo(f"[{mem.id[:8]}] ({mem.memory_type}, {mem.importance}){tags_str} {mem.content}")


@memory.command()
@click.argument("memory_ref")
@click.pass_context
def delete(ctx: click.Context, memory_ref: str) -> None:
    """Delete a memory by ID (UUID or prefix)."""
    manager = get_memory_manager(ctx)
    memory_id = resolve_memory_id(manager, memory_ref)
    success = manager.forget(memory_id)
    if success:
        click.echo(f"Deleted memory: {memory_id}")
    else:
        click.echo(f"Memory not found: {memory_id}")


@memory.command("list")
@click.option("--type", "-t", "memory_type", help="Filter by memory type")
@click.option("--min-importance", "-i", type=float, help="Minimum importance threshold")
@click.option("--limit", "-n", default=50, help="Max results")
@click.option("--project", "-p", "project_ref", help="Project (name or UUID)")
@click.option("--tags-all", "tags_all", help="Require ALL tags (comma-separated)")
@click.option("--tags-any", "tags_any", help="Require ANY tag (comma-separated)")
@click.option("--tags-none", "tags_none", help="Exclude memories with these tags (comma-separated)")
@click.pass_context
def list_memories(
    ctx: click.Context,
    memory_type: str | None,
    min_importance: float | None,
    project_ref: str | None,
    limit: int,
    tags_all: str | None,
    tags_any: str | None,
    tags_none: str | None,
) -> None:
    """List all memories with optional filtering."""
    project_id = resolve_project_ref(project_ref) if project_ref else None
    manager = get_memory_manager(ctx)

    # Parse comma-separated tags
    tags_all_list = [t.strip() for t in tags_all.split(",") if t.strip()] if tags_all else None
    tags_any_list = [t.strip() for t in tags_any.split(",") if t.strip()] if tags_any else None
    tags_none_list = [t.strip() for t in tags_none.split(",") if t.strip()] if tags_none else None

    memories = manager.list_memories(
        project_id=project_id,
        memory_type=memory_type,
        min_importance=min_importance,
        limit=limit,
        tags_all=tags_all_list,
        tags_any=tags_any_list,
        tags_none=tags_none_list,
    )
    if not memories:
        click.echo("No memories found.")
        return

    for mem in memories:
        tags_str = f" [{', '.join(mem.tags)}]" if mem.tags else ""
        click.echo(f"[{mem.id[:8]}] ({mem.memory_type}, {mem.importance:.2f}){tags_str}")
        click.echo(f"  {mem.content[:100]}{'...' if len(mem.content) > 100 else ''}")


@memory.command("show")
@click.argument("memory_ref")
@click.pass_context
def show_memory(ctx: click.Context, memory_ref: str) -> None:
    """Show details of a specific memory (UUID or prefix)."""
    manager = get_memory_manager(ctx)
    memory_id = resolve_memory_id(manager, memory_ref)
    memory = manager.get_memory(memory_id)
    if not memory:
        click.echo(f"Memory not found: {memory_id}")
        return

    click.echo(f"ID: {memory.id}")
    click.echo(f"Type: {memory.memory_type}")
    click.echo(f"Importance: {memory.importance}")
    click.echo(f"Created: {memory.created_at}")
    click.echo(f"Updated: {memory.updated_at}")
    click.echo(f"Source: {memory.source_type}")
    click.echo(f"Access Count: {memory.access_count}")
    if memory.tags:
        click.echo(f"Tags: {', '.join(memory.tags)}")
    click.echo(f"Content:\n{memory.content}")


@memory.command("update")
@click.argument("memory_ref")
@click.option("--content", "-c", help="New content")
@click.option("--importance", "-i", type=float, help="New importance (0.0-1.0)")
@click.option("--tags", "-t", help="New tags (comma-separated)")
@click.pass_context
def update_memory(
    ctx: click.Context,
    memory_ref: str,
    content: str | None,
    importance: float | None,
    tags: str | None,
) -> None:
    """Update an existing memory (UUID or prefix)."""
    manager = get_memory_manager(ctx)
    memory_id = resolve_memory_id(manager, memory_ref)

    # Parse tags if provided
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    if tag_list is not None and len(tag_list) == 0:
        tag_list = None

    try:
        memory = manager.update_memory(
            memory_id=memory_id,
            content=content,
            importance=importance,
            tags=tag_list,
        )
        click.echo(f"Updated memory: {memory.id}")
        click.echo(f"  Content: {memory.content[:80]}{'...' if len(memory.content) > 80 else ''}")
        click.echo(f"  Importance: {memory.importance}")
    except ValueError as e:
        click.echo(f"Error: {e}")


@memory.command("stats")
@click.option("--project", "-p", "project_ref", help="Project (name or UUID)")
@click.pass_context
def memory_stats(ctx: click.Context, project_ref: str | None) -> None:
    """Show memory system statistics."""
    project_id = resolve_project_ref(project_ref) if project_ref else None
    manager = get_memory_manager(ctx)
    stats = manager.get_stats(project_id=project_id)

    click.echo("Memory Statistics:")
    click.echo(f"  Total Memories: {stats['total_count']}")
    click.echo(f"  Average Importance: {stats['avg_importance']:.3f}")
    if stats["by_type"]:
        click.echo("  By Type:")
        for mem_type, count in stats["by_type"].items():
            click.echo(f"    {mem_type}: {count}")


def resolve_memory_id(manager: MemoryManager, memory_ref: str) -> str:
    """Resolve memory reference (UUID or prefix) to full ID."""
    # Try exact match first
    # Optimization: check 36 chars?
    if len(memory_ref) == 36 and manager.get_memory(memory_ref):
        return memory_ref

    # Try prefix match using MemoryManager method
    memories = manager.find_by_prefix(memory_ref, limit=5)

    if not memories:
        raise click.ClickException(f"Memory not found: {memory_ref}")

    if len(memories) > 1:
        click.echo(f"Ambiguous memory reference '{memory_ref}' matches:", err=True)
        for mem in memories:
            click.echo(f"  {mem.id}", err=True)
        raise click.ClickException(f"Ambiguous memory reference: {memory_ref}")

    return memories[0].id
