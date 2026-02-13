"""
Shared content installation for Gobby hooks.

This module handles installing shared workflows and plugins
that are used across all CLI integrations (Claude, Gemini, Codex, etc.).
"""

import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from shutil import copy2, copytree
from typing import Any

from gobby.cli.utils import get_install_dir

logger = logging.getLogger(__name__)


def _is_dev_mode(project_path: Path) -> bool:
    """Detect if running inside the gobby source repo.

    When the project IS the gobby source repo, we use symlinks instead of
    copies so that .gobby/ and install/shared/ stay in sync during development.
    """
    return (project_path / "src" / "gobby" / "install" / "shared").is_dir()


def _install_resource_dir(source: Path, target: Path, dev_mode: bool) -> None:
    """Install a resource directory, handling existing symlinks safely.

    In dev mode, creates a symlink from target -> source.
    In normal mode, copies the directory tree.

    Safely handles existing symlinks by unlinking (not following) before
    replacing, which prevents shutil.rmtree from destroying source files.
    """
    if target.is_symlink():
        os.unlink(target)  # Safe: removes symlink, not target
    elif target.exists():
        shutil.rmtree(target)

    if dev_mode:
        os.symlink(source.resolve(), target)
    else:
        copytree(source, target)


def _install_file(source: Path, target: Path, dev_mode: bool, executable: bool = False) -> None:
    """Install a single file, using symlink in dev mode or copy otherwise.

    In dev mode, creates a symlink from target -> source.
    In normal mode, copies the file. Symlinks inherit permissions from the
    source, so chmod is only applied to copies.

    Args:
        source: Source file path
        target: Target file path
        dev_mode: If True, create symlink; if False, copy
        executable: If True (and not dev_mode), chmod 0o755 after copying
    """
    if target.is_symlink():
        os.unlink(target)
    elif target.exists():
        target.unlink()

    if dev_mode:
        os.symlink(source.resolve(), target)
    else:
        copy2(source, target)
        if executable:
            target.chmod(0o755)


def install_shared_content(cli_path: Path, project_path: Path) -> dict[str, list[str]]:
    """Install shared content from src/install/shared/.

    Workflows are cross-CLI and go to {project_path}/.gobby/workflows/.
    Agents are cross-CLI and go to {project_path}/.gobby/agents/.
    Plugins are project-scoped and go to {project_path}/.gobby/plugins/.
    Prompts are project-scoped and go to {project_path}/.gobby/prompts/.
    Docs are project-local and go to {project_path}/.gobby/docs/.

    In dev mode (running inside the gobby source repo), symlinks are created
    instead of copies so that .gobby/ and install/shared/ stay in sync.

    Args:
        cli_path: Path to CLI config directory (e.g., .claude, .gemini)
        project_path: Path to project root

    Returns:
        Dict with lists of installed items by type
    """
    shared_dir = get_install_dir() / "shared"
    dev_mode = _is_dev_mode(project_path)
    installed: dict[str, list[str]] = {
        "workflows": [],
        "agents": [],
        "plugins": [],
        "prompts": [],
        "docs": [],
    }

    if dev_mode:
        logger.info("Dev mode detected: using symlinks instead of copies")

    # Resource directories to install: (source_subdir, target_subdir, type_key)
    resource_dirs = [
        ("workflows", "workflows", "workflows"),
        ("agents", "agents", "agents"),
        ("plugins", "plugins", "plugins"),
        ("prompts", "prompts", "prompts"),
        ("docs", "docs", "docs"),
    ]

    for source_name, target_name, type_key in resource_dirs:
        source = shared_dir / source_name
        if not source.exists():
            continue

        target = project_path / ".gobby" / target_name

        if dev_mode:
            # Symlink the entire directory
            target.parent.mkdir(parents=True, exist_ok=True)
            _install_resource_dir(source, target, dev_mode=True)
            installed[type_key].append(f"{source_name}/ -> (symlink)")
        else:
            # Copy files individually (preserving existing per-item logic)
            target.mkdir(parents=True, exist_ok=True)
            if type_key == "workflows":
                _copy_workflows(source, target, installed)
            elif type_key == "agents":
                _copy_agents(source, target, installed)
            elif type_key == "plugins":
                _copy_plugins(source, target, installed)
            elif type_key == "prompts":
                _copy_prompts(source, target, installed)
            elif type_key == "docs":
                _copy_docs(source, target, installed)

    return installed


def _safe_remove_target(path: Path) -> None:
    """Remove a symlink or directory at path so it can be replaced."""
    if path.is_symlink():
        os.unlink(path)
    elif path.exists():
        shutil.rmtree(path)


