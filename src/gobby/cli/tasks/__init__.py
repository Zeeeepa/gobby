"""
Task management CLI commands.

This package contains the task management commands, split into logical modules:
- _utils: Shared utilities (formatting, task resolution)
- deps: Dependency management subgroup
- commands: Main task commands
"""

from gobby.cli.tasks._utils import (
    check_tasks_enabled,
    get_sync_manager,
    get_task_manager,
)
from gobby.cli.tasks.commands import tasks

__all__ = [
    "check_tasks_enabled",
    "get_task_manager",
    "get_sync_manager",
    "tasks",
]
