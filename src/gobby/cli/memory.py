import asyncio

import click

from gobby.cli.utils import resolve_project_ref
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


@memory.command("rebuild-embeddings")
@click.option("--project", "-p", "project_ref", help="Project (name or UUID)")
@click.option("--force", "-f", is_flag=True, help="Force re-embed all memories")
@click.pass_context
def rebuild_embeddings(ctx: click.Context, project_ref: str | None, force: bool) -> None:
    """Rebuild semantic search embeddings for memories.

    Generates vector embeddings for memories that don't have them,
    or all memories if --force is specified.

    Requires OPENAI_API_KEY in config (llm_providers.api_keys.OPENAI_API_KEY).
    """
    project_id = resolve_project_ref(project_ref) if project_ref else None
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
@click.option("--project", "-p", "project_ref", help="Project (name or UUID)")
@click.pass_context
def embedding_stats(ctx: click.Context, project_ref: str | None) -> None:
    """Show embedding statistics for semantic search."""
    project_id = resolve_project_ref(project_ref) if project_ref else None
    manager = get_memory_manager(ctx)
    stats = manager.get_embedding_stats(project_id=project_id)

    click.echo("Embedding Statistics:")
    click.echo(f"  Total Memories: {stats['total_memories']}")
    click.echo(f"  Embedded: {stats['embedded_memories']}")
    click.echo(f"  Pending: {stats['pending_embeddings']}")
    click.echo(f"  Model: {stats['embedding_model']}")
    click.echo(f"  Dimensions: {stats['embedding_dim']}")


@memory.command("reindex")
@click.pass_context
def reindex_search(ctx: click.Context) -> None:
    """Rebuild the TF-IDF search index for memories.

    Forces a complete rebuild of the search index from all stored memories.
    This is useful after bulk operations or to recover from index corruption.
    """
    manager = get_memory_manager(ctx)

    click.echo("Rebuilding memory search index...")
    result = manager.reindex_search()

    if result.get("success"):
        click.echo("Done!")
        click.echo(f"  Memories indexed: {result.get('memory_count', 0)}")
        click.echo(f"  Backend: {result.get('backend_type', 'unknown')}")
        if "vocabulary_size" in result:
            click.echo(f"  Vocabulary size: {result['vocabulary_size']}")
    else:
        click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
        raise SystemExit(1)


@memory.command("related")
@click.argument("memory_id")
@click.option("--limit", "-n", default=5, help="Max results")
@click.option(
    "--min-similarity", "-s", type=float, default=0.0, help="Minimum similarity (0.0-1.0)"
)
@click.pass_context
def related_memories(
    ctx: click.Context,
    memory_id: str,
    limit: int,
    min_similarity: float,
) -> None:
    """Show memories related to a specific memory via cross-references.

    Cross-references are created automatically when memories are stored
    (if auto_crossref is enabled in config). They link semantically similar
    memories together.
    """
    manager = get_memory_manager(ctx)

    # First verify the memory exists
    memory = manager.get_memory(memory_id)
    if not memory:
        click.echo(f"Memory not found: {memory_id}", err=True)
        raise SystemExit(1)

    click.echo(f"Memories related to: {memory_id}")
    click.echo(f"  Content: {memory.content[:60]}{'...' if len(memory.content) > 60 else ''}")
    click.echo()

    related = manager.get_related(
        memory_id=memory_id,
        limit=limit,
        min_similarity=min_similarity,
    )

    if not related:
        click.echo("No related memories found.")
        click.echo("Note: Cross-references are created when auto_crossref is enabled in config.")
        return

    for i, mem in enumerate(related, 1):
        click.echo(f"{i}. [{mem.id[:8]}] ({mem.memory_type}, {mem.importance:.2f})")
        click.echo(f"   {mem.content[:80]}{'...' if len(mem.content) > 80 else ''}")


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


