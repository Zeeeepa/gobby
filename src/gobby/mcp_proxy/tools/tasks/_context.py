"""Registry context for task tools.

Provides RegistryContext dataclass that bundles shared state and helpers
used across task tool modules.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from gobby.storage.projects import LocalProjectManager
from gobby.storage.session_tasks import SessionTaskManager
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import LocalTaskManager
from gobby.utils.project_context import get_project_context
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.state_manager import WorkflowStateManager

if TYPE_CHECKING:
    from gobby.agents.runner import AgentRunner
    from gobby.config.app import DaemonConfig
    from gobby.config.tasks import TaskValidationConfig
    from gobby.sync.tasks import TaskSyncManager
    from gobby.tasks.validation import TaskValidator


@dataclass
class RegistryContext:
    """Shared context for task tool registries.

    Bundles managers, config, and helper methods used across all task tools.
    """

    # Core managers
    task_manager: LocalTaskManager
    sync_manager: "TaskSyncManager"

    # Optional managers
    task_validator: "TaskValidator | None" = None
    agent_runner: "AgentRunner | None" = None
    config: "DaemonConfig | None" = None

    # Derived managers (initialized in __post_init__)
    dep_manager: TaskDependencyManager = field(init=False)
    session_task_manager: SessionTaskManager = field(init=False)
    session_manager: LocalSessionManager = field(init=False)
    workflow_state_manager: WorkflowStateManager = field(init=False)
    project_manager: LocalProjectManager = field(init=False)

    # Config settings (initialized in __post_init__)
    show_result_on_create: bool = field(init=False)
    auto_generate_on_expand: bool = field(init=False)
    validation_config: "TaskValidationConfig | None" = field(init=False)

    def __post_init__(self) -> None:
        """Initialize derived managers and config settings."""
        # Initialize managers from task_manager's database connection
        db = self.task_manager.db
        self.dep_manager = TaskDependencyManager(db)
        self.session_task_manager = SessionTaskManager(db)
        self.session_manager = LocalSessionManager(db)
        self.workflow_state_manager = WorkflowStateManager(db)
        self.project_manager = LocalProjectManager(db)

        # Initialize config settings
        self.show_result_on_create = False
        self.auto_generate_on_expand = True
        self.validation_config = None

        if self.config is not None:
            tasks_config = self.config.get_gobby_tasks_config()
            self.show_result_on_create = tasks_config.show_result_on_create
            self.validation_config = tasks_config.validation
            self.auto_generate_on_expand = self.validation_config.auto_generate_on_expand

    def get_project_repo_path(self, project_id: str | None) -> str | None:
        """Get the repo_path for a project by ID."""
        if not project_id:
            return None
        project = self.project_manager.get(project_id)
        return project.repo_path if project else None

    def get_current_project_id(self) -> str | None:
        """Get the current project ID from context, or None if not in a project."""
        ctx = get_project_context()
        if ctx and ctx.get("id"):
            project_id: str = ctx["id"]
            return project_id
        return None

    def get_workflow_state(self, session_id: str | None) -> WorkflowState | None:
        """Get workflow state for a session, if available."""
        if not session_id:
            return None
        return self.workflow_state_manager.get_state(session_id)

    def resolve_session_id(self, session_id: str) -> str:
        """Resolve session reference (#N, N, UUID, or prefix) to UUID.

        Args:
            session_id: Session reference string

        Returns:
            Resolved UUID string

        Raises:
            ValueError: If session cannot be resolved
        """
        project_id = self.get_current_project_id()
        return self.session_manager.resolve_session_reference(session_id, project_id)
