import asyncio

import click

from gobby.config.app import DaemonConfig
from gobby.memory.manager import MemoryManager
from gobby.storage.database import LocalDatabase


def get_memory_manager(ctx: click.Context) -> MemoryManager:
    """Get memory manager with OpenAI API key if available."""
    config: DaemonConfig = ctx.obj["config"]
    db = LocalDatabase()

    # Get OpenAI API key from config if available
    openai_api_key = None
    if config.llm_providers and config.llm_providers.api_keys:
        openai_api_key = config.llm_providers.api_keys.get("OPENAI_API_KEY")

    return MemoryManager(db, config.memory, openai_api_key=openai_api_key)


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
def create(
    ctx: click.Context, content: str, memory_type: str, importance: float, project_id: str | None
) -> None:
    """Create a new memory."""
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
def delete(ctx: click.Context, memory_id: str) -> None:
    """Delete a memory by ID."""
    manager = get_memory_manager(ctx)
    success = manager.forget(memory_id)
    if success:
        click.echo(f"Deleted memory: {memory_id}")
    else:
        click.echo(f"Memory not found: {memory_id}")


@memory.command("list")
@click.option("--type", "-t", "memory_type", help="Filter by memory type")
@click.option("--min-importance", "-i", type=float, help="Minimum importance threshold")
@click.option("--limit", "-n", default=50, help="Max results")
@click.option("--project", "-p", "project_id", help="Project ID")
@click.pass_context
def list_memories(
    ctx: click.Context,
    memory_type: str | None,
    min_importance: float | None,
    project_id: str | None,
    limit: int,
) -> None:
    """List all memories with optional filtering."""
    manager = get_memory_manager(ctx)
    memories = manager.list_memories(
        project_id=project_id,
        memory_type=memory_type,
        min_importance=min_importance,
        limit=limit,
    )
    if not memories:
        click.echo("No memories found.")
        return

    for mem in memories:
        tags_str = f" [{', '.join(mem.tags)}]" if mem.tags else ""
        click.echo(f"[{mem.id}] ({mem.memory_type}, {mem.importance:.2f}){tags_str}")
        click.echo(f"  {mem.content[:100]}{'...' if len(mem.content) > 100 else ''}")


@memory.command("show")
@click.argument("memory_id")
@click.pass_context
def show_memory(ctx: click.Context, memory_id: str) -> None:
    """Show details of a specific memory."""
    manager = get_memory_manager(ctx)
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
@click.argument("memory_id")
@click.option("--content", "-c", help="New content")
@click.option("--importance", "-i", type=float, help="New importance (0.0-1.0)")
@click.option("--tags", "-t", help="New tags (comma-separated)")
@click.pass_context
def update_memory(
    ctx: click.Context,
    memory_id: str,
    content: str | None,
    importance: float | None,
    tags: str | None,
) -> None:
    """Update an existing memory."""
    manager = get_memory_manager(ctx)

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
@click.option("--project", "-p", "project_id", help="Project ID")
@click.pass_context
def memory_stats(ctx: click.Context, project_id: str | None) -> None:
    """Show memory system statistics."""
    manager = get_memory_manager(ctx)
    stats = manager.get_stats(project_id=project_id)

    click.echo("Memory Statistics:")
    click.echo(f"  Total Memories: {stats['total_count']}")
    click.echo(f"  Average Importance: {stats['avg_importance']:.3f}")
    if stats["by_type"]:
        click.echo("  By Type:")
        for mem_type, count in stats["by_type"].items():
            click.echo(f"    {mem_type}: {count}")


@memory.command("rebuild-embeddings")
@click.option("--project", "-p", "project_id", help="Project ID filter")
@click.option("--force", "-f", is_flag=True, help="Force re-embed all memories")
@click.pass_context
def rebuild_embeddings(ctx: click.Context, project_id: str | None, force: bool) -> None:
    """Rebuild semantic search embeddings for memories.

    Generates vector embeddings for memories that don't have them,
    or all memories if --force is specified.

    Requires OPENAI_API_KEY in config (llm_providers.api_keys.OPENAI_API_KEY).
    """
    manager = get_memory_manager(ctx)

    click.echo("Rebuilding memory embeddings...")
    if force:
        click.echo("  (force mode: re-embedding all memories)")

    try:
        stats = asyncio.run(manager.rebuild_embeddings(project_id=project_id, force=force))

        click.echo("Done!")
        click.echo(f"  Embedded: {stats['embedded']}")
        click.echo(f"  Skipped: {stats['skipped']}")
        if stats["failed"] > 0:
            click.echo(f"  Failed: {stats['failed']}")
            for error in stats.get("errors", [])[:5]:
                click.echo(f"    - {error}")

    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from None