@memory.command("graph")
@click.option("--output", "-o", "output_path", help="Output file path (default: memory_graph.html)")
@click.option("--open", "open_browser", is_flag=True, help="Open in browser after export")
@click.option("--project", "-p", "project_ref", help="Project (name or UUID)")
@click.option("--title", "-t", default="Memory Knowledge Graph", help="Graph title")
@click.pass_context
def export_graph(
    ctx: click.Context,
    output_path: str | None,
    open_browser: bool,
    project_ref: str | None,
    title: str,
) -> None:
    """Export memories as an interactive knowledge graph.

    Creates a standalone HTML file with vis.js visualization showing
    memories as nodes and cross-references as edges.

    Nodes are colored by type and sized by importance.
    """
    import webbrowser
    from pathlib import Path

    from gobby.memory.viz import export_memory_graph
    from gobby.storage.memories import LocalMemoryManager

    project_id = resolve_project_ref(project_ref) if project_ref else None
    manager = get_memory_manager(ctx)
    db = LocalDatabase()
    storage = LocalMemoryManager(db)

    # Get memories
    memories = manager.list_memories(project_id=project_id, limit=1000)
    if not memories:
        click.echo("No memories found.")
        return

    # Get cross-references
    crossrefs = storage.get_all_crossrefs(project_id=project_id, limit=5000)

    click.echo(f"Exporting {len(memories)} memories with {len(crossrefs)} cross-references...")

    # Generate HTML
    html_content = export_memory_graph(memories, crossrefs, title=title)

    # Determine output path
    if output_path is None:
        output_path = "memory_graph.html"
    output_file = Path(output_path)

    # Write file
    output_file.write_text(html_content)
    click.echo(f"Graph exported to: {output_file.absolute()}")

    # Open in browser if requested
    if open_browser:
        url = f"file://{output_file.absolute()}"
        click.echo("Opening in browser...")
        webbrowser.open(url)


@memory.command("migrate-v2")
@click.option("--project", "-p", "project_ref", help="Project (name or UUID)")
@click.option("--threshold", "-T", type=float, default=0.3, help="Crossref similarity threshold")
@click.option("--max-links", "-n", type=int, default=5, help="Max crossrefs per memory")
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes")
@click.pass_context
def migrate_v2(
    ctx: click.Context,
    project_ref: str | None,
    threshold: float,
    max_links: int,
    dry_run: bool,
) -> None:
    """Migrate to Memory V2 (TF-IDF search + cross-references).

    This command performs a one-time migration to enable Memory V2 features:

    1. Builds the TF-IDF search index for all existing memories
    2. Creates cross-references between semantically similar memories

    The migration is safe to run multiple times - it will rebuild the index
    and recreate cross-references based on current similarities.

    After migration, ensure your config has Memory V2 settings:

    \b
        memory:
          search_backend: "tfidf"
          auto_crossref: true
          crossref_threshold: 0.3
          crossref_max_links: 5
    """
    project_id = resolve_project_ref(project_ref) if project_ref else None
    manager = get_memory_manager(ctx)

    # Get all memories
    click.echo("Fetching memories...")
    memories = manager.list_memories(project_id=project_id, limit=10000)

    if not memories:
        click.echo("No memories found. Nothing to migrate.")
        return

    click.echo(f"Found {len(memories)} memories to migrate.")

    if dry_run:
        click.echo("\n[DRY RUN] Would perform the following:")
        click.echo(f"  1. Build TF-IDF search index for {len(memories)} memories")
        click.echo(
            f"  2. Create cross-references with threshold={threshold}, max_links={max_links}"
        )
        click.echo("\nRun without --dry-run to execute migration.")
        return

    # Step 1: Build TF-IDF search index
    click.echo("\nStep 1: Building TF-IDF search index...")
    result = manager.reindex_search()

    if result.get("success"):
        click.echo(f"  Index built with {result.get('memory_count', 0)} memories")
        if "vocabulary_size" in result:
            click.echo(f"  Vocabulary size: {result['vocabulary_size']}")
    else:
        click.echo(f"  Error: {result.get('error', 'Unknown error')}", err=True)
        raise SystemExit(1)

    # Step 2: Backfill cross-references
    click.echo("\nStep 2: Creating cross-references...")
    crossref_count = 0
    errors = []

    with click.progressbar(memories, label="Processing memories") as bar:
        for mem in bar:
            try:
                count = manager._create_crossrefs(
                    mem,
                    threshold=threshold,
                    max_links=max_links,
                )
                crossref_count += count
            except Exception as e:
                errors.append(f"{mem.id}: {e}")

    click.echo(f"  Created {crossref_count} cross-references")

    if errors:
        click.echo(f"\n  Errors ({len(errors)}):")
        for error in errors[:10]:
            click.echo(f"    - {error}")
        if len(errors) > 10:
            click.echo(f"    ... and {len(errors) - 10} more")

    click.echo("\nMigration complete!")
    click.echo("\nTo enable auto cross-referencing for new memories, add to config.yaml:")
    click.echo("  memory:")
    click.echo("    auto_crossref: true")
    click.echo(f"    crossref_threshold: {threshold}")
    click.echo(f"    crossref_max_links: {max_links}")
