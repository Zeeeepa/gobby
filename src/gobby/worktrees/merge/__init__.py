"""Merge conflict resolution utilities for worktrees."""

from gobby.worktrees.merge.conflict_parser import ConflictHunk, extract_conflict_hunks
from gobby.worktrees.merge.resolver import (
    MergeResolver,
    MergeResult,
    ResolutionResult,
    ResolutionStrategy,
    ResolutionTier,
)

__all__ = [
    "ConflictHunk",
    "extract_conflict_hunks",
    "MergeResolver",
    "MergeResult",
    "ResolutionResult",
    "ResolutionStrategy",
    "ResolutionTier",
]
