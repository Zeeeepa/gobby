"""
Service container for dependency injection in Gobby daemon.

Holds references to singleton services to avoid prop-drilling in HTTPServer
and other components.
"""

from dataclasses import dataclass
from typing import Any

from gobby.config.app import DaemonConfig
from gobby.llm import LLMService
from gobby.memory.manager import MemoryManager
from gobby.storage.clones import LocalCloneManager
from gobby.storage.database import DatabaseProtocol
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.tasks import LocalTaskManager
from gobby.storage.worktrees import LocalWorktreeManager
from gobby.sync.memories import MemorySyncManager
from gobby.sync.tasks import TaskSyncManager


@dataclass
class ServiceContainer:
    """Container for daemon services."""

    # Core Infrastructure
    config: DaemonConfig
    database: DatabaseProtocol

    # Core Managers
    session_manager: LocalSessionManager
    task_manager: LocalTaskManager

    # Sync Managers
    task_sync_manager: TaskSyncManager | None = None
    memory_sync_manager: MemorySyncManager | None = None

    # Advanced Features
    memory_manager: MemoryManager | None = None
    llm_service: LLMService | None = None

    # MCP & Agents
    mcp_manager: Any | None = None  # MCPClientManager
    mcp_db_manager: Any | None = None  # LocalMCPManager
    metrics_manager: Any | None = None  # ToolMetricsManager
    agent_runner: Any | None = None  # AgentRunner
    message_processor: Any | None = None  # SessionMessageProcessor
    message_manager: Any | None = None  # LocalSessionMessageManager

    # Validation & Git
    task_validator: Any | None = None  # TaskValidator
    worktree_storage: LocalWorktreeManager | None = None
    clone_storage: LocalCloneManager | None = None
    git_manager: Any | None = None  # WorktreeGitManager

    # Context
    project_id: str | None = None
    websocket_server: Any | None = None