def _copy_workflows(source: Path, target: Path, installed: dict[str, list[str]]) -> None:
    """Copy workflow files from source to target."""
    for item in source.iterdir():
        # Skip deprecated workflows - they are kept for reference only
        if item.name == "deprecated":
            continue
        if item.is_file():
            copy2(item, target / item.name)
            installed["workflows"].append(item.name)
        elif item.is_dir():
            target_subdir = target / item.name
            _safe_remove_target(target_subdir)
            copytree(item, target_subdir)
            installed["workflows"].append(f"{item.name}/")


def _copy_agents(source: Path, target: Path, installed: dict[str, list[str]]) -> None:
    """Copy agent files from source to target."""
    for item in source.iterdir():
        if item.is_file() and item.suffix in (".yaml", ".yml"):
            copy2(item, target / item.name)
            installed["agents"].append(item.name)
        elif item.is_dir():
            target_subdir = target / item.name
            _safe_remove_target(target_subdir)
            copytree(item, target_subdir)
            installed["agents"].append(f"{item.name}/")


def _copy_plugins(source: Path, target: Path, installed: dict[str, list[str]]) -> None:
    """Copy plugin files from source to target."""
    for plugin_file in source.iterdir():
        if plugin_file.is_file() and plugin_file.suffix == ".py":
            copy2(plugin_file, target / plugin_file.name)
            installed["plugins"].append(plugin_file.name)


def _copy_prompts(source: Path, target: Path, installed: dict[str, list[str]]) -> None:
    """Copy prompt files from source to target."""
    for item in source.iterdir():
        if item.is_file():
            copy2(item, target / item.name)
            installed["prompts"].append(item.name)
        elif item.is_dir():
            target_subdir = target / item.name
            _safe_remove_target(target_subdir)
            copytree(item, target_subdir)
            installed["prompts"].append(f"{item.name}/")


def _copy_docs(source: Path, target: Path, installed: dict[str, list[str]]) -> None:
    """Copy doc files from source to target."""
    for doc_file in source.iterdir():
        if doc_file.is_file():
            copy2(doc_file, target / doc_file.name)
            installed["docs"].append(doc_file.name)


def backup_gobby_skills(skills_dir: Path) -> dict[str, Any]:
    """Move gobby-prefixed skill directories to a backup location.

    This function is called during installation to preserve existing gobby skills
    before they are replaced by database-synced skills. User custom skills
    (non-gobby prefixed) are not touched.

    Args:
        skills_dir: Path to skills directory (e.g., .claude/skills)

    Returns:
        Dict with:
        - success: bool
        - backed_up: int - number of skills moved to backup
        - skipped: str (optional) - reason for skipping
    """
    result: dict[str, Any] = {
        "success": True,
        "backed_up": 0,
    }

    if not skills_dir.exists():
        result["skipped"] = "skills directory does not exist"
        return result

    # Find gobby-prefixed skill directories
    gobby_skills = [d for d in skills_dir.iterdir() if d.is_dir() and d.name.startswith("gobby-")]

    if not gobby_skills:
        return result

    # Create backup directory (sibling to skills/)
    backup_dir = skills_dir.parent / "skills.backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Move each gobby skill to backup
    import shutil

    for skill_dir in gobby_skills:
        target = backup_dir / skill_dir.name
        # If already exists in backup, remove it first (replace with newer)
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(skill_dir), str(target))
        result["backed_up"] += 1

    return result


def install_shared_skills(target_dir: Path) -> list[str]:
    """Install shared SKILL.md files to target directory.

    Copies skills from src/gobby/install/shared/skills/ to target_dir.
    Backs up existing SKILL.md if content differs.

    Args:
        target_dir: Directory where skills should be installed (e.g. .claude/skills)

    Returns:
        List of installed skill names
    """
    shared_skills_dir = get_install_dir() / "shared" / "skills"
    installed: list[str] = []

    if not shared_skills_dir.exists():
        return installed

    target_dir.mkdir(parents=True, exist_ok=True)

    for skill_path in shared_skills_dir.iterdir():
        if not skill_path.is_dir():
            continue

        skill_name = skill_path.name
        source_skill_md = skill_path / "SKILL.md"

        if not source_skill_md.exists():
            continue

        # Target: target_dir/skill_name/SKILL.md
        target_skill_dir = target_dir / skill_name
        target_skill_dir.mkdir(parents=True, exist_ok=True)
        target_skill_md = target_skill_dir / "SKILL.md"

        # Backup if exists and differs
        if target_skill_md.exists():
            try:
                # Read both to compare
                source_content = source_skill_md.read_text(encoding="utf-8")
                target_content = target_skill_md.read_text(encoding="utf-8")

                if source_content != target_content:
                    timestamp = int(time.time())
                    backup_path = target_skill_md.with_suffix(f".md.{timestamp}.backup")
                    target_skill_md.rename(backup_path)
            except OSError as e:
                logger.warning(f"Failed to backup/read skill {skill_name}: {e}")
                continue

        # Copy new file
        try:
            copy2(source_skill_md, target_skill_md)
            installed.append(skill_name)
        except OSError as e:
            logger.error(f"Failed to copy skill {skill_name}: {e}")

    return installed


