import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from gobby.storage.database import DatabaseProtocol
from gobby.storage.tasks._aggregates import (
    count_blocked_tasks as _count_blocked_tasks,
)
from gobby.storage.tasks._aggregates import (
    count_by_status as _count_by_status,
)
from gobby.storage.tasks._aggregates import (
    count_ready_tasks as _count_ready_tasks,
)
from gobby.storage.tasks._aggregates import (
    count_tasks as _count_tasks,
)
from gobby.storage.tasks._crud import (
    create_task as _create_task,
)
from gobby.storage.tasks._crud import (
    find_task_by_prefix as _find_task_by_prefix,
)
from gobby.storage.tasks._crud import (
    find_tasks_by_prefix as _find_tasks_by_prefix,
)
from gobby.storage.tasks._crud import (
    get_task as _get_task,
)
from gobby.storage.tasks._crud import (
    update_task as _update_task,
)
from gobby.storage.tasks._id import generate_task_id, resolve_task_reference
from gobby.storage.tasks._lifecycle import (
    add_label as _add_label,
)
from gobby.storage.tasks._lifecycle import (
    close_task as _close_task,
)
from gobby.storage.tasks._lifecycle import (
    delete_task as _delete_task,
)
from gobby.storage.tasks._lifecycle import (
    link_commit as _link_commit,
)
from gobby.storage.tasks._lifecycle import (
    remove_label as _remove_label,
)
from gobby.storage.tasks._lifecycle import (
    reopen_task as _reopen_task,
)
from gobby.storage.tasks._lifecycle import (
    unlink_commit as _unlink_commit,
)
from gobby.storage.tasks._models import (
    PRIORITY_MAP,
    UNSET,
    VALID_CATEGORIES,
    Task,
    TaskIDCollisionError,
    TaskNotFoundError,
    normalize_priority,
    validate_category,
)
from gobby.storage.tasks._ordering import order_tasks_hierarchically
from gobby.storage.tasks._path_cache import (
    compute_path_cache,
    update_descendant_paths,
    update_path_cache,
)
from gobby.storage.tasks._queries import (
    list_blocked_tasks as _list_blocked_tasks,
)
from gobby.storage.tasks._queries import (
    list_ready_tasks as _list_ready_tasks,
)
from gobby.storage.tasks._queries import (
    list_tasks as _list_tasks,
)
from gobby.storage.tasks._queries import (
    list_workflow_tasks as _list_workflow_tasks,
)
from gobby.storage.tasks._search import TaskSearcher

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    "PRIORITY_MAP",
    "UNSET",
    "VALID_CATEGORIES",
    "Task",
    "TaskIDCollisionError",
    "TaskNotFoundError",
    "normalize_priority",
    "validate_category",
    "generate_task_id",
    "order_tasks_hierarchically",
    "LocalTaskManager",
]


