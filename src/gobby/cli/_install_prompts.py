"""Interactive prompt and UI helpers for install/uninstall commands."""

from __future__ import annotations

import logging
import os
from typing import Any

import click

logger = logging.getLogger(__name__)


def _echo_install_details(
    result: dict[str, Any],
    mcp_config_path: str | None = None,
    config_path: str | None = None,
) -> None:
    """Print common install result details (hooks, workflows, agents, commands, plugins, MCP)."""
    click.echo(f"Installed {len(result['hooks_installed'])} hooks")
    for hook in result["hooks_installed"]:
        click.echo(f"  - {hook}")

    for key, label in [
        ("workflows_installed", "workflows"),
        ("agents_installed", "agents"),
        ("commands_installed", "skills/commands"),
    ]:
        items = result.get(key)
        if items:
            click.echo(f"Installed {len(items)} {label}")
            for item in items:
                click.echo(f"  - {item}")

    plugins = result.get("plugins_installed")
    if plugins:
        click.echo(f"Installed {len(plugins)} plugins to .gobby/plugins/")
        for plugin in plugins:
            click.echo(f"  - {plugin}")

    if mcp_config_path:
        if result.get("mcp_configured"):
            click.echo(f"Configured MCP server: {mcp_config_path}")
        elif result.get("mcp_already_configured"):
            click.echo(f"MCP server already configured: {mcp_config_path}")

    if config_path:
        click.echo(f"Configuration: {config_path}")


def _echo_uninstall_details(
    result: dict[str, Any],
    label: str = "hooks from settings",
) -> None:
    """Print common uninstall result details (hooks removed, files removed)."""
    if result["hooks_removed"]:
        click.echo(f"Removed {len(result['hooks_removed'])} {label}")
        for hook in result["hooks_removed"]:
            click.echo(f"  - {hook}")
    if result["files_removed"]:
        click.echo(f"Removed {len(result['files_removed'])} files")
    if not result["hooks_removed"] and not result["files_removed"]:
        click.echo("  (no hooks found to remove)")


_API_KEY_PROMPTS = [
    {
        "secret_name": "github_personal_access_token",
        "env_var": "GITHUB_PERSONAL_ACCESS_TOKEN",
        "label": "GitHub Personal Access Token",
        "category": "mcp_server",
        "description": "GitHub MCP server authentication",
    },
    {
        "secret_name": "linear_api_key",
        "env_var": "LINEAR_API_KEY",
        "label": "Linear API Key",
        "category": "mcp_server",
        "description": "Linear MCP server authentication",
    },
    {
        "secret_name": "openai_api_key",
        "env_var": "OPENAI_API_KEY",
        "label": "OpenAI API Key",
        "category": "llm",
        "description": "OpenAI embeddings and LLM execution",
    },
    {
        "secret_name": "context7_api_key",
        "env_var": "CONTEXT7_API_KEY",
        "label": "Context7 API Key",
        "category": "mcp_server",
        "description": "Context7 library docs (private repos)",
    },
]


def _prompt_api_keys(no_interactive: bool = False) -> dict[str, Any]:
    """Prompt for API keys and store them in the secret store.

    Skips keys that are already stored or found in environment variables.
    In non-interactive mode, skips all prompts.

    Returns:
        Dict with stored, skipped, env_found counts.
    """
    result: dict[str, Any] = {"stored": 0, "skipped": 0, "env_found": 0, "already_configured": 0}

    if no_interactive:
        return result

    try:
        from gobby.storage.database import LocalDatabase
        from gobby.storage.secrets import SecretStore

        db = LocalDatabase()
        store = SecretStore(db)
    except Exception as e:
        click.echo(f"  Warning: Could not initialize secret store: {e}")
        return result

    click.echo("")
    click.echo("-" * 40)
    click.echo("API Keys (optional)")
    click.echo("-" * 40)
    click.echo("These enable external integrations. Press Enter to skip any.")
    click.echo("")

    for key_info in _API_KEY_PROMPTS:
        secret_name = key_info["secret_name"]
        env_var = key_info["env_var"]
        label = key_info["label"]

        # Check if already stored in secret store
        if store.exists(secret_name):
            click.echo(f"  {label}: (already configured)")
            result["already_configured"] += 1
            continue

        # Check if set in environment
        if os.environ.get(env_var):
            click.echo(f"  {label}: (found in environment)")
            result["env_found"] += 1
            continue

        # Prompt for value
        try:
            value = click.prompt(f"  {label}", default="", hide_input=True, show_default=False)
        except (click.Abort, EOFError):
            click.echo("")
            break

        if value.strip():
            try:
                store.set(
                    name=secret_name,
                    plaintext_value=value.strip(),
                    category=key_info["category"],
                    description=key_info["description"],
                )
                click.echo(f"    Stored {secret_name}")
                result["stored"] += 1
            except Exception as e:
                logger.warning("Failed to store %s: %s", secret_name, e)
                click.echo(f"    Warning: Failed to store {secret_name}: {e}")
        else:
            result["skipped"] += 1

    return result
