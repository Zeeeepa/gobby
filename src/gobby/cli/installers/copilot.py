"""
GitHub Copilot CLI installation for Gobby hooks.

This module handles installing and uninstalling Gobby hooks for Copilot CLI.
Hooks are written to .github/hooks/gobby-hooks.json using the version 1 format:
  { "version": 1, "hooks": { "<event>": [{ "type": "command", "bash": "...", "timeoutSec": N }] } }
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

from .shared import install_global_hooks, install_shared_content

logger = logging.getLogger(__name__)


def install_copilot(project_path: Path, mode: str = "global") -> dict[str, Any]:
    """Install Gobby integration for Copilot CLI (hooks, workflows).

    Args:
        project_path: Path to the project root
        mode: "global" is not supported for Copilot (no global hooks).
            "project" installs per-project (existing behavior).

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

    if mode == "global":
        result["success"] = True
        result["skipped"] = True
        result["skip_reason"] = (
            "Copilot CLI does not support global hooks. "
            "Use 'gobby install --copilot --project' to install per-project."
        )
        return result

    github_hooks_path = project_path / ".github" / "hooks"
    hooks_file = github_hooks_path / "gobby-hooks.json"
    hooks_dir = Path.home() / ".gobby" / "hooks"

    # Ensure .github/hooks/ directory exists
    github_hooks_path.mkdir(parents=True, exist_ok=True)

    # Get source files
    install_dir = get_install_dir()
    copilot_install_dir = install_dir / "copilot"

    source_hooks_template = copilot_install_dir / "hooks-template.json"

    if not source_hooks_template.exists():
        result["error"] = f"Missing source files: [{source_hooks_template}]"
        return result

    # Install shared hook files (always global)
    try:
        install_global_hooks()
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

    # Backup existing hooks file if it exists
    backup_file = None
    if hooks_file.exists():
        timestamp = int(time.time())
        backup_file = github_hooks_path / f"gobby-hooks.json.{timestamp}.backup"
        try:
            copy2(hooks_file, backup_file)
        except OSError as e:
            logger.error(f"Failed to create backup of gobby-hooks.json: {e}")
            result["error"] = f"Failed to create backup: {e}"
            return result

    # Load existing hooks or create empty (version 1 format)
    existing_hooks: dict[str, Any] = {"version": 1, "hooks": {}}
    if hooks_file.exists():
        try:
            with open(hooks_file) as f:
                existing_hooks = json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse gobby-hooks.json, starting fresh: {e}")
        except OSError as e:
            logger.error(f"Failed to read gobby-hooks.json: {e}")
            result["error"] = f"Failed to read gobby-hooks.json: {e}"
            return result

    # Ensure structure
    if "hooks" not in existing_hooks:
        existing_hooks["hooks"] = {}
    if "version" not in existing_hooks:
        existing_hooks["version"] = 1

    # Load Gobby hooks from template
    try:
        with open(source_hooks_template) as f:
            gobby_hooks_str = f.read()
    except OSError as e:
        logger.error(f"Failed to read hooks template: {e}")
        result["error"] = f"Failed to read hooks template: {e}"
        return result

    # Replace $HOOKS_DIR with absolute hooks directory path
    gobby_hooks_str = gobby_hooks_str.replace("$HOOKS_DIR", str(hooks_dir.resolve()))

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
        fd, temp_path = tempfile.mkstemp(dir=str(github_hooks_path), suffix=".tmp", prefix="hooks_")
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
        logger.error(f"Failed to write gobby-hooks.json: {e}")
        if backup_file and backup_file.exists():
            try:
                copy2(backup_file, hooks_file)
                logger.info("Restored gobby-hooks.json from backup after write failure")
            except OSError as restore_error:
                logger.error(f"Failed to restore from backup: {restore_error}")
        result["error"] = f"Failed to write gobby-hooks.json: {e}"
        return result

    result["success"] = True
    return result


def uninstall_copilot(project_path: Path) -> dict[str, Any]:
    """Uninstall Gobby integration from Copilot CLI.

    Checks both .github/hooks/ (new format) and .copilot/ (legacy) locations.

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

    # --- New location: .github/hooks/gobby-hooks.json ---
    github_hooks_file = project_path / ".github" / "hooks" / "gobby-hooks.json"
    if github_hooks_file.exists():
        try:
            with open(github_hooks_file) as f:
                hooks_config = json.load(f)

            if "hooks" in hooks_config:
                hooks_to_remove = []
                for hook_type, hook_list in hooks_config["hooks"].items():
                    if isinstance(hook_list, list):
                        for hook in hook_list:
                            bash_cmd = hook.get("bash", "")
                            if "hook_dispatcher.py" in bash_cmd:
                                hooks_to_remove.append(hook_type)
                                break

                for hook_type in hooks_to_remove:
                    # Only remove gobby entries, preserve user hooks
                    hook_list = hooks_config["hooks"][hook_type]
                    if isinstance(hook_list, list):
                        filtered = [
                            h for h in hook_list if "hook_dispatcher.py" not in h.get("bash", "")
                        ]
                        if filtered:
                            hooks_config["hooks"][hook_type] = filtered
                        else:
                            del hooks_config["hooks"][hook_type]
                    else:
                        del hooks_config["hooks"][hook_type]
                    result["hooks_removed"].append(hook_type)

                if hooks_config["hooks"]:
                    # Other hooks remain — write back
                    with open(github_hooks_file, "w") as f:
                        json.dump(hooks_config, f, indent=2)
                else:
                    # No hooks left — remove the file
                    github_hooks_file.unlink()
                    result["files_removed"].append(str(github_hooks_file))

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to update gobby-hooks.json: {e}")

    # --- Legacy location: .copilot/hooks.json ---
    copilot_path = project_path / ".copilot"
    legacy_hooks_file = copilot_path / "hooks.json"
    legacy_hooks_dir = copilot_path / "hooks"

    # Remove legacy hook dispatcher
    dispatcher = legacy_hooks_dir / "hook_dispatcher.py"
    if dispatcher.exists():
        try:
            dispatcher.unlink()
            result["files_removed"].append(str(dispatcher))
        except OSError as e:
            logger.warning(f"Failed to remove {dispatcher}: {e}")

    # Remove hooks from legacy hooks.json
    if legacy_hooks_file.exists():
        try:
            with open(legacy_hooks_file) as f:
                hooks_config = json.load(f)

            if "hooks" in hooks_config:
                hooks_to_remove = []
                for hook_type, hook_list in hooks_config["hooks"].items():
                    if isinstance(hook_list, list):
                        for hook in hook_list:
                            # Legacy format uses "command" field
                            cmd = hook.get("command", "")
                            if "hook_dispatcher.py" in cmd:
                                hooks_to_remove.append(hook_type)
                                break

                for hook_type in hooks_to_remove:
                    # Only remove gobby entries, preserve user hooks
                    hook_list = hooks_config["hooks"][hook_type]
                    if isinstance(hook_list, list):
                        filtered = [
                            h for h in hook_list if "hook_dispatcher.py" not in h.get("command", "")
                        ]
                        if filtered:
                            hooks_config["hooks"][hook_type] = filtered
                        else:
                            del hooks_config["hooks"][hook_type]
                    else:
                        del hooks_config["hooks"][hook_type]
                    result["hooks_removed"].append(hook_type)

                with open(legacy_hooks_file, "w") as f:
                    json.dump(hooks_config, f, indent=2)

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to update legacy hooks.json: {e}")

    result["success"] = True
    return result
