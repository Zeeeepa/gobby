"""CLI commands for managing local embedding models.

Provides commands to download, list, and remove GGUF embedding models
used by the local embedding backend.
"""

import asyncio

import click


@click.group()
def models() -> None:
    """Manage local embedding models."""


@models.command()
@click.argument("model_name", default="nomic-embed-text-v1.5")
def pull(model_name: str) -> None:
    """Download an embedding model.

    MODEL_NAME defaults to nomic-embed-text-v1.5 (the default local backend).
    """
    from gobby.search.local_embeddings import download_model, get_default_model_path

    model_path = get_default_model_path(model_name)
    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024 * 1024)
        click.echo(f"Model already downloaded: {model_path} ({size_mb:.1f} MB)")
        return

    click.echo(f"Downloading model: {model_name}...")
    try:
        path = asyncio.run(download_model(model_name))
        size_mb = path.stat().st_size / (1024 * 1024)
        click.echo(f"Downloaded: {path} ({size_mb:.1f} MB)")
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from e


@models.command("list")
def list_models() -> None:
    """List downloaded models."""
    from gobby.search.local_embeddings import list_downloaded_models

    downloaded = list_downloaded_models()
    if not downloaded:
        click.echo("No models downloaded.")
        click.echo("Run 'gobby models pull' to download the default embedding model.")
        return

    click.echo(f"{'Name':<40} {'Size':<12} {'Path'}")
    click.echo("-" * 80)
    for model in downloaded:
        click.echo(f"{model['name']:<40} {model['size']:<12} {model['path']}")


@models.command()
@click.argument("model_name")
def remove(model_name: str) -> None:
    """Remove a downloaded model."""
    from gobby.search.local_embeddings import remove_model

    if remove_model(model_name):
        click.echo(f"Removed model: {model_name}")
    else:
        click.echo(f"Model not found: {model_name}", err=True)
        raise SystemExit(1)