def install_router_skills_as_commands(target_commands_dir: Path) -> list[str]:
    """Install router skills as flattened Claude commands.

    Claude Code uses .claude/commands/name.md format for slash commands.
    This function copies the gobby router skills from shared/skills/ to
    commands/ as flattened .md files.

    Also cleans up stale command files from removed skills (e.g., g.md).

    Args:
        target_commands_dir: Path to commands directory (e.g., .claude/commands)

    Returns:
        List of installed command names
    """
    shared_skills_dir = get_install_dir() / "shared" / "skills"
    installed: list[str] = []

    # Router skills to install as commands
    router_skills = ["gobby"]

    # Clean up stale command files from removed skills
    stale_commands = ["g.md"]
    for stale in stale_commands:
        stale_path = target_commands_dir / stale
        if stale_path.exists():
            try:
                stale_path.unlink()
                logger.info(f"Removed stale command: {stale}")
            except OSError as e:
                logger.warning(f"Failed to remove stale command {stale}: {e}")

    target_commands_dir.mkdir(parents=True, exist_ok=True)

    for skill_name in router_skills:
        source_skill_md = shared_skills_dir / skill_name / "SKILL.md"
        if not source_skill_md.exists():
            logger.warning(f"Router skill not found: {source_skill_md}")
            continue

        # Flatten: copy SKILL.md to commands/name.md
        target_cmd = target_commands_dir / f"{skill_name}.md"

        try:
            copy2(source_skill_md, target_cmd)
            installed.append(f"{skill_name}.md")
        except OSError as e:
            logger.error(f"Failed to copy router skill {skill_name}: {e}")

    return installed


def install_router_skills_as_gemini_skills(target_skills_dir: Path) -> list[str]:
    """Install router skills as Gemini skills (directory structure).

    Gemini CLI uses .gemini/skills/name/SKILL.md format for skills.
    This function copies the gobby router skills from shared/skills/ to
    the target skills directory preserving the directory structure.

    Also cleans up stale skill directories from removed skills (e.g., g/).

    Args:
        target_skills_dir: Path to skills directory (e.g., .gemini/skills)

    Returns:
        List of installed skill names
    """
    shared_skills_dir = get_install_dir() / "shared" / "skills"
    installed: list[str] = []

    # Router skills to install
    router_skills = ["gobby"]

    # Clean up stale skill directories from removed skills
    stale_skills = ["g"]
    for stale in stale_skills:
        stale_path = target_skills_dir / stale
        if stale_path.exists():
            try:
                shutil.rmtree(stale_path)
                logger.info(f"Removed stale skill directory: {stale}/")
            except OSError as e:
                logger.warning(f"Failed to remove stale skill {stale}: {e}")

    target_skills_dir.mkdir(parents=True, exist_ok=True)

    for skill_name in router_skills:
        source_skill_dir = shared_skills_dir / skill_name
        source_skill_md = source_skill_dir / "SKILL.md"
        if not source_skill_md.exists():
            logger.warning(f"Router skill not found: {source_skill_md}")
            continue

        # Create skill directory and copy SKILL.md
        target_skill_dir = target_skills_dir / skill_name
        target_skill_dir.mkdir(parents=True, exist_ok=True)
        target_skill_md = target_skill_dir / "SKILL.md"

        try:
            copy2(source_skill_md, target_skill_md)
            installed.append(f"{skill_name}/")
        except OSError as e:
            logger.error(f"Failed to copy router skill {skill_name}: {e}")

    return installed


