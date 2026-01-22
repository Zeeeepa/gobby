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
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from gobby.mcp_proxy.tools.internal import InternalToolRegistry

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.clones.git import CloneGitManager
    from gobby.storage.clones import LocalCloneManager

logger = logging.getLogger(__name__)


def create_clones_registry(
    clone_storage: LocalCloneManager,
    git_manager: CloneGitManager,
    project_id: str,
    agent_runner: AgentRunner | None = None,
) -> InternalToolRegistry:
    """
    Create the gobby-clones MCP server registry.

    Args:
        clone_storage: Clone storage manager for CRUD operations
        git_manager: Git manager for clone operations
        project_id: Default project ID for new clones
        agent_runner: Optional agent runner for spawning agents in clones

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
                # Record successful sync
                clone_storage.record_sync(clone_id)
                return {
                    "success": True,
                    "message": f"Synced clone {clone_id} ({direction})",
                }
            else:
                # Revert to active status
                clone_storage.update(clone_id, status="active")
                return {
                    "success": False,
                    "error": f"Sync failed: {result.error or result.message}",
                }

        except Exception as e:
            # Revert to active status
            clone_storage.update(clone_id, status="active")
            return {
                "success": False,
                "error": str(e),
            }

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

    # ===== spawn_agent_in_clone =====
    async def spawn_agent_in_clone(
        prompt: str,
        branch_name: str,
        parent_session_id: str | None = None,
        task_id: str | None = None,
        base_branch: str = "main",
        clone_path: str | None = None,
        mode: str = "terminal",
        terminal: str = "auto",
        provider: Literal["claude", "gemini", "codex", "antigravity"] = "claude",
        model: str | None = None,
        workflow: str | None = None,
        timeout: float = 120.0,
        max_turns: int = 10,
    ) -> dict[str, Any]:
        """
        Create a clone (if needed) and spawn an agent in it.

        This combines clone creation with agent spawning for isolated development.
        Unlike worktrees, clones are full repository copies that can be worked on
        independently without affecting the main repository.

        Args:
            prompt: The task/prompt for the agent.
            branch_name: Name for the branch in the clone.
            parent_session_id: Parent session ID for context (required).
            task_id: Optional task ID to link to this clone.
            base_branch: Branch to clone from (default: main).
            clone_path: Optional custom path for the clone.
            mode: Execution mode (terminal, embedded, headless).
            terminal: Terminal for terminal/embedded modes (auto, ghostty, etc.).
            provider: LLM provider (claude, gemini, etc.).
            model: Optional model override.
            workflow: Workflow name to execute.
            timeout: Execution timeout in seconds (default: 120).
            max_turns: Maximum turns (default: 10).

        Returns:
            Dict with clone_id, run_id, and status.
        """
        if agent_runner is None:
            return {
                "success": False,
                "error": "Agent runner not configured. Cannot spawn agent.",
            }

        if parent_session_id is None:
            return {
                "success": False,
                "error": "parent_session_id is required for agent spawning.",
            }

        # Handle mode aliases and validation
        if mode == "interactive":
            mode = "terminal"

        valid_modes = ["terminal", "embedded", "headless"]
        if mode not in valid_modes:
            return {
                "success": False,
                "error": (
                    f"Invalid mode '{mode}'. Must be one of: {', '.join(valid_modes)}. "
                    f"Note: 'in_process' mode is not supported for spawn_agent_in_clone."
                ),
            }

        # Normalize terminal parameter to lowercase
        if isinstance(terminal, str):
            terminal = terminal.lower()

        # Check spawn depth limit
        can_spawn, reason, _depth = agent_runner.can_spawn(parent_session_id)
        if not can_spawn:
            return {
                "success": False,
                "error": reason,
            }

        # Check if clone already exists for this branch
        existing = clone_storage.get_by_branch(project_id, branch_name)
        if existing:
            clone = existing
            logger.info(f"Using existing clone for branch '{branch_name}'")
        else:
            # Get remote URL
            remote_url = git_manager.get_remote_url() if git_manager else None
            if not remote_url:
                return {
                    "success": False,
                    "error": "No remote URL available. Cannot create clone.",
                }

            # Generate clone path if not provided
            if clone_path is None:
                import platform
                import tempfile

                if platform.system() == "Windows":
                    base = Path(tempfile.gettempdir()) / "gobby-clones"
                else:
                    # nosec B108: /tmp is intentional for clones - they're temporary
                    base = Path("/tmp").resolve() / "gobby-clones"  # nosec B108
                base.mkdir(parents=True, exist_ok=True)
                safe_branch = branch_name.replace("/", "-")
                clone_path = str(base / f"{project_id}-{safe_branch}")

            # Create the clone
            result = git_manager.shallow_clone(
                remote_url=remote_url,
                clone_path=clone_path,
                branch=base_branch,
                depth=1,
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

        # Import AgentConfig and get machine_id
        from gobby.agents.runner import AgentConfig
        from gobby.utils.machine_id import get_machine_id

        machine_id = get_machine_id()

        # Create agent config
        config = AgentConfig(
            prompt=prompt,
            parent_session_id=parent_session_id,
            project_id=project_id,
            machine_id=machine_id,
            source=provider,
            workflow=workflow,
            task=task_id,
            session_context="summary_markdown",
            mode=mode,
            terminal=terminal,
            provider=provider,
            model=model,
            max_turns=max_turns,
            timeout=timeout,
            project_path=clone.clone_path,
        )

        # Prepare the run
        from gobby.llm.executor import AgentResult

        prepare_result = agent_runner.prepare_run(config)
        if isinstance(prepare_result, AgentResult):
            return {
                "success": False,
                "clone_id": clone.id,
                "clone_path": clone.clone_path,
                "branch_name": clone.branch_name,
                "error": prepare_result.error,
            }

        context = prepare_result
        if context.session is None or context.run is None:
            return {
                "success": False,
                "clone_id": clone.id,
                "error": "Internal error: context missing session or run",
            }

        child_session = context.session
        agent_run = context.run

        # Claim clone for the child session
        clone_storage.claim(clone.id, child_session.id)

        # Build enhanced prompt with clone context
        context_lines = [
            "## CRITICAL: Clone Context",
            "You are working in an ISOLATED git clone, NOT the main repository.",
            "",
            f"**Your workspace:** {clone.clone_path}",
            f"**Your branch:** {clone.branch_name}",
        ]
        if task_id:
            context_lines.append(f"**Your task:** {task_id}")
        context_lines.extend(
            [
                "",
                "**IMPORTANT RULES:**",
                f"1. ALL file operations must be within {clone.clone_path}",
                "2. Do NOT access the main repository",
                "3. Run `pwd` to verify your location before any file operations",
                f"4. Commit to YOUR branch ({clone.branch_name})",
                "5. When your assigned task is complete, STOP - do not claim other tasks",
                "",
                "---",
                "",
            ]
        )
        enhanced_prompt = "\n".join(context_lines) + prompt

        # Spawn based on mode
        if mode == "terminal":
            from gobby.agents.spawn import TerminalSpawner

            terminal_spawner = TerminalSpawner()
            terminal_result = terminal_spawner.spawn_agent(
                cli=provider,
                cwd=clone.clone_path,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                agent_run_id=agent_run.id,
                project_id=project_id,
                workflow_name=workflow,
                agent_depth=child_session.agent_depth,
                max_agent_depth=agent_runner._child_session_manager.max_agent_depth,
                terminal=terminal,
                prompt=enhanced_prompt,
            )

            if not terminal_result.success:
                return {
                    "success": False,
                    "clone_id": clone.id,
                    "clone_path": clone.clone_path,
                    "branch_name": clone.branch_name,
                    "run_id": agent_run.id,
                    "child_session_id": child_session.id,
                    "error": terminal_result.error or terminal_result.message,
                }

            return {
                "success": True,
                "clone_id": clone.id,
                "clone_path": clone.clone_path,
                "branch_name": clone.branch_name,
                "run_id": agent_run.id,
                "child_session_id": child_session.id,
                "status": "pending",
                "message": f"Agent spawned in {terminal_result.terminal_type} (PID: {terminal_result.pid})",
                "terminal_type": terminal_result.terminal_type,
                "pid": terminal_result.pid,
            }

        elif mode == "embedded":
            from gobby.agents.spawn import EmbeddedSpawner

            embedded_spawner = EmbeddedSpawner()
            embedded_result = embedded_spawner.spawn_agent(
                cli=provider,
                cwd=clone.clone_path,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                agent_run_id=agent_run.id,
                project_id=project_id,
                workflow_name=workflow,
                agent_depth=child_session.agent_depth,
                max_agent_depth=agent_runner._child_session_manager.max_agent_depth,
                prompt=enhanced_prompt,
            )

            return {
                "success": embedded_result.success,
                "clone_id": clone.id,
                "clone_path": clone.clone_path,
                "branch_name": clone.branch_name,
                "run_id": agent_run.id,
                "child_session_id": child_session.id,
                "status": "pending" if embedded_result.success else "error",
                "error": embedded_result.error if not embedded_result.success else None,
            }

        else:  # headless
            from gobby.agents.spawn import HeadlessSpawner

            headless_spawner = HeadlessSpawner()
            headless_result = headless_spawner.spawn_agent(
                cli=provider,
                cwd=clone.clone_path,
                session_id=child_session.id,
                parent_session_id=parent_session_id,
                agent_run_id=agent_run.id,
                project_id=project_id,
                workflow_name=workflow,
                agent_depth=child_session.agent_depth,
                max_agent_depth=agent_runner._child_session_manager.max_agent_depth,
                prompt=enhanced_prompt,
            )

            return {
                "success": headless_result.success,
                "clone_id": clone.id,
                "clone_path": clone.clone_path,
                "branch_name": clone.branch_name,
                "run_id": agent_run.id,
                "child_session_id": child_session.id,
                "status": "pending" if headless_result.success else "error",
                "pid": headless_result.pid if headless_result.success else None,
                "error": headless_result.error if not headless_result.success else None,
            }

    registry.register(
        name="spawn_agent_in_clone",
        description="Create a clone and spawn an agent to work in it",
        input_schema={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The task/prompt for the agent",
                },
                "branch_name": {
                    "type": "string",
                    "description": "Name for the branch in the clone",
                },
                "parent_session_id": {
                    "type": "string",
                    "description": "Parent session ID for context (required)",
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional task ID to link to this clone",
                },
                "base_branch": {
                    "type": "string",
                    "description": "Branch to clone from",
                    "default": "main",
                },
                "clone_path": {
                    "type": "string",
                    "description": "Optional custom path for the clone",
                },
                "mode": {
                    "type": "string",
                    "description": "Execution mode",
                    "enum": ["terminal", "embedded", "headless"],
                    "default": "terminal",
                },
                "terminal": {
                    "type": "string",
                    "description": "Terminal type for terminal/embedded modes",
                    "default": "auto",
                },
                "provider": {
                    "type": "string",
                    "description": "LLM provider",
                    "enum": ["claude", "gemini", "codex", "antigravity"],
                    "default": "claude",
                },
                "model": {
                    "type": "string",
                    "description": "Optional model override",
                },
                "workflow": {
                    "type": "string",
                    "description": "Workflow name to execute",
                },
                "timeout": {
                    "type": "number",
                    "description": "Execution timeout in seconds",
                    "default": 120.0,
                },
                "max_turns": {
                    "type": "integer",
                    "description": "Maximum turns",
                    "default": 10,
                },
            },
            "required": ["prompt", "branch_name", "parent_session_id"],
        },
        func=spawn_agent_in_clone,
    )

    return registry
