"""Factory for creating the spawn_agent MCP tool registry.

Contains create_spawn_agent_registry() with validation logic for
orchestrator enforcement, internal workflow enforcement, and workflow resolution.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from gobby.agents.definitions import AgentDefinitionLoader
from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.utils.project_context import get_project_context
from gobby.workflows.loader import WorkflowLoader

from ._implementation import spawn_agent_impl

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.storage.tasks import LocalTaskManager

logger = logging.getLogger(__name__)


def create_spawn_agent_registry(
    runner: AgentRunner,
    agent_loader: AgentDefinitionLoader | None = None,
    task_manager: LocalTaskManager | None = None,
    worktree_storage: Any | None = None,
    git_manager: Any | None = None,
    clone_storage: Any | None = None,
    clone_manager: Any | None = None,
    session_manager: Any | None = None,
    workflow_loader: WorkflowLoader | None = None,
    # For mode=self (workflow activation on caller session)
    state_manager: Any | None = None,  # WorkflowStateManager
    db: Any | None = None,  # DatabaseProtocol
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
        workflow_loader: Loader for workflow validation.
        state_manager: WorkflowStateManager for mode=self activation.
        db: Database instance for mode=self activation.

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

    # Use provided loaders or create defaults
    loader = agent_loader or AgentDefinitionLoader(db=db)
    wf_loader = workflow_loader or WorkflowLoader()

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
        agent: str = "default",
        task_id: str | None = None,
        # Isolation
        isolation: Literal["current", "worktree", "clone"] | None = None,
        branch_name: str | None = None,
        base_branch: str | None = None,
        clone_id: str | None = None,
        # Execution
        workflow: str | None = None,
        mode: Literal["terminal", "embedded", "headless", "self"] | None = None,
        initial_step: str | None = None,
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
            agent: Agent definition name (defaults to "default")
            task_id: Optional - link to task (supports N, #N, UUID)
            isolation: Isolation mode (current/worktree/clone)
            branch_name: Git branch name (auto-generated from task if not provided)
            base_branch: Base branch for worktree/clone
            workflow: Workflow to use
            mode: Execution mode (terminal/embedded/headless/self).
                  'self' activates workflow on caller session instead of spawning.
            initial_step: For mode=self, start at specific step (defaults to first)
            terminal: Terminal type for terminal mode
            provider: AI provider (claude/gemini/codex/cursor/windsurf/copilot)
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

        # Load agent definition (defaults to "default")
        agent_def = loader.load(agent)
        if agent_def is None and agent != "default":
            return {"success": False, "error": f"Agent '{agent}' not found"}

        # Check orchestrator workflow enforcement:
        # If agent has a default workflow with mode: self (orchestrator), then
        # non-default workflows can only be spawned by sessions running the orchestrator.
        if agent_def and workflow and workflow != agent_def.default_workflow:
            orchestrator_wf = agent_def.get_orchestrator_workflow()
            if orchestrator_wf:
                # Get parent session's active workflow from WorkflowState
                # (not Session.workflow_name, which is for terminal pickup metadata)
                parent_workflow: str | None = None
                if state_manager and resolved_parent_session_id:
                    try:
                        parent_state = state_manager.get_state(resolved_parent_session_id)
                        if parent_state:
                            parent_workflow = parent_state.workflow_name
                    except Exception as e:
                        logger.warning(f"Could not get parent session workflow state: {e}")
                        return {
                            "success": False,
                            "error": (
                                f"Could not verify parent session workflow state for orchestrator enforcement: {e}. "
                                f"Ensure the orchestrator workflow is active before spawning '{agent}' with workflow='{workflow}'."
                            ),
                        }

                # Build expected orchestrator workflow names
                # Could be "agent:workflow" (inline) or file reference
                orchestrator_spec = agent_def.get_workflow_spec(orchestrator_wf)
                expected_names = {
                    f"{agent_def.name}:{orchestrator_wf}",  # Inline: meeseeks:box
                    f"{agent}:{orchestrator_wf}",  # Using param agent name
                    orchestrator_wf,  # Just the workflow key
                }
                if orchestrator_spec and orchestrator_spec.file:
                    expected_names.add(orchestrator_spec.file.removesuffix(".yaml"))

                if parent_workflow not in expected_names:
                    return {
                        "success": False,
                        "error": (
                            f"Cannot spawn '{agent}' with workflow='{workflow}' directly. "
                            f"The '{orchestrator_wf}' orchestrator workflow must be active first.\n\n"
                            f"Either:\n"
                            f'1. Use spawn_agent(agent="{agent}") without workflow param '
                            f"(activates orchestrator in your session)\n"
                            f"2. Or activate the orchestrator first: "
                            f'activate_workflow(name="{agent_def.get_effective_workflow(orchestrator_wf)}")'
                        ),
                    }

        # Check internal workflow enforcement:
        # Workflows marked `internal: true` can only be spawned by sessions
        # running the agent's orchestrator workflow.
        if agent_def and workflow and agent_def.workflows and workflow in agent_def.workflows:
            wf_spec = agent_def.workflows[workflow]
            if wf_spec.internal:
                orchestrator_wf = agent_def.get_orchestrator_workflow()
                if orchestrator_wf:
                    # Reuse the same orchestrator parent check pattern
                    parent_workflow = None
                    if state_manager and resolved_parent_session_id:
                        try:
                            parent_state = state_manager.get_state(resolved_parent_session_id)
                            if parent_state:
                                parent_workflow = parent_state.workflow_name
                        except Exception as e:
                            logger.warning(f"Could not get parent session workflow state: {e}")
                            return {
                                "success": False,
                                "error": (
                                    f"Could not verify parent session workflow state for "
                                    f"internal workflow enforcement: {e}. "
                                    f"Ensure the orchestrator workflow is active before "
                                    f"spawning '{agent}' with workflow='{workflow}'."
                                ),
                            }

                    orchestrator_spec = agent_def.get_workflow_spec(orchestrator_wf)
                    expected_names = {
                        f"{agent_def.name}:{orchestrator_wf}",
                        f"{agent}:{orchestrator_wf}",
                        orchestrator_wf,
                    }
                    if orchestrator_spec and orchestrator_spec.file:
                        expected_names.add(orchestrator_spec.file.removesuffix(".yaml"))

                    if parent_workflow not in expected_names:
                        return {
                            "success": False,
                            "error": (
                                f"Cannot spawn '{agent}' with workflow='{workflow}' — "
                                f"it is marked as internal and can only be spawned by "
                                f"sessions running the '{orchestrator_wf}' orchestrator.\n\n"
                                f"Either:\n"
                                f'1. Use spawn_agent(agent="{agent}") without workflow param '
                                f"(activates orchestrator in your session)\n"
                                f"2. Or activate the orchestrator first: "
                                f'activate_workflow(name="{agent_def.get_effective_workflow(orchestrator_wf)}")'
                            ),
                        }
                else:
                    # Internal workflow but no orchestrator — block unconditionally
                    return {
                        "success": False,
                        "error": (
                            f"Cannot spawn '{agent}' with workflow='{workflow}' — "
                            f"it is marked as internal but the agent has no orchestrator "
                            f"workflow configured."
                        ),
                    }

        # Determine effective workflow using agent's named workflows map
        # Resolution: explicit param > agent's workflows map > default_workflow
        effective_workflow: str | None = None
        inline_workflow_spec = None

        if agent_def:
            effective_workflow = agent_def.get_effective_workflow(workflow)

            # Check if this is an inline workflow that needs registration
            if workflow and agent_def.workflows and workflow in agent_def.workflows:
                spec = agent_def.workflows[workflow]
                if spec.is_inline():
                    inline_workflow_spec = spec
            elif (
                not workflow
                and agent_def.default_workflow
                and agent_def.workflows
                and agent_def.default_workflow in agent_def.workflows
            ):
                spec = agent_def.workflows[agent_def.default_workflow]
                if spec.is_inline():
                    inline_workflow_spec = spec
        elif workflow:
            effective_workflow = workflow

        # Get project_path for workflow lookup
        ctx = get_project_context(Path(project_path) if project_path else None)
        wf_project_path = ctx.get("project_path") if ctx else None

        # Register inline workflow if needed
        if inline_workflow_spec and effective_workflow:
            wf_loader.register_inline_workflow(
                effective_workflow, inline_workflow_spec.model_dump(), project_path=wf_project_path
            )

        # Validate workflow exists if specified (skip for inline that we just registered)
        if effective_workflow and not inline_workflow_spec:
            loaded_workflow = await wf_loader.load_workflow(
                effective_workflow, project_path=wf_project_path
            )
            if loaded_workflow is None:
                return {
                    "success": False,
                    "error": f"Workflow '{effective_workflow}' not found. "
                    f"Check available workflows with list_workflows().",
                }

        # Determine workflow_key for mode resolution
        # Use explicit workflow param, or fall back to default_workflow key
        resolved_workflow_key = workflow
        if resolved_workflow_key is None and agent_def and agent_def.default_workflow:
            resolved_workflow_key = agent_def.default_workflow

        # Delegate to spawn_agent_impl
        return await spawn_agent_impl(
            prompt=prompt,
            runner=runner,
            agent_def=agent_def,
            agent_lookup_name=agent,
            task_id=task_id,
            task_manager=task_manager,
            isolation=isolation,
            branch_name=branch_name,
            base_branch=base_branch,
            clone_id=clone_id,
            worktree_storage=worktree_storage,
            git_manager=git_manager,
            clone_storage=clone_storage,
            clone_manager=clone_manager,
            workflow=effective_workflow,
            workflow_key=resolved_workflow_key,  # Original key (e.g., "box") for mode resolution
            mode=mode,
            initial_step=initial_step,
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
            # For mode=self
            workflow_loader=wf_loader,
            state_manager=state_manager,
            session_manager=session_manager,
            db=db,
        )

    return registry
