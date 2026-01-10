"""
Database management CLI commands.
"""

from pathlib import Path

import click

from gobby.config.app import DaemonConfig
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations


def _get_project_db_path() -> Path | None:
    """Get project database path if in project context."""
    cwd = Path.cwd()
    project_json = cwd / ".gobby" / "project.json"
    if project_json.exists():
        return cwd / ".gobby" / "gobby.db"
    return None


def _get_hub_db_path(config: DaemonConfig) -> Path:
    """Get hub database path from config."""
    return Path(config.database_path).expanduser()


def _sync_table_to_hub(
    source_db: LocalDatabase,
    dest_db: LocalDatabase,
    table: str,
    project_id: str | None = None,
) -> int:
    """
    Sync records from source to destination database for a table.

    Uses INSERT OR REPLACE to handle duplicates.
    Returns count of synced records.
    """
    # Get column names
    columns_result = source_db.fetchall(f"PRAGMA table_info({table})")
    if not columns_result:
        return 0

    columns = [row["name"] for row in columns_result]
    columns_str = ", ".join(columns)
    placeholders = ", ".join(["?"] * len(columns))

    # Build query with optional project_id filter
    if project_id and "project_id" in columns:
        query = f"SELECT {columns_str} FROM {table} WHERE project_id = ?"
        rows = source_db.fetchall(query, (project_id,))
    else:
        query = f"SELECT {columns_str} FROM {table}"
        rows = source_db.fetchall(query)

    if not rows:
        return 0

    # Insert into destination
    insert_sql = f"INSERT OR REPLACE INTO {table} ({columns_str}) VALUES ({placeholders})"
    for row in rows:
        values = tuple(row[col] for col in columns)
        dest_db.execute(insert_sql, values)

    return len(rows)


def _sync_table_from_hub(
    source_db: LocalDatabase,
    dest_db: LocalDatabase,
    table: str,
    project_id: str,
) -> int:
    """
    Sync records from hub to project database for a table.

    Only syncs records matching the project_id.
    Uses INSERT OR REPLACE to handle duplicates.
    Returns count of synced records.
    """
    # Get column names
    columns_result = source_db.fetchall(f"PRAGMA table_info({table})")
    if not columns_result:
        return 0

    columns = [row["name"] for row in columns_result]
    columns_str = ", ".join(columns)
    placeholders = ", ".join(["?"] * len(columns))

    # Only sync records for this project
    if "project_id" not in columns:
        return 0

    query = f"SELECT {columns_str} FROM {table} WHERE project_id = ?"
    rows = source_db.fetchall(query, (project_id,))

    if not rows:
        return 0

    # Insert into destination
    insert_sql = f"INSERT OR REPLACE INTO {table} ({columns_str}) VALUES ({placeholders})"
    for row in rows:
        values = tuple(row[col] for col in columns)
        dest_db.execute(insert_sql, values)

    return len(rows)


# Tables to sync (order matters for foreign keys)
SYNC_TABLES = [
    "projects",  # Must be first - other tables reference project_id
    "sessions",
    "session_messages",
    "tasks",
    "memories",
    "memory_crossrefs",
    "worktrees",
]


@click.group()
def db() -> None:
    """Database management commands."""
    pass


@db.command()
@click.option(
    "--direction",
    type=click.Choice(["to-hub", "from-hub"]),
    default="to-hub",
    help="Sync direction: to-hub (project->hub) or from-hub (hub->project)",
)
@click.pass_context
def sync(ctx: click.Context, direction: str) -> None:
    """Sync data between project and hub databases.

    to-hub: Copy all records from project .gobby/gobby.db to ~/.gobby/gobby-hub.db
    from-hub: Import records for current project from hub into local db
    """
    config: DaemonConfig = ctx.obj["config"]

    project_db_path = _get_project_db_path()
    hub_db_path = _get_hub_db_path(config)

    if direction == "to-hub":
        if project_db_path is None or not project_db_path.exists():
            click.echo("Error: Not in a project context or project database doesn't exist.", err=True)
            click.echo("Run this command from a directory with .gobby/project.json", err=True)
            raise SystemExit(1)

        click.echo("Syncing project database to hub...")
        click.echo(f"  Source: {project_db_path}")
        click.echo(f"  Destination: {hub_db_path}")

        # Ensure hub db directory exists
        hub_db_path.parent.mkdir(parents=True, exist_ok=True)

        source_db = LocalDatabase(project_db_path)
        dest_db = LocalDatabase(hub_db_path)

        # Run migrations on destination
        run_migrations(dest_db)

        total_synced = 0
        for table in SYNC_TABLES:
            try:
                count = _sync_table_to_hub(source_db, dest_db, table)
                if count > 0:
                    click.echo(f"  {table}: {count} records")
                    total_synced += count
            except Exception as e:
                click.echo(f"  {table}: error - {e}", err=True)

        click.echo(f"\nSync complete: {total_synced} total records synced to hub")

    else:  # from-hub
        if project_db_path is None:
            click.echo("Error: Not in a project context.", err=True)
            click.echo("Run this command from a directory with .gobby/project.json", err=True)
            raise SystemExit(1)

        if not hub_db_path.exists():
            click.echo(f"Error: Hub database doesn't exist: {hub_db_path}", err=True)
            raise SystemExit(1)

        # Get project ID from project.json
        import json

        project_json_path = Path.cwd() / ".gobby" / "project.json"
        try:
            project_data = json.loads(project_json_path.read_text())
            project_id = project_data.get("project_id")
            if not project_id:
                click.echo("Error: project_id not found in .gobby/project.json", err=True)
                raise SystemExit(1)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            click.echo(f"Error reading project.json: {e}", err=True)
            raise SystemExit(1) from None

        click.echo("Syncing from hub to project database...")
        click.echo(f"  Source: {hub_db_path}")
        click.echo(f"  Destination: {project_db_path}")
        click.echo(f"  Project ID: {project_id}")

        # Ensure project db directory exists
        project_db_path.parent.mkdir(parents=True, exist_ok=True)

        source_db = LocalDatabase(hub_db_path)
        dest_db = LocalDatabase(project_db_path)

        # Run migrations on destination
        run_migrations(dest_db)

        total_synced = 0
        for table in SYNC_TABLES:
            try:
                count = _sync_table_from_hub(source_db, dest_db, table, project_id)
                if count > 0:
                    click.echo(f"  {table}: {count} records")
                    total_synced += count
            except Exception as e:
                click.echo(f"  {table}: error - {e}", err=True)

        click.echo(f"\nSync complete: {total_synced} total records imported from hub")


@db.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show database status and paths."""
    config: DaemonConfig = ctx.obj["config"]

    project_db_path = _get_project_db_path()
    hub_db_path = _get_hub_db_path(config)

    click.echo("Database Status:")
    click.echo()

    # Hub database
    click.echo(f"Hub Database: {hub_db_path}")
    if hub_db_path.exists():
        size_mb = hub_db_path.stat().st_size / (1024 * 1024)
        click.echo(f"  Status: exists ({size_mb:.2f} MB)")
    else:
        click.echo("  Status: not created")

    click.echo()

    # Project database
    if project_db_path:
        click.echo(f"Project Database: {project_db_path}")
        if project_db_path.exists():
            size_mb = project_db_path.stat().st_size / (1024 * 1024)
            click.echo(f"  Status: exists ({size_mb:.2f} MB)")
        else:
            click.echo("  Status: not created")
    else:
        click.echo("Project Database: N/A (not in project context)")
