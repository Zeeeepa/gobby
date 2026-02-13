"""
Shared content installation for Gobby hooks.

This module handles installing shared workflows and plugins
that are used across all CLI integrations (Claude, Gemini, Codex, etc.).
"""

import logging
import os
import shutil
from pathlib import Path
from shutil import copy2, copytree

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
