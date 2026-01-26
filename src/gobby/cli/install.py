"""
Installation commands for hooks.
"""

import logging
import shutil
import sys
from pathlib import Path
from shutil import copy2
from typing import Any

import click

from .installers import (
    install_antigravity,
    install_claude,
    install_codex_notify,
    install_default_mcp_servers,
    install_gemini,
    install_git_hooks,
    uninstall_claude,
    uninstall_codex_notify,
    uninstall_gemini,
)
from .utils import get_install_dir

logger = logging.getLogger(__name__)


def _ensure_daemon_config() -> dict[str, Any]:
    """Ensure daemon config exists at ~/.gobby/config.yaml.

    If config doesn't exist, copies the shared config template.

    Returns:
        Dict with 'created' (bool) and 'path' (str) keys
    """
    config_path = Path("~/.gobby/config.yaml").expanduser()

    if config_path.exists():
        return {"created": False, "path": str(config_path)}

    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy shared config template
    shared_config = get_install_dir() / "shared" / "config" / "config.yaml"
    if shared_config.exists():
        copy2(shared_config, config_path)
        # Set restrictive permissions
        config_path.chmod(0o600)
        return {"created": True, "path": str(config_path), "source": "shared"}

    # Fallback: generate from Pydantic defaults
    from gobby.config.app import generate_default_config

    generate_default_config(str(config_path))
    # Set restrictive permissions (same as copied template)
    config_path.chmod(0o600)
    return {"created": True, "path": str(config_path), "source": "generated"}


def _is_claude_code_installed() -> bool:
    """Check if Claude Code CLI is installed."""
    return shutil.which("claude") is not None


def _is_gemini_cli_installed() -> bool:
    """Check if Gemini CLI is installed."""
    return shutil.which("gemini") is not None


def _is_codex_cli_installed() -> bool:
    """Check if OpenAI Codex CLI is installed."""
    return shutil.which("codex") is not None


