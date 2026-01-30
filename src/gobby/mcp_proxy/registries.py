"""Internal registry initialization."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from gobby.mcp_proxy.tools.internal import InternalRegistryManager

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.config.app import DaemonConfig
    from gobby.llm.service import LLMService
    from gobby.mcp_proxy.metrics import ToolMetricsManager
    from gobby.mcp_proxy.services.tool_proxy import ToolProxyService
    from gobby.memory.manager import MemoryManager
    from gobby.sessions.manager import SessionManager
    from gobby.storage.clones import LocalCloneManager
    from gobby.storage.inter_session_messages import InterSessionMessageManager
    from gobby.storage.merge_resolutions import MergeResolutionManager
    from gobby.storage.session_messages import LocalSessionMessageManager
    from gobby.storage.sessions import LocalSessionManager
    from gobby.storage.tasks import LocalTaskManager
    from gobby.storage.worktrees import LocalWorktreeManager
    from gobby.sync.tasks import TaskSyncManager
    from gobby.tasks.validation import TaskValidator
    from gobby.worktrees.git import WorktreeGitManager
    from gobby.worktrees.merge import MergeResolver

logger = logging.getLogger("gobby.mcp.registries")


def setup_internal_registries(
    _config: DaemonConfig | None,
    _session_manager: SessionManager | None = None,
    memory_manager: MemoryManager | None = None,
    task_manager: LocalTaskManager | None = None,
    sync_manager: TaskSyncManager | None = None,
    task_validator: TaskValidator | None = None,
    message_manager: LocalSessionMessageManager | None = None,
    local_session_manager: LocalSessionManager | None = None,
    metrics_manager: ToolMetricsManager | None = None,
    llm_service: LLMService | None = None,
    agent_runner: AgentRunner | None = None,
    worktree_storage: LocalWorktreeManager | None = None,
    clone_storage: LocalCloneManager | None = None,
    git_manager: WorktreeGitManager | None = None,
    merge_storage: MergeResolutionManager | None = None,
    merge_resolver: MergeResolver | None = None,
    project_id: str | None = None,
    tool_proxy_getter: Callable[[], ToolProxyService | None] | None = None,
    inter_session_message_manager: InterSessionMessageManager | None = None,
) -> InternalRegistryManager:
    """
    Setup internal MCP registries (tasks, messages, memory, metrics, agents, worktrees).

    Args:
        _config: Daemon configuration (reserved for future use)
        _session_manager: Session manager (reserved for future use)
        memory_manager: Memory manager for memory operations
        task_manager: Task storage manager
        sync_manager: Task sync manager for git sync
        task_validator: Task validator for validation
        message_manager: Message storage manager
        local_session_manager: Local session manager for session CRUD
        metrics_manager: Tool metrics manager for metrics operations
        llm_service: LLM service for AI-powered operations
        agent_runner: Agent runner for spawning subagents
        worktree_storage: Worktree storage manager for worktree operations
        git_manager: Git manager for git worktree operations
        merge_storage: Merge storage manager for conflict resolution
        merge_resolver: Merge resolver for AI resolution
        project_id: Default project ID for worktree operations
        tool_proxy_getter: Callable that returns ToolProxyService for routing
            tool calls in in-process agents. Called lazily during agent execution.
        inter_session_message_manager: Inter-session message manager for agent messaging

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
                task_validator=task_validator,
                config=_config,
                agent_runner=agent_runner,
                worktree_storage=worktree_storage,
                git_manager=git_manager,
                project_id=project_id,
            )
            manager.add_registry(tasks_registry)
            logger.debug("Tasks registry initialized")

    # Initialize sessions registry (messages + session CRUD)
    # Register if either message_manager or local_session_manager is available
    if message_manager is not None or local_session_manager is not None:
        from gobby.mcp_proxy.tools.sessions import create_session_messages_registry

        session_messages_registry = create_session_messages_registry(
            message_manager=message_manager,
            session_manager=local_session_manager,
        )
        manager.add_registry(session_messages_registry)
        logger.debug("Sessions registry initialized")

    # Initialize memory registry if memory_manager is available
    if memory_manager is not None:
        from gobby.mcp_proxy.tools.memory import create_memory_registry

        # Set llm_service on memory_manager for remember_with_image support
        if llm_service is not None:
            memory_manager.llm_service = llm_service

        memory_registry = create_memory_registry(
            memory_manager=memory_manager,
            llm_service=llm_service,
        )
        manager.add_registry(memory_registry)
        logger.debug("Memory registry initialized")

    # Initialize workflows registry (always available)
    from gobby.mcp_proxy.tools.workflows import create_workflows_registry

    workflows_registry = create_workflows_registry(
        session_manager=local_session_manager,
        db=getattr(local_session_manager, "db", None) if local_session_manager else None,
    )
    manager.add_registry(workflows_registry)
    logger.debug("Workflows registry initialized")

    # Initialize metrics registry if metrics_manager is available
    if metrics_manager is not None:
        from gobby.mcp_proxy.tools.metrics import create_metrics_registry

        # Get daily budget from conductor config if available
        daily_budget_usd = 50.0  # Default
        if _config is not None:
            conductor_config = _config.conductor
            if conductor_config is not None:
                daily_budget_usd = conductor_config.daily_budget_usd

        metrics_registry = create_metrics_registry(
            metrics_manager=metrics_manager,
            session_storage=local_session_manager,
            daily_budget_usd=daily_budget_usd,
        )
        manager.add_registry(metrics_registry)
        logger.debug("Metrics registry initialized with token tracking")

    # Initialize agents registry if agent_runner is available
    if agent_runner is not None:
        from gobby.agents.definitions import AgentDefinitionLoader
        from gobby.mcp_proxy.tools.agents import create_agents_registry

        # Create clone git manager if we have a git manager
        clone_git_manager = None
        if git_manager is not None:
            try:
                from gobby.clones.git import CloneGitManager

                clone_git_manager = CloneGitManager(git_manager.repo_path)
            except Exception as e:
                logger.debug(f"CloneGitManager not available for spawn_agent: {e}")

        agents_registry = create_agents_registry(
            runner=agent_runner,
            agent_loader=AgentDefinitionLoader(),
            session_manager=local_session_manager,
            task_manager=task_manager,
            worktree_storage=worktree_storage,
            git_manager=git_manager,
            clone_storage=clone_storage,
            clone_manager=clone_git_manager,
        )

        # Add inter-agent messaging tools if message manager and session manager are available
        if inter_session_message_manager is not None and local_session_manager is not None:
            from gobby.mcp_proxy.tools.agent_messaging import add_messaging_tools

            add_messaging_tools(
                registry=agents_registry,
                message_manager=inter_session_message_manager,
                session_manager=local_session_manager,
            )
            logger.debug("Agent messaging tools added to agents registry")

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

    # Initialize clones registry if clone_storage is available
    if clone_storage is not None:
        from gobby.clones.git import CloneGitManager
        from gobby.mcp_proxy.tools.clones import create_clones_registry

        # Create CloneGitManager from the same repo path as WorktreeGitManager
        clone_git_manager = None
        if git_manager is not None:
            try:
                clone_git_manager = CloneGitManager(git_manager.repo_path)
            except Exception as e:
                logger.warning(f"Failed to create CloneGitManager: {e}")

        # Only create clones registry if we have a git manager
        if clone_git_manager is not None:
            clones_registry = create_clones_registry(
                clone_storage=clone_storage,
                git_manager=clone_git_manager,
                project_id=project_id or "",
            )
            manager.add_registry(clones_registry)
            logger.debug("Clones registry initialized")
        else:
            logger.debug("Clones registry not initialized: CloneGitManager not available")

    # Initialize merge resolution registry if merge components are available
    if merge_storage is not None and merge_resolver is not None:
        from gobby.mcp_proxy.tools.merge import create_merge_registry

        merge_registry = create_merge_registry(
            merge_storage=merge_storage,
            merge_resolver=merge_resolver,
            git_manager=git_manager,
            worktree_manager=worktree_storage,
        )
        manager.add_registry(merge_registry)
        logger.debug("Merge registry initialized")

    # Initialize hub registry (cross-project queries) if config has database_path
    if _config is not None and hasattr(_config, "database_path"):
        from pathlib import Path

        from gobby.mcp_proxy.tools.hub import create_hub_registry

        hub_db_path = Path(_config.database_path).expanduser()
        hub_registry = create_hub_registry(hub_db_path=hub_db_path)
        manager.add_registry(hub_registry)
        logger.debug("Hub registry initialized")

    # Initialize skills registry using the existing database from task_manager
    # to avoid creating a duplicate connection that would leak
    if task_manager is not None:
        from gobby.mcp_proxy.tools.skills import create_skills_registry

        skills_registry = create_skills_registry(
            db=task_manager.db,
            project_id=project_id,
        )
        manager.add_registry(skills_registry)
        logger.debug("Skills registry initialized")
    else:
        logger.debug("Skills registry not initialized: task_manager is None")

    # Initialize artifacts registry using the existing database from task_manager
    if task_manager is not None:
        from gobby.mcp_proxy.tools.artifacts import create_artifacts_registry

        artifacts_registry = create_artifacts_registry(
            db=task_manager.db,
            session_manager=local_session_manager,
        )
        manager.add_registry(artifacts_registry)
        logger.debug("Artifacts registry initialized")
    else:
        logger.debug("Artifacts registry not initialized: task_manager is None")

    logger.info(f"Internal registries initialized: {len(manager)} registries")
    return manager


# Re-export for convenience
__all__ = [
    "setup_internal_registries",
    "InternalRegistryManager",
]
