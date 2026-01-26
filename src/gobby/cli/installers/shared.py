"""
Shared content installation for Gobby hooks.

This module handles installing shared workflows and plugins
that are used across all CLI integrations (Claude, Gemini, Codex, etc.).
"""

import json
import logging
import os
import shutil
import time
from pathlib import Path
from shutil import copy2, copytree
from typing import Any

from gobby.cli.utils import get_install_dir

logger = logging.getLogger(__name__)


def install_shared_content(cli_path: Path, project_path: Path) -> dict[str, list[str]]:
    """Install shared content from src/install/shared/.

    Workflows are cross-CLI and go to {project_path}/.gobby/workflows/.
    Plugins are project-scoped and go to {project_path}/.gobby/plugins/.
    Prompts are project-scoped and go to {project_path}/.gobby/prompts/.
    Docs are project-local and go to {project_path}/.gobby/docs/.

    Args:
        cli_path: Path to CLI config directory (e.g., .claude, .gemini)
        project_path: Path to project root

    Returns:
        Dict with lists of installed items by type
    """
    shared_dir = get_install_dir() / "shared"
    installed: dict[str, list[str]] = {"workflows": [], "plugins": [], "prompts": [], "docs": []}

    # Install shared workflows to .gobby/workflows/ (cross-CLI)
    shared_workflows = shared_dir / "workflows"
    if shared_workflows.exists():
        target_workflows = project_path / ".gobby" / "workflows"
        target_workflows.mkdir(parents=True, exist_ok=True)
        for item in shared_workflows.iterdir():
            if item.is_file():
                copy2(item, target_workflows / item.name)
                installed["workflows"].append(item.name)
            elif item.is_dir():
                # Copy subdirectories (e.g., lifecycle/)
                target_subdir = target_workflows / item.name
                if target_subdir.exists():
                    shutil.rmtree(target_subdir)
                copytree(item, target_subdir)
                installed["workflows"].append(f"{item.name}/")

    # Install shared plugins to .gobby/plugins/ (project-scoped)
    shared_plugins = shared_dir / "plugins"
    if shared_plugins.exists():
        target_plugins = project_path / ".gobby" / "plugins"
        target_plugins.mkdir(parents=True, exist_ok=True)
        for plugin_file in shared_plugins.iterdir():
            if plugin_file.is_file() and plugin_file.suffix == ".py":
                copy2(plugin_file, target_plugins / plugin_file.name)
                installed["plugins"].append(plugin_file.name)

    # Install shared prompts to .gobby/prompts/ (project-scoped)
    shared_prompts = shared_dir / "prompts"
    if shared_prompts.exists():
        target_prompts = project_path / ".gobby" / "prompts"
        target_prompts.mkdir(parents=True, exist_ok=True)
        for item in shared_prompts.iterdir():
            if item.is_file():
                copy2(item, target_prompts / item.name)
                installed["prompts"].append(item.name)
            elif item.is_dir():
                # Copy subdirectories (e.g., expansion/, validation/)
                target_subdir = target_prompts / item.name
                if target_subdir.exists():
                    shutil.rmtree(target_subdir)
                copytree(item, target_subdir)
                installed["prompts"].append(f"{item.name}/")

    # Install shared docs to .gobby/docs/ (project-local)
    shared_docs = shared_dir / "docs"
    if shared_docs.exists():
        target_docs = project_path / ".gobby" / "docs"
        target_docs.mkdir(parents=True, exist_ok=True)
        for doc_file in shared_docs.iterdir():
            if doc_file.is_file():
                copy2(doc_file, target_docs / doc_file.name)
                installed["docs"].append(doc_file.name)

    return installed


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
    """Install router skills (gobby, g) as flattened Claude commands.

    Claude Code uses .claude/commands/name.md format for slash commands.
    This function copies the gobby router skills from shared/skills/ to
    commands/ as flattened .md files.

    Args:
        target_commands_dir: Path to commands directory (e.g., .claude/commands)

    Returns:
        List of installed command names
    """
    shared_skills_dir = get_install_dir() / "shared" / "skills"
    installed: list[str] = []

    # Router skills to install as commands
    router_skills = ["gobby", "g"]

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
    """Install router skills (gobby, g) as Gemini skills (directory structure).

    Gemini CLI uses .gemini/skills/name/SKILL.md format for skills.
    This function copies the gobby router skills from shared/skills/ to
    the target skills directory preserving the directory structure.

    Args:
        target_skills_dir: Path to skills directory (e.g., .gemini/skills)

    Returns:
        List of installed skill names
    """
    shared_skills_dir = get_install_dir() / "shared" / "skills"
    installed: list[str] = []

    # Router skills to install
    router_skills = ["gobby", "g"]

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


