"""Merge conflict resolution utilities for worktrees."""

from gobby.worktrees.merge.conflict_parser import ConflictHunk, extract_conflict_hunks

__all__ = ["ConflictHunk", "extract_conflict_hunks"]
