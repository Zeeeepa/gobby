"""
Git hooks installation for Gobby task sync.

This module handles installing git hooks for automatic task
synchronization on commit, merge, and checkout operations.

Features:
- Backs up existing hooks before modification
- Chains with existing hooks (doesn't overwrite)
- Integrates with pre-commit framework when available
- Supports clean uninstallation
"""

import logging
import shutil
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Markers for identifying Gobby hook sections
GOBBY_HOOK_START = "# >>> GOBBY HOOK START >>>"
GOBBY_HOOK_END = "# <<< GOBBY HOOK END <<<"

# Hook script templates - these get wrapped with markers
HOOK_TEMPLATES = {
    "pre-commit": """
# Gobby task sync - export tasks before commit
if command -v gobby >/dev/null 2>&1; then
    gobby tasks sync --export --quiet 2>/dev/null || true
fi
""",
    "post-merge": """
# Gobby task sync - import tasks after merge/pull
if command -v gobby >/dev/null 2>&1; then
    gobby tasks sync --import --quiet 2>/dev/null || true
fi
""",
    "post-checkout": """
# Gobby task sync - import tasks on branch switch
# $3 is 1 if this was a branch checkout (vs file checkout)
if [ "$3" = "1" ]; then
    if command -v gobby >/dev/null 2>&1; then
        gobby tasks sync --import --quiet 2>/dev/null || true
    fi
fi
""",
}


def _backup_hook(hook_path: Path, hooks_dir: Path) -> str | None:
    """Create a timestamped backup of an existing hook.

    Args:
        hook_path: Path to the hook file
        hooks_dir: Directory containing hooks

    Returns:
        Backup path if created, None otherwise
    """
    if not hook_path.exists():
        return None

    timestamp = int(time.time())
    backup_path = hooks_dir / f"{hook_path.name}.{timestamp}.backup"

    try:
        shutil.copy2(hook_path, backup_path)
        logger.debug(f"Backed up {hook_path.name} to {backup_path.name}")
        return str(backup_path)
    except OSError as e:
        logger.warning(f"Failed to backup {hook_path.name}: {e}")
        return None


def _has_gobby_hook(content: str) -> bool:
    """Check if content already contains Gobby hook markers."""
    return GOBBY_HOOK_START in content or "gobby" in content.lower()


def _wrap_gobby_section(script: str) -> str:
    """Wrap a script section with Gobby markers."""
    return f"{GOBBY_HOOK_START}\n{script.strip()}\n{GOBBY_HOOK_END}\n"


def _remove_gobby_section(content: str) -> str:
    """Remove Gobby hook section from content."""
    lines = content.split("\n")
    result = []
    in_gobby_section = False

    for line in lines:
        if GOBBY_HOOK_START in line:
            in_gobby_section = True
            continue
        if GOBBY_HOOK_END in line:
            in_gobby_section = False
            continue
        if not in_gobby_section:
            result.append(line)

    # Clean up multiple blank lines
    cleaned = "\n".join(result)
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")

    return cleaned.strip() + "\n" if cleaned.strip() else ""


def _check_precommit_installed() -> bool:
    """Check if pre-commit framework is installed and configured."""
    return shutil.which("pre-commit") is not None


def _has_precommit_config(project_path: Path) -> bool:
    """Check if project has a .pre-commit-config.yaml."""
    return (project_path / ".pre-commit-config.yaml").exists()


