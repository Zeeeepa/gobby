"""Interactive prompt and UI helpers for install/uninstall commands."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
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


# ---------------------------------------------------------------------------
# Per-CLI install/uninstall orchestration helpers
# ---------------------------------------------------------------------------

# Mapping: cli_name -> (display_name, global_config, project_config_subpath, mcp_config_path)
_CLI_INSTALL_META: dict[str, tuple[str, str, str, str | None]] = {
    "claude": ("Claude Code", "~/.claude/settings.json", ".claude/settings.json", "~/.claude.json"),
    "gemini": (
        "Gemini CLI",
        "~/.gemini/settings.json",
        ".gemini/settings.json",
        "~/.gemini/settings.json",
    ),
    "cursor": ("Cursor", "~/.cursor/hooks.json", ".cursor/hooks.json", None),
    "windsurf": (
        "Windsurf (Cascade)",
        "~/.codeium/windsurf/hooks.json",
        ".windsurf/hooks.json",
        None,
    ),
}


def _run_standard_cli_install(
    cli_name: str,
    installer: Callable[..., dict[str, Any]],
    project_path: Path,
    mode: str,
    results: dict[str, dict[str, Any]],
) -> None:
    """Run install + echo for a standard CLI (claude, gemini, cursor, windsurf)."""
    display_name, global_config, project_subpath, mcp_path = _CLI_INSTALL_META[cli_name]

    click.echo("-" * 40)
    click.echo(display_name)
    click.echo("-" * 40)

    result = installer(project_path, mode=mode)
    results[cli_name] = result

    if result["success"]:
        config = global_config if mode == "global" else str(project_path / project_subpath)
        _echo_install_details(result, mcp_config_path=mcp_path, config_path=config)
    else:
        click.echo(f"Failed: {result['error']}", err=True)
    click.echo("")


def _run_copilot_install(
    installer: Callable[..., dict[str, Any]],
    project_path: Path,
    mode: str,
    results: dict[str, dict[str, Any]],
) -> None:
    """Run install + echo for Copilot CLI (has 'skipped' special case)."""
    click.echo("-" * 40)
    click.echo("GitHub Copilot CLI")
    click.echo("-" * 40)

    result = installer(project_path, mode=mode)
    results["copilot"] = result

    if result.get("skipped"):
        click.echo(f"Skipped: {result['skip_reason']}")
    elif result["success"]:
        _echo_install_details(result, config_path=str(project_path / ".copilot" / "hooks.json"))
    else:
        click.echo(f"Failed: {result['error']}", err=True)
    click.echo("")


def _run_codex_install(
    installer: Callable[..., dict[str, Any]],
    project_path: Path,
    codex_detected: bool,
    results: dict[str, dict[str, Any]],
) -> None:
    """Run install + echo for Codex notify integration."""
    click.echo("-" * 40)
    click.echo("Codex")
    click.echo("-" * 40)

    if not codex_detected:
        click.echo("Codex CLI not detected in PATH (`codex`).", err=True)
        click.echo("Install Codex first, then re-run:")
        click.echo("  npm install -g @openai/codex\n")
        results["codex"] = {"success": False, "error": "Codex CLI not detected"}
    else:
        result = installer(project_path)
        results["codex"] = result

        if result["success"]:
            click.echo("Installed Codex notify integration")
            for file_path in result["files_installed"]:
                click.echo(f"  - {file_path}")
            if result.get("config_updated"):
                click.echo("Updated: ~/.codex/config.toml (set `notify = ...`)")
            else:
                click.echo("~/.codex/config.toml already configured")

            for key, label in [
                ("workflows_installed", "workflows"),
                ("commands_installed", "commands"),
            ]:
                items = result.get(key)
                if items:
                    click.echo(f"Installed {len(items)} {label}")
                    for item in items:
                        click.echo(f"  - {item}")

            if result.get("plugins_installed"):
                click.echo(
                    f"Installed {len(result['plugins_installed'])} plugins to .gobby/plugins/"
                )
                for plugin in result["plugins_installed"]:
                    click.echo(f"  - {plugin}")
            if result.get("mcp_configured"):
                click.echo("Configured MCP server: ~/.codex/config.toml")
            elif result.get("mcp_already_configured"):
                click.echo("MCP server already configured: ~/.codex/config.toml")
        else:
            click.echo(f"Failed: {result['error']}", err=True)
    click.echo("")


def _run_git_hooks_install(
    installer: Callable[..., dict[str, Any]],
    project_path: Path,
    results: dict[str, dict[str, Any]],
) -> None:
    """Run install + echo for Git hooks."""
    click.echo("-" * 40)
    click.echo("Git Hooks (Task Auto-Sync)")
    click.echo("-" * 40)

    result = installer(project_path)
    results["git-hooks"] = result

    if result["success"]:
        if result.get("installed"):
            click.echo("Installed git hooks:")
            for hook in result["installed"]:
                click.echo(f"  - {hook}")
        if result.get("skipped"):
            click.echo("Skipped:")
            for hook in result["skipped"]:
                click.echo(f"  - {hook}")
        if not result.get("installed") and not result.get("skipped"):
            click.echo("No hooks to install")
    else:
        click.echo(f"Failed: {result['error']}", err=True)
    click.echo("")


def _run_antigravity_install(
    installer: Callable[..., dict[str, Any]],
    project_path: Path,
    results: dict[str, dict[str, Any]],
) -> None:
    """Run install + echo for Antigravity agent."""
    click.echo("-" * 40)
    click.echo("Antigravity Agent")
    click.echo("-" * 40)

    result = installer(project_path)
    results["antigravity"] = result

    if result["success"]:
        _echo_install_details(
            result,
            mcp_config_path="~/.gemini/antigravity/mcp_config.json",
            config_path=str(project_path / ".antigravity" / "settings.json"),
        )
    else:
        click.echo(f"Failed: {result['error']}", err=True)
    click.echo("")


def _run_neo4j_install(
    installer: Callable[..., dict[str, Any]],
    neo4j_password: str | None,
    results: dict[str, dict[str, Any]],
) -> None:
    """Run install + echo for Neo4j."""
    click.echo("-" * 40)
    click.echo("Neo4j Knowledge Graph")
    click.echo("-" * 40)

    result = installer(password=neo4j_password)
    results["neo4j"] = result

    if result["success"]:
        click.echo("Neo4j installed (local mode)")
        click.echo(f"  HTTP: {result['neo4j_url']}")
        click.echo(f"  Bolt: {result.get('bolt_url', 'N/A')}")
        if result.get("compose_file"):
            click.echo(f"  Compose: {result['compose_file']}")
        click.echo("\nRestart the daemon to apply: gobby restart")
    else:
        click.echo(f"Failed: {result['error']}", err=True)
    click.echo("")


def _echo_migration_notice(project_path: Path) -> None:
    """Detect and warn about per-project hooks that can be cleaned up."""
    per_project_hooks = []
    for cli_name, cli_dir in [
        ("claude", ".claude"),
        ("gemini", ".gemini"),
        ("cursor", ".cursor"),
        ("windsurf", ".windsurf"),
        ("copilot", ".copilot"),
    ]:
        hooks_dir = project_path / cli_dir / "hooks"
        hooks_json = project_path / cli_dir / "hooks.json"
        if (hooks_dir / "hook_dispatcher.py").exists() or (
            cli_name in ("cursor", "windsurf", "copilot") and hooks_json.exists()
        ):
            per_project_hooks.append(cli_name)

    if per_project_hooks:
        click.echo("-" * 40)
        click.echo("Migration Notice")
        click.echo("-" * 40)
        click.echo(f"Per-project hooks detected for: {', '.join(per_project_hooks)}")
        click.echo("Run 'gobby uninstall --project' to clean up per-project hooks.")
        click.echo("")


def _echo_install_summary(
    results: dict[str, dict[str, Any]],
    no_interactive_flag: bool,
) -> bool:
    """Print install summary, next steps, and API key prompts. Returns True if all succeeded."""
    click.echo("=" * 60)
    click.echo("  Summary")
    click.echo("=" * 60)

    all_success = all(r.get("success", False) for r in results.values())

    if all_success:
        click.echo("\nInstallation completed successfully!")
    else:
        failed = [cli for cli, r in results.items() if not r.get("success", False)]
        click.echo(f"\nSome installations failed: {', '.join(failed)}")

    click.echo("\nNext steps:")
    click.echo("  1. Ensure the Gobby daemon is running:")
    click.echo("     gobby start")
    click.echo("  2. Start a new session in your AI coding CLI")
    click.echo("  3. Your sessions will now be tracked locally")

    api_key_result = _prompt_api_keys(no_interactive=no_interactive_flag)
    if no_interactive_flag or (
        api_key_result["stored"] == 0
        and api_key_result["already_configured"] == 0
        and api_key_result["env_found"] == 0
    ):
        click.echo("\nMCP Servers (via Gobby proxy):")
        click.echo("  Configure API keys to enable external integrations:")
        click.echo("    gobby secrets set github_personal_access_token")
        click.echo("    gobby secrets set linear_api_key")
        click.echo("    gobby secrets set openai_api_key")
        click.echo("    gobby secrets set context7_api_key")
        click.echo("  Or set environment variables (GITHUB_PERSONAL_ACCESS_TOKEN, etc.)")
        click.echo("  Restart the daemon after setting: gobby restart")

    return all_success


def _echo_uninstall_summary(results: dict[str, dict[str, Any]]) -> bool:
    """Print uninstall summary. Returns True if all succeeded."""
    click.echo("=" * 60)
    click.echo("  Summary")
    click.echo("=" * 60)

    all_success = all(r.get("success", False) for r in results.values())

    if all_success:
        click.echo("\nUninstallation completed successfully!")
    else:
        failed = [cli for cli, r in results.items() if not r.get("success", False)]
        click.echo(f"\nSome uninstallations failed: {', '.join(failed)}")

    return all_success


# Uninstall CLI meta: cli_name -> (display_name, uninstall_label)
_CLI_UNINSTALL_META: dict[str, tuple[str, str]] = {
    "claude": ("Claude Code", "hooks from settings"),
    "gemini": ("Gemini CLI", "hooks from settings"),
    "cursor": ("Cursor", "hooks from hooks.json"),
    "windsurf": ("Windsurf", "hooks from hooks.json"),
    "copilot": ("Copilot CLI", "hooks from hooks.json"),
}


def _run_standard_cli_uninstall(
    cli_name: str,
    uninstaller: Callable[..., dict[str, Any]],
    uninstall_base: Path,
    results: dict[str, dict[str, Any]],
    **kwargs: Any,
) -> None:
    """Run uninstall + echo for a standard CLI."""
    display_name, label = _CLI_UNINSTALL_META[cli_name]

    click.echo("-" * 40)
    click.echo(display_name)
    click.echo("-" * 40)

    result = uninstaller(uninstall_base, **kwargs)
    results[cli_name] = result

    if result["success"]:
        _echo_uninstall_details(result, label=label)
    else:
        click.echo(f"Failed: {result['error']}", err=True)
    click.echo("")


def _run_codex_uninstall(
    uninstaller: Callable[..., dict[str, Any]],
    results: dict[str, dict[str, Any]],
) -> None:
    """Run uninstall + echo for Codex notify integration."""
    click.echo("-" * 40)
    click.echo("Codex")
    click.echo("-" * 40)

    result = uninstaller()
    results["codex"] = result

    if result["success"]:
        if result["files_removed"]:
            click.echo(f"Removed {len(result['files_removed'])} files")
            for f in result["files_removed"]:
                click.echo(f"  - {f}")
        if result.get("config_updated"):
            click.echo("Updated: ~/.codex/config.toml (removed `notify = ...`)")
        if not result["files_removed"] and not result.get("config_updated"):
            click.echo("  (no codex integration found to remove)")
    else:
        click.echo(f"Failed: {result['error']}", err=True)
    click.echo("")


def _run_neo4j_uninstall(
    uninstaller: Callable[..., dict[str, Any]],
    volumes_flag: bool,
    results: dict[str, dict[str, Any]],
) -> None:
    """Run uninstall + echo for Neo4j."""
    click.echo("-" * 40)
    click.echo("Neo4j Knowledge Graph")
    click.echo("-" * 40)

    result = uninstaller(remove_volumes=volumes_flag)
    results["neo4j"] = result

    if result["success"]:
        if result.get("already_uninstalled"):
            click.echo("Neo4j was not installed")
        else:
            click.echo("Neo4j services removed")
            if result.get("volumes_removed"):
                click.echo("  Docker volumes removed (data deleted)")
        click.echo("\nRestart the daemon to apply: gobby restart")
    else:
        click.echo(f"Failed: {result['error']}", err=True)
    click.echo("")
