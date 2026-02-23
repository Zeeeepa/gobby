"""CLI command for managing web UI authentication."""

import click

from gobby.cli.utils import get_gobby_home
from gobby.storage.config_store import ConfigStore
from gobby.storage.database import LocalDatabase
from gobby.storage.secrets import SecretStore


@click.command()
@click.option("--remove", is_flag=True, help="Remove auth credentials and disable web UI login.")
def auth(remove: bool) -> None:
    """Set up or reset web UI authentication credentials."""
    db_path = get_gobby_home() / "gobby-hub.db"
    if not db_path.exists():
        click.echo("Error: Gobby database not found. Run 'gobby start' first.", err=True)
        raise SystemExit(1)

    db = LocalDatabase(str(db_path))
    config_store = ConfigStore(db)
    secret_store = SecretStore(db)

    existing_username = config_store.get("auth.username")

    if remove:
        if not existing_username:
            click.echo("No auth configured. Nothing to remove.")
            return
        config_store.delete("auth.username")
        config_store.clear_secret("auth.password", secret_store)
        click.echo(f"Auth removed for user '{existing_username}'.")
        click.echo("Restart the daemon for changes to take effect.")
        return

    if existing_username:
        click.echo(f"Auth configured for user '{existing_username}'. Resetting password.")
        password = click.prompt("New password", hide_input=True, confirmation_prompt=True)
        config_store.set_secret("auth.password", password, secret_store, source="user")
        click.echo(f"Password updated for user '{existing_username}'.")
    else:
        click.echo("No auth configured. Setting up web UI authentication.")
        username = click.prompt("Username")
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        config_store.set("auth.username", username, source="user")
        config_store.set_secret("auth.password", password, secret_store, source="user")
        click.echo(f"Auth enabled for user '{username}'.")

    click.echo("Restart the daemon for changes to take effect.")
