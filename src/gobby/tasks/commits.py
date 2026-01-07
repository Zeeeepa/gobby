"""Commit linking and diff functionality for Task System V2.

Provides utilities for linking commits to tasks and computing diffs.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from gobby.utils.git import run_git_command

if TYPE_CHECKING:
    from gobby.storage.tasks import LocalTaskManager

logger = logging.getLogger(__name__)


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
            # Commits are stored in chronological order (oldest at index 0, newest at index -1)
            # git diff oldest^..newest shows all changes in the range
            result = run_git_command(
                ["git", "diff", f"{commits[0]}^..{commits[-1]}"],
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


# Doc file extensions that don't need LLM validation
DOC_EXTENSIONS = {".md", ".txt", ".rst", ".adoc", ".markdown"}


def is_doc_only_diff(diff: str) -> bool:
    """Check if a diff only affects documentation files.

    Args:
        diff: Git diff string.

    Returns:
        True if all modified files are documentation files.
    """
    if not diff:
        return False

    # Find all file paths in the diff
    file_pattern = r"^diff --git a/(.+?) b/"
    matches = re.findall(file_pattern, diff, re.MULTILINE)

    if not matches:
        return False

    # Check if all files are doc files
    for file_path in matches:
        ext = Path(file_path).suffix.lower()
        if ext not in DOC_EXTENSIONS:
            return False

    return True


def summarize_diff_for_validation(
    diff: str,
    max_chars: int = 30000,
    max_hunk_lines: int = 50,
) -> str:
    """Summarize a diff for LLM validation, ensuring all files are visible.

    For large diffs, this:
    1. Always shows the complete file list with stats
    2. Truncates individual hunks to avoid overwhelming the LLM
    3. Prioritizes showing file names over full content

    Args:
        diff: Full git diff string.
        max_chars: Maximum characters to return.
        max_hunk_lines: Maximum lines per hunk before truncation.

    Returns:
        Summarized diff string that fits within max_chars.
    """
    if not diff or len(diff) <= max_chars:
        return diff

    # Parse the diff into files
    file_diffs = re.split(r"(?=^diff --git)", diff, flags=re.MULTILINE)
    file_diffs = [f for f in file_diffs if f.strip()]

    if not file_diffs:
        return diff[:max_chars] + "\n\n... [diff truncated] ..."

    # First, collect file stats
    file_stats: list[dict[str, str | int]] = []
    for file_diff in file_diffs:
        # Extract file name
        name_match = re.match(r"diff --git a/(.+?) b/", file_diff)
        if name_match:
            file_name = name_match.group(1)
        else:
            file_name = "(unknown)"

        # Count additions/deletions
        additions = len(re.findall(r"^\+[^+]", file_diff, re.MULTILINE))
        deletions = len(re.findall(r"^-[^-]", file_diff, re.MULTILINE))

        file_stats.append(
            {
                "name": file_name,
                "additions": additions,
                "deletions": deletions,
                "diff": file_diff,
            }
        )

    # Build summary header
    total_additions = sum(int(f["additions"]) for f in file_stats)
    total_deletions = sum(int(f["deletions"]) for f in file_stats)

    summary_parts: list[str] = [
        f"## Diff Summary ({len(file_stats)} files, +{total_additions}/-{total_deletions})\n",
        "### Files Changed:\n",
    ]

    for f in file_stats:
        summary_parts.append(f"- {f['name']} (+{f['additions']}/-{f['deletions']})\n")

    summary_parts.append("\n### File Details:\n\n")

    # Calculate remaining space for file contents
    header_size = sum(len(p) for p in summary_parts)
    remaining_chars = max_chars - header_size - 100  # Buffer for truncation message

    # Distribute remaining space among files
    chars_per_file = remaining_chars // len(file_stats) if file_stats else remaining_chars

    for f in file_stats:
        file_content = str(f["diff"])

        if len(file_content) > chars_per_file:
            # Truncate this file's diff but keep the header
            header_end = file_content.find("@@")
            if header_end > 0:
                header = file_content[:header_end]
                hunks = file_content[header_end:]
                # Keep first part of hunks
                truncated_hunks = hunks[: chars_per_file - len(header) - 50]
                file_content = header + truncated_hunks + "\n... [file diff truncated] ...\n"
            else:
                file_content = file_content[:chars_per_file] + "\n... [file diff truncated] ...\n"

        summary_parts.append(file_content)

    result = "".join(summary_parts)

    # Final safety check
    if len(result) > max_chars:
        result = result[:max_chars] + "\n\n... [diff truncated] ..."

    return result


# Task ID patterns to search for in commit messages
TASK_ID_PATTERNS = [
    # [gt-xxxxx] - bracket format
    r"\[gt-([a-zA-Z0-9]+)\]",
    # gt-xxxxx: - colon format
    r"\bgt-([a-zA-Z0-9]+):",
    # Implements/Fixes/Closes gt-xxxxx
    r"(?:implements|fixes|closes)\s+gt-([a-zA-Z0-9]+)",
]


def extract_task_ids_from_message(message: str) -> list[str]:
    """Extract task IDs from a commit message.

    Supports patterns:
    - [gt-xxxxx] - bracket format
    - gt-xxxxx: - colon format (at start of message)
    - Implements/Fixes/Closes gt-xxxxx

    Args:
        message: Commit message to parse.

    Returns:
        List of unique task IDs found (e.g., ["gt-abc123", "gt-def456"]).
    """
    task_ids = set()

    for pattern in TASK_ID_PATTERNS:
        matches = re.findall(pattern, message, re.IGNORECASE)
        for match in matches:
            # Normalize to lowercase
            task_id = f"gt-{match.lower()}"
            task_ids.add(task_id)

    return list(task_ids)


@dataclass
class AutoLinkResult:
    """Result of auto-linking commits to tasks.

    Attributes:
        linked_tasks: Dict mapping task_id -> list of newly linked commit SHAs.
        total_linked: Total number of commits newly linked.
        skipped: Number of commits skipped (already linked or task not found).
    """

    linked_tasks: dict[str, list[str]] = field(default_factory=dict)
    total_linked: int = 0
    skipped: int = 0


def auto_link_commits(
    task_manager: "LocalTaskManager",
    task_id: str | None = None,
    since: str | None = None,
    cwd: str | Path | None = None,
) -> AutoLinkResult:
    """Auto-detect and link commits that mention task IDs.

    Searches commit messages for task ID patterns and links matching commits
    to the corresponding tasks.

    Args:
        task_manager: LocalTaskManager instance for task operations.
        task_id: Optional specific task ID to filter for.
        since: Optional git --since parameter (e.g., "1 week ago", "2024-01-01").
        cwd: Working directory for git commands.

    Returns:
        AutoLinkResult with details of linked and skipped commits.
    """
    working_dir = Path(cwd) if cwd else Path.cwd()

    # Build git log command
    # Format: "sha|message" for easy parsing
    git_cmd = ["git", "log", "--pretty=format:%h|%s"]

    if since:
        git_cmd.append(f"--since={since}")

    # Get git log output
    log_output = run_git_command(git_cmd, cwd=working_dir)

    if not log_output:
        return AutoLinkResult()

    result = AutoLinkResult()

    # Parse each commit line
    for line in log_output.strip().split("\n"):
        if not line or "|" not in line:
            continue

        parts = line.split("|", 1)
        if len(parts) != 2:
            continue

        commit_sha, message = parts

        # Extract task IDs from message
        found_task_ids = extract_task_ids_from_message(message)

        if not found_task_ids:
            continue

        # Filter to specific task if requested
        if task_id:
            if task_id not in found_task_ids:
                continue
            found_task_ids = [task_id]

        # Try to link each found task
        for tid in found_task_ids:
            try:
                task = task_manager.get_task(tid)

                # Check if already linked
                existing_commits = task.commits or []
                if commit_sha in existing_commits:
                    result.skipped += 1
                    continue

                # Link the commit
                task_manager.link_commit(tid, commit_sha)

                # Track in result
                if tid not in result.linked_tasks:
                    result.linked_tasks[tid] = []
                result.linked_tasks[tid].append(commit_sha)
                result.total_linked += 1

                logger.debug(f"Auto-linked commit {commit_sha} to task {tid}")

            except ValueError:
                # Task doesn't exist, skip
                logger.debug(f"Skipping commit {commit_sha}: task {tid} not found")
                result.skipped += 1
                continue

    return result
