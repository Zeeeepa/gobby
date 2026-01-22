"""Clone management for parallel development.

This module provides git clone operations, distinct from worktrees.
Clones are full repository copies while worktrees share a single .git directory.
"""

from gobby.clones.git import CloneGitManager, CloneStatus, GitOperationResult

__all__ = [
    "CloneGitManager",
    "CloneStatus",
    "GitOperationResult",
]
