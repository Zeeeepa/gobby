"""Common helper functions for workflow CLI commands."""

from pathlib import Path

from gobby.cli.utils import resolve_session_id as resolve_session_id
from gobby.storage.database import LocalDatabase
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

_db_instance: LocalDatabase | None = None
_state_manager_instance: WorkflowStateManager | None = None


def get_workflow_loader() -> WorkflowLoader:
    """Get workflow loader instance."""
    return WorkflowLoader()


def get_state_manager(db: LocalDatabase | None = None) -> WorkflowStateManager:
    """Get workflow state manager instance (cached).

    Args:
        db: Optional database instance to inject. If not provided, a shared
            instance is used. LocalDatabase uses thread-local connections
            internally, so sharing one instance is safe.
    """
    global _db_instance, _state_manager_instance
    if db is not None:
        return WorkflowStateManager(db)
    if _state_manager_instance is None:
        _db_instance = LocalDatabase()
        _state_manager_instance = WorkflowStateManager(_db_instance)
    return _state_manager_instance


def truncate_id(session_id: str, length: int = 12) -> str:
    """Truncate ID for display, appending '...' only if truncated."""
    return f"{session_id[:length]}..." if len(session_id) > length else session_id


def get_project_path() -> Path | None:
    """Get current project path if in a gobby project."""
    cwd = Path.cwd()
    if (cwd / ".gobby").exists():
        return cwd
    return None
