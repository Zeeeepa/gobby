"""Git utility functions for workflow actions.

Extracted from actions.py as part of strangler fig decomposition.
These are pure utility functions with no ActionContext dependency.
"""

import logging
import subprocess  # nosec B404 - subprocess needed for git commands

logger = logging.getLogger(__name__)


def get_git_status() -> str:
    """Get git status for current directory.

    Returns:
        Short git status output, or error message if not a git repo.
    """
    try:
        result = subprocess.run(  # nosec B603 B607 - hardcoded git command
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or "No changes"
    except Exception:
        return "Not a git repository or git not available"


def get_recent_git_commits(max_commits: int = 10) -> list[dict[str, str]]:
    """Get recent git commits with hash and message.

    Args:
        max_commits: Maximum number of commits to return

    Returns:
        List of dicts with 'hash' and 'message' keys
    """
    try:
        result = subprocess.run(  # nosec B603 B607 - hardcoded git command
            ["git", "log", f"-{max_commits}", "--format=%H|%s"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                hash_part, message = line.split("|", 1)
                commits.append({"hash": hash_part, "message": message})
        return commits
    except Exception:
        return []


def get_file_changes() -> str:
    """Get detailed file changes from git.

    Returns:
        Formatted string with modified/deleted and untracked files.
    """
    try:
        # Get changed files with status
        diff_result = subprocess.run(  # nosec B603 B607 - hardcoded git command
            ["git", "diff", "HEAD", "--name-status"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Get untracked files
        untracked_result = subprocess.run(  # nosec B603 B607 - hardcoded git command
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Combine results
        changes = []
        if diff_result.stdout.strip():
            changes.append("Modified/Deleted:")
            changes.append(diff_result.stdout.strip())

        if untracked_result.stdout.strip():
            changes.append("\nUntracked:")
            changes.append(untracked_result.stdout.strip())

        return "\n".join(changes) if changes else "No changes"

    except Exception:
        return "Unable to determine file changes"
