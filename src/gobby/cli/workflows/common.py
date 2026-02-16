"""Common helper functions for workflow CLI commands."""

from pathlib import Path

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


def get_project_path() -> Path | None:
    """Get current project path if in a gobby project."""
    cwd = Path.cwd()
    if (cwd / ".gobby").exists():
        return cwd
    return None