@memory.command("embedding-stats")
@click.option("--project", "-p", "project_id", help="Project ID filter")
@click.pass_context
def embedding_stats(ctx: click.Context, project_id: str | None) -> None:
    """Show embedding statistics for semantic search."""
    manager = get_memory_manager(ctx)
    stats = manager.get_embedding_stats(project_id=project_id)

    click.echo("Embedding Statistics:")
    click.echo(f"  Total Memories: {stats['total_memories']}")
    click.echo(f"  Embedded: {stats['embedded_memories']}")
    click.echo(f"  Pending: {stats['pending_embeddings']}")
    click.echo(f"  Model: {stats['embedding_model']}")
    click.echo(f"  Dimensions: {stats['embedding_dim']}")


@memory.command("init")
@click.option("--path", "-p", "project_path", default=".", help="Project path to scan")
@click.option("--max-files", "-n", default=20, help="Maximum files to sample")
@click.option("--project", "project_id", help="Project ID for memories")
@click.pass_context
def init(
    ctx: click.Context,
    project_path: str,
    max_files: int,
    project_id: str | None,
) -> None:
    """Initialize memory by extracting patterns and conventions from codebase."""
    from gobby.memory.extractor import MemoryExtractor

    manager = get_memory_manager(ctx)
    config: DaemonConfig = ctx.obj["config"]

    # Get LLM service if available
    llm_service = None
    try:
        from gobby.llm.service import LLMService

        llm_service = LLMService(config)
    except Exception as e:
        click.echo(f"Warning: LLM service not available: {e}", err=True)
        click.echo("Extraction requires an LLM. Configure llm_providers in config.yaml")
        raise SystemExit(1) from None

    extractor = MemoryExtractor(manager, llm_service)

    click.echo(f"Extracting patterns from codebase at {project_path}...")

    result = asyncio.run(
        extractor.extract_from_codebase(
            project_path=project_path,
            project_id=project_id,
            max_files=max_files,
        )
    )

    click.echo("Done!")
    click.echo(f"  Created: {result.created}")
    click.echo(f"  Skipped (duplicates): {result.skipped}")
    if result.errors:
        click.echo(f"  Errors: {len(result.errors)}")
        for error in result.errors[:5]:
            click.echo(f"    - {error}")


@memory.command("sync")
@click.option("--import", "do_import", is_flag=True, help="Import memories from JSONL")
@click.option("--export", "do_export", is_flag=True, help="Export memories to JSONL")
@click.option("--quiet", "-q", is_flag=True, help="Suppress output")
@click.pass_context
def sync_memories(ctx: click.Context, do_import: bool, do_export: bool, quiet: bool) -> None:
    """Sync memories with .gobby/memories.jsonl.

    If neither --import nor --export specified, does both.
    """
    from gobby.sync.memories import MemorySyncManager

    config: DaemonConfig = ctx.obj["config"]
    manager = get_memory_manager(ctx)
    db = LocalDatabase()

    sync_manager = MemorySyncManager(
        db=db,
        memory_manager=manager,
        config=config.memory_sync,
    )

    # Default to both if neither specified
    if not do_import and not do_export:
        do_import = True
        do_export = True

    if do_import:
        if not quiet:
            click.echo("Importing memories...")
        count = asyncio.run(sync_manager.import_from_files())
        if not quiet:
            click.echo(f"  Imported {count} memories")

    if do_export:
        if not quiet:
            click.echo("Exporting memories...")
        count = asyncio.run(sync_manager.export_to_files())
        if not quiet:
            click.echo(f"  Exported {count} memories")

    if not quiet:
        click.echo("Sync completed")
