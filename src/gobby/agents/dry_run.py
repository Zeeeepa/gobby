"""
Agent spawn dry-run evaluator.

Simulates a spawn_agent call without executing, reporting what would happen
and identifying misconfigurations before any resources are allocated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from gobby.workflows.dry_run import EvaluationItem, WorkflowEvaluation

if TYPE_CHECKING:
    from gobby.agents.definitions import AgentDefinitionLoader
    from gobby.agents.runner import AgentRunner
    from gobby.mcp_proxy.manager import MCPClientManager
    from gobby.workflows.loader import WorkflowLoader
    from gobby.workflows.state_manager import WorkflowStateManager

logger = logging.getLogger(__name__)


@dataclass
class SpawnEvaluation:
    """Result of evaluating a spawn_agent dry-run."""

    can_spawn: bool
    items: list[EvaluationItem] = field(default_factory=list)

    # Agent resolution
    agent_name: str | None = None
    agent_found: bool = False
    agent_file_path: str | None = None
    effective_workflow: str | None = None
    effective_mode: str | None = None
    effective_isolation: str | None = None
    effective_provider: str | None = None
    effective_terminal: str | None = None
    branch_name: str | None = None

    # Embedded workflow evaluation
    workflow_evaluation: WorkflowEvaluation | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_spawn": self.can_spawn,
            "items": [i.to_dict() for i in self.items],
            "agent_name": self.agent_name,
            "agent_found": self.agent_found,
            "agent_file_path": self.agent_file_path,
            "effective_workflow": self.effective_workflow,
            "effective_mode": self.effective_mode,
            "effective_isolation": self.effective_isolation,
            "effective_provider": self.effective_provider,
            "effective_terminal": self.effective_terminal,
            "branch_name": self.branch_name,
            "workflow_evaluation": self.workflow_evaluation.to_dict()
            if self.workflow_evaluation
            else None,
        }

    @property
    def errors(self) -> list[EvaluationItem]:
        return [i for i in self.items if i.level == "error"]

    @property
    def warnings(self) -> list[EvaluationItem]:
        return [i for i in self.items if i.level == "warning"]


async def evaluate_spawn(
    agent: str = "generic",
    workflow: str | None = None,
    task_id: str | None = None,
    isolation: str | None = None,
    mode: str | None = None,
    terminal: str = "auto",
    provider: str | None = None,
    branch_name: str | None = None,
    base_branch: str | None = None,
    parent_session_id: str | None = None,
    project_path: str | None = None,
    # Injected dependencies
    agent_loader: AgentDefinitionLoader | None = None,
    workflow_loader: WorkflowLoader | None = None,
    runner: AgentRunner | None = None,
    state_manager: WorkflowStateManager | None = None,
    session_manager: Any | None = None,
    git_manager: Any | None = None,
    worktree_storage: Any | None = None,
    clone_storage: Any | None = None,
    clone_manager: Any | None = None,
    task_manager: Any | None = None,
    mcp_manager: MCPClientManager | None = None,
) -> SpawnEvaluation:
    """
    Evaluate a spawn_agent call without executing.

    Checks agent definition, workflow resolution, isolation config,
    and runtime environment to identify issues before spawning.

    Args:
        agent: Agent name to evaluate.
        workflow: Optional workflow name override.
        task_id: Optional task ID for branch naming.
        isolation: Optional isolation mode override.
        mode: Optional execution mode override.
        terminal: Terminal type.
        provider: Optional provider override.
        branch_name: Optional explicit branch name.
        base_branch: Optional base branch.
        parent_session_id: Optional parent session for depth/mode checks.
        project_path: Optional project path.
        agent_loader: AgentDefinitionLoader instance.
        workflow_loader: WorkflowLoader instance.
        runner: AgentRunner for depth checks.
        state_manager: WorkflowStateManager for mode=self checks.
        session_manager: Session manager for resolution.
        git_manager: Git manager for isolation.
        worktree_storage: Worktree storage for isolation.
        clone_storage: Clone storage for isolation.
        clone_manager: Clone manager for isolation.
        task_manager: Task manager for task resolution.
        mcp_manager: MCPClientManager for semantic checks.

    Returns:
        SpawnEvaluation with all findings.
    """
    result = SpawnEvaluation(can_spawn=True, agent_name=agent)

    # ---- Layer 1: Agent Definition Resolution ----
    agent_def = None
    if agent_loader is not None:
        agent_def = agent_loader.load(agent)

    if agent_def is None:
        result.agent_found = False
        result.can_spawn = False
        result.items.append(
            EvaluationItem(
                layer="agent",
                level="error",
                code="AGENT_NOT_FOUND",
                message=f"Agent definition '{agent}' not found",
            )
        )
        return result

    result.agent_found = True

    # Resolve effective values
    eff_provider = provider or agent_def.provider
    eff_terminal = terminal or agent_def.terminal
    eff_isolation = isolation or agent_def.isolation or "current"

    result.effective_provider = eff_provider
    result.effective_terminal = eff_terminal
    result.effective_isolation = eff_isolation

    result.items.append(
        EvaluationItem(
            layer="agent",
            level="info",
            code="AGENT_RESOLVED",
            message=f"Agent '{agent}' found: provider={eff_provider}, mode={agent_def.mode}, terminal={eff_terminal}",
            detail={
                "provider": eff_provider,
                "mode": agent_def.mode,
                "terminal": eff_terminal,
                "isolation": eff_isolation,
                "model": agent_def.model,
                "timeout": agent_def.timeout,
                "max_turns": agent_def.max_turns,
            },
        )
    )

    # ---- Layer 2: Workflow Resolution ----
    # KEY CHECK: default_workflow set but NOT in workflows map
    if agent_def.default_workflow and agent_def.workflows:
        if agent_def.default_workflow not in agent_def.workflows:
            result.can_spawn = False
            result.items.append(
                EvaluationItem(
                    layer="workflow_resolution",
                    level="error",
                    code="WORKFLOW_KEY_MISMATCH",
                    message=(
                        f"default_workflow '{agent_def.default_workflow}' is not a key "
                        f"in workflows map. Available keys: {sorted(agent_def.workflows.keys())}"
                    ),
                    detail={
                        "default_workflow": agent_def.default_workflow,
                        "available_keys": sorted(agent_def.workflows.keys()),
                    },
                )
            )

    effective_workflow = agent_def.get_effective_workflow(workflow)
    eff_mode = mode or agent_def.get_effective_mode(workflow)
    result.effective_workflow = effective_workflow
    result.effective_mode = eff_mode

    if effective_workflow:
        result.items.append(
            EvaluationItem(
                layer="workflow_resolution",
                level="info",
                code="WORKFLOW_RESOLVED",
                message=f"Workflow resolved to '{effective_workflow}' (mode={eff_mode})",
                detail={"workflow": effective_workflow, "mode": eff_mode},
            )
        )

        # Validate workflow for agent usage
        if workflow_loader is not None:
            is_valid, error_msg = await workflow_loader.validate_workflow_for_agent(
                effective_workflow,
                project_path,
            )
            if not is_valid:
                result.can_spawn = False
                result.items.append(
                    EvaluationItem(
                        layer="workflow_resolution",
                        level="error",
                        code="WORKFLOW_INVALID_FOR_AGENT",
                        message=error_msg
                        or f"Workflow '{effective_workflow}' is not valid for agent spawning",
                    )
                )
    else:
        result.items.append(
            EvaluationItem(
                layer="workflow_resolution",
                level="info",
                code="NO_WORKFLOW",
                message="No workflow configured — agent will run without workflow enforcement",
            )
        )

    # ---- Layer 3: Orchestrator Enforcement ----
    orchestrator_wf = agent_def.get_orchestrator_workflow()
    if orchestrator_wf and workflow and workflow != orchestrator_wf:
        if parent_session_id and state_manager:
            parent_state = state_manager.get_state(parent_session_id)
            if parent_state and parent_state.workflow_name != orchestrator_wf:
                result.items.append(
                    EvaluationItem(
                        layer="orchestrator",
                        level="warning",
                        code="ORCHESTRATOR_MISMATCH",
                        message=(
                            f"Non-default workflow '{workflow}' requested but parent session "
                            f"does not have orchestrator workflow '{orchestrator_wf}' active"
                        ),
                        detail={
                            "requested_workflow": workflow,
                            "orchestrator": orchestrator_wf,
                            "parent_workflow": parent_state.workflow_name,
                        },
                    )
                )
        else:
            result.items.append(
                EvaluationItem(
                    layer="orchestrator",
                    level="info",
                    code="ORCHESTRATOR_NOT_EVALUATED",
                    message="Orchestrator enforcement not evaluated (no parent session provided)",
                )
            )

    # ---- Layer 3b: Internal Workflow Enforcement ----
    if (
        agent_def
        and workflow
        and agent_def.workflows
        and workflow in agent_def.workflows
        and agent_def.workflows[workflow].internal
    ):
        orchestrator_wf = agent_def.get_orchestrator_workflow()
        if orchestrator_wf:
            if parent_session_id and state_manager:
                parent_state = state_manager.get_state(parent_session_id)
                parent_wf = parent_state.workflow_name if parent_state else None

                orchestrator_spec = agent_def.get_workflow_spec(orchestrator_wf)
                expected_names = {
                    f"{agent_def.name}:{orchestrator_wf}",
                    f"{agent}:{orchestrator_wf}",
                    orchestrator_wf,
                }
                if orchestrator_spec and orchestrator_spec.file:
                    expected_names.add(orchestrator_spec.file.removesuffix(".yaml"))

                if parent_wf not in expected_names:
                    result.items.append(
                        EvaluationItem(
                            layer="orchestrator",
                            level="warning",
                            code="INTERNAL_WORKFLOW_BLOCKED",
                            message=(
                                f"Workflow '{workflow}' is marked internal and can only be "
                                f"spawned by sessions running the '{orchestrator_wf}' orchestrator"
                            ),
                            detail={
                                "requested_workflow": workflow,
                                "orchestrator": orchestrator_wf,
                                "parent_workflow": parent_wf,
                            },
                        )
                    )
            else:
                result.items.append(
                    EvaluationItem(
                        layer="orchestrator",
                        level="warning",
                        code="INTERNAL_WORKFLOW_BLOCKED",
                        message=(
                            f"Workflow '{workflow}' is marked internal and requires "
                            f"the '{orchestrator_wf}' orchestrator — no parent session provided"
                        ),
                        detail={
                            "requested_workflow": workflow,
                            "orchestrator": orchestrator_wf,
                        },
                    )
                )
        else:
            result.items.append(
                EvaluationItem(
                    layer="orchestrator",
                    level="warning",
                    code="INTERNAL_WORKFLOW_BLOCKED",
                    message=(
                        f"Workflow '{workflow}' is marked internal but agent has no "
                        f"orchestrator workflow configured"
                    ),
                    detail={"requested_workflow": workflow},
                )
            )

    # ---- Layer 4: Isolation Resolution ----
    if eff_isolation == "worktree":
        if git_manager is None or worktree_storage is None:
            result.items.append(
                EvaluationItem(
                    layer="isolation",
                    level="warning",
                    code="ISOLATION_DEPS_MISSING",
                    message="Worktree isolation requires git_manager and worktree_storage",
                )
            )
        elif worktree_storage is not None and project_path:
            # Check for existing worktree
            from gobby.agents.isolation import SpawnConfig, generate_branch_name

            config = SpawnConfig(
                prompt="",
                task_id=task_id,
                task_title=None,
                task_seq_num=None,
                branch_name=branch_name,
                branch_prefix=agent_def.branch_prefix,
                base_branch=base_branch or agent_def.base_branch,
                project_id="",
                project_path=project_path,
                provider=eff_provider,
                parent_session_id=parent_session_id or "",
            )
            computed_branch = generate_branch_name(config)
            result.branch_name = computed_branch

            try:
                from gobby.utils.project_context import get_project_context

                ctx = get_project_context()
                proj_id = ctx.get("id", "") if ctx else ""
                existing = worktree_storage.get_by_branch(proj_id, computed_branch)
                if existing:
                    result.items.append(
                        EvaluationItem(
                            layer="isolation",
                            level="info",
                            code="EXISTING_WORKTREE",
                            message=f"Existing worktree found for branch '{computed_branch}' — will be reused",
                            detail={"branch": computed_branch, "worktree_id": existing.id},
                        )
                    )
            except Exception:
                logger.debug("Failed to check existing worktree for branch '%s'", computed_branch, exc_info=True)

    elif eff_isolation == "clone":
        if clone_manager is None or clone_storage is None:
            result.items.append(
                EvaluationItem(
                    layer="isolation",
                    level="warning",
                    code="ISOLATION_DEPS_MISSING",
                    message="Clone isolation requires clone_manager and clone_storage",
                )
            )
        elif clone_storage is not None and project_path:
            from gobby.agents.isolation import SpawnConfig, generate_branch_name

            config = SpawnConfig(
                prompt="",
                task_id=task_id,
                task_title=None,
                task_seq_num=None,
                branch_name=branch_name,
                branch_prefix=agent_def.branch_prefix,
                base_branch=base_branch or agent_def.base_branch,
                project_id="",
                project_path=project_path,
                provider=eff_provider,
                parent_session_id=parent_session_id or "",
            )
            computed_branch = generate_branch_name(config)
            result.branch_name = computed_branch

            try:
                from gobby.utils.project_context import get_project_context

                ctx = get_project_context()
                proj_id = ctx.get("id", "") if ctx else ""
                existing = clone_storage.get_by_branch(proj_id, computed_branch)
                if existing:
                    result.items.append(
                        EvaluationItem(
                            layer="isolation",
                            level="info",
                            code="EXISTING_CLONE",
                            message=f"Existing clone found for branch '{computed_branch}' — will be reused",
                            detail={"branch": computed_branch, "clone_id": existing.id},
                        )
                    )
            except Exception:
                logger.debug("Failed to check existing clone for branch '%s'", computed_branch, exc_info=True)

    # ---- Layer 5: Runtime Environment ----
    if parent_session_id and runner is not None:
        can_spawn_result, reason, _depth = runner.can_spawn(parent_session_id)
        if not can_spawn_result:
            result.can_spawn = False
            result.items.append(
                EvaluationItem(
                    layer="runtime",
                    level="error",
                    code="SPAWN_DEPTH_EXCEEDED",
                    message=f"Cannot spawn: {reason}",
                    detail={"reason": reason},
                )
            )
        else:
            result.items.append(
                EvaluationItem(
                    layer="runtime",
                    level="info",
                    code="SPAWN_DEPTH_OK",
                    message=f"Spawn depth check passed: {reason}",
                )
            )

    # mode=self: check for existing step workflow on parent session
    if eff_mode == "self" and parent_session_id and state_manager:
        parent_state = state_manager.get_state(parent_session_id)
        if (
            parent_state
            and parent_state.workflow_name
            and parent_state.workflow_name != "__lifecycle__"
        ):
            result.items.append(
                EvaluationItem(
                    layer="runtime",
                    level="warning",
                    code="SELF_MODE_WORKFLOW_CONFLICT",
                    message=(
                        f"mode=self would activate workflow on parent session, but parent "
                        f"already has workflow '{parent_state.workflow_name}' active"
                    ),
                    detail={"parent_workflow": parent_state.workflow_name},
                )
            )

    # Terminal availability check
    if eff_mode in ("terminal", "embedded") and eff_terminal == "auto":
        try:
            from gobby.agents.spawn import TerminalSpawner

            spawner = TerminalSpawner()
            available = spawner.get_available_terminals()
            if not available:
                result.items.append(
                    EvaluationItem(
                        layer="runtime",
                        level="warning",
                        code="NO_TERMINALS_AVAILABLE",
                        message="No terminal emulators detected — agent may fail to spawn",
                    )
                )
            else:
                result.items.append(
                    EvaluationItem(
                        layer="runtime",
                        level="info",
                        code="TERMINALS_AVAILABLE",
                        message=f"Available terminals: {[t.value if hasattr(t, 'value') else str(t) for t in available]}",
                    )
                )
        except Exception:
            logger.debug("Failed to check terminal availability", exc_info=True)

    # ---- Layer 6: Workflow Evaluation (delegates to evaluate_workflow) ----
    if effective_workflow and workflow_loader is not None:
        from gobby.workflows.dry_run import evaluate_workflow

        wf_eval = await evaluate_workflow(
            effective_workflow,
            workflow_loader,
            project_path,
            mcp_manager,
        )
        result.workflow_evaluation = wf_eval

        # Merge workflow items into top-level items
        for item in wf_eval.items:
            result.items.append(item)

        if not wf_eval.valid:
            result.can_spawn = False

    # Final validity determination
    if any(i.level == "error" for i in result.items):
        result.can_spawn = False

    return result
