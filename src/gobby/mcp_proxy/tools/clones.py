"""
Internal MCP tools for Gobby Clone Management.

Exposes functionality for:
- Creating git clones for isolated development
- Managing clone lifecycle (get, list, delete)
- Syncing clones with remote repositories

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool, list_tools, get_tool_schema).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from gobby.mcp_proxy.tools.internal import InternalToolRegistry

if TYPE_CHECKING:
    from gobby.clones.git import CloneGitManager
    from gobby.storage.clones import LocalCloneManager

logger = logging.getLogger(__name__)


def create_clones_registry(
    clone_storage: LocalCloneManager,
    git_manager: CloneGitManager,
    project_id: str,
) -> InternalToolRegistry:
    """
    Create the gobby-clones MCP server registry.

    Args:
        clone_storage: Clone storage manager for CRUD operations
        git_manager: Git manager for clone operations
        project_id: Default project ID for new clones

    Returns:
        InternalToolRegistry with clone management tools
    """
    registry = InternalToolRegistry(
        name="gobby-clones",
        description="Git clone management for isolated development",
    )

    # ===== create_clone =====
    async def create_clone(
        branch_name: str,
        clone_path: str,
        remote_url: str | None = None,
        task_id: str | None = None,
        base_branch: str = "main",
        depth: int = 1,
    ) -> dict[str, Any]:
        """
        Create a new git clone.

        Args:
            branch_name: Branch to clone
            clone_path: Path where clone will be created
            remote_url: Remote URL (defaults to origin of parent repo)
            task_id: Optional task ID to link
            base_branch: Base branch for the clone
            depth: Clone depth (default: 1 for shallow)

        Returns:
            Dict with clone info or error
        """
        try:
            # Get remote URL if not provided
            if not remote_url:
                remote_url = git_manager.get_remote_url()
                if not remote_url:
                    return {
                        "success": False,
                        "error": "No remote URL provided and could not get from repository",
                    }

            # Create the clone
            result = git_manager.shallow_clone(
                remote_url=remote_url,
                clone_path=clone_path,
                branch=branch_name,
                depth=depth,
            )

            if not result.success:
                return {
                    "success": False,
                    "error": f"Clone failed: {result.error or result.message}",
                }

            # Store clone record
            clone = clone_storage.create(
                project_id=project_id,
                branch_name=branch_name,
                clone_path=clone_path,
                base_branch=base_branch,
                task_id=task_id,
                remote_url=remote_url,
            )

            return {
                "success": True,
                "clone": clone.to_dict(),
                "message": f"Created clone at {clone_path}",
            }

        except Exception as e:
            logger.error(f"Error creating clone: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    registry.register(
        name="create_clone",
        description="Create a new git clone for isolated development",
        input_schema={
            "type": "object",
            "properties": {
                "branch_name": {
                    "type": "string",
                    "description": "Branch to clone",
                },
                "clone_path": {
                    "type": "string",
                    "description": "Path where clone will be created",
                },
                "remote_url": {
                    "type": "string",
                    "description": "Remote URL (defaults to origin of parent repo)",
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task ID to link",
                },
                "base_branch": {
                    "type": "string",
                    "description": "Base branch for the clone",
                    "default": "main",
                },
                "depth": {
                    "type": "integer",
                    "description": "Clone depth (default: 1 for shallow)",
                    "default": 1,
                },
            },
            "required": ["branch_name", "clone_path"],
        },
        func=create_clone,
    )

    # ===== get_clone =====
    async def get_clone(clone_id: str) -> dict[str, Any]:
        """
        Get clone by ID.

        Args:
            clone_id: Clone ID

        Returns:
            Dict with clone info or error
        """
        clone = clone_storage.get(clone_id)
        if not clone:
            return {
                "success": False,
                "error": f"Clone not found: {clone_id}",
            }

        return {
            "success": True,
            "clone": clone.to_dict(),
        }

    registry.register(
        name="get_clone",
        description="Get clone by ID",
        input_schema={
            "type": "object",
            "properties": {
                "clone_id": {
                    "type": "string",
                    "description": "Clone ID",
                },
            },
            "required": ["clone_id"],
        },
        func=get_clone,
    )

    # ===== list_clones =====
    async def list_clones(
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        List clones with optional filters.

        Args:
            status: Filter by status (active, syncing, stale, cleanup)
            limit: Maximum number of results

        Returns:
            Dict with list of clones
        """
        clones = clone_storage.list_clones(
            project_id=project_id,
            status=status,
            limit=limit,
        )

        return {
            "success": True,
            "clones": [c.to_dict() for c in clones],
            "count": len(clones),
        }

    registry.register(
        name="list_clones",
        description="List clones with optional status filter",
        input_schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status (active, syncing, stale, cleanup)",
                    "enum": ["active", "syncing", "stale", "cleanup"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 50,
                },
            },
        },
        func=list_clones,
    )

    # ===== delete_clone =====
    async def delete_clone(
        clone_id: str,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Delete a clone.

        Args:
            clone_id: Clone ID to delete
            force: Force deletion even if there are uncommitted changes

        Returns:
            Dict with success status
        """
        clone = clone_storage.get(clone_id)
        if not clone:
            return {
                "success": False,
                "error": f"Clone not found: {clone_id}",
            }

        # Store clone info for potential rollback
        clone_path = clone.clone_path

        # Delete the database record first (can be rolled back more easily)
        try:
            clone_storage.delete(clone_id)
        except Exception as e:
            logger.error(f"Failed to delete clone record {clone_id}: {e}")
            return {
                "success": False,
                "error": f"Failed to delete clone record: {e}",
            }

        # Delete the files
        result = git_manager.delete_clone(clone_path, force=force)
        if not result.success:
            # Rollback: recreate the clone record since file deletion failed
            logger.error(
                f"Failed to delete clone files for {clone_id}, "
                f"attempting to restore record: {result.error or result.message}"
            )
            try:
                clone_storage.create(
                    project_id=clone.project_id,
                    branch_name=clone.branch_name,
                    clone_path=clone_path,
                    base_branch=clone.base_branch,
                    task_id=clone.task_id,
                    remote_url=clone.remote_url,
                )
                logger.info(f"Restored clone record for {clone_id} after file deletion failure")
            except Exception as restore_error:
                logger.error(
                    f"Failed to restore clone record {clone_id}: {restore_error}. "
                    f"Clone is now orphaned in database."
                )
            return {
                "success": False,
                "error": f"Failed to delete clone files: {result.error or result.message}",
            }

        return {
            "success": True,
            "message": f"Deleted clone {clone_id}",
        }

    registry.register(
        name="delete_clone",
        description="Delete a clone and its files",
        input_schema={
            "type": "object",
            "properties": {
                "clone_id": {
                    "type": "string",
                    "description": "Clone ID to delete",
                },
                "force": {
                    "type": "boolean",
                    "description": "Force deletion even with uncommitted changes",
                    "default": False,
                },
            },
            "required": ["clone_id"],
        },
        func=delete_clone,
    )

    # ===== sync_clone =====
    async def sync_clone(
        clone_id: str,
        direction: Literal["pull", "push", "both"] = "pull",
    ) -> dict[str, Any]:
        """
        Sync a clone with its remote.

        Args:
            clone_id: Clone ID to sync
            direction: Sync direction (pull, push, or both)

        Returns:
            Dict with sync result
        """
        clone = clone_storage.get(clone_id)
        if not clone:
            return {
                "success": False,
                "error": f"Clone not found: {clone_id}",
            }

        # Mark as syncing
        clone_storage.mark_syncing(clone_id)

        try:
            result = git_manager.sync_clone(
                clone_path=clone.clone_path,
                direction=direction,
            )

            if result.success:
                # Record successful sync and mark as active
                clone_storage.record_sync(clone_id)
                clone_storage.update(clone_id, status="active")
                return {
                    "success": True,
                    "message": f"Synced clone {clone_id} ({direction})",
                }
            else:
                return {
                    "success": False,
                    "error": f"Sync failed: {result.error or result.message}",
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
        finally:
            # Ensure status is reset to active if record_sync didn't complete
            clone = clone_storage.get(clone_id)
            if clone and clone.status == "syncing":
                clone_storage.update(clone_id, status="active")

    registry.register(
        name="sync_clone",
        description="Sync a clone with its remote repository",
        input_schema={
            "type": "object",
            "properties": {
                "clone_id": {
                    "type": "string",
                    "description": "Clone ID to sync",
                },
                "direction": {
                    "type": "string",
                    "description": "Sync direction",
                    "enum": ["pull", "push", "both"],
                    "default": "pull",
                },
            },
            "required": ["clone_id"],
        },
        func=sync_clone,
    )

    # ===== merge_clone_to_target =====
    async def merge_clone_to_target(
        clone_id: str,
        target_branch: str = "main",
    ) -> dict[str, Any]:
        """
        Merge clone branch to target branch in main repository.

        Performs:
        1. Push clone changes to remote (sync_clone push)
        2. Fetch branch in main repo
        3. Attempt merge to target branch

        On success, sets cleanup_after to 7 days from now.

        Args:
            clone_id: Clone ID to merge
            target_branch: Target branch to merge into (default: main)

        Returns:
            Dict with merge result and conflict info if any
        """
        from datetime import UTC, datetime, timedelta

        clone = clone_storage.get(clone_id)
        if not clone:
            return {
                "success": False,
                "error": f"Clone not found: {clone_id}",
            }

        # Step 1: Push clone changes to remote
        clone_storage.mark_syncing(clone_id)
        sync_result = git_manager.sync_clone(
            clone_path=clone.clone_path,
            direction="push",
        )

        if not sync_result.success:
            clone_storage.update(clone_id, status="active")
            return {
                "success": False,
                "error": f"Sync failed: {sync_result.error or sync_result.message}",
                "step": "sync",
            }

        clone_storage.record_sync(clone_id)

        # Step 2: Merge in main repo
        merge_result = git_manager.merge_branch(
            source_branch=clone.branch_name,
            target_branch=target_branch,
        )

        if not merge_result.success:
            # Check for conflicts
            if merge_result.error == "merge_conflict":
                conflicted_files = merge_result.output.split("\n") if merge_result.output else []
                return {
                    "success": False,
                    "has_conflicts": True,
                    "conflicted_files": conflicted_files,
                    "error": merge_result.message,
                    "step": "merge",
                    "message": (
                        f"Merge conflicts detected in {len(conflicted_files)} files. "
                        "Use gobby-merge tools to resolve."
                    ),
                }

            return {
                "success": False,
                "has_conflicts": False,
                "error": merge_result.error or merge_result.message,
                "step": "merge",
            }

        # Step 3: Success - set cleanup_after
        cleanup_after = (datetime.now(UTC) + timedelta(days=7)).isoformat()
        clone_storage.update(clone_id, cleanup_after=cleanup_after)

        return {
            "success": True,
            "message": f"Successfully merged {clone.branch_name} into {target_branch}",
            "cleanup_after": cleanup_after,
        }

    registry.register(
        name="merge_clone_to_target",
        description="Merge clone branch to target branch in main repository",
        input_schema={
            "type": "object",
            "properties": {
                "clone_id": {
                    "type": "string",
                    "description": "Clone ID to merge",
                },
                "target_branch": {
                    "type": "string",
                    "description": "Target branch to merge into",
                    "default": "main",
                },
            },
            "required": ["clone_id"],
        },
        func=merge_clone_to_target,
    )

    return registry
