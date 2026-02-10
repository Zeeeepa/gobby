"""
Task routes for Gobby HTTP server.

Provides CRUD endpoints for the task management system.
"""

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from gobby.storage.tasks._models import VALID_CATEGORIES, TaskNotFoundError
from gobby.utils.metrics import get_metrics_collector

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


# =============================================================================
# Request/Response models
# =============================================================================


class TaskCreateRequest(BaseModel):
    """Request body for creating a task."""

    title: str = Field(..., description="Task title")
    description: str | None = Field(default=None, description="Detailed description")
    priority: int = Field(default=2, description="Priority (0=Critical, 1=High, 2=Medium, 3=Low, 4=Backlog)")
    task_type: str = Field(default="task", description="Task type (task, bug, feature, epic, chore)")
    parent_task_id: str | None = Field(default=None, description="Parent task ID")
    labels: list[str] | None = Field(default=None, description="Labels for categorization")
    category: str | None = Field(
        default=None,
        description=f"Task domain: {', '.join(sorted(VALID_CATEGORIES))}",
    )
    validation_criteria: str | None = Field(default=None, description="Acceptance criteria")
    assignee: str | None = Field(default=None, description="Assignee session ID")
    project_id: str | None = Field(default=None, description="Project ID (resolved from cwd if omitted)")


class TaskUpdateRequest(BaseModel):
    """Request body for updating a task."""

    title: str | None = Field(default=None, description="New title")
    description: str | None = Field(default=None, description="New description")
    status: str | None = Field(default=None, description="New status")
    priority: int | None = Field(default=None, description="New priority")
    task_type: str | None = Field(default=None, description="New task type")
    assignee: str | None = Field(default=None, description="New assignee")
    labels: list[str] | None = Field(default=None, description="New labels")
    parent_task_id: str | None = Field(default=None, description="New parent task ID")
    category: str | None = Field(default=None, description="New category")
    validation_criteria: str | None = Field(default=None, description="New validation criteria")


# =============================================================================
# Router
# =============================================================================


def create_tasks_router(server: "HTTPServer") -> APIRouter:
    """Create tasks router with endpoints bound to server instance."""
    router = APIRouter(prefix="/tasks", tags=["tasks"])
    metrics = get_metrics_collector()

    def _resolve_project(project_id: str | None) -> str:
        """Resolve project ID, falling back to server's project context."""
        if project_id:
            return project_id
        return server._resolve_project_id(project_id=None, cwd=None)

    @router.post("", status_code=201)
    async def create_task(request_data: TaskCreateRequest) -> Any:
        """Create a new task."""
        metrics.inc_counter("http_requests_total")
        try:
            project_id = _resolve_project(request_data.project_id)
            task = server.task_manager.create_task(
                project_id=project_id,
                title=request_data.title,
                description=request_data.description,
                priority=request_data.priority,
                task_type=request_data.task_type,
                parent_task_id=request_data.parent_task_id,
                labels=request_data.labels,
                category=request_data.category,
                validation_criteria=request_data.validation_criteria,
                assignee=request_data.assignee,
            )
            return task.to_dict()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/{task_id}")
    async def get_task(task_id: str) -> Any:
        """Get a task by ID, seq_num (#N), or path (1.2.3)."""
        metrics.inc_counter("http_requests_total")
        try:
            task = server.task_manager.get_task(task_id)
            return task.to_dict()
        except (ValueError, TaskNotFoundError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.patch("/{task_id}")
    async def update_task(task_id: str, request_data: TaskUpdateRequest) -> Any:
        """Update a task's fields. Only provided fields are changed."""
        metrics.inc_counter("http_requests_total")
        try:
            # Resolve the task ID first
            task = server.task_manager.get_task(task_id)
            resolved_id = task.id

            # Build kwargs only for fields that were explicitly set
            kwargs: dict[str, Any] = {}
            for field_name in request_data.model_fields_set:
                kwargs[field_name] = getattr(request_data, field_name)

            if not kwargs:
                return task.to_dict()

            updated = server.task_manager.update_task(resolved_id, **kwargs)
            return updated.to_dict()
        except (ValueError, TaskNotFoundError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Failed to update task {task_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.delete("/{task_id}")
    async def delete_task(
        task_id: str,
        cascade: bool = Query(False, description="Delete children and dependents recursively"),
    ) -> dict[str, Any]:
        """Delete a task."""
        metrics.inc_counter("http_requests_total")
        try:
            # Resolve first
            task = server.task_manager.get_task(task_id)
            resolved_id = task.id
            result = server.task_manager.delete_task(resolved_id, cascade=cascade)
            if not result:
                raise HTTPException(status_code=404, detail="Task not found")
            return {"deleted": True, "id": resolved_id}
        except (ValueError, TaskNotFoundError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Failed to delete task {task_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    return router