class LocalTaskManager:
    def __init__(self, db: DatabaseProtocol):
        self.db = db
        self._change_listeners: list[Callable[[], Any]] = []
        self._searcher: TaskSearcher | None = None

    def add_change_listener(self, listener: Callable[[], Any]) -> None:
        """Add a listener to be called when tasks change."""
        self._change_listeners.append(listener)

    def _notify_listeners(self) -> None:
        """Notify all listeners of a change and mark search index dirty."""
        # Mark search index as needing refit
        if self._searcher is not None:
            self._searcher.mark_dirty()

        for listener in self._change_listeners:
            try:
                listener()
            except Exception as e:
                logger.error(f"Error in task change listener: {e}")

    def compute_path_cache(self, task_id: str) -> str | None:
        """Compute the hierarchical path for a task.

        Traverses up the parent chain to build a dotted path from seq_nums.
        Format: 'ancestor_seq.parent_seq.task_seq' (e.g., '1.3.47')

        Args:
            task_id: The task ID to compute path for

        Returns:
            Dotted path string (e.g., '1.3.47'), or None if task not found
            or any task in the chain is missing a seq_num.
        """
        return compute_path_cache(self.db, task_id)

    def update_path_cache(self, task_id: str) -> str | None:
        """Compute and store the path_cache for a task.

        Args:
            task_id: The task ID to update

        Returns:
            The computed path, or None if computation failed
        """
        return update_path_cache(self.db, task_id)

    def update_descendant_paths(self, task_id: str) -> int:
        """Update path_cache for a task and all its descendants.

        Use this after reparenting a task to cascade path updates.

        Args:
            task_id: The root task ID to start updating from

        Returns:
            Number of tasks updated
        """
        return update_descendant_paths(self.db, task_id)

    def create_task(
        self,
        project_id: str,
        title: str,
        description: str | None = None,
        parent_task_id: str | None = None,
        created_in_session_id: str | None = None,
        priority: int = 2,
        task_type: str = "task",
        assignee: str | None = None,
        labels: list[str] | None = None,
        category: str | None = None,
        complexity_score: int | None = None,
        estimated_subtasks: int | None = None,
        expansion_context: str | None = None,
        validation_criteria: str | None = None,
        use_external_validator: bool = False,
        workflow_name: str | None = None,
        verification: str | None = None,
        sequence_order: int | None = None,
        github_issue_number: int | None = None,
        github_pr_number: int | None = None,
        github_repo: str | None = None,
        linear_issue_id: str | None = None,
        linear_team_id: str | None = None,
        agent_name: str | None = None,
        reference_doc: str | None = None,
        requires_user_review: bool = False,
    ) -> Task:
        """Create a new task with collision handling."""
        task_id = _create_task(
            self.db,
            project_id=project_id,
            title=title,
            description=description,
            parent_task_id=parent_task_id,
            created_in_session_id=created_in_session_id,
            priority=priority,
            task_type=task_type,
            assignee=assignee,
            labels=labels,
            category=category,
            complexity_score=complexity_score,
            estimated_subtasks=estimated_subtasks,
            expansion_context=expansion_context,
            validation_criteria=validation_criteria,
            use_external_validator=use_external_validator,
            workflow_name=workflow_name,
            verification=verification,
            sequence_order=sequence_order,
            github_issue_number=github_issue_number,
            github_pr_number=github_pr_number,
            github_repo=github_repo,
            linear_issue_id=linear_issue_id,
            linear_team_id=linear_team_id,
            agent_name=agent_name,
            reference_doc=reference_doc,
            requires_user_review=requires_user_review,
        )
        self._notify_listeners()
        return self.get_task(task_id)

    def get_task(self, task_id: str, project_id: str | None = None) -> Task:
        """Get a task by ID or reference.

        Accepts multiple formats:
          - UUID: Direct lookup
          - #N: Project-scoped seq_num (requires project_id)
          - N: Plain seq_num (requires project_id)

        Args:
            task_id: Task identifier in any supported format
            project_id: Required for #N and N formats

        Returns:
            The Task object

        Raises:
            ValueError: If task not found or format requires project_id
        """
        return _get_task(self.db, task_id, project_id)

    def find_task_by_prefix(self, prefix: str) -> Task | None:
        """Find a task by ID prefix. Returns None if no match or multiple matches."""
        return _find_task_by_prefix(self.db, prefix)

    def find_tasks_by_prefix(self, prefix: str) -> list[Task]:
        """Find all tasks matching an ID prefix."""
        return _find_tasks_by_prefix(self.db, prefix)

    def resolve_task_reference(self, ref: str, project_id: str) -> str:
        """Resolve a task reference to its UUID.

        Accepts multiple reference formats:
          - N: Plain seq_num (e.g., 47)
          - #N: Project-scoped seq_num (e.g., #47)
          - 1.2.3: Path cache format
          - UUID: Direct UUID (validated to exist)

        Args:
            ref: Task reference in any supported format
            project_id: Project ID for scoped lookups

        Returns:
            The task's UUID

        Raises:
            TaskNotFoundError: If the reference cannot be resolved
        """
        return resolve_task_reference(self.db, ref, project_id)

    def update_task(
        self,
        task_id: str,
        title: str | None | Any = UNSET,
        description: str | None | Any = UNSET,
        status: str | None | Any = UNSET,
        priority: int | None | Any = UNSET,
        task_type: str | None | Any = UNSET,
        assignee: str | None | Any = UNSET,
        labels: list[str] | None | Any = UNSET,
        parent_task_id: str | None | Any = UNSET,
        validation_status: str | None | Any = UNSET,
        validation_feedback: str | None | Any = UNSET,
        category: str | None | Any = UNSET,
        complexity_score: int | None | Any = UNSET,
        estimated_subtasks: int | None | Any = UNSET,
        expansion_context: str | None | Any = UNSET,
        validation_criteria: str | None | Any = UNSET,
        use_external_validator: bool | None | Any = UNSET,
        validation_fail_count: int | None | Any = UNSET,
        workflow_name: str | None | Any = UNSET,
        verification: str | None | Any = UNSET,
        sequence_order: int | None | Any = UNSET,
        escalated_at: str | None | Any = UNSET,
        escalation_reason: str | None | Any = UNSET,
        github_issue_number: int | None | Any = UNSET,
        github_pr_number: int | None | Any = UNSET,
        github_repo: str | None | Any = UNSET,
        linear_issue_id: str | None | Any = UNSET,
        linear_team_id: str | None | Any = UNSET,
        agent_name: str | None | Any = UNSET,
        reference_doc: str | None | Any = UNSET,
        is_expanded: bool | None | Any = UNSET,
        expansion_status: str | None | Any = UNSET,
        validation_override_reason: str | None | Any = UNSET,
        requires_user_review: bool | None | Any = UNSET,
    ) -> Task:
        """Update task fields."""
        parent_changed = _update_task(
            self.db,
            task_id=task_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            task_type=task_type,
            assignee=assignee,
            labels=labels,
            parent_task_id=parent_task_id,
            validation_status=validation_status,
            validation_feedback=validation_feedback,
            category=category,
            complexity_score=complexity_score,
            estimated_subtasks=estimated_subtasks,
            expansion_context=expansion_context,
            validation_criteria=validation_criteria,
            use_external_validator=use_external_validator,
            validation_fail_count=validation_fail_count,
            workflow_name=workflow_name,
            verification=verification,
            sequence_order=sequence_order,
            escalated_at=escalated_at,
            escalation_reason=escalation_reason,
            github_issue_number=github_issue_number,
            github_pr_number=github_pr_number,
            github_repo=github_repo,
            linear_issue_id=linear_issue_id,
            linear_team_id=linear_team_id,
            agent_name=agent_name,
            reference_doc=reference_doc,
            is_expanded=is_expanded,
            expansion_status=expansion_status,
            validation_override_reason=validation_override_reason,
            requires_user_review=requires_user_review,
        )

        # If parent_task_id was changed, update path_cache for this task and all descendants
        if parent_changed:
            self.update_descendant_paths(task_id)

        self._notify_listeners()
        return self.get_task(task_id)

    def close_task(
        self,
        task_id: str,
        reason: str | None = None,
        force: bool = False,
        closed_in_session_id: str | None = None,
        closed_commit_sha: str | None = None,
        validation_override_reason: str | None = None,
    ) -> Task:
        """Close a task.

        Args:
            task_id: The task ID to close
            reason: Optional reason for closing
            force: If True, close even if there are open children (default: False)
            closed_in_session_id: Session ID where task was closed
            closed_commit_sha: Git commit SHA at time of closing
            validation_override_reason: Why agent bypassed validation (if applicable)

        Raises:
            ValueError: If task not found or has open children (and force=False)
        """
        _close_task(
            self.db,
            task_id=task_id,
            reason=reason,
            force=force,
            closed_in_session_id=closed_in_session_id,
            closed_commit_sha=closed_commit_sha,
            validation_override_reason=validation_override_reason,
        )
        self._notify_listeners()
        return self.get_task(task_id)

    def reopen_task(
        self,
        task_id: str,
        reason: str | None = None,
    ) -> Task:
        """Reopen a closed or review task.

        Args:
            task_id: The task ID to reopen
            reason: Optional reason for reopening

        Raises:
            ValueError: If task not found or not closed/review
        """
        _reopen_task(self.db, task_id=task_id, reason=reason)
        self._notify_listeners()
        return self.get_task(task_id)

    def add_label(self, task_id: str, label: str) -> Task:
        """Add a label to a task if not present."""
        result = _add_label(self.db, task_id, label)
        self._notify_listeners()
        return result

    def remove_label(self, task_id: str, label: str) -> Task:
        """Remove a label from a task if present."""
        result = _remove_label(self.db, task_id, label)
        self._notify_listeners()
        return result

    def link_commit(self, task_id: str, commit_sha: str, cwd: str | Path | None = None) -> Task:
        """Link a commit SHA to a task.

        Adds the commit SHA to the task's commits array if not already present.
        The SHA is normalized to dynamic short format for consistency.

        Args:
            task_id: The task ID to link the commit to.
            commit_sha: The git commit SHA to link (short or full).
            cwd: Working directory for git operations (defaults to current directory).

        Returns:
            Updated Task object.

        Raises:
            ValueError: If task not found or SHA cannot be resolved.
        """
        if _link_commit(self.db, task_id, commit_sha, cwd):
            self._notify_listeners()
        return self.get_task(task_id)

    def unlink_commit(self, task_id: str, commit_sha: str, cwd: str | Path | None = None) -> Task:
        """Unlink a commit SHA from a task.

        Removes the commit SHA from the task's commits array if present.
        Handles both normalized and legacy SHA formats via prefix matching.

        Args:
            task_id: The task ID to unlink the commit from.
            commit_sha: The git commit SHA to unlink (short or full).
            cwd: Working directory for git operations (defaults to current directory).

        Returns:
            Updated Task object.

        Raises:
            ValueError: If task not found.
        """
        if _unlink_commit(self.db, task_id, commit_sha, cwd):
            self._notify_listeners()
        return self.get_task(task_id)

    def delete_task(self, task_id: str, cascade: bool = False, unlink: bool = False) -> bool:
        """Delete a task.

        Args:
            task_id: The task ID to delete
            cascade: If True, delete children AND dependent tasks recursively
            unlink: If True, remove dependency links but preserve dependent tasks
                    (ignored if cascade=True)

        Returns:
            True if task was deleted, False if task not found.

        Raises:
            ValueError: If task has children or dependents and neither cascade nor unlink is True.
        """
        result = _delete_task(self.db, task_id, cascade=cascade, unlink=unlink)
        if result:
            self._notify_listeners()
        return result

    def list_tasks(
        self,
        project_id: str | None = None,
        status: str | list[str] | None = None,
        priority: int | None = None,
        assignee: str | None = None,
        task_type: str | None = None,
        label: str | None = None,
        parent_task_id: str | None = None,
        title_like: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        """List tasks with filtering.

        Args:
            status: Filter by status. Can be a single status string, a list of statuses,
                or None to include all statuses.

        Results are ordered hierarchically: parents appear before their children,
        with siblings sorted by priority ASC, then created_at ASC.
        """
        return _list_tasks(
            self.db,
            project_id=project_id,
            status=status,
            priority=priority,
            assignee=assignee,
            task_type=task_type,
            label=label,
            parent_task_id=parent_task_id,
            title_like=title_like,
            limit=limit,
            offset=offset,
        )

    def list_ready_tasks(
        self,
        project_id: str | None = None,
        priority: int | None = None,
        task_type: str | None = None,
        assignee: str | None = None,
        parent_task_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        """List tasks that are ready to work on (open or in_progress) and not blocked.

        A task is ready if:
        1. It is open or in_progress
        2. It has no open blocking dependencies
        3. Its parent (if any) is also ready (recursive check up the chain)

        Note: in_progress tasks are included because they represent active work
        that should remain visible in the ready queue.

        Results are ordered hierarchically: parents appear before their children,
        with siblings sorted by priority ASC, then created_at ASC.
        """
        return _list_ready_tasks(
            self.db,
            project_id=project_id,
            priority=priority,
            task_type=task_type,
            assignee=assignee,
            parent_task_id=parent_task_id,
            limit=limit,
            offset=offset,
        )

    def list_blocked_tasks(
        self,
        project_id: str | None = None,
        parent_task_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        """List tasks that are blocked by at least one open blocking dependency.

        Only considers "external" blockers - excludes parent tasks being blocked
        by their own descendants (which is a "completion" block, not a "work" block).

        Results are ordered hierarchically: parents appear before their children,
        with siblings sorted by priority ASC, then created_at ASC.
        """
        return _list_blocked_tasks(
            self.db,
            project_id=project_id,
            parent_task_id=parent_task_id,
            limit=limit,
            offset=offset,
        )

    def list_workflow_tasks(
        self,
        workflow_name: str,
        project_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        """List tasks associated with a workflow, ordered by sequence_order.

        Args:
            workflow_name: The workflow name to filter by
            project_id: Optional project ID filter
            status: Optional status filter ('open', 'in_progress', 'closed')
            limit: Maximum tasks to return
            offset: Pagination offset

        Returns:
            List of tasks ordered by sequence_order (nulls last), then created_at
        """
        return _list_workflow_tasks(
            self.db,
            workflow_name=workflow_name,
            project_id=project_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    def count_tasks(
        self,
        project_id: str | None = None,
        status: str | None = None,
    ) -> int:
        """Count tasks with optional filters.

        Args:
            project_id: Filter by project
            status: Filter by status

        Returns:
            Count of matching tasks
        """
        return _count_tasks(self.db, project_id=project_id, status=status)

    def count_by_status(self, project_id: str | None = None) -> dict[str, int]:
        """Count tasks grouped by status.

        Args:
            project_id: Optional project filter

        Returns:
            Dictionary mapping status to count
        """
        return _count_by_status(self.db, project_id=project_id)

    def count_ready_tasks(self, project_id: str | None = None) -> int:
        """Count tasks that are ready (open or in_progress) and not blocked.

        A task is ready if it has no external blocking dependencies.
        Excludes parent tasks blocked by their own descendants (completion block, not work block).

        Args:
            project_id: Optional project filter

        Returns:
            Count of ready tasks
        """
        return _count_ready_tasks(self.db, project_id=project_id)

    def count_blocked_tasks(self, project_id: str | None = None) -> int:
        """Count tasks that are blocked by at least one external blocking dependency.

        Excludes parent tasks blocked by their own descendants (completion block, not work block).

        Args:
            project_id: Optional project filter

        Returns:
            Count of blocked tasks
        """
        return _count_blocked_tasks(self.db, project_id=project_id)

    def create_task_with_decomposition(
        self,
        project_id: str,
        title: str,
        description: str | None = None,
        parent_task_id: str | None = None,
        created_in_session_id: str | None = None,
        priority: int = 2,
        task_type: str = "task",
        assignee: str | None = None,
        labels: list[str] | None = None,
        category: str | None = None,
        complexity_score: int | None = None,
        estimated_subtasks: int | None = None,
        expansion_context: str | None = None,
        validation_criteria: str | None = None,
        use_external_validator: bool = False,
        workflow_name: str | None = None,
        verification: str | None = None,
        sequence_order: int | None = None,
    ) -> dict[str, Any]:
        """Create a task and return result dict.

        Args:
            project_id: Project ID
            title: Task title
            description: Task description
            parent_task_id: Optional parent task ID
            created_in_session_id: Session ID where task was created
            priority: Task priority
            task_type: Task type
            assignee: Optional assignee
            labels: Optional labels list
            category: Task domain category
            complexity_score: Complexity score
            estimated_subtasks: Estimated number of subtasks
            expansion_context: Additional context for expansion
            validation_criteria: Validation criteria for completion
            use_external_validator: Whether to use external validator
            workflow_name: Workflow name
            verification: Verification steps
            sequence_order: Sequence order in parent

        Returns:
            Dict with task details.
        """
        task = self.create_task(
            project_id=project_id,
            title=title,
            description=description,
            parent_task_id=parent_task_id,
            created_in_session_id=created_in_session_id,
            priority=priority,
            task_type=task_type,
            assignee=assignee,
            labels=labels,
            category=category,
            complexity_score=complexity_score,
            estimated_subtasks=estimated_subtasks,
            expansion_context=expansion_context,
            validation_criteria=validation_criteria,
            use_external_validator=use_external_validator,
            workflow_name=workflow_name,
            verification=verification,
            sequence_order=sequence_order,
        )
        return {"task": task.to_dict()}

    def update_task_with_result(
        self,
        task_id: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update a task's description and return result dict.

        Args:
            task_id: Task ID
            description: New description

        Returns:
            Dict with task details.
        """
        updated = self.update_task(task_id, description=description)
        return {"task": updated.to_dict()}

    # --- Search Methods ---

    def _ensure_searcher(self) -> TaskSearcher:
        """Get or create the task searcher instance."""
        if self._searcher is None:
            self._searcher = TaskSearcher()
        return self._searcher

    def _ensure_search_fitted(self, project_id: str | None = None) -> None:
        """Ensure the search index is fitted with current tasks.

        Note: The index is always built from ALL tasks (not project-scoped) to ensure
        the index remains valid for searches against any project. Project filtering
        is applied in search_tasks() after TF-IDF ranking.

        Args:
            project_id: Unused - kept for API compatibility. Index always includes all tasks.
        """
        _ = project_id  # Unused - index is always global
        searcher = self._ensure_searcher()

        if not searcher.needs_refit():
            return

        # Always fetch ALL tasks to build a global index
        # Project-scoped filtering happens in search_tasks() after ranking
        index_limit = 10000
        tasks = _list_tasks(
            self.db,
            project_id=None,  # Always global
            limit=index_limit,
        )

        if len(tasks) == index_limit:
            logger.warning(
                f"Task search index may be incomplete: fetched exactly {index_limit} tasks. "
                "Consider increasing the index limit or implementing pagination."
            )

        searcher.fit(tasks)
        logger.info(f"Task search index fitted with {len(tasks)} tasks")

    def mark_search_refit_needed(self) -> None:
        """Mark that the search index needs to be rebuilt."""
        if self._searcher is not None:
            self._searcher.mark_dirty()

    def search_tasks(
        self,
        query: str,
        project_id: str | None = None,
        status: str | list[str] | None = None,
        task_type: str | None = None,
        priority: int | None = None,
        parent_task_id: str | None = None,
        category: str | None = None,
        limit: int = 20,
        min_score: float = 0.0,
    ) -> list[tuple[Task, float]]:
        """Search tasks using TF-IDF semantic search.

        Two-phase search: TF-IDF ranking first, then apply SQL filters.

        Args:
            query: Search query text
            project_id: Filter by project
            status: Filter by status (string or list of strings)
            task_type: Filter by task type
            priority: Filter by priority
            parent_task_id: Filter by parent task ID (UUID)
            category: Filter by task category
            limit: Maximum results to return
            min_score: Minimum similarity score threshold (0.0-1.0)

        Returns:
            List of (Task, similarity_score) tuples, sorted by score descending
        """
        # Ensure the search index is fitted
        self._ensure_search_fitted(project_id)

        searcher = self._ensure_searcher()

        # Phase 1: TF-IDF search to get candidate task IDs
        # Get more candidates than limit to allow for filtering
        search_results = searcher.search(query, top_k=limit * 3)

        if not search_results:
            return []

        # Phase 2: Fetch tasks and apply filters
        results: list[tuple[Task, float]] = []

        for task_id, score in search_results:
            if score < min_score:
                continue

            try:
                task = self.get_task(task_id)
            except (ValueError, TaskNotFoundError):
                # Task may have been deleted since indexing
                continue

            # Apply filters
            if project_id and task.project_id != project_id:
                continue

            if status:
                if isinstance(status, list):
                    if task.status not in status:
                        continue
                elif task.status != status:
                    continue

            if task_type and task.task_type != task_type:
                continue

            if priority is not None and task.priority != priority:
                continue

            if parent_task_id and task.parent_task_id != parent_task_id:
                continue

            if category and task.category != category:
                continue

            results.append((task, score))

            if len(results) >= limit:
                break

        return results

    def reindex_search(self, project_id: str | None = None) -> dict[str, Any]:
        """Force rebuild of the task search index.

        Note: The index is always global (includes all tasks). Project-scoped
        filtering is applied at search time in search_tasks().

        Args:
            project_id: Unused - kept for API compatibility. Index always rebuilds globally.

        Returns:
            Dict with index statistics
        """
        searcher = self._ensure_searcher()

        # Force refit by marking dirty
        searcher.mark_dirty()

        # Ensure fitted will rebuild the index
        self._ensure_search_fitted(project_id)

        return searcher.get_stats()
