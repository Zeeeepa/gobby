"""
Installation commands for hooks.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

import click

from ._detectors import (
    _is_claude_code_installed,
    _is_codex_cli_installed,
    _is_copilot_cli_installed,
    _is_cursor_installed,
    _is_gemini_cli_installed,
    _is_windsurf_installed,
)
from ._install_prompts import (
    _API_KEY_PROMPTS,
    _echo_install_details,
    _echo_install_summary,
    _echo_migration_notice,
    _echo_uninstall_details,
    _echo_uninstall_summary,
    _prompt_api_keys,
    _run_antigravity_install,
    _run_codex_install,
    _run_codex_uninstall,
    _run_copilot_install,
    _run_git_hooks_install,
    _run_neo4j_install,
    _run_neo4j_uninstall,
    _run_qdrant_install,
    _run_standard_cli_install,
    _run_standard_cli_uninstall,
)
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
    install_qdrant,
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

# Re-exports from extracted modules (tests import these from gobby.cli.install)
__all__ = [
    "_is_claude_code_installed",
    "_is_codex_cli_installed",
    "_is_copilot_cli_installed",
    "_is_cursor_installed",
    "_is_gemini_cli_installed",
    "_is_windsurf_installed",
    "_echo_install_details",
    "_echo_uninstall_details",
    "_API_KEY_PROMPTS",
    "_prompt_api_keys",
    "_ensure_daemon_config",
    "install",
    "uninstall",
]


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
    "--no-interactive",
    "no_interactive_flag",
    is_flag=True,
    help="Skip interactive prompts (for CI/automation)",
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
    no_interactive_flag: bool,
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
    clis_to_install: list[str] = []

    # Local copy of hooks_flag — mutated by auto-detection below
    install_hooks = hooks_flag

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
            install_hooks = True

        if not clis_to_install and not install_hooks:
            click.echo("No supported AI coding CLIs detected.")
            click.echo("\nSupported CLIs:")
            click.echo("  - Claude Code: npm install -g @anthropic-ai/claude-code")
            click.echo("  - Gemini CLI:  npm install -g @google/gemini-cli")
            click.echo("  - Codex CLI:   npm install -g @openai/codex")
            click.echo("  - Cursor:      https://cursor.com")
            click.echo("  - Windsurf:    https://codeium.com/windsurf")
            click.echo("  - Copilot CLI: gh extension install github/gh-copilot")
            click.echo(
                "\nYou can still install manually with --claude, --gemini, --codex,"
                " --cursor, --windsurf, or --copilot flags."
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
    if install_hooks:
        toggles.append("git-hooks")

    click.echo(f"Components to configure: {', '.join(toggles)}")
    click.echo("")

    # Track results
    results: dict[str, dict[str, Any]] = {}

    # Standard CLIs (claude, gemini, cursor, windsurf)
    _standard_installers = {
        "claude": install_claude,
        "gemini": install_gemini,
        "cursor": install_cursor,
        "windsurf": install_windsurf,
    }
    for cli_name, installer_fn in _standard_installers.items():
        if cli_name in clis_to_install:
            _run_standard_cli_install(cli_name, installer_fn, project_path, mode, results)

    # Codex (special: detection check + custom echo)
    if "codex" in clis_to_install:
        _run_codex_install(install_codex_notify, project_path, codex_detected, results)

    # Copilot (special: has 'skipped' case)
    if "copilot" in clis_to_install:
        _run_copilot_install(install_copilot, project_path, mode, results)

    # Git hooks
    if install_hooks:
        _run_git_hooks_install(install_git_hooks, project_path, results)

    # Antigravity
    if "antigravity" in clis_to_install:
        _run_antigravity_install(install_antigravity, project_path, results)

    # Qdrant (installed by default if Docker available)
    _run_qdrant_install(install_qdrant, results)

    # Neo4j
    if neo4j_flag:
        _run_neo4j_install(install_neo4j, neo4j_password, results)

    # Migration detection
    if mode == "global":
        _echo_migration_notice(project_path)

    # Summary, next steps, API key prompts
    all_success = _echo_install_summary(results, no_interactive_flag)
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
    Use --claude, --gemini, --codex, --cursor, --windsurf, or --copilot to uninstall
    only from specific CLIs.
    """
    project_path = working_dir.resolve() if working_dir else Path.cwd()

    # Determine which CLIs to uninstall
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
    clis_to_uninstall: list[str] = []

    if all_flag:
        if project_flag:
            claude_settings = project_path / ".claude" / "settings.json"
            gemini_settings = project_path / ".gemini" / "settings.json"
            cursor_hooks = project_path / ".cursor" / "hooks.json"
            windsurf_hooks = project_path / ".windsurf" / "hooks.json"
            copilot_hooks = project_path / ".copilot" / "hooks.json"
        else:
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
    uninstall_base = project_path if project_flag else Path.home()

    # Track results
    results: dict[str, dict[str, Any]] = {}

    # Standard CLIs (claude, gemini, cursor)
    _standard_uninstallers = {
        "claude": uninstall_claude,
        "gemini": uninstall_gemini,
        "cursor": uninstall_cursor,
    }
    for cli_name, uninstaller_fn in _standard_uninstallers.items():
        if cli_name in clis_to_uninstall:
            _run_standard_cli_uninstall(cli_name, uninstaller_fn, uninstall_base, results)

    # Codex (special: no base path arg)
    if "codex" in clis_to_uninstall:
        _run_codex_uninstall(uninstall_codex_notify, results)

    # Windsurf (special: takes project_path + mode kwarg)
    if "windsurf" in clis_to_uninstall:
        uninstall_mode = "project" if project_flag else "global"
        _run_standard_cli_uninstall(
            "windsurf", uninstall_windsurf, project_path, results, mode=uninstall_mode
        )

    # Copilot (special: always uses project_path)
    if "copilot" in clis_to_uninstall:
        _run_standard_cli_uninstall("copilot", uninstall_copilot, project_path, results)

    # Remove global hooks directory for global uninstall
    if not project_flag and all_flag:
        global_hooks_dir = Path(
            os.environ.get("GOBBY_HOOKS_DIR", str(Path.home() / ".gobby" / "hooks"))
        )
        for fname in ("hook_dispatcher.py", "validate_settings.py"):
            fpath = global_hooks_dir / fname
            if fpath.exists():
                try:
                    fpath.unlink()
                except OSError as e:
                    click.echo(f"  Warning: could not remove {fpath}: {e}", err=True)
        click.echo("Removed global hook dispatchers from ~/.gobby/hooks/")
        click.echo("")

    # Neo4j
    if neo4j_flag:
        _run_neo4j_uninstall(uninstall_neo4j, volumes_flag, results)

    # Summary
    all_success = _echo_uninstall_summary(results)
    if not all_success:
        sys.exit(1)