def configure_project_mcp_server(project_path: Path, server_name: str = "gobby") -> dict[str, Any]:
    """Add Gobby MCP server to project-specific config in ~/.claude.json.

    Claude Code stores project-specific MCP servers in:
    {
      "projects": {
        "/path/to/project": {
          "mcpServers": { "gobby": { ... } }
        }
      }
    }

    Args:
        project_path: Path to the project root
        server_name: Name for the MCP server entry (default: "gobby")

    Returns:
        Dict with 'success', 'added', 'already_configured', 'backup_path', and 'error' keys
    """
    result: dict[str, Any] = {
        "success": False,
        "added": False,
        "already_configured": False,
        "backup_path": None,
        "error": None,
    }

    settings_path = Path.home() / ".claude.json"
    abs_project_path = str(project_path.resolve())

    # Load existing settings or create empty
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

    # Ensure projects section exists
    if "projects" not in existing_settings:
        existing_settings["projects"] = {}

    # Ensure project entry exists
    if abs_project_path not in existing_settings["projects"]:
        existing_settings["projects"][abs_project_path] = {}

    project_settings = existing_settings["projects"][abs_project_path]

    # Ensure mcpServers section exists in project
    if "mcpServers" not in project_settings:
        project_settings["mcpServers"] = {}

    # Check if already configured
    if server_name in project_settings["mcpServers"]:
        result["success"] = True
        result["already_configured"] = True
        return result

    # Create backup if file exists
    if settings_path.exists():
        timestamp = int(time.time())
        backup_path = settings_path.parent / f".claude.json.{timestamp}.backup"
        try:
            copy2(settings_path, backup_path)
            result["backup_path"] = str(backup_path)
        except OSError as e:
            result["error"] = f"Failed to create backup: {e}"
            return result

    # Add gobby MCP server config
    project_settings["mcpServers"][server_name] = {
        "type": "stdio",
        "command": "uv",
        "args": ["run", "gobby", "mcp-server"],
    }

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


def remove_project_mcp_server(project_path: Path, server_name: str = "gobby") -> dict[str, Any]:
    """Remove Gobby MCP server from project-specific config in ~/.claude.json.

    Args:
        project_path: Path to the project root
        server_name: Name of the MCP server entry to remove

    Returns:
        Dict with 'success', 'removed', 'backup_path', and 'error' keys
    """
    result: dict[str, Any] = {
        "success": False,
        "removed": False,
        "backup_path": None,
        "error": None,
    }

    settings_path = Path.home() / ".claude.json"
    abs_project_path = str(project_path.resolve())

    if not settings_path.exists():
        result["success"] = True
        return result

    try:
        with open(settings_path) as f:
            settings = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        result["error"] = f"Failed to read {settings_path}: {e}"
        return result

    # Check if project and server exist
    projects = settings.get("projects", {})
    project_settings = projects.get(abs_project_path, {})
    mcp_servers = project_settings.get("mcpServers", {})

    if server_name not in mcp_servers:
        result["success"] = True
        return result

    # Create backup
    timestamp = int(time.time())
    backup_path = settings_path.parent / f".claude.json.{timestamp}.backup"
    try:
        copy2(settings_path, backup_path)
        result["backup_path"] = str(backup_path)
    except OSError as e:
        result["error"] = f"Failed to create backup: {e}"
        return result

    # Remove the server
    del mcp_servers[server_name]

    # Write updated settings
    try:
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)
    except OSError as e:
        result["error"] = f"Failed to write {settings_path}: {e}"
        return result

    result["success"] = True
    result["removed"] = True
    return result


def configure_mcp_server_json(settings_path: Path, server_name: str = "gobby") -> dict[str, Any]:
    """Add Gobby MCP server to a JSON settings file (Claude, Gemini, Antigravity).

    Merges the gobby MCP server config into the existing mcpServers section,
    preserving all other servers. Creates a timestamped backup before modifying.

    Args:
        settings_path: Path to the settings.json file (e.g., ~/.claude/settings.json)
        server_name: Name for the MCP server entry (default: "gobby")

    Returns:
        Dict with 'success', 'added', 'backup_path', and 'error' keys
    """
    result: dict[str, Any] = {
        "success": False,
        "added": False,
        "already_configured": False,
        "backup_path": None,
        "error": None,
    }

    # Ensure parent directory exists
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing settings or create empty
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
    if "mcpServers" in existing_settings and server_name in existing_settings["mcpServers"]:
        result["success"] = True
        result["already_configured"] = True
        return result

    # Create backup if file exists
    if settings_path.exists():
        timestamp = int(time.time())
        backup_path = settings_path.parent / f"{settings_path.name}.{timestamp}.backup"
        try:
            copy2(settings_path, backup_path)
            result["backup_path"] = str(backup_path)
        except OSError as e:
            result["error"] = f"Failed to create backup: {e}"
            return result

    # Ensure mcpServers section exists
    if "mcpServers" not in existing_settings:
        existing_settings["mcpServers"] = {}

    # Add gobby MCP server config
    # Use 'uv run gobby' since most users won't have gobby installed globally
    existing_settings["mcpServers"][server_name] = {
        "command": "uv",
        "args": ["run", "gobby", "mcp-server"],
    }

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