@click.command("install")
@click.option(
    "--claude",
    "claude_flag",
    is_flag=True,
    help="Install Claude Code hooks only",
)
@click.option(
    "--gemini",
    "gemini_flag",
    is_flag=True,
    help="Install Gemini CLI hooks only",
)
@click.option(
    "--codex",
    "codex_flag",
    is_flag=True,
    help="Configure Codex notify integration (interactive Codex)",
)
@click.option(
    "--hooks",
    "--git-hooks",
    "hooks_flag",
    is_flag=True,
    help="Install Git hooks for task auto-sync (pre-commit, post-merge, post-checkout)",
)
@click.option(
    "--all",
    "all_flag",
    is_flag=True,
    default=False,
    help="Install hooks for all detected CLIs (default behavior when no flags specified)",
)
@click.option(
    "--antigravity",
    "antigravity_flag",
    is_flag=True,
    help="Install Antigravity agent hooks (internal)",
)
def install(
    claude_flag: bool,
    gemini_flag: bool,
    codex_flag: bool,
    hooks_flag: bool,
    all_flag: bool,
    antigravity_flag: bool,
) -> None:
    """Install Gobby hooks to AI coding CLIs and Git.

    By default (no flags), installs to all detected CLIs.
    Use --claude, --gemini, --codex to install only to specific CLIs.
    Use --hooks to install Git hooks for task auto-sync.
    """
    project_path = Path.cwd()

    # Determine which CLIs to install
    # If no flags specified, act like --all (but don't force git hooks unless implied or explicit)
    # Actually, let's keep git hooks opt-in or part of --all?
    # Let's make --all include git hooks if we are in a git repo?
    # For safety, let's make git hooks explicit or part of --all if user approves?
    # Requirement: "Users must run this command explicitly to enable auto-sync"
    # So --all might NOT include hooks by default in this logic unless we change policy.
    # Let's explicitly check flags.

    if (
        not claude_flag
        and not gemini_flag
        and not codex_flag
        and not hooks_flag
        and not all_flag
        and not antigravity_flag
    ):
        all_flag = True

    codex_detected = _is_codex_cli_installed()

    # Build list of CLIs to install
    clis_to_install = []

    if all_flag:
        # Auto-detect installed CLIs
        if _is_claude_code_installed():
            clis_to_install.append("claude")
        if _is_gemini_cli_installed():
            clis_to_install.append("gemini")
        if codex_detected:
            clis_to_install.append("codex")

        # Check for git
        if (project_path / ".git").exists():
            hooks_flag = True  # Include git hooks in --all? Or leave separate?
            # Let's include them in --all for "complete setup", but maybe log it clearly.

        if not clis_to_install and not hooks_flag:
            click.echo("No supported AI coding CLIs detected.")
            click.echo("\nSupported CLIs:")
            click.echo("  - Claude Code: npm install -g @anthropic-ai/claude-code")
            click.echo("  - Gemini CLI:  npm install -g @google/gemini-cli")
            click.echo("  - Codex CLI:   npm install -g @openai/codex")
            click.echo(
                "\nYou can still install manually with --claude, --gemini, or --codex flags."
            )
            sys.exit(1)
    else:
        if claude_flag:
            clis_to_install.append("claude")
        if gemini_flag:
            clis_to_install.append("gemini")
        if codex_flag:
            clis_to_install.append("codex")
        if antigravity_flag:
            clis_to_install.append("antigravity")

    # Get install directory info
    install_dir = get_install_dir()
    is_dev_mode = "src" in str(install_dir)

    click.echo("=" * 60)
    click.echo("  Gobby Hooks Installation")
    click.echo("=" * 60)
    click.echo(f"\nProject: {project_path}")
    if is_dev_mode:
        click.echo("Mode: Development (using source directory)")

    # Ensure daemon config exists
    config_result = _ensure_daemon_config()
    if config_result["created"]:
        click.echo(f"Created daemon config: {config_result['path']}")

    # Install default external MCP servers (GitHub, Linear, context7)
    mcp_result = install_default_mcp_servers()
    if mcp_result["success"]:
        if mcp_result["servers_added"]:
            click.echo(f"Added MCP servers to proxy: {', '.join(mcp_result['servers_added'])}")
        if mcp_result["servers_skipped"]:
            click.echo(
                f"MCP servers already configured: {', '.join(mcp_result['servers_skipped'])}"
            )
    else:
        click.echo(f"Warning: Failed to configure MCP servers: {mcp_result['error']}")

    toggles = list(clis_to_install)
    if hooks_flag:
        toggles.append("git-hooks")

    click.echo(f"Components to configure: {', '.join(toggles)}")
    click.echo("")

    # Track results
    results = {}

    # Install Claude Code hooks
    if "claude" in clis_to_install:
        click.echo("-" * 40)
        click.echo("Claude Code")
        click.echo("-" * 40)

        result = install_claude(project_path)
        results["claude"] = result

        if result["success"]:
            click.echo(f"Installed {len(result['hooks_installed'])} hooks")
            for hook in result["hooks_installed"]:
                click.echo(f"  - {hook}")

            if result.get("workflows_installed"):
                click.echo(f"Installed {len(result['workflows_installed'])} workflows")
                for workflow in result["workflows_installed"]:
                    click.echo(f"  - {workflow}")
            if result.get("commands_installed"):
                click.echo(f"Installed {len(result['commands_installed'])} skills/commands")
                for cmd in result["commands_installed"]:
                    click.echo(f"  - {cmd}")
            if result.get("plugins_installed"):
                click.echo(
                    f"Installed {len(result['plugins_installed'])} plugins to .gobby/plugins/"
                )
                for plugin in result["plugins_installed"]:
                    click.echo(f"  - {plugin}")
            if result.get("mcp_configured"):
                click.echo("Configured MCP server: ~/.claude.json")
            elif result.get("mcp_already_configured"):
                click.echo("MCP server already configured: ~/.claude.json")
            click.echo(f"Configuration: {project_path / '.claude' / 'settings.json'}")
        else:
            click.echo(f"Failed: {result['error']}", err=True)
        click.echo("")

    # Install Gemini CLI hooks
    if "gemini" in clis_to_install:
        click.echo("-" * 40)
        click.echo("Gemini CLI")
        click.echo("-" * 40)

        result = install_gemini(project_path)
        results["gemini"] = result

        if result["success"]:
            click.echo(f"Installed {len(result['hooks_installed'])} hooks")
            for hook in result["hooks_installed"]:
                click.echo(f"  - {hook}")

            if result.get("workflows_installed"):
                click.echo(f"Installed {len(result['workflows_installed'])} workflows")
                for workflow in result["workflows_installed"]:
                    click.echo(f"  - {workflow}")
            if result.get("commands_installed"):
                click.echo(f"Installed {len(result['commands_installed'])} skills/commands")
                for cmd in result["commands_installed"]:
                    click.echo(f"  - {cmd}")
            if result.get("plugins_installed"):
                click.echo(
                    f"Installed {len(result['plugins_installed'])} plugins to .gobby/plugins/"
                )
                for plugin in result["plugins_installed"]:
                    click.echo(f"  - {plugin}")
            if result.get("mcp_configured"):
                click.echo("Configured MCP server: ~/.gemini/settings.json")
            elif result.get("mcp_already_configured"):
                click.echo("MCP server already configured: ~/.gemini/settings.json")
            click.echo(f"Configuration: {project_path / '.gemini' / 'settings.json'}")
        else:
            click.echo(f"Failed: {result['error']}", err=True)
        click.echo("")

    # Configure Codex notify integration (interactive Codex)
    if "codex" in clis_to_install:
        click.echo("-" * 40)
        click.echo("Codex")
        click.echo("-" * 40)

        if not codex_detected:
            click.echo("Codex CLI not detected in PATH (`codex`).", err=True)
            click.echo("Install Codex first, then re-run:")
            click.echo("  npm install -g @openai/codex\n")
            results["codex"] = {"success": False, "error": "Codex CLI not detected"}
        else:
            result = install_codex_notify()
            results["codex"] = result

            if result["success"]:
                click.echo("Installed Codex notify integration")
                for file_path in result["files_installed"]:
                    click.echo(f"  - {file_path}")
                if result.get("config_updated"):
                    click.echo("Updated: ~/.codex/config.toml (set `notify = ...`)")
                else:
                    click.echo("~/.codex/config.toml already configured")

                if result.get("workflows_installed"):
                    click.echo(f"Installed {len(result['workflows_installed'])} workflows")
                    for workflow in result["workflows_installed"]:
                        click.echo(f"  - {workflow}")
                if result.get("commands_installed"):
                    click.echo(f"Installed {len(result['commands_installed'])} commands")
                    for cmd in result["commands_installed"]:
                        click.echo(f"  - {cmd}")
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

    # Install Git Hooks
    if hooks_flag:
        click.echo("-" * 40)
        click.echo("Git Hooks (Task Auto-Sync)")
        click.echo("-" * 40)

        result = install_git_hooks(project_path)
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

    # Install Antigravity hooks
    # Note: Antigravity is an internal configuration, so we treat it similarly to Gemini
    if "antigravity" in clis_to_install:
        click.echo("-" * 40)
        click.echo("Antigravity Agent")
        click.echo("-" * 40)

        result = install_antigravity(project_path)
        results["antigravity"] = result

        if result["success"]:
            click.echo(f"Installed {len(result['hooks_installed'])} hooks")
            for hook in result["hooks_installed"]:
                click.echo(f"  - {hook}")

            if result.get("workflows_installed"):
                click.echo(f"Installed {len(result['workflows_installed'])} workflows")
                for workflow in result["workflows_installed"]:
                    click.echo(f"  - {workflow}")
            if result.get("commands_installed"):
                click.echo(f"Installed {len(result['commands_installed'])} skills/commands")
                for cmd in result["commands_installed"]:
                    click.echo(f"  - {cmd}")
            if result.get("plugins_installed"):
                click.echo(
                    f"Installed {len(result['plugins_installed'])} plugins to .gobby/plugins/"
                )
                for plugin in result["plugins_installed"]:
                    click.echo(f"  - {plugin}")
            if result.get("mcp_configured"):
                click.echo("Configured MCP server: ~/.gemini/antigravity/mcp_config.json")
            elif result.get("mcp_already_configured"):
                click.echo("MCP server already configured: ~/.gemini/antigravity/mcp_config.json")
            click.echo(f"Configuration: {project_path / '.antigravity' / 'settings.json'}")
        else:
            click.echo(f"Failed: {result['error']}", err=True)
        click.echo("")

    # Summary
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

    # Show MCP server API key instructions
    click.echo("\nMCP Servers (via Gobby proxy):")
    click.echo("  The following MCP servers are available through the Gobby proxy.")
    click.echo("  Configure API keys to enable them:")
    click.echo("")
    click.echo("  GitHub (issues, PRs, repos):")
    click.echo("    export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...")
    click.echo("")
    click.echo("  Linear (issue tracking):")
    click.echo("    export LINEAR_API_KEY=lin_api_...")
    click.echo("")
    click.echo("  Context7 (library docs, optional for private repos):")
    click.echo("    export CONTEXT7_API_KEY=...  # from context7.com/dashboard")
    click.echo("")
    click.echo("  Add these to your shell profile (~/.zshrc, ~/.bashrc) for persistence.")
    click.echo("  Restart the daemon after setting: gobby restart")

    if not all_success:
        sys.exit(1)


