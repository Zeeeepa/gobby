"""
Cursor installation for Gobby hooks.

This module handles installing and uninstalling Gobby hooks for Cursor.
"""

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from shutil import copy2
from typing import Any

from gobby.cli.utils import get_install_dir

from .ide_config import configure_ide_terminal_title
from .shared import (
    _install_file,
    _is_dev_mode,
    install_shared_content,
)

logger = logging.getLogger(__name__)


def install_cursor(project_path: Path) -> dict[str, Any]:
    """Install Gobby integration for Cursor (hooks, workflows).

    Args:
        project_path: Path to the project root

    Returns:
        Dict with installation results including success status and installed items
    """
    hooks_installed: list[str] = []
    result: dict[str, Any] = {
        "success": False,
        "hooks_installed": hooks_installed,
        "workflows_installed": [],
        "error": None,
    }

    cursor_path = project_path / ".cursor"
    hooks_file = cursor_path / "hooks.json"

    # Ensure .cursor subdirectories exist
    cursor_path.mkdir(parents=True, exist_ok=True)
    hooks_dir = cursor_path / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Get source files
    install_dir = get_install_dir()
    cursor_install_dir = install_dir / "cursor"
    install_hooks_dir = cursor_install_dir / "hooks"

    # Hook files to copy
    hook_files = {
        "hook_dispatcher.py": True,  # Make executable
    }

    source_hooks_template = cursor_install_dir / "hooks-template.json"

    # Verify all source files exist
    missing_files = []
    for filename in hook_files.keys():
        source_file = install_hooks_dir / filename
        if not source_file.exists():
            missing_files.append(str(source_file))

    if not source_hooks_template.exists():
        missing_files.append(str(source_hooks_template))

    if missing_files:
        result["error"] = f"Missing source files: {missing_files}"
        return result

    # Install hook files (symlink in dev mode, copy otherwise)
    try:
        dev_mode = _is_dev_mode(project_path)
        for filename, make_executable in hook_files.items():
            source_file = install_hooks_dir / filename
            target_file = hooks_dir / filename
            _install_file(source_file, target_file, dev_mode=dev_mode, executable=make_executable)
    except OSError as e:
        logger.error(f"Failed to install hook files: {e}")
        result["error"] = f"Failed to install hook files: {e}"
        return result

    # Install shared content (workflows) to .gobby/
    try:
        gobby_path = project_path / ".gobby"
        shared = install_shared_content(gobby_path, project_path)
        result["workflows_installed"] = shared.get("workflows", [])
        result["agents_installed"] = shared.get("agents", [])
        result["plugins_installed"] = shared.get("plugins", [])
        result["prompts_installed"] = shared.get("prompts", [])
        result["docs_installed"] = shared.get("docs", [])
    except Exception as e:
        logger.warning(f"Failed to install shared content: {e}")
        # Non-fatal - continue with hooks installation

    # Backup existing hooks.json if it exists
    backup_file = None
    if hooks_file.exists():
        timestamp = int(time.time())
        backup_file = cursor_path / f"hooks.json.{timestamp}.backup"
        try:
            copy2(hooks_file, backup_file)
        except OSError as e:
            logger.error(f"Failed to create backup of hooks.json: {e}")
            result["error"] = f"Failed to create backup: {e}"
            return result

    # Load existing hooks or create empty
    existing_hooks: dict[str, Any] = {"version": 1, "hooks": {}}
    if hooks_file.exists():
        try:
            with open(hooks_file) as f:
                existing_hooks = json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse hooks.json, starting fresh: {e}")
        except OSError as e:
            logger.error(f"Failed to read hooks.json: {e}")
            result["error"] = f"Failed to read hooks.json: {e}"
            return result

    # Ensure structure
    if "version" not in existing_hooks:
        existing_hooks["version"] = 1
    if "hooks" not in existing_hooks:
        existing_hooks["hooks"] = {}

    # Load Gobby hooks from template
    try:
        with open(source_hooks_template) as f:
            gobby_hooks_str = f.read()
    except OSError as e:
        logger.error(f"Failed to read hooks template: {e}")
        result["error"] = f"Failed to read hooks template: {e}"
        return result

    # Replace $PROJECT_PATH with absolute project path
    abs_project_path = str(project_path.resolve())
    gobby_hooks_str = gobby_hooks_str.replace("$PROJECT_PATH", abs_project_path)

    try:
        gobby_hooks = json.loads(gobby_hooks_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse hooks template: {e}")
        result["error"] = f"Failed to parse hooks template: {e}"
        return result

    # Merge Gobby hooks
    new_hooks = gobby_hooks.get("hooks", {})
    for hook_type, hook_config in new_hooks.items():
        existing_hooks["hooks"][hook_type] = hook_config
        hooks_installed.append(hook_type)

    # Write merged hooks back using atomic write
    try:
        fd, temp_path = tempfile.mkstemp(dir=str(cursor_path), suffix=".tmp", prefix="hooks_")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(existing_hooks, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            # Atomic replace
            os.replace(temp_path, hooks_file)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
    except OSError as e:
        logger.error(f"Failed to write hooks.json: {e}")
        if backup_file and backup_file.exists():
            try:
                copy2(backup_file, hooks_file)
                logger.info("Restored hooks.json from backup after write failure")
            except OSError as restore_error:
                logger.error(f"Failed to restore from backup: {restore_error}")
        result["error"] = f"Failed to write hooks.json: {e}"
        return result

    # Configure terminal tab title so tmux set-titles propagates to IDE
    terminal_result = configure_ide_terminal_title("Cursor")
    result["terminal_configured"] = terminal_result.get("added", False)
    if not terminal_result.get("success", True):
        logger.warning("Terminal title config failed for Cursor: %s", terminal_result.get("error"))

    result["success"] = True
    return result


def uninstall_cursor(project_path: Path) -> dict[str, Any]:
    """Uninstall Gobby integration from Cursor.

    Args:
        project_path: Path to the project root

    Returns:
        Dict with uninstallation results
    """
    result: dict[str, Any] = {
        "success": False,
        "hooks_removed": [],
        "files_removed": [],
        "error": None,
    }

    cursor_path = project_path / ".cursor"
    hooks_file = cursor_path / "hooks.json"
    hooks_dir = cursor_path / "hooks"

    # Remove hook dispatcher
    dispatcher = hooks_dir / "hook_dispatcher.py"
    if dispatcher.exists():
        try:
            dispatcher.unlink()
            result["files_removed"].append(str(dispatcher))
        except OSError as e:
            logger.warning(f"Failed to remove {dispatcher}: {e}")

    # Remove hooks from hooks.json
    if hooks_file.exists():
        try:
            with open(hooks_file) as f:
                hooks_config = json.load(f)

            # Remove all Gobby hooks (those that reference hook_dispatcher.py)
            if "hooks" in hooks_config:
                hooks_to_remove = []
                for hook_type, hook_list in hooks_config["hooks"].items():
                    if isinstance(hook_list, list):
                        for hook in hook_list:
                            cmd = hook.get("command", "")
                            if "hook_dispatcher.py" in cmd:
                                hooks_to_remove.append(hook_type)
                                break

                for hook_type in hooks_to_remove:
                    del hooks_config["hooks"][hook_type]
                    result["hooks_removed"].append(hook_type)

                # Write back
                with open(hooks_file, "w") as f:
                    json.dump(hooks_config, f, indent=2)

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to update hooks.json: {e}")

    result["success"] = True
    return result
