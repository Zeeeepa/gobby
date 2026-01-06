"""Internal registry initialization."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gobby.mcp_proxy.tools.internal import InternalRegistryManager

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.config.app import DaemonConfig
    from gobby.llm.service import LLMService
    from gobby.mcp_proxy.metrics import ToolMetricsManager
    from gobby.memory.manager import MemoryManager
    from gobby.sessions.manager import SessionManager
    from gobby.skills import SkillLearner
    from gobby.storage.session_messages import LocalSessionMessageManager
    from gobby.storage.sessions import LocalSessionManager
    from gobby.storage.skills import LocalSkillManager
    from gobby.storage.tasks import LocalTaskManager
    from gobby.storage.worktrees import LocalWorktreeManager
    from gobby.sync.skills import SkillSyncManager
    from gobby.sync.tasks import TaskSyncManager
    from gobby.tasks.expansion import TaskExpander
    from gobby.tasks.validation import TaskValidator
    from gobby.worktrees.git import WorktreeGitManager

logger = logging.getLogger("gobby.mcp.registries")


def setup_internal_registries(
    _config: DaemonConfig | None,
    _session_manager: SessionManager | None = None,
    memory_manager: MemoryManager | None = None,
    skill_learner: SkillLearner | None = None,
    task_manager: LocalTaskManager | None = None,
    sync_manager: TaskSyncManager | None = None,
    task_expander: TaskExpander | None = None,
    task_validator: TaskValidator | None = None,
    message_manager: LocalSessionMessageManager | None = None,
    skill_storage: LocalSkillManager | None = None,
    local_session_manager: LocalSessionManager | None = None,
    skill_sync_manager: SkillSyncManager | None = None,
    metrics_manager: ToolMetricsManager | None = None,
    llm_service: LLMService | None = None,
    agent_runner: AgentRunner | None = None,
    worktree_storage: LocalWorktreeManager | None = None,
    git_manager: WorktreeGitManager | None = None,
    project_id: str | None = None,
) -> InternalRegistryManager:
    """
    Setup internal MCP registries (tasks, messages, memory, skills, metrics, agents, worktrees).

    Args:
        _config: Daemon configuration (reserved for future use)
        _session_manager: Session manager (reserved for future use)
        memory_manager: Memory manager for memory operations
        skill_learner: Skill learner for skill extraction
        task_manager: Task storage manager
        sync_manager: Task sync manager for git sync
        task_expander: Task expander for AI expansion
        task_validator: Task validator for validation
        message_manager: Message storage manager
        skill_storage: Skill storage manager
        local_session_manager: Local session manager for session CRUD
        skill_sync_manager: Skill sync manager for skill export
        metrics_manager: Tool metrics manager for metrics operations
        llm_service: LLM service for AI-powered operations
        agent_runner: Agent runner for spawning subagents
        worktree_storage: Worktree storage manager for worktree operations
        git_manager: Git manager for git worktree operations
        project_id: Default project ID for worktree operations

    Returns:
        InternalRegistryManager containing all registries
    """
    manager = InternalRegistryManager()

    # Initialize tasks registry if enabled and task_manager is available
    if _config is None:
        gobby_tasks_enabled = False
        logger.warning("Tasks registry not initialized: config is None")
    else:
        gobby_tasks_enabled = _config.get_gobby_tasks_config().enabled
        if not gobby_tasks_enabled:
            logger.debug("Tasks registry disabled by config")

    if gobby_tasks_enabled:
        if task_manager is None:
            logger.warning("Tasks registry not initialized: task_manager is None")
        elif sync_manager is None:
            logger.warning("Tasks registry not initialized: sync_manager is None")
        else:
            from gobby.mcp_proxy.tools.tasks import create_task_registry

            tasks_registry = create_task_registry(
                task_manager=task_manager,
                sync_manager=sync_manager,
                task_expander=task_expander,
                task_validator=task_validator,
                config=_config,
            )
            manager.add_registry(tasks_registry)
            logger.debug("Tasks registry initialized")

    # Initialize sessions registry (messages + session CRUD)
    # Register if either message_manager or local_session_manager is available
    if message_manager is not None or local_session_manager is not None:
        from gobby.mcp_proxy.tools.session_messages import create_session_messages_registry

        session_messages_registry = create_session_messages_registry(
            message_manager=message_manager,
            session_manager=local_session_manager,
        )
        manager.add_registry(session_messages_registry)
        logger.debug("Sessions registry initialized")

    # Initialize memory registry if memory_manager is available
    if memory_manager is not None:
        from gobby.mcp_proxy.tools.memory import create_memory_registry

        memory_registry = create_memory_registry(
            memory_manager=memory_manager,
            llm_service=llm_service,
        )
        manager.add_registry(memory_registry)
        logger.debug("Memory registry initialized")

    # Initialize skills registry if skill_storage is available
    if skill_storage is not None:
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        skills_registry = create_skills_registry(
            storage=skill_storage,
            learner=skill_learner,
            session_manager=local_session_manager,
            sync_manager=skill_sync_manager,
        )
        manager.add_registry(skills_registry)
        logger.debug("Skills registry initialized")

    # Initialize workflows registry (always available)
    from gobby.mcp_proxy.tools.workflows import create_workflows_registry

    workflows_registry = create_workflows_registry(
        session_manager=local_session_manager,
    )
    manager.add_registry(workflows_registry)
    logger.debug("Workflows registry initialized")

    # Initialize metrics registry if metrics_manager is available
    if metrics_manager is not None:
        from gobby.mcp_proxy.tools.metrics import create_metrics_registry

        metrics_registry = create_metrics_registry(
            metrics_manager=metrics_manager,
        )
        manager.add_registry(metrics_registry)
        logger.debug("Metrics registry initialized")

    # Initialize agents registry if agent_runner is available
    if agent_runner is not None:
        from gobby.mcp_proxy.tools.agents import create_agents_registry

        agents_registry = create_agents_registry(
            runner=agent_runner,
        )
        manager.add_registry(agents_registry)
        logger.debug("Agents registry initialized")

    # Initialize worktrees registry if worktree_storage is available
    if worktree_storage is not None:
        from gobby.mcp_proxy.tools.worktrees import create_worktrees_registry

        worktrees_registry = create_worktrees_registry(
            worktree_storage=worktree_storage,
            git_manager=git_manager,
            project_id=project_id,
        )
        manager.add_registry(worktrees_registry)
        logger.debug("Worktrees registry initialized")

    logger.info(f"Internal registries initialized: {len(manager)} registries")
    return manager


# Re-export for convenience
__all__ = [
    "setup_internal_registries",
    "InternalRegistryManager",
]
