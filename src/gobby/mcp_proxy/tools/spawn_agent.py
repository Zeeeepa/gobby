"""
Unified spawn_agent MCP tool.

Consolidates three separate agent spawning tools into one:
- start_agent
- spawn_agent_in_worktree
- spawn_agent_in_clone

One tool: spawn_agent(prompt, agent="generic", isolation="current"|"worktree"|"clone", ...)
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from gobby.agents.definitions import AgentDefinition, AgentDefinitionLoader
from gobby.agents.isolation import (
    SpawnConfig,
    get_isolation_handler,
)
from gobby.agents.registry import RunningAgent, get_running_agent_registry
from gobby.agents.sandbox import SandboxConfig
from gobby.agents.spawn_executor import SpawnRequest, execute_spawn
from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.tasks import resolve_task_id_for_mcp
from gobby.utils.machine_id import get_machine_id
from gobby.utils.project_context import get_project_context

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.storage.tasks import LocalTaskManager

logger = logging.getLogger(__name__)


async def spawn_agent_impl(
    prompt: str,
    runner: AgentRunner,
    agent_def: AgentDefinition | None = None,
    task_id: str | None = None,
    task_manager: LocalTaskManager | None = None,
    # Isolation
    isolation: Literal["current", "worktree", "clone"] | None = None,
    branch_name: str | None = None,
    base_branch: str | None = None,
    # Storage/managers for isolation
    worktree_storage: Any | None = None,
    git_manager: Any | None = None,
    clone_storage: Any | None = None,
    clone_manager: Any | None = None,
    # Execution
    workflow: str | None = None,
    mode: Literal["terminal", "embedded", "headless"] | None = None,
    terminal: str = "auto",
    provider: str | None = None,
    model: str | None = None,
    # Limits
    timeout: float | None = None,
    max_turns: int | None = None,
    # Sandbox
    sandbox: bool | None = None,
    sandbox_mode: Literal["permissive", "restrictive"] | None = None,
    sandbox_allow_network: bool | None = None,
    sandbox_extra_paths: list[str] | None = None,
    # Context
    parent_session_id: str | None = None,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Core spawn_agent implementation that can be called directly.

    This is the internal implementation used by both the spawn_agent MCP tool
    and the deprecated spawn_agent_in_worktree/spawn_agent_in_clone tools.

    Args:
        prompt: Required - what the agent should do
        runner: AgentRunner instance for executing agents
        agent_def: Optional loaded agent definition
        task_id: Optional - link to task (supports N, #N, UUID)
        task_manager: Task manager for task resolution
        isolation: Isolation mode (current/worktree/clone)
        branch_name: Git branch name (auto-generated from task if not provided)
        base_branch: Base branch for worktree/clone
        worktree_storage: Storage for worktree records
        git_manager: Git manager for worktree operations
        clone_storage: Storage for clone records
        clone_manager: Git manager for clone operations
        workflow: Workflow to use
        mode: Execution mode (terminal/embedded/headless)
        terminal: Terminal type for terminal mode
        provider: AI provider (claude/gemini/codex)
        model: Model to use
        timeout: Timeout in seconds
        max_turns: Maximum conversation turns
        sandbox: Enable sandbox (True/False/None). None inherits from agent_def.
        sandbox_mode: Sandbox mode (permissive/restrictive). Overrides agent_def.
        sandbox_allow_network: Allow network access. Overrides agent_def.
        sandbox_extra_paths: Extra paths for sandbox write access.
        parent_session_id: Parent session ID
        project_path: Project path override

    Returns:
        Dict with success status, run_id, child_session_id, isolation metadata
    """
    # 1. Merge config: agent_def defaults < params
    effective_isolation = isolation
    if effective_isolation is None and agent_def:
        effective_isolation = agent_def.isolation
    effective_isolation = effective_isolation or "current"

    effective_provider = provider
    if effective_provider is None and agent_def:
        effective_provider = agent_def.provider
    effective_provider = effective_provider or "claude"

    effective_mode: Literal["terminal", "embedded", "headless"] | None = mode
    if effective_mode is None and agent_def:
        effective_mode = cast(Literal["terminal", "embedded", "headless"], agent_def.mode)
    effective_mode = effective_mode or "terminal"

    effective_workflow = workflow
    if effective_workflow is None and agent_def:
        effective_workflow = agent_def.workflow

    effective_base_branch = base_branch
    if effective_base_branch is None and agent_def:
        effective_base_branch = agent_def.base_branch
    effective_base_branch = effective_base_branch or "main"

    effective_branch_prefix = None
    if agent_def:
        effective_branch_prefix = agent_def.branch_prefix

    # Build effective sandbox config (merge agent_def.sandbox with params)
    effective_sandbox_config: SandboxConfig | None = None

    # Start with agent_def.sandbox if present
    base_sandbox = agent_def.sandbox if agent_def and hasattr(agent_def, "sandbox") else None

    # Determine if sandbox should be enabled
    sandbox_enabled = sandbox  # Explicit param takes precedence
    if sandbox_enabled is None and base_sandbox is not None:
        sandbox_enabled = base_sandbox.enabled

    # Build sandbox config if enabled or if we have params to apply
    if sandbox_enabled is True or (
        sandbox_enabled is None
        and (sandbox_mode is not None or sandbox_allow_network is not None or sandbox_extra_paths)
    ):
        # Start from base or create new
        if base_sandbox is not None:
            effective_sandbox_config = SandboxConfig(
                enabled=True if sandbox_enabled is None else sandbox_enabled,
                mode=sandbox_mode if sandbox_mode is not None else base_sandbox.mode,
                allow_network=(
                    sandbox_allow_network
                    if sandbox_allow_network is not None
                    else base_sandbox.allow_network
                ),
                extra_read_paths=base_sandbox.extra_read_paths,
                extra_write_paths=(
                    list(base_sandbox.extra_write_paths) + (sandbox_extra_paths or [])
                ),
            )
        else:
            effective_sandbox_config = SandboxConfig(
                enabled=True,
                mode=sandbox_mode or "permissive",
                allow_network=sandbox_allow_network if sandbox_allow_network is not None else True,
                extra_write_paths=sandbox_extra_paths or [],
            )
    elif sandbox_enabled is False:
        # Explicitly disabled - set config with enabled=False
        effective_sandbox_config = SandboxConfig(enabled=False)

    # 2. Resolve project context
    ctx = get_project_context(Path(project_path) if project_path else None)
    if ctx is None:
        return {"success": False, "error": "Could not resolve project context"}

    project_id = ctx.get("id") or ctx.get("project_id")
    resolved_project_path = ctx.get("project_path")

    if not project_id or not isinstance(project_id, str):
        return {"success": False, "error": "Could not resolve project_id from context"}
    if not resolved_project_path or not isinstance(resolved_project_path, str):
        return {"success": False, "error": "Could not resolve project_path from context"}

    # 3. Validate parent_session_id and spawn depth
    if parent_session_id is None:
        return {"success": False, "error": "parent_session_id is required"}

    can_spawn, reason, _depth = runner.can_spawn(parent_session_id)
    if not can_spawn:
        return {"success": False, "error": reason}

    # 4. Resolve task_id if provided (supports N, #N, UUID)
    resolved_task_id: str | None = None
    task_title: str | None = None
    task_seq_num: int | None = None

    if task_id and task_manager:
        try:
            resolved_task_id = resolve_task_id_for_mcp(task_manager, task_id, project_id)
            task = task_manager.get_task(resolved_task_id)
            if task:
                task_title = task.title
                task_seq_num = task.seq_num
        except Exception as e:
            logger.warning(f"Failed to resolve task_id {task_id}: {e}")

    # 5. Get isolation handler
    handler = get_isolation_handler(
        effective_isolation,
        git_manager=git_manager,
        worktree_storage=worktree_storage,
        clone_manager=clone_manager,
        clone_storage=clone_storage,
    )

    # 6. Build spawn config
    spawn_config = SpawnConfig(
        prompt=prompt,
        task_id=resolved_task_id,
        task_title=task_title,
        task_seq_num=task_seq_num,
        branch_name=branch_name,
        branch_prefix=effective_branch_prefix,
        base_branch=effective_base_branch,
        project_id=project_id,
        project_path=resolved_project_path,
        provider=effective_provider,
        parent_session_id=parent_session_id,
    )

    # 7. Prepare environment (worktree/clone creation)
    try:
        isolation_ctx = await handler.prepare_environment(spawn_config)
    except Exception as e:
        logger.error(f"Failed to prepare environment: {e}", exc_info=True)
        return {"success": False, "error": f"Failed to prepare environment: {e}"}

    # 8. Build enhanced prompt with isolation context
    enhanced_prompt = handler.build_context_prompt(prompt, isolation_ctx)

    # 9. Generate session and run IDs
    session_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    # 10. Execute spawn via SpawnExecutor
    spawn_request = SpawnRequest(
        prompt=enhanced_prompt,
        cwd=isolation_ctx.cwd,
        mode=effective_mode,
        provider=effective_provider,
        terminal=terminal,
        session_id=session_id,
        run_id=run_id,
        parent_session_id=parent_session_id,
        project_id=project_id,
        workflow=effective_workflow,
        worktree_id=isolation_ctx.worktree_id,
        clone_id=isolation_ctx.clone_id,
        session_manager=runner._child_session_manager,
        machine_id=get_machine_id() or "unknown",
        sandbox_config=effective_sandbox_config,
    )

    spawn_result = await execute_spawn(spawn_request)

    # 11. Register with RunningAgentRegistry for send_to_parent/child messaging
    # Only register if spawn succeeded and we have a valid child_session_id
    if spawn_result.success and spawn_result.child_session_id is not None:
        agent_registry = get_running_agent_registry()
        agent_registry.add(
            RunningAgent(
                run_id=spawn_result.run_id,
                session_id=spawn_result.child_session_id,
                parent_session_id=parent_session_id,
                mode=effective_mode,
                pid=spawn_result.pid,
                provider=effective_provider,
                workflow_name=effective_workflow,
                worktree_id=isolation_ctx.worktree_id,
            )
        )

    # 12. Return response with isolation metadata
    return {
        "success": spawn_result.success,
        "run_id": spawn_result.run_id,
        "child_session_id": spawn_result.child_session_id,
        "status": spawn_result.status,
        "isolation": effective_isolation,
        "branch_name": isolation_ctx.branch_name,
        "worktree_id": isolation_ctx.worktree_id,
        "worktree_path": isolation_ctx.cwd if effective_isolation == "worktree" else None,
        "clone_id": isolation_ctx.clone_id,
        "pid": spawn_result.pid,
        "error": spawn_result.error,
        "message": spawn_result.message,
    }


