"""
Shared content installation for Gobby hooks.

This module handles installing shared skills, workflows, and plugins
that are used across all CLI integrations (Claude, Gemini, Codex, etc.).
"""

import shutil
from pathlib import Path
from shutil import copy2, copytree

from gobby.cli.utils import get_install_dir


def install_shared_content(cli_path: Path, project_path: Path) -> dict[str, list[str]]:
    """Install shared content from src/install/shared/.

    Skills are CLI-specific and go to {cli_path}/skills/.
    Workflows are cross-CLI and go to {project_path}/.gobby/workflows/.
    Plugins are global and go to ~/.gobby/plugins/.

    Args:
        cli_path: Path to CLI config directory (e.g., .claude, .gemini)
        project_path: Path to project root

    Returns:
        Dict with lists of installed items by type
    """
    shared_dir = get_install_dir() / "shared"
    installed: dict[str, list[str]] = {"skills": [], "workflows": [], "plugins": []}

    # Install shared skills to CLI directory
    shared_skills = shared_dir / "skills"
    if shared_skills.exists():
        target_skills = cli_path / "skills"
        target_skills.mkdir(parents=True, exist_ok=True)
        for skill_dir in shared_skills.iterdir():
            if skill_dir.is_dir():
                target_skill = target_skills / skill_dir.name
                if target_skill.exists():
                    shutil.rmtree(target_skill)
                copytree(skill_dir, target_skill)
                installed["skills"].append(skill_dir.name)

    # Install shared workflows to .gobby/workflows/ (cross-CLI)
    shared_workflows = shared_dir / "workflows"
    if shared_workflows.exists():
        target_workflows = project_path / ".gobby" / "workflows"
        target_workflows.mkdir(parents=True, exist_ok=True)
        for workflow_file in shared_workflows.iterdir():
            if workflow_file.is_file():
                copy2(workflow_file, target_workflows / workflow_file.name)
                installed["workflows"].append(workflow_file.name)

    # Install shared plugins to ~/.gobby/plugins/ (global)
    shared_plugins = shared_dir / "plugins"
    if shared_plugins.exists():
        target_plugins = Path("~/.gobby/plugins").expanduser()
        target_plugins.mkdir(parents=True, exist_ok=True)
        for plugin_file in shared_plugins.iterdir():
            if plugin_file.is_file() and plugin_file.suffix == ".py":
                copy2(plugin_file, target_plugins / plugin_file.name)
                installed["plugins"].append(plugin_file.name)

    return installed


def install_cli_content(cli_name: str, target_path: Path) -> dict[str, list[str]]:
    """Install CLI-specific skills/workflows/commands (layered on top of shared).

    CLI-specific content can add to or override shared content.

    Args:
        cli_name: Name of the CLI (e.g., "claude", "gemini", "codex")
        target_path: Path to CLI config directory

    Returns:
        Dict with lists of installed items by type
    """
    cli_dir = get_install_dir() / cli_name
    installed: dict[str, list[str]] = {"skills": [], "workflows": [], "commands": []}

    # CLI-specific skills (can override shared)
    cli_skills = cli_dir / "skills"
    if cli_skills.exists():
        target_skills = target_path / "skills"
        target_skills.mkdir(parents=True, exist_ok=True)
        for skill_dir in cli_skills.iterdir():
            if skill_dir.is_dir():
                target_skill = target_skills / skill_dir.name
                if target_skill.exists():
                    shutil.rmtree(target_skill)
                copytree(skill_dir, target_skill)
                installed["skills"].append(skill_dir.name)

    # CLI-specific workflows
    cli_workflows = cli_dir / "workflows"
    if cli_workflows.exists():
        target_workflows = target_path / "workflows"
        target_workflows.mkdir(parents=True, exist_ok=True)
        for workflow_file in cli_workflows.iterdir():
            if workflow_file.is_file():
                copy2(workflow_file, target_workflows / workflow_file.name)
                installed["workflows"].append(workflow_file.name)

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
