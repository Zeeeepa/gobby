"""Commit linking and diff functionality for Task System V2.

Provides utilities for linking commits to tasks and computing diffs.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from gobby.utils.git import run_git_command

if TYPE_CHECKING:
    from gobby.storage.tasks import LocalTaskManager


@dataclass
class TaskDiffResult:
    """Result of computing a task's diff.

    Attributes:
        diff: Combined diff content from all linked commits
        commits: List of commit SHAs included in the diff
        has_uncommitted_changes: Whether uncommitted changes were included
        file_count: Number of files modified in the diff
    """

    diff: str
    commits: list[str] = field(default_factory=list)
    has_uncommitted_changes: bool = False
    file_count: int = 0


def get_task_diff(
    task_id: str,
    task_manager: "LocalTaskManager",
    include_uncommitted: bool = False,
    cwd: str | Path | None = None,
) -> TaskDiffResult:
    """Get the combined diff for all commits linked to a task.

    Args:
        task_id: The task ID to get diff for.
        task_manager: LocalTaskManager instance to fetch task data.
        include_uncommitted: If True, include uncommitted changes in diff.
        cwd: Working directory for git commands. Defaults to current directory.

    Returns:
        TaskDiffResult with combined diff and metadata.

    Raises:
        ValueError: If task not found.
    """
    # Get the task (raises ValueError if not found)
    task = task_manager.get_task(task_id)

    # Handle no commits
    commits = task.commits or []
    if not commits and not include_uncommitted:
        return TaskDiffResult(diff="", commits=[], has_uncommitted_changes=False)

    working_dir = Path(cwd) if cwd else Path.cwd()
    diff_parts = []
    has_uncommitted = False

    # Get diff for each linked commit
    if commits:
        # For multiple commits, we get the combined diff
        # git diff <first_commit>^..<last_commit> shows all changes
        if len(commits) == 1:
            # Single commit: show its changes
            result = run_git_command(
                ["git", "show", "--format=", commits[0]],
                cwd=working_dir,
            )
            if result:
                diff_parts.append(result)
        else:
            # Multiple commits: get combined diff
            # This assumes commits are in chronological order (oldest to newest)
            # We reverse to get oldest first, then get diff from oldest^ to newest
            result = run_git_command(
                ["git", "diff", f"{commits[-1]}^..{commits[0]}"],
                cwd=working_dir,
            )
            if result:
                diff_parts.append(result)

    # Include uncommitted changes if requested
    if include_uncommitted:
        uncommitted = run_git_command(
            ["git", "diff", "HEAD"],
            cwd=working_dir,
        )
        if uncommitted:
            diff_parts.append(uncommitted)
            has_uncommitted = True

    # Combine all diff parts
    combined_diff = "\n".join(diff_parts)

    # Count files in the diff
    file_count = len(re.findall(r"^diff --git", combined_diff, re.MULTILINE))

    return TaskDiffResult(
        diff=combined_diff,
        commits=commits,
        has_uncommitted_changes=has_uncommitted,
        file_count=file_count,
    )