@click.command("uninstall")
@click.option(
    "--claude",
    "claude_flag",
    is_flag=True,
    help="Uninstall Claude Code hooks only",
)
@click.option(
    "--gemini",
    "gemini_flag",
    is_flag=True,
    help="Uninstall Gemini CLI hooks only",
)
@click.option(
    "--codex",
    "codex_flag",
    is_flag=True,
    help="Uninstall Codex notify integration",
)
@click.option(
    "--all",
    "all_flag",
    is_flag=True,
    default=False,
    help="Uninstall hooks from all CLIs (default behavior when no flags specified)",
)
@click.confirmation_option(prompt="Are you sure you want to uninstall Gobby hooks?")
def uninstall(claude_flag: bool, gemini_flag: bool, codex_flag: bool, all_flag: bool) -> None:
    """Uninstall Gobby hooks from AI coding CLIs.

    By default (no flags), uninstalls from all CLIs that have hooks installed.
    Use --claude, --gemini, or --codex to uninstall only from specific CLIs.

    Uninstalls from project-level directories in current working directory.
    """
    project_path = Path.cwd()

    # Determine which CLIs to uninstall
    # If no flags specified, act like --all
    if not claude_flag and not gemini_flag and not codex_flag and not all_flag:
        all_flag = True

    # Build list of CLIs to uninstall
    clis_to_uninstall = []

    if all_flag:
        # Check which CLIs have hooks installed
        claude_settings = project_path / ".claude" / "settings.json"
        gemini_settings = project_path / ".gemini" / "settings.json"
        codex_notify = Path.home() / ".gobby" / "hooks" / "codex" / "hook_dispatcher.py"

        if claude_settings.exists():
            clis_to_uninstall.append("claude")
        if gemini_settings.exists():
            clis_to_uninstall.append("gemini")
        if codex_notify.exists():
            clis_to_uninstall.append("codex")

        if not clis_to_uninstall:
            click.echo("No Gobby hooks found to uninstall.")
            click.echo(f"\nChecked: {project_path / '.claude'}")
            click.echo(f"         {project_path / '.gemini'}")
            click.echo(f"         {codex_notify}")
            sys.exit(0)
    else:
        if claude_flag:
            clis_to_uninstall.append("claude")
        if gemini_flag:
            clis_to_uninstall.append("gemini")
        if codex_flag:
            clis_to_uninstall.append("codex")

    click.echo("=" * 60)
    click.echo("  Gobby Hooks Uninstallation")
    click.echo("=" * 60)
    click.echo(f"\nProject: {project_path}")
    click.echo(f"CLIs to uninstall from: {', '.join(clis_to_uninstall)}")
    click.echo("")

    # Track results
    results = {}

    # Uninstall Claude Code hooks
    if "claude" in clis_to_uninstall:
        click.echo("-" * 40)
        click.echo("Claude Code")
        click.echo("-" * 40)

        result = uninstall_claude(project_path)
        results["claude"] = result

        if result["success"]:
            if result["hooks_removed"]:
                click.echo(f"Removed {len(result['hooks_removed'])} hooks from settings")
                for hook in result["hooks_removed"]:
                    click.echo(f"  - {hook}")
            if result["files_removed"]:
                click.echo(f"Removed {len(result['files_removed'])} files")

            if not result["hooks_removed"] and not result["files_removed"]:
                click.echo("  (no hooks found to remove)")
        else:
            click.echo(f"Failed: {result['error']}", err=True)
        click.echo("")

    # Uninstall Gemini CLI hooks
    if "gemini" in clis_to_uninstall:
        click.echo("-" * 40)
        click.echo("Gemini CLI")
        click.echo("-" * 40)

        result = uninstall_gemini(project_path)
        results["gemini"] = result

        if result["success"]:
            if result["hooks_removed"]:
                click.echo(f"Removed {len(result['hooks_removed'])} hooks from settings")
                for hook in result["hooks_removed"]:
                    click.echo(f"  - {hook}")
            if result["files_removed"]:
                click.echo(f"Removed {len(result['files_removed'])} files")
            if not result["hooks_removed"] and not result["files_removed"]:
                click.echo("  (no hooks found to remove)")
        else:
            click.echo(f"Failed: {result['error']}", err=True)
        click.echo("")

    # Uninstall Codex notify integration
    if "codex" in clis_to_uninstall:
        click.echo("-" * 40)
        click.echo("Codex")
        click.echo("-" * 40)

        result = uninstall_codex_notify()
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

    # Summary
    click.echo("=" * 60)
    click.echo("  Summary")
    click.echo("=" * 60)

    all_success = all(r.get("success", False) for r in results.values())

    if all_success:
        click.echo("\nUninstallation completed successfully!")
    else:
        failed = [cli for cli, r in results.items() if not r.get("success", False)]
        click.echo(f"\nSome uninstallations failed: {', '.join(failed)}")

    if not all_success:
        sys.exit(1)