def remove_mcp_server_json(settings_path: Path, server_name: str = "gobby") -> dict[str, Any]:
    """Remove Gobby MCP server from a JSON settings file.

    Args:
        settings_path: Path to the settings.json file
        server_name: Name of the MCP server entry to remove

    Returns:
        Dict with 'success', 'removed', 'backup_path', and 'error' keys
    """
    result: dict[str, Any] = {
        "success": False,
        "removed": False,
        "backup_path": None,
        "error": None,
    }

    if not settings_path.exists():
        result["success"] = True
        return result

    try:
        with open(settings_path) as f:
            settings = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        result["error"] = f"Failed to read {settings_path}: {e}"
        return result

    # Check if server exists
    if "mcpServers" not in settings or server_name not in settings["mcpServers"]:
        result["success"] = True
        return result

    # Create backup
    timestamp = int(time.time())
    backup_path = settings_path.parent / f"{settings_path.name}.{timestamp}.backup"
    try:
        copy2(settings_path, backup_path)
        result["backup_path"] = str(backup_path)
    except OSError as e:
        result["error"] = f"Failed to create backup: {e}"
        return result

    # Remove the server
    del settings["mcpServers"][server_name]

    # Clean up empty mcpServers section
    if not settings["mcpServers"]:
        del settings["mcpServers"]

    # Write updated settings
    try:
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)
    except OSError as e:
        result["error"] = f"Failed to write {settings_path}: {e}"
        return result

    result["success"] = True
    result["removed"] = True
    return result


def configure_mcp_server_toml(config_path: Path, server_name: str = "gobby") -> dict[str, Any]:
    """Add Gobby MCP server to a TOML config file (Codex).

    Adds [mcp_servers.gobby] section with command and args.
    Creates a timestamped backup before modifying.

    Args:
        config_path: Path to the config.toml file (e.g., ~/.codex/config.toml)
        server_name: Name for the MCP server entry (default: "gobby")

    Returns:
        Dict with 'success', 'added', 'backup_path', and 'error' keys
    """
    import re

    result: dict[str, Any] = {
        "success": False,
        "added": False,
        "already_configured": False,
        "backup_path": None,
        "error": None,
    }

    # Ensure parent directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing config
    existing = ""
    if config_path.exists():
        try:
            existing = config_path.read_text(encoding="utf-8")
        except OSError as e:
            result["error"] = f"Failed to read {config_path}: {e}"
            return result

    # Check if already configured
    pattern = re.compile(rf"^\s*\[mcp_servers\.{re.escape(server_name)}\]", re.MULTILINE)
    if pattern.search(existing):
        result["success"] = True
        result["already_configured"] = True
        return result

    # Create backup if file exists
    if config_path.exists():
        timestamp = int(time.time())
        backup_path = config_path.with_suffix(f".toml.{timestamp}.backup")
        try:
            backup_path.write_text(existing, encoding="utf-8")
            result["backup_path"] = str(backup_path)
        except OSError as e:
            result["error"] = f"Failed to create backup: {e}"
            return result

    # Add MCP server config
    # Use 'uv run gobby' since most users won't have gobby installed globally
    mcp_config = f"""
[mcp_servers.{server_name}]
command = "uv"
args = ["run", "gobby", "mcp-server"]
"""
    updated = (existing.rstrip() + "\n" if existing.strip() else "") + mcp_config

    try:
        config_path.write_text(updated, encoding="utf-8")
    except OSError as e:
        result["error"] = f"Failed to write {config_path}: {e}"
        return result

    result["success"] = True
    result["added"] = True
    return result


