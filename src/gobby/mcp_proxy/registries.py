"""Internal registry initialization."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gobby.mcp_proxy.tools.internal import InternalRegistryManager

if TYPE_CHECKING:
    from gobby.config.app import DaemonConfig
    from gobby.memory.manager import MemoryManager
    from gobby.memory.skills import SkillLearner
    from gobby.sessions.manager import SessionManager
    from gobby.storage.messages import LocalMessageManager
    from gobby.storage.sessions import LocalSessionManager
    from gobby.storage.skills import LocalSkillManager
    from gobby.storage.tasks import LocalTaskManager
    from gobby.sync.memories import MemorySyncManager
    from gobby.sync.tasks import TaskSyncManager
    from gobby.tasks.expansion import TaskExpander
    from gobby.tasks.validation import TaskValidator

logger = logging.getLogger("gobby.mcp.registries")


def setup_internal_registries(
    _config: DaemonConfig,
    _session_manager: SessionManager | None = None,
    memory_manager: MemoryManager | None = None,
    skill_learner: SkillLearner | None = None,
    task_manager: LocalTaskManager | None = None,
    sync_manager: TaskSyncManager | None = None,
    task_expander: TaskExpander | None = None,
    task_validator: TaskValidator | None = None,
    message_manager: LocalMessageManager | None = None,
    skill_storage: LocalSkillManager | None = None,
    local_session_manager: LocalSessionManager | None = None,
    memory_sync_manager: MemorySyncManager | None = None,
) -> InternalRegistryManager:
    """
    Setup internal MCP registries (tasks, messages, memory, skills).

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
        memory_sync_manager: Memory sync manager for skill export

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

    # Initialize messages registry if message_manager is available
    if message_manager is not None:
        from gobby.mcp_proxy.tools.messages import create_messages_registry

        messages_registry = create_messages_registry(
            message_manager=message_manager,
        )
        manager.add_registry(messages_registry)
        logger.debug("Messages registry initialized")

    # Initialize memory registry if memory_manager is available
    if memory_manager is not None:
        from gobby.mcp_proxy.tools.memory import create_memory_registry

        memory_registry = create_memory_registry(
            memory_manager=memory_manager,
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
            sync_manager=memory_sync_manager,
        )
        manager.add_registry(skills_registry)
        logger.debug("Skills registry initialized")

    logger.info(f"Internal registries initialized: {len(manager)} registries")
    return manager


# Re-export for convenience
__all__ = [
    "setup_internal_registries",
    "InternalRegistryManager",
]
