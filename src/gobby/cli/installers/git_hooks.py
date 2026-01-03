"""
Git hooks installation for Gobby task sync.

This module handles installing git hooks for automatic task
synchronization on commit, merge, and checkout operations.
"""

import logging
import stat
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def install_git_hooks(project_path: Path) -> dict[str, Any]:
    """Install Gobby git hooks to the current repository.

    Uses inline scripts for task auto-sync on commit/merge/checkout.

    Args:
        project_path: Path to the project root

    Returns:
        Dict with installation results including success status and installed hooks
    """
    git_dir = project_path / ".git"
    if not git_dir.exists():
        return {"success": False, "error": "Not a git repository (no .git directory found)"}

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Inline hook scripts for task sync
    hook_scripts = {
        "pre-commit": """#!/bin/sh
# Gobby task sync hook - export tasks before commit
# Installed by: gobby install --hooks

if command -v gobby >/dev/null 2>&1; then
    gobby tasks sync --export --quiet 2>/dev/null || true
fi
""",
        "post-merge": """#!/bin/sh
# Gobby task sync hook - import tasks after merge/pull
# Installed by: gobby install --hooks

if command -v gobby >/dev/null 2>&1; then
    gobby tasks sync --import --quiet 2>/dev/null || true
fi
""",
        "post-checkout": """#!/bin/sh
# Gobby task sync hook - import tasks on branch switch
# Installed by: gobby install --hooks

# $3 is 1 if this was a branch checkout (vs file checkout)
if [ "$3" = "1" ]; then
    if command -v gobby >/dev/null 2>&1; then
        gobby tasks sync --import --quiet 2>/dev/null || true
    fi
fi
""",
    }

    installed = []
    skipped = []

    for hook_name, script in hook_scripts.items():
        hook_path = hooks_dir / hook_name

        if hook_path.exists():
            content = hook_path.read_text()
            if "gobby" in content.lower():
                skipped.append(f"{hook_name} (already installed)")
                continue
            else:
                skipped.append(f"{hook_name} (existing hook)")
                continue

        hook_path.write_text(script)
        hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        installed.append(hook_name)

    return {"success": True, "installed": installed, "skipped": skipped}