def install_cli_content(cli_name: str, target_path: Path) -> dict[str, list[str]]:
    """Install CLI-specific workflows/commands (layered on top of shared).

    CLI-specific content can add to or override shared content.

    Args:
        cli_name: Name of the CLI (e.g., "claude", "gemini", "codex")
        target_path: Path to CLI config directory

    Returns:
        Dict with lists of installed items by type
    """
    cli_dir = get_install_dir() / cli_name
    installed: dict[str, list[str]] = {"workflows": [], "commands": []}

    # CLI-specific workflows
    cli_workflows = cli_dir / "workflows"
    if cli_workflows.exists():
        target_workflows = target_path / "workflows"
        target_workflows.mkdir(parents=True, exist_ok=True)
        for item in cli_workflows.iterdir():
            if item.is_file():
                copy2(item, target_workflows / item.name)
                installed["workflows"].append(item.name)
            elif item.is_dir():
                # Copy subdirectories
                target_subdir = target_workflows / item.name
                if target_subdir.exists():
                    shutil.rmtree(target_subdir)
                copytree(item, target_subdir)
                installed["workflows"].append(f"{item.name}/")

    # CLI-specific commands (slash commands)
    # Claude/Gemini: commands/, Codex: prompts/
    for cmd_dir_name in ["commands", "prompts"]:
        cli_commands = cli_dir / cmd_dir_name
        if cli_commands.exists():
            target_commands = target_path / cmd_dir_name
            target_commands.mkdir(parents=True, exist_ok=True)
            for item in cli_commands.iterdir():
                if item.is_dir():
                    # Directory of commands (e.g., memory/)
                    target_subdir = target_commands / item.name
                    if target_subdir.exists():
                        shutil.rmtree(target_subdir)
                    copytree(item, target_subdir)
                    installed["commands"].append(f"{item.name}/")
                elif item.is_file():
                    # Single command file
                    copy2(item, target_commands / item.name)
                    installed["commands"].append(item.name)

    return installed


# --- MCP config functions (delegated to mcp_config.py) ---
# Re-exported for backward compatibility
from .mcp_config import DEFAULT_MCP_SERVERS as DEFAULT_MCP_SERVERS  # noqa: E402
from .mcp_config import configure_mcp_server_json as configure_mcp_server_json  # noqa: E402
from .mcp_config import configure_mcp_server_toml as configure_mcp_server_toml  # noqa: E402
from .mcp_config import configure_project_mcp_server as configure_project_mcp_server  # noqa: E402
from .mcp_config import install_default_mcp_servers as install_default_mcp_servers  # noqa: E402
from .mcp_config import remove_mcp_server_json as remove_mcp_server_json  # noqa: E402
from .mcp_config import remove_mcp_server_toml as remove_mcp_server_toml  # noqa: E402
from .mcp_config import remove_project_mcp_server as remove_project_mcp_server  # noqa: E402


def _get_ide_config_dir(ide_name: str) -> Path:
    """Get the IDE's config root directory (cross-platform).

    macOS:   ~/Library/Application Support/<ide_name>/
    Linux:   ~/.config/<ide_name>/
    Windows: %APPDATA%/<ide_name>/
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / ide_name
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) / ide_name
    else:
        return Path.home() / ".config" / ide_name


def configure_ide_terminal_title(ide_name: str) -> dict[str, Any]:
    """Configure terminal.integrated.tabs.title for a VS Code-family IDE.

    Adds ``${sequence}`` so tmux ``set-titles`` OSC escapes propagate to
    tab/sidebar labels. Uses backup + atomic write pattern. No-op if
    already configured.

    Skips silently if the IDE is not installed (config dir doesn't exist).

    Args:
        ide_name: IDE name matching the Application Support / config dir
                  (e.g. "Cursor", "Windsurf", "Antigravity").

    Returns:
        Dict with 'success', 'added', 'already_configured', 'skipped',
        'backup_path', and 'error' keys.
    """
    result: dict[str, Any] = {
        "success": False,
        "added": False,
        "already_configured": False,
        "skipped": False,
        "backup_path": None,
        "error": None,
    }

    config_dir = _get_ide_config_dir(ide_name)
    if not config_dir.exists():
        # IDE not installed — skip silently
        result["success"] = True
        result["skipped"] = True
        return result

    settings_path = config_dir / "User" / "settings.json"

    # Load existing settings or start with empty dict
    existing_settings: dict[str, Any] = {}
    if settings_path.exists():
        try:
            with open(settings_path) as f:
                existing_settings = json.load(f)
        except json.JSONDecodeError as e:
            result["error"] = f"Failed to parse {settings_path}: {e}"
            return result
        except OSError as e:
            result["error"] = f"Failed to read {settings_path}: {e}"
            return result

    # Check if already configured
    setting_key = "terminal.integrated.tabs.title"
    if setting_key in existing_settings:
        result["success"] = True
        result["already_configured"] = True
        return result

    # Create backup if file exists
    if settings_path.exists():
        timestamp = int(time.time())
        backup_path = settings_path.parent / f"settings.json.{timestamp}.backup"
        try:
            copy2(settings_path, backup_path)
            result["backup_path"] = str(backup_path)
        except OSError as e:
            result["error"] = f"Failed to create backup: {e}"
            return result

    # Add the setting
    existing_settings[setting_key] = "${sequence}"

    # Ensure User/ directory exists
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Write updated settings
    try:
        with open(settings_path, "w") as f:
            json.dump(existing_settings, f, indent=2)
    except OSError as e:
        result["error"] = f"Failed to write {settings_path}: {e}"
        return result

    result["success"] = True
    result["added"] = True
    return result
