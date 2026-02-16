"""Common helper functions for workflow CLI commands."""

from pathlib import Path

from gobby.cli.utils import resolve_session_id as resolve_session_id  # noqa: F401
from gobby.storage.database import LocalDatabase
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager


def get_workflow_loader() -> WorkflowLoader:
    """Get workflow loader instance."""
    return WorkflowLoader()


def get_state_manager() -> WorkflowStateManager:
    """Get workflow state manager instance."""
    db = LocalDatabase()
    return WorkflowStateManager(db)


def truncate_id(session_id: str, length: int = 12) -> str:
    """Truncate ID for display, appending '...' only if truncated."""
    return f"{session_id[:length]}..." if len(session_id) > length else session_id


def get_project_path() -> Path | None:
    """Get current project path if in a gobby project."""
    cwd = Path.cwd()
    if (cwd / ".gobby").exists():
        return cwd
    return None
