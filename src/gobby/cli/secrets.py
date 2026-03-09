"""CLI commands for managing encrypted secrets."""

import click

from gobby.cli.utils import get_gobby_home
from gobby.storage.database import LocalDatabase
from gobby.storage.secrets import VALID_CATEGORIES, SecretStore


def _get_secret_store() -> SecretStore:
    """Open the DB and return a SecretStore (no daemon required)."""
    db_path = get_gobby_home() / "gobby-hub.db"
    if not db_path.exists():
        click.echo("Error: Gobby database not found. Run 'gobby start' first.", err=True)
        raise SystemExit(1)
    db = LocalDatabase(str(db_path))
    return SecretStore(db)


@click.group()
def secrets() -> None:
    """Manage encrypted secrets (API keys, tokens, etc.)."""


@secrets.command("set")
@click.argument("name")
@click.option(
    "--category",
    type=click.Choice(sorted(VALID_CATEGORIES), case_sensitive=False),
    default="general",
    help="Secret category.",
)
@click.option("--description", "-d", default=None, help="Human-readable description.")
def set_secret(name: str, category: str, description: str | None) -> None:
    """Store a secret. Value is prompted interactively (never passed as an argument).

    NAME is the secret identifier (e.g. anthropic_api_key). Reference it
    elsewhere as $secret:NAME.
    """
    value = click.prompt("Secret value", hide_input=True, confirmation_prompt=True)
    if not value.strip():
        click.echo("Error: Secret value cannot be empty.", err=True)
        raise SystemExit(1)

    store = _get_secret_store()
    info = store.set(name, value, category=category, description=description)
    click.echo(f"Stored secret '{info.name}' (category={info.category}).")


@secrets.command("list")
def list_secrets() -> None:
    """List stored secrets (metadata only, never values)."""
    store = _get_secret_store()
    items = store.list()
    if not items:
        click.echo("No secrets stored.")
        return

    # Simple table output
    name_width = max(len(s.name) for s in items)
    cat_width = max(len(s.category) for s in items)
    click.echo(f"{'NAME':<{name_width}}  {'CATEGORY':<{cat_width}}  DESCRIPTION")
    click.echo(f"{'-' * name_width}  {'-' * cat_width}  {'-' * 11}")
    for s in items:
        desc = s.description or ""
        click.echo(f"{s.name:<{name_width}}  {s.category:<{cat_width}}  {desc}")


@secrets.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def delete_secret(name: str, yes: bool) -> None:
    """Delete a secret by NAME."""
    store = _get_secret_store()
    if not store.exists(name):
        click.echo(f"Secret '{name}' not found.", err=True)
        raise SystemExit(1)

    if not yes:
        click.confirm(f"Delete secret '{name}'?", abort=True)

    store.delete(name)
    click.echo(f"Deleted secret '{name}'.")


@secrets.command("get")
@click.argument("name")
def get_secret(name: str) -> None:
    """Check if a secret exists (does NOT reveal the value)."""
    store = _get_secret_store()
    if store.exists(name):
        click.echo(f"Secret '{name}' exists.")
    else:
        click.echo(f"Secret '{name}' not found.", err=True)
        raise SystemExit(1)
