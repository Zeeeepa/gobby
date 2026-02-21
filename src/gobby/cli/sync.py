"""CLI command for syncing bundled content to the database.

Provides ``gobby sync`` with options for integrity verification,
selective syncing, and force mode.
"""

import logging
import sys
from pathlib import Path

import click

from .utils import get_install_dir

logger = logging.getLogger(__name__)

VALID_CONTENT_TYPES = {"skills", "prompts", "rules", "agents", "workflows"}


@click.command("sync")
@click.option("--force", is_flag=True, help="Skip integrity check even in production mode.")
@click.option("--verify-only", is_flag=True, help="Only run integrity check, don't sync.")
@click.option(
    "--type",
    "types",
    multiple=True,
    type=click.Choice(sorted(VALID_CONTENT_TYPES), case_sensitive=False),
    help="Sync only specific content types (repeatable).",
)
@click.option("--verbose", is_flag=True, help="Show per-type details.")
def sync(
    force: bool,
    verify_only: bool,
    types: tuple[str, ...],
    verbose: bool,
) -> None:
    """Sync bundled content (skills, prompts, rules, agents, workflows) to the database.

    In dev mode, syncs freely without integrity checks.
    In production mode, verifies git integrity first and blocks tampered types.
    """
    from gobby.utils.dev import is_dev_mode

    dev_mode = is_dev_mode(Path.cwd())
    install_dir = get_install_dir()
    skip_types: set[str] | None = None

    # --- Integrity check ---
    if not dev_mode and not force:
        from gobby.sync.integrity import (
            get_dirty_content_types,
            verify_bundled_integrity,
        )

        click.echo("Verifying bundled content integrity...")
        result = verify_bundled_integrity(install_dir)

        if not result.git_available:
            if verbose:
                click.echo("  Git not available — skipping integrity check")
        elif result.all_clean:
            click.echo("  All bundled content is clean")
        else:
            if result.dirty_files:
                click.echo(f"  Modified files ({len(result.dirty_files)}):")
                for f in result.dirty_files:
                    click.echo(f"    {f}")
            if result.untracked_files:
                click.echo(f"  Untracked files ({len(result.untracked_files)}):")
                for f in result.untracked_files:
                    click.echo(f"    {f}")

            tampered = get_dirty_content_types(
                result.dirty_files + result.untracked_files, install_dir
            )
            if tampered:
                skip_types = tampered
                click.echo(f"  Blocking tampered content types: {', '.join(sorted(tampered))}")

        if verify_only:
            sys.exit(0 if (not result.git_available or result.all_clean) else 1)
    elif dev_mode and not force:
        if verbose:
            click.echo("Dev mode: skipping integrity check")
    elif force:
        if verbose:
            click.echo("Force mode: skipping integrity check")

    if verify_only:
        # In dev mode or force mode with --verify-only, nothing to report
        click.echo("No integrity check performed (dev mode or --force)")
        sys.exit(0)

    # --- Filter to requested types ---
    if types:
        requested = set(types)
        if skip_types:
            skip_types = (VALID_CONTENT_TYPES - requested) | (skip_types & requested)
        else:
            skip_types = VALID_CONTENT_TYPES - requested

    # --- Initialize DB and sync ---
    from gobby.config.app import load_config
    from gobby.storage.database import LocalDatabase
    from gobby.storage.migrations import run_migrations

    config = load_config()
    db_path = Path(config.database_path).expanduser()
    if not db_path.exists():
        click.echo(f"Database not found at {db_path}. Run 'gobby install' first.")
        sys.exit(1)

    db = LocalDatabase(db_path)
    run_migrations(db)

    from gobby.cli.installers.shared import sync_bundled_content_to_db

    click.echo("Syncing bundled content to database...")
    sync_result = sync_bundled_content_to_db(db, skip_types=skip_types)

    total = sync_result["total_synced"]
    errors = sync_result["errors"]

    if total > 0:
        click.echo(f"Synced {total} bundled items to database")
    else:
        click.echo("No changes to sync")

    if verbose and sync_result.get("details"):
        for content_type, detail in sync_result["details"].items():
            synced = detail.get("synced", 0) + detail.get("updated", 0)
            if synced > 0:
                click.echo(f"  {content_type}: {synced} items")

    if skip_types and skip_types & VALID_CONTENT_TYPES:
        skipped = skip_types & VALID_CONTENT_TYPES
        # Only show types that were actually skipped due to tampering (not type filtering)
        if types:
            skipped = skipped & set(types)
        if skipped:
            click.echo(f"Skipped tampered types: {', '.join(sorted(skipped))}")

    if errors:
        for err in errors:
            click.echo(f"  Warning: {err}", err=True)
        sys.exit(1)
