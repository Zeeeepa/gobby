"""
Shared content installation for Gobby hooks.

This module handles installing shared plugins and docs
that are used across all CLI integrations (Claude, Gemini, Codex, etc.).

Workflows, agents, rules, prompts, and skills are DB-managed:
they are synced from bundled YAML to the database during ``gobby install``
via :func:`sync_bundled_content_to_db`, NOT copied to ``.gobby/`` on disk.
"""

import logging
import os
import shutil
from pathlib import Path
from shutil import copy2, copytree
from typing import TYPE_CHECKING, Any

from gobby.cli.utils import get_install_dir

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


def _is_dev_mode(project_path: Path) -> bool:
    """Detect if running inside the gobby source repo.

    When the project IS the gobby source repo, we use symlinks instead of
    copies so that .gobby/ and install/shared/ stay in sync during development.
    """
    from gobby.utils.dev import is_dev_mode

    return is_dev_mode(project_path)


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

    Plugins are project-scoped and go to {project_path}/.gobby/plugins/.
    Docs are project-local and go to {project_path}/.gobby/docs/.

    Note: Workflows, agents, prompts, rules, and skills are DB-managed.
    They are synced to the database during ``gobby install`` via
    :func:`sync_bundled_content_to_db`, NOT copied to ``.gobby/``.

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
        "plugins": [],
        "docs": [],
    }

    if dev_mode:
        logger.info("Dev mode detected: using symlinks instead of copies")

    # Only plugins and docs are file-based; workflows/agents/rules/prompts/skills
    # are DB-managed and synced via sync_bundled_content_to_db().
    resource_dirs = [
        ("plugins", "plugins", "plugins"),
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
            # Copy files individually
            target.mkdir(parents=True, exist_ok=True)
            if type_key == "plugins":
                _copy_plugins(source, target, installed)
            elif type_key == "docs":
                _copy_docs(source, target, installed)

    return installed


def _copy_plugins(source: Path, target: Path, installed: dict[str, list[str]]) -> None:
    """Copy plugin files from source to target."""
    for plugin_file in source.iterdir():
        if plugin_file.is_file() and plugin_file.suffix == ".py":
            copy2(plugin_file, target / plugin_file.name)
            installed["plugins"].append(plugin_file.name)


def _copy_docs(source: Path, target: Path, installed: dict[str, list[str]]) -> None:
    """Copy doc files from source to target."""
    for doc_file in source.iterdir():
        if doc_file.is_file():
            copy2(doc_file, target / doc_file.name)
            installed["docs"].append(doc_file.name)


def sync_bundled_content_to_db(db: "DatabaseProtocol") -> dict[str, Any]:
    """Sync all bundled content (skills, prompts, rules, agents, workflows) to the database.

    Called during ``gobby install`` as the single import point.
    The daemon no longer syncs on startup.

    Args:
        db: Database connection implementing DatabaseProtocol.

    Returns:
        Dict with total_synced count and any errors.
    """
    result: dict[str, Any] = {
        "total_synced": 0,
        "errors": [],
        "details": {},
    }

    # (content_type, module_path, function_name)
    sync_targets: list[tuple[str, str, str]] = [
        ("skills", "gobby.skills.sync", "sync_bundled_skills"),
        ("prompts", "gobby.prompts.sync", "sync_bundled_prompts"),
        ("rules", "gobby.workflows.rule_sync", "sync_bundled_rules_sync"),
        ("agents", "gobby.agents.sync", "sync_bundled_agents"),
        ("workflows", "gobby.workflows.sync", "sync_bundled_workflows"),
    ]

    for content_type, module_path, func_name in sync_targets:
        try:
            module = __import__(module_path, fromlist=[func_name])
            sync_fn = getattr(module, func_name)
            sync_result = sync_fn(db)
            synced = sync_result.get("synced", 0) + sync_result.get("updated", 0)
            result["total_synced"] += synced
            result["details"][content_type] = sync_result
            if synced > 0:
                logger.info(f"Synced {synced} bundled {content_type} to database")
        except Exception as e:
            msg = f"Failed to sync bundled {content_type}: {e}"
            logger.warning(msg)
            result["errors"].append(msg)

    return result


def install_cli_content(cli_name: str, target_path: Path) -> dict[str, list[str]]:
    """Install CLI-specific commands (layered on top of shared).

    CLI-specific content can add to or override shared content.

    Args:
        cli_name: Name of the CLI (e.g., "claude", "gemini", "codex")
        target_path: Path to CLI config directory

    Returns:
        Dict with lists of installed items by type
    """
    cli_dir = get_install_dir() / cli_name
    installed: dict[str, list[str]] = {"commands": []}

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