def remove_mcp_server_toml(config_path: Path, server_name: str = "gobby") -> dict[str, Any]:
    """Remove Gobby MCP server from a TOML config file.

    Uses tomllib (stdlib) for reading and tomli_w for writing to properly
    handle TOML syntax including multi-line strings.

    Args:
        config_path: Path to the config.toml file
        server_name: Name of the MCP server entry to remove

    Returns:
        Dict with 'success', 'removed', 'backup_path', and 'error' keys
    """
    import tomllib

    import tomli_w

    result: dict[str, Any] = {
        "success": False,
        "removed": False,
        "backup_path": None,
        "error": None,
    }

    if not config_path.exists():
        result["success"] = True
        return result

    # Read existing TOML file
    try:
        existing_text = config_path.read_text(encoding="utf-8")
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        result["error"] = f"Failed to parse TOML {config_path}: {e}"
        return result
    except OSError as e:
        result["error"] = f"Failed to read {config_path}: {e}"
        return result

    # Check if server exists in mcp_servers section
    mcp_servers = config.get("mcp_servers", {})
    if server_name not in mcp_servers:
        result["success"] = True
        return result

    # Create backup
    timestamp = int(time.time())
    backup_path = config_path.with_suffix(f".toml.{timestamp}.backup")
    try:
        backup_path.write_text(existing_text, encoding="utf-8")
        result["backup_path"] = str(backup_path)
    except OSError as e:
        result["error"] = f"Failed to create backup: {e}"
        return result

    # Remove the server from config
    del mcp_servers[server_name]

    # Clean up empty mcp_servers section
    if not mcp_servers:
        del config["mcp_servers"]
    else:
        config["mcp_servers"] = mcp_servers

    # Write updated config using tomli_w
    try:
        with open(config_path, "wb") as f:
            tomli_w.dump(config, f, multiline_strings=True)
    except OSError as e:
        result["error"] = f"Failed to write {config_path}: {e}"
        return result

    result["success"] = True
    result["removed"] = True
    return result


# Default external MCP servers to install
DEFAULT_MCP_SERVERS: list[dict[str, Any]] = [
    {
        "name": "github",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"},  # nosec B105 - env var placeholder
        "description": "GitHub API integration for issues, PRs, repos, and code search",
    },
    {
        "name": "linear",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "mcp-linear"],
        "env": {"LINEAR_API_KEY": "${LINEAR_API_KEY}"},
        "description": "Linear issue tracking integration",
    },
    {
        "name": "context7",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp"],
        # API key args added dynamically if CONTEXT7_API_KEY is set
        "optional_env_args": {"CONTEXT7_API_KEY": ["--api-key", "${CONTEXT7_API_KEY}"]},
        "description": "Context7 library documentation lookup (set CONTEXT7_API_KEY for private repos)",
    },
]


def install_default_mcp_servers() -> dict[str, Any]:
    """Install default external MCP servers to ~/.gobby/.mcp.json.

    Adds GitHub, Linear, and context7 MCP servers if not already configured.
    These servers pull API keys from environment variables.

    Returns:
        Dict with 'success', 'servers_added', 'servers_skipped', and 'error' keys
    """
    result: dict[str, Any] = {
        "success": False,
        "servers_added": [],
        "servers_skipped": [],
        "error": None,
    }

    mcp_config_path = Path("~/.gobby/.mcp.json").expanduser()

    # Ensure parent directory exists
    mcp_config_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing config or create empty
    existing_config: dict[str, Any] = {"servers": []}
    if mcp_config_path.exists():
        try:
            with open(mcp_config_path) as f:
                content = f.read()
                if content.strip():
                    existing_config = json.loads(content)
                    if "servers" not in existing_config:
                        existing_config["servers"] = []
        except (json.JSONDecodeError, OSError) as e:
            result["error"] = f"Failed to read MCP config: {e}"
            return result

    # Get existing server names
    existing_names = {s.get("name") for s in existing_config["servers"]}

    # Add default servers if not already present
    for server in DEFAULT_MCP_SERVERS:
        if server["name"] in existing_names:
            result["servers_skipped"].append(server["name"])
        else:
            # Build args list, adding optional env-dependent args
            args = list(server.get("args") or [])
            optional_env_args = server.get("optional_env_args", {})
            for env_var, extra_args in optional_env_args.items():
                if os.environ.get(env_var):
                    args.extend(extra_args)

            existing_config["servers"].append(
                {
                    "name": server["name"],
                    "enabled": True,
                    "transport": server["transport"],
                    "command": server.get("command"),
                    "args": args if args else None,
                    "env": server.get("env"),
                    "description": server.get("description"),
                }
            )
            result["servers_added"].append(server["name"])

    # Write updated config if any servers were added
    if result["servers_added"]:
        try:
            with open(mcp_config_path, "w") as f:
                json.dump(existing_config, f, indent=2)
            # Set restrictive permissions
            mcp_config_path.chmod(0o600)
        except OSError as e:
            result["error"] = f"Failed to write MCP config: {e}"
            return result

    result["success"] = True
    return result
