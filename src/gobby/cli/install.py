"""
Installation commands for hooks.
"""

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import click

from .install_setup import ensure_daemon_config, run_daemon_setup
from .installers import (
    install_antigravity,
    install_claude,
    install_codex_notify,
    install_copilot,
    install_cursor,
    install_gemini,
    install_git_hooks,
    install_neo4j,
    install_windsurf,
    uninstall_claude,
    uninstall_codex_notify,
    uninstall_copilot,
    uninstall_cursor,
    uninstall_gemini,
    uninstall_neo4j,
    uninstall_windsurf,
)
from .utils import get_install_dir

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility (tests import from here)
_ensure_daemon_config = ensure_daemon_config


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


def _is_claude_code_installed() -> bool:
    """Check if Claude Code CLI is installed."""
    return shutil.which("claude") is not None


def _is_gemini_cli_installed() -> bool:
    """Check if Gemini CLI is installed."""
    return shutil.which("gemini") is not None


def _is_codex_cli_installed() -> bool:
    """Check if OpenAI Codex CLI is installed."""
    return shutil.which("codex") is not None


def _is_cursor_installed() -> bool:
    """Check if Cursor is installed."""
    # Cursor is an IDE, check for common install locations
    if sys.platform == "darwin":
        return Path("/Applications/Cursor.app").exists()
    elif sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", ""), "Programs", "cursor").exists()
    else:
        # Linux - check common locations
        return (Path.home() / ".local" / "share" / "cursor").exists() or shutil.which(
            "cursor"
        ) is not None


def _is_windsurf_installed() -> bool:
    """Check if Windsurf (Codeium) is installed."""
    # Windsurf is an IDE
    if sys.platform == "darwin":
        return Path("/Applications/Windsurf.app").exists()
    elif sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", ""), "Programs", "windsurf").exists()
    else:
        return shutil.which("windsurf") is not None


