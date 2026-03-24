"""Pre-approve workspace trust for CLI agents.

When spawning agents in clone or worktree directories, CLIs show interactive
trust prompts that block headless execution. This module pre-approves
directories so those prompts never appear.

Each CLI has a different trust mechanism:
- Claude Code: ~/.claude/projects/<encoded-path>/ (directory existence = trust)
- Cursor/Windsurf: Also use ~/.claude/projects/ (they embed Claude Code)
- Copilot CLI: ~/.copilot/config.json trusted_folders array
- Gemini CLI: ~/.gemini/trustedFolders.json + ~/.gemini/projects.json
- Codex CLI: sandboxed via --full-auto, no trust needed
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# CLIs that use Claude Code's ~/.claude/projects/ directory trust.
# Cursor and Windsurf embed Claude Code, so they inherit its trust mechanism.
_CLAUDE_COMPATIBLE_CLIS = frozenset({"claude", "cursor", "windsurf"})


def _encode_claude_project_path(directory: str) -> str:
    """Encode a directory path into Claude's project directory name.

    Claude Code replaces '/' and '.' with '-'.

    Example: /Users/josh/.gobby/clones/foo -> -Users-josh--gobby-clones-foo
    """
    return directory.replace("/", "-").replace(".", "-")


def pre_approve_directory(cli: str, directory: str) -> None:
    """Pre-approve a directory for the given CLI so trust prompts are skipped.

    Resolves symlinks (e.g. /tmp -> /private/tmp on macOS) to match what
    the CLI sees at runtime, and creates trust entries for both the original
    and resolved paths to cover all cases.

    Args:
        cli: CLI name (claude, gemini, codex, cursor, windsurf, copilot)
        directory: Absolute path to the workspace directory
    """
    # Resolve symlinks — on macOS /tmp -> /private/tmp, and CLIs resolve
    # the real path for their trust checks
    resolved = os.path.realpath(directory)
    paths = {directory, resolved}

    if cli in _CLAUDE_COMPATIBLE_CLIS:
        for path in paths:
            _pre_approve_claude(path)
    elif cli == "copilot":
        for path in paths:
            _pre_approve_copilot(path)
    elif cli == "gemini":
        for path in paths:
            _pre_approve_gemini(path)
    # Codex uses --full-auto sandbox; no trust pre-approval needed


def _pre_approve_claude(directory: str) -> None:
    """Pre-approve a directory for Claude Code (and Cursor/Windsurf).

    Creates the project directory under ~/.claude/projects/ if it doesn't
    exist. Claude treats directory existence as implicit trust.
    """
    claude_home = Path.home() / ".claude" / "projects"
    encoded = _encode_claude_project_path(directory)
    project_dir = claude_home / encoded

    if project_dir.exists():
        return

    try:
        project_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Pre-approved Claude workspace trust for {directory}")
    except OSError as e:
        logger.warning(f"Failed to pre-approve Claude trust for {directory}: {e}")


def _pre_approve_copilot(directory: str) -> None:
    """Pre-approve a directory for GitHub Copilot CLI.

    Adds the directory to the trusted_folders array in
    ~/.copilot/config.json (or $COPILOT_HOME/config.json).

    See: https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/configure-copilot-cli
    """
    copilot_home = Path(os.environ.get("COPILOT_HOME", Path.home() / ".copilot"))
    config_file = copilot_home / "config.json"

    try:
        if config_file.exists():
            data = json.loads(config_file.read_text())
            if not isinstance(data, dict):
                logger.warning(f"Copilot config.json root is not a dict, resetting: {config_file}")
                data = {}
        else:
            copilot_home.mkdir(parents=True, exist_ok=True)
            data = {}

        trusted: list[str] = data.get("trusted_folders", [])
        if not isinstance(trusted, list):
            logger.warning(
                f"Copilot config.json trusted_folders is not a list, resetting: {config_file}"
            )
            trusted = []

        if directory in trusted:
            return

        trusted.append(directory)
        data["trusted_folders"] = trusted

        config_file.write_text(json.dumps(data, indent=2) + "\n")
        logger.info(f"Pre-approved Copilot CLI trust for {directory}")
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to pre-approve Copilot trust for {directory}: {e}")


def _pre_approve_gemini(directory: str) -> None:
    """Pre-approve a directory for Gemini CLI.

    Writes to both:
    - ~/.gemini/projects.json — workspace registry
    - ~/.gemini/trustedFolders.json — actual folder trust (TRUST_PARENT)

    Without the trustedFolders entry, Gemini shows an interactive trust
    prompt that blocks headless agent execution.
    """
    gemini_home = Path.home() / ".gemini"
    gemini_home.mkdir(parents=True, exist_ok=True)

    # 1. Register in projects.json
    projects_file = gemini_home / "projects.json"
    try:
        if projects_file.exists():
            data = json.loads(projects_file.read_text())
            if not isinstance(data, dict):
                logger.warning(
                    f"Gemini projects.json root is not a dict, resetting: {projects_file}"
                )
                data = {"projects": {}}
        else:
            data = {"projects": {}}

        projects = data.get("projects") or {}
        if not isinstance(projects, dict):
            projects = {}

        if directory not in projects:
            project_name = Path(directory).name
            projects[directory] = project_name
            data["projects"] = projects
            projects_file.write_text(json.dumps(data, indent=2) + "\n")
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to update Gemini projects.json for {directory}: {e}")

    # 2. Pre-trust in trustedFolders.json (the actual trust gate)
    trust_file = gemini_home / "trustedFolders.json"
    try:
        if trust_file.exists():
            raw = json.loads(trust_file.read_text())
            if not isinstance(raw, dict):
                logger.warning(
                    f"Gemini trustedFolders.json root is not a dict, resetting: {trust_file}"
                )
            trusted: dict[str, str] = raw if isinstance(raw, dict) else {}
        else:
            trusted = {}

        if trusted.get(directory) == "TRUST_PARENT":
            return  # Already fully trusted

        trusted[directory] = "TRUST_PARENT"
        trust_file.write_text(json.dumps(trusted, indent=2) + "\n")
        logger.info(f"Pre-approved Gemini folder trust for {directory}")
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to update Gemini trustedFolders.json for {directory}: {e}")