def create_spawn_agent_registry(
    runner: AgentRunner,
    agent_loader: AgentDefinitionLoader | None = None,
    task_manager: LocalTaskManager | None = None,
    worktree_storage: Any | None = None,
    git_manager: Any | None = None,
    clone_storage: Any | None = None,
    clone_manager: Any | None = None,
    session_manager: Any | None = None,
) -> InternalToolRegistry:
    """
    Create a spawn_agent tool registry with the unified spawn_agent tool.

    Args:
        runner: AgentRunner instance for executing agents.
        agent_loader: Loader for agent definitions.
        task_manager: Task manager for task resolution.
        worktree_storage: Storage for worktree records.
        git_manager: Git manager for worktree operations.
        clone_storage: Storage for clone records.
        clone_manager: Git manager for clone operations.
        session_manager: Session manager for resolving session references.

    Returns:
        InternalToolRegistry with spawn_agent tool registered.
    """

    def _resolve_session_id(ref: str) -> str:
        """Resolve session reference (#N, N, UUID, or prefix) to UUID."""
        if session_manager is None:
            return ref  # No resolution available, return as-is
        ctx = get_project_context()
        project_id = ctx.get("id") if ctx else None
        return str(session_manager.resolve_session_reference(ref, project_id))

    registry = InternalToolRegistry(
        name="gobby-spawn-agent",
        description="Unified agent spawning with isolation support",
    )

    # Use provided loader or create default
    loader = agent_loader or AgentDefinitionLoader()

    @registry.tool(
        name="spawn_agent",
        description=(
            "Spawn a subagent to execute a task. Supports isolation modes: "
            "'current' (work in current directory), 'worktree' (create git worktree), "
            "'clone' (create shallow clone). Can use named agent definitions or raw parameters. "
            "Accepts #N, N, UUID, or prefix for parent_session_id."
        ),
    )
    async def spawn_agent(
        prompt: str,
        agent: str = "generic",
        task_id: str | None = None,
        # Isolation
        isolation: Literal["current", "worktree", "clone"] | None = None,
        branch_name: str | None = None,
        base_branch: str | None = None,
        # Execution
        workflow: str | None = None,
        mode: Literal["terminal", "embedded", "headless"] | None = None,
        terminal: str = "auto",
        provider: str | None = None,
        model: str | None = None,
        # Limits
        timeout: float | None = None,
        max_turns: int | None = None,
        # Sandbox
        sandbox: bool | None = None,
        sandbox_mode: Literal["permissive", "restrictive"] | None = None,
        sandbox_allow_network: bool | None = None,
        sandbox_extra_paths: list[str] | None = None,
        # Context
        parent_session_id: str | None = None,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Spawn a subagent with the specified configuration.

        Args:
            prompt: Required - what the agent should do
            agent: Agent definition name (defaults to "generic")
            task_id: Optional - link to task (supports N, #N, UUID)
            isolation: Isolation mode (current/worktree/clone)
            branch_name: Git branch name (auto-generated from task if not provided)
            base_branch: Base branch for worktree/clone
            workflow: Workflow to use
            mode: Execution mode (terminal/embedded/headless)
            terminal: Terminal type for terminal mode
            provider: AI provider (claude/gemini/codex)
            model: Model to use
            timeout: Timeout in seconds
            max_turns: Maximum conversation turns
            sandbox: Enable sandbox (True/False/None). None inherits from agent_def.
            sandbox_mode: Sandbox mode (permissive/restrictive). Overrides agent_def.
            sandbox_allow_network: Allow network access. Overrides agent_def.
            sandbox_extra_paths: Extra paths for sandbox write access.
            parent_session_id: Session reference (accepts #N, N, UUID, or prefix) for the parent session
            project_path: Project path override

        Returns:
            Dict with success status, run_id, child_session_id, isolation metadata
        """
        # Resolve parent_session_id to UUID (accepts #N, N, UUID, or prefix)
        resolved_parent_session_id = parent_session_id
        if parent_session_id:
            try:
                resolved_parent_session_id = _resolve_session_id(parent_session_id)
            except ValueError as e:
                return {"success": False, "error": str(e)}

        # Load agent definition (defaults to "generic")
        agent_def = loader.load(agent)
        if agent_def is None and agent != "generic":
            return {"success": False, "error": f"Agent '{agent}' not found"}

        # Delegate to spawn_agent_impl
        return await spawn_agent_impl(
            prompt=prompt,
            runner=runner,
            agent_def=agent_def,
            task_id=task_id,
            task_manager=task_manager,
            isolation=isolation,
            branch_name=branch_name,
            base_branch=base_branch,
            worktree_storage=worktree_storage,
            git_manager=git_manager,
            clone_storage=clone_storage,
            clone_manager=clone_manager,
            workflow=workflow,
            mode=mode,
            terminal=terminal,
            provider=provider,
            model=model,
            timeout=timeout,
            max_turns=max_turns,
            sandbox=sandbox,
            sandbox_mode=sandbox_mode,
            sandbox_allow_network=sandbox_allow_network,
            sandbox_extra_paths=sandbox_extra_paths,
            parent_session_id=resolved_parent_session_id,
            project_path=project_path,
        )

    return registry
