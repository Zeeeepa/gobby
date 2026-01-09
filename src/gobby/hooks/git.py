"""Git-related hooks for merge operations.

Provides hooks for pre-merge and post-merge events that can be used
to integrate merge resolution with other systems.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Type aliases for hook callbacks
PreMergeHook = Callable[[str, str, str], bool]  # (worktree_id, source, target) -> allow
PostMergeHook = Callable[[str, bool], None]  # (resolution_id, success) -> None


class MergeHookManager:
    """
    Manager for merge-related hooks.

    Allows registration of pre-merge and post-merge hooks that can be
    used to integrate merge resolution with other systems (task status,
    notifications, etc.).
    """

    def __init__(self) -> None:
        """Initialize the hook manager."""
        self._pre_merge_hooks: list[PreMergeHook] = []
        self._post_merge_hooks: list[PostMergeHook] = []

    def register_pre_merge(self, hook: PreMergeHook) -> None:
        """
        Register a pre-merge hook.

        Pre-merge hooks are called before a merge operation starts.
        They receive the worktree ID, source branch, and target branch.
        If any hook returns False, the merge is blocked.

        Args:
            hook: Callback function (worktree_id, source_branch, target_branch) -> bool
        """
        self._pre_merge_hooks.append(hook)
        logger.debug(f"Registered pre-merge hook: {hook.__name__}")

    def register_post_merge(self, hook: PostMergeHook) -> None:
        """
        Register a post-merge hook.

        Post-merge hooks are called after a merge operation completes.
        They receive the resolution ID and success status.

        Args:
            hook: Callback function (resolution_id, success) -> None
        """
        self._post_merge_hooks.append(hook)
        logger.debug(f"Registered post-merge hook: {hook.__name__}")

    def unregister_pre_merge(self, hook: PreMergeHook) -> bool:
        """
        Unregister a pre-merge hook.

        Args:
            hook: Hook to unregister

        Returns:
            True if hook was found and removed
        """
        try:
            self._pre_merge_hooks.remove(hook)
            return True
        except ValueError:
            return False

    def unregister_post_merge(self, hook: PostMergeHook) -> bool:
        """
        Unregister a post-merge hook.

        Args:
            hook: Hook to unregister

        Returns:
            True if hook was found and removed
        """
        try:
            self._post_merge_hooks.remove(hook)
            return True
        except ValueError:
            return False

    def run_pre_merge_hooks(
        self, worktree_id: str, source_branch: str, target_branch: str
    ) -> tuple[bool, str | None]:
        """
        Run all pre-merge hooks.

        Args:
            worktree_id: ID of the worktree
            source_branch: Branch being merged
            target_branch: Target branch

        Returns:
            Tuple of (allowed, blocking_reason)
            If any hook returns False, returns (False, reason)
        """
        for hook in self._pre_merge_hooks:
            try:
                result = hook(worktree_id, source_branch, target_branch)
                if not result:
                    reason = f"Merge blocked by pre-merge hook: {hook.__name__}"
                    logger.warning(reason)
                    return (False, reason)
            except Exception as e:
                reason = f"Pre-merge hook {hook.__name__} raised exception: {e}"
                logger.error(reason)
                # Continue with other hooks on exception
                continue

        return (True, None)

    def run_post_merge_hooks(self, resolution_id: str, success: bool) -> None:
        """
        Run all post-merge hooks.

        Args:
            resolution_id: ID of the merge resolution
            success: Whether the merge was successful
        """
        for hook in self._post_merge_hooks:
            try:
                hook(resolution_id, success)
            except Exception as e:
                logger.error(f"Post-merge hook {hook.__name__} raised exception: {e}")
                # Continue with other hooks on exception
                continue

    @property
    def pre_merge_hook_count(self) -> int:
        """Get number of registered pre-merge hooks."""
        return len(self._pre_merge_hooks)

    @property
    def post_merge_hook_count(self) -> int:
        """Get number of registered post-merge hooks."""
        return len(self._post_merge_hooks)


# Singleton instance for global hook management
_default_manager: MergeHookManager | None = None


def get_merge_hook_manager() -> MergeHookManager:
    """
    Get the default MergeHookManager instance.

    Returns:
        The global MergeHookManager singleton
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = MergeHookManager()
    return _default_manager


def reset_merge_hook_manager() -> None:
    """Reset the default MergeHookManager (for testing)."""
    global _default_manager
    _default_manager = None