def install_git_hooks(
    project_path: Path,
    *,
    force: bool = False,
    setup_precommit: bool = True,
) -> dict[str, Any]:
    """Install Gobby git hooks to the current repository.

    Safely installs hooks by:
    1. Backing up existing hooks
    2. Chaining with existing hooks (appending Gobby section)
    3. Optionally setting up pre-commit framework

    Args:
        project_path: Path to the project root
        force: If True, reinstall even if already present
        setup_precommit: If True, run `pre-commit install` if config exists

    Returns:
        Dict with installation results including:
        - success: bool
        - installed: list of installed hook names
        - skipped: list of skipped hooks with reasons
        - backups: list of backup file paths
        - precommit_installed: bool if pre-commit was set up
        - error: error message if failed
    """
    result: dict[str, Any] = {
        "success": False,
        "installed": [],
        "skipped": [],
        "backups": [],
        "precommit_installed": False,
        "error": None,
    }

    git_dir = project_path / ".git"
    if not git_dir.exists():
        result["error"] = "Not a git repository (no .git directory found)"
        return result

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Install each hook
    for hook_name, gobby_script in HOOK_TEMPLATES.items():
        hook_path = hooks_dir / hook_name
        gobby_section = _wrap_gobby_section(gobby_script)

        if hook_path.exists():
            content = hook_path.read_text()

            # Check if already installed
            if _has_gobby_hook(content) and not force:
                result["skipped"].append(f"{hook_name} (already installed)")
                continue

            # Backup existing hook
            backup_path = _backup_hook(hook_path, hooks_dir)
            if backup_path:
                result["backups"].append(backup_path)

            # Remove old Gobby section if force reinstalling
            if force and GOBBY_HOOK_START in content:
                content = _remove_gobby_section(content)

            # Append Gobby section to existing hook
            if content.strip():
                # Ensure shebang is preserved at top
                if content.startswith("#!"):
                    lines = content.split("\n", 1)
                    shebang = lines[0]
                    rest = lines[1] if len(lines) > 1 else ""
                    new_content = f"{shebang}\n\n{gobby_section}\n{rest.strip()}\n"
                else:
                    new_content = f"#!/bin/sh\n\n{gobby_section}\n{content}"
            else:
                new_content = f"#!/bin/sh\n\n{gobby_section}"

            hook_path.write_text(new_content)
            logger.info(f"Appended Gobby hook to existing {hook_name}")

        else:
            # Create new hook
            new_content = f"#!/bin/sh\n\n{gobby_section}"
            hook_path.write_text(new_content)
            logger.info(f"Created new {hook_name} hook")

        # Ensure executable
        hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        result["installed"].append(hook_name)

    # Optionally set up pre-commit framework
    if setup_precommit and _has_precommit_config(project_path) and _check_precommit_installed():
        try:
            subprocess.run(
                ["pre-commit", "install"],
                cwd=project_path,
                capture_output=True,
                timeout=30,
            )
            result["precommit_installed"] = True
            logger.info("Installed pre-commit hooks")
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.warning(f"Failed to install pre-commit hooks: {e}")

    result["success"] = True
    return result


def uninstall_git_hooks(project_path: Path) -> dict[str, Any]:
    """Remove Gobby sections from git hooks.

    Safely removes only Gobby-added sections, preserving other hook functionality.

    Args:
        project_path: Path to the project root

    Returns:
        Dict with uninstallation results
    """
    result: dict[str, Any] = {
        "success": False,
        "removed": [],
        "not_found": [],
        "error": None,
    }

    git_dir = project_path / ".git"
    if not git_dir.exists():
        result["error"] = "Not a git repository"
        return result

    hooks_dir = git_dir / "hooks"
    if not hooks_dir.exists():
        result["success"] = True
        return result

    for hook_name in HOOK_TEMPLATES:
        hook_path = hooks_dir / hook_name

        if not hook_path.exists():
            result["not_found"].append(hook_name)
            continue

        content = hook_path.read_text()

        if not _has_gobby_hook(content):
            result["not_found"].append(hook_name)
            continue

        # Remove Gobby section
        new_content = _remove_gobby_section(content)

        if new_content.strip():
            # Hook still has content, keep it
            hook_path.write_text(new_content)
        else:
            # Hook is now empty, remove it
            hook_path.unlink()

        result["removed"].append(hook_name)
        logger.info(f"Removed Gobby section from {hook_name}")

    result["success"] = True
    return result