def _is_copilot_cli_installed() -> bool:
    """Check if GitHub Copilot CLI is installed."""
    # Check for gh copilot extension or standalone CLI
    return shutil.which("gh") is not None or shutil.which("github-copilot-cli") is not None


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
    "--cursor",
    "cursor_flag",
    is_flag=True,
    help="Install Cursor hooks",
)
@click.option(
    "--windsurf",
    "windsurf_flag",
    is_flag=True,
    help="Install Windsurf (Cascade) hooks",
)
@click.option(
    "--copilot",
    "copilot_flag",
    is_flag=True,
    help="Install GitHub Copilot CLI hooks",
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
@click.option(
    "--neo4j",
    "neo4j_flag",
    is_flag=True,
    help="Install Neo4j knowledge graph backend (Docker-based)",
)
@click.option(
    "--neo4j-password",
    "neo4j_password",
    default=None,
    help="Set a custom Neo4j password (default: auto-generated)",
)
@click.option(
    "--project",
    "project_flag",
    is_flag=True,
    help="Install hooks per-project instead of globally (legacy behavior)",
)
@click.option(
    "-C",
    "--path",
    "working_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Target directory (default: current directory)",
)
def install(
    claude_flag: bool,
    gemini_flag: bool,
    codex_flag: bool,
    cursor_flag: bool,
    windsurf_flag: bool,
    copilot_flag: bool,
    hooks_flag: bool,
    all_flag: bool,
    antigravity_flag: bool,
    neo4j_flag: bool,
    neo4j_password: str | None,
    project_flag: bool,
    working_dir: Path | None,
) -> None:
    """Install Gobby hooks to AI coding CLIs and Git.

    By default (no flags), installs hooks globally (one-time setup).
    Use --project to install per-project instead (legacy behavior).
    Use --claude, --gemini, --codex to install only to specific CLIs.
    Use --hooks to install Git hooks for task auto-sync.
    """
    project_path = working_dir.resolve() if working_dir else Path.cwd()
    mode = "project" if project_flag else "global"

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
        and not cursor_flag
        and not windsurf_flag
        and not copilot_flag
        and not hooks_flag
        and not all_flag
        and not antigravity_flag
        and not neo4j_flag
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
        if _is_cursor_installed():
            clis_to_install.append("cursor")
        if _is_windsurf_installed():
            clis_to_install.append("windsurf")
        if _is_copilot_cli_installed():
            clis_to_install.append("copilot")

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
            click.echo("  - Cursor:      https://cursor.com")
            click.echo("  - Windsurf:    https://codeium.com/windsurf")
            click.echo("  - Copilot CLI: gh extension install github/gh-copilot")
            click.echo(
                "\nYou can still install manually with --claude, --gemini, --codex, --cursor, --windsurf, or --copilot flags."
            )
            sys.exit(1)
    else:
        if claude_flag:
            clis_to_install.append("claude")
        if gemini_flag:
            clis_to_install.append("gemini")
        if codex_flag:
            clis_to_install.append("codex")
        if cursor_flag:
            clis_to_install.append("cursor")
        if windsurf_flag:
            clis_to_install.append("windsurf")
        if copilot_flag:
            clis_to_install.append("copilot")
        if antigravity_flag:
            clis_to_install.append("antigravity")

    # Get install directory info
    install_dir = get_install_dir()
    is_dev_mode = "src" in str(install_dir)

    click.echo("=" * 60)
    click.echo("  Gobby Hooks Installation")
    click.echo("=" * 60)
    if mode == "global":
        click.echo("\nScope: Global (hooks installed to ~/.gobby/hooks/)")
    else:
        click.echo(f"\nScope: Project ({project_path})")
    if is_dev_mode:
        click.echo("Mode: Development (using source directory)")

    # Phase 1: daemon config, database, bundled content, MCP servers, IDE config
    config_result = _ensure_daemon_config()
    if config_result["created"]:
        click.echo(f"Created daemon config: {config_result['path']}")
    run_daemon_setup(project_path)

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
        result = install_claude(project_path, mode=mode)
        results["claude"] = result
        if result["success"]:
            config = (
                "~/.claude/settings.json"
                if mode == "global"
                else str(project_path / ".claude" / "settings.json")
            )
            _echo_install_details(result, mcp_config_path="~/.claude.json", config_path=config)
        else:
            click.echo(f"Failed: {result['error']}", err=True)
        click.echo("")

    # Install Gemini CLI hooks
    if "gemini" in clis_to_install:
        click.echo("-" * 40)
        click.echo("Gemini CLI")
        click.echo("-" * 40)
        result = install_gemini(project_path, mode=mode)
        results["gemini"] = result
        if result["success"]:
            config = (
                "~/.gemini/settings.json"
                if mode == "global"
                else str(project_path / ".gemini" / "settings.json")
            )
            _echo_install_details(
                result, mcp_config_path="~/.gemini/settings.json", config_path=config
            )
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
            result = install_codex_notify(project_path)
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

    # Install Cursor hooks
    if "cursor" in clis_to_install:
        click.echo("-" * 40)
        click.echo("Cursor")
        click.echo("-" * 40)
        result = install_cursor(project_path, mode=mode)
        results["cursor"] = result
        if result["success"]:
            config = (
                "~/.cursor/hooks.json"
                if mode == "global"
                else str(project_path / ".cursor" / "hooks.json")
            )
            _echo_install_details(result, config_path=config)
        else:
            click.echo(f"Failed: {result['error']}", err=True)
        click.echo("")

    # Install Windsurf hooks
    if "windsurf" in clis_to_install:
        click.echo("-" * 40)
        click.echo("Windsurf (Cascade)")
        click.echo("-" * 40)
        result = install_windsurf(project_path, mode=mode)
        results["windsurf"] = result
        if result["success"]:
            config = (
                "~/.codeium/windsurf/hooks.json"
                if mode == "global"
                else str(project_path / ".windsurf" / "hooks.json")
            )
            _echo_install_details(result, config_path=config)
        else:
            click.echo(f"Failed: {result['error']}", err=True)
        click.echo("")

    # Install Copilot CLI hooks
    if "copilot" in clis_to_install:
        click.echo("-" * 40)
        click.echo("GitHub Copilot CLI")
        click.echo("-" * 40)
        result = install_copilot(project_path, mode=mode)
        results["copilot"] = result
        if result.get("skipped"):
            click.echo(f"Skipped: {result['skip_reason']}")
        elif result["success"]:
            _echo_install_details(result, config_path=str(project_path / ".copilot" / "hooks.json"))
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
    if "antigravity" in clis_to_install:
        click.echo("-" * 40)
        click.echo("Antigravity Agent")
        click.echo("-" * 40)
        result = install_antigravity(project_path)
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

    # Install Neo4j services
    if neo4j_flag:
        click.echo("-" * 40)
        click.echo("Neo4j Knowledge Graph")
        click.echo("-" * 40)

        result = install_neo4j(password=neo4j_password)
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

    # Migration detection: suggest cleanup of per-project hooks after global install
    if mode == "global":
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
    "--cursor",
    "cursor_flag",
    is_flag=True,
    help="Uninstall Cursor hooks",
)
@click.option(
    "--windsurf",
    "windsurf_flag",
    is_flag=True,
    help="Uninstall Windsurf hooks",
)
@click.option(
    "--copilot",
    "copilot_flag",
    is_flag=True,
    help="Uninstall Copilot CLI hooks",
)
@click.option(
    "--all",
    "all_flag",
    is_flag=True,
    default=False,
    help="Uninstall hooks from all CLIs (default behavior when no flags specified)",
)
@click.option(
    "--neo4j",
    "neo4j_flag",
    is_flag=True,
    help="Uninstall Neo4j knowledge graph backend",
)
@click.option(
    "--volumes",
    "volumes_flag",
    is_flag=True,
    help="Also remove Docker volumes (data loss, use with --neo4j)",
)
@click.option(
    "--project",
    "project_flag",
    is_flag=True,
    help="Uninstall per-project hooks from current directory (instead of global)",
)
@click.option(
    "-C",
    "--path",
    "working_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Target directory (default: current directory)",
)
@click.confirmation_option(prompt="Are you sure you want to uninstall Gobby hooks?")
def uninstall(
    claude_flag: bool,
    gemini_flag: bool,
    codex_flag: bool,
    cursor_flag: bool,
    windsurf_flag: bool,
    copilot_flag: bool,
    all_flag: bool,
    neo4j_flag: bool,
    volumes_flag: bool,
    project_flag: bool,
    working_dir: Path | None,
) -> None:
    """Uninstall Gobby hooks from AI coding CLIs.

    By default (no flags), uninstalls global hooks from CLI settings and ~/.gobby/hooks/.
    Use --project to uninstall per-project hooks from the current directory.
    Use --claude, --gemini, --codex, --cursor, --windsurf, or --copilot to uninstall only from specific CLIs.
    """
    project_path = working_dir.resolve() if working_dir else Path.cwd()

    # Determine which CLIs to uninstall
    # If no flags specified, act like --all
    if (
        not claude_flag
        and not gemini_flag
        and not codex_flag
        and not cursor_flag
        and not windsurf_flag
        and not copilot_flag
        and not all_flag
        and not neo4j_flag
    ):
        all_flag = True

    # Build list of CLIs to uninstall
    clis_to_uninstall = []

    if all_flag:
        if project_flag:
            # Check project-level paths
            claude_settings = project_path / ".claude" / "settings.json"
            gemini_settings = project_path / ".gemini" / "settings.json"
            cursor_hooks = project_path / ".cursor" / "hooks.json"
            windsurf_hooks = project_path / ".windsurf" / "hooks.json"
            copilot_hooks = project_path / ".copilot" / "hooks.json"
        else:
            # Check global paths
            claude_settings = Path.home() / ".claude" / "settings.json"
            gemini_settings = Path.home() / ".gemini" / "settings.json"
            cursor_hooks = Path.home() / ".cursor" / "hooks.json"
            windsurf_hooks = Path.home() / ".codeium" / "windsurf" / "hooks.json"
            copilot_hooks = (
                project_path / ".copilot" / "hooks.json"
            )  # Copilot is always per-project

        codex_notify = Path.home() / ".gobby" / "hooks" / "codex" / "hook_dispatcher.py"

        if claude_settings.exists():
            clis_to_uninstall.append("claude")
        if gemini_settings.exists():
            clis_to_uninstall.append("gemini")
        if codex_notify.exists():
            clis_to_uninstall.append("codex")
        if cursor_hooks.exists():
            clis_to_uninstall.append("cursor")
        if windsurf_hooks.exists():
            clis_to_uninstall.append("windsurf")
        if copilot_hooks.exists():
            clis_to_uninstall.append("copilot")

        if not clis_to_uninstall:
            click.echo("No Gobby hooks found to uninstall.")
            if project_flag:
                click.echo(f"\nChecked: {project_path / '.claude'}")
                click.echo(f"         {project_path / '.gemini'}")
                click.echo(f"         {project_path / '.cursor'}")
                click.echo(f"         {project_path / '.windsurf'}")
                click.echo(f"         {project_path / '.copilot'}")
            else:
                click.echo(f"\nChecked: {Path.home() / '.claude'}")
                click.echo(f"         {Path.home() / '.gemini'}")
                click.echo(f"         {Path.home() / '.cursor'}")
                click.echo(f"         {Path.home() / '.codeium' / 'windsurf'}")
            click.echo(f"         {codex_notify}")
            sys.exit(0)
    else:
        if claude_flag:
            clis_to_uninstall.append("claude")
        if gemini_flag:
            clis_to_uninstall.append("gemini")
        if codex_flag:
            clis_to_uninstall.append("codex")
        if cursor_flag:
            clis_to_uninstall.append("cursor")
        if windsurf_flag:
            clis_to_uninstall.append("windsurf")
        if copilot_flag:
            clis_to_uninstall.append("copilot")

    click.echo("=" * 60)
    click.echo("  Gobby Hooks Uninstallation")
    click.echo("=" * 60)
    if project_flag:
        click.echo(f"\nScope: Project ({project_path})")
    else:
        click.echo("\nScope: Global")
    click.echo(f"CLIs to uninstall from: {', '.join(clis_to_uninstall)}")
    click.echo("")

    # For global uninstall, use Path.home() so uninstallers find ~/.{cli}/
    # For project uninstall, use CWD (existing behavior)
    uninstall_base = project_path if project_flag else Path.home()

    # Track results
    results = {}

    # Uninstall Claude Code hooks
    if "claude" in clis_to_uninstall:
        click.echo("-" * 40)
        click.echo("Claude Code")
        click.echo("-" * 40)
        result = uninstall_claude(uninstall_base)
        results["claude"] = result
        if result["success"]:
            _echo_uninstall_details(result)
        else:
            click.echo(f"Failed: {result['error']}", err=True)
        click.echo("")

    # Uninstall Gemini CLI hooks
    if "gemini" in clis_to_uninstall:
        click.echo("-" * 40)
        click.echo("Gemini CLI")
        click.echo("-" * 40)
        result = uninstall_gemini(uninstall_base)
        results["gemini"] = result
        if result["success"]:
            _echo_uninstall_details(result)
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

    # Uninstall Cursor hooks
    if "cursor" in clis_to_uninstall:
        click.echo("-" * 40)
        click.echo("Cursor")
        click.echo("-" * 40)
        result = uninstall_cursor(uninstall_base)
        results["cursor"] = result
        if result["success"]:
            _echo_uninstall_details(result, label="hooks from hooks.json")
        else:
            click.echo(f"Failed: {result['error']}", err=True)
        click.echo("")

    # Uninstall Windsurf hooks
    if "windsurf" in clis_to_uninstall:
        click.echo("-" * 40)
        click.echo("Windsurf")
        click.echo("-" * 40)
        uninstall_mode = "project" if project_flag else "global"
        result = uninstall_windsurf(project_path, mode=uninstall_mode)
        results["windsurf"] = result
        if result["success"]:
            _echo_uninstall_details(result, label="hooks from hooks.json")
        else:
            click.echo(f"Failed: {result['error']}", err=True)
        click.echo("")

    # Uninstall Copilot hooks
    if "copilot" in clis_to_uninstall:
        click.echo("-" * 40)
        click.echo("Copilot CLI")
        click.echo("-" * 40)
        result = uninstall_copilot(project_path)
        results["copilot"] = result
        if result["success"]:
            _echo_uninstall_details(result, label="hooks from hooks.json")
        else:
            click.echo(f"Failed: {result['error']}", err=True)
        click.echo("")

    # Remove global hooks directory for global uninstall
    if not project_flag and all_flag:
        global_hooks_dir = Path(
            os.environ.get("GOBBY_HOOKS_DIR", str(Path.home() / ".gobby" / "hooks"))
        )
        # Only remove hook_dispatcher.py and validate_settings.py, not codex/ subdir
        for fname in ("hook_dispatcher.py", "validate_settings.py"):
            fpath = global_hooks_dir / fname
            if fpath.exists():
                try:
                    fpath.unlink()
                except OSError as e:
                    click.echo(f"  Warning: could not remove {fpath}: {e}", err=True)
        click.echo("Removed global hook dispatchers from ~/.gobby/hooks/")
        click.echo("")

    # Uninstall Neo4j services
    if neo4j_flag:
        click.echo("-" * 40)
        click.echo("Neo4j Knowledge Graph")
        click.echo("-" * 40)

        result = uninstall_neo4j(remove_volumes=volumes_flag)
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
