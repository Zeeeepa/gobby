"""
Internal MCP tools for Gobby Cron Scheduler.

Exposes functionality for:
- Listing cron jobs (list_cron_jobs)
- Creating cron jobs (create_cron_job)
- Getting job details (get_cron_job)
- Updating cron jobs (update_cron_job)
- Toggling jobs (toggle_cron_job)
- Deleting jobs (delete_cron_job)
- Running jobs immediately (run_cron_job)
- Listing run history (list_cron_runs)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry

if TYPE_CHECKING:
    from gobby.scheduler.scheduler import CronScheduler
    from gobby.storage.cron import CronJobStorage

logger = logging.getLogger(__name__)


def create_cron_registry(
    cron_storage: CronJobStorage,
    cron_scheduler: CronScheduler | None = None,
) -> InternalToolRegistry:
    """
    Create a cron tool registry with all cron job management tools.

    Args:
        cron_storage: CronJobStorage instance for CRUD operations
        cron_scheduler: CronScheduler instance for run_now (optional)

    Returns:
        InternalToolRegistry with cron tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-cron",
        description="Cron job management - list, create, update, toggle, delete, run, view history",
    )

    @registry.tool(
        name="list_cron_jobs",
        description="List cron jobs with optional filtering by project and enabled state.",
    )
    def list_cron_jobs(
        project_id: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        """
        List cron jobs.

        Args:
            project_id: Filter by project ID
            enabled: Filter by enabled state (true/false)
        """
        try:
            jobs = cron_storage.list_jobs(project_id=project_id, enabled=enabled)
            return {
                "success": True,
                "jobs": [j.to_brief() for j in jobs],
                "count": len(jobs),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="create_cron_job",
        description="Create a new cron job. Supports cron expressions, intervals, or one-shot schedules.",
    )
    def create_cron_job(
        name: str,
        action_type: str,
        action_config: dict[str, Any],
        project_id: str = "",
        schedule_type: str = "cron",
        cron_expr: str | None = None,
        interval_seconds: int | None = None,
        run_at: str | None = None,
        timezone: str = "UTC",
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new cron job.

        Args:
            name: Job name
            action_type: Action type (shell, agent_spawn, pipeline)
            action_config: Action configuration dict
            project_id: Project ID
            schedule_type: Schedule type (cron, interval, once)
            cron_expr: Cron expression (for schedule_type=cron)
            interval_seconds: Interval in seconds (for schedule_type=interval)
            run_at: ISO 8601 datetime (for schedule_type=once)
            timezone: Timezone (default: UTC)
            description: Job description
        """
        try:
            job = cron_storage.create_job(
                project_id=project_id,
                name=name,
                schedule_type=schedule_type,
                action_type=action_type,
                action_config=action_config,
                cron_expr=cron_expr,
                interval_seconds=interval_seconds,
                run_at=run_at,
                timezone=timezone,
                description=description,
            )
            return {"success": True, "job": job.to_dict()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="get_cron_job",
        description="Get details of a specific cron job by ID.",
    )
    def get_cron_job(job_id: str) -> dict[str, Any]:
        """
        Get cron job details.

        Args:
            job_id: The cron job ID
        """
        try:
            job = cron_storage.get_job(job_id)
            if not job:
                return {"success": False, "error": f"Cron job not found: {job_id}"}
            return {"success": True, "job": job.to_dict()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="update_cron_job",
        description="Update a cron job's configuration.",
    )
    def update_cron_job(
        job_id: str,
        name: str | None = None,
        description: str | None = None,
        schedule_type: str | None = None,
        cron_expr: str | None = None,
        interval_seconds: int | None = None,
        timezone: str | None = None,
        action_type: str | None = None,
        action_config: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        """
        Update a cron job.

        Args:
            job_id: The cron job ID
            name: New name
            description: New description
            schedule_type: New schedule type
            cron_expr: New cron expression
            interval_seconds: New interval
            timezone: New timezone
            action_type: New action type
            action_config: New action config
            enabled: New enabled state
        """
        try:
            kwargs: dict[str, Any] = {}
            for field, val in [
                ("name", name), ("description", description),
                ("schedule_type", schedule_type), ("cron_expr", cron_expr),
                ("interval_seconds", interval_seconds), ("timezone", timezone),
                ("action_type", action_type), ("action_config", action_config),
                ("enabled", enabled),
            ]:
                if val is not None:
                    kwargs[field] = val

            if not kwargs:
                return {"success": False, "error": "No fields to update"}

            updated = cron_storage.update_job(job_id, **kwargs)
            if not updated:
                return {"success": False, "error": f"Cron job not found: {job_id}"}
            return {"success": True, "job": updated.to_dict()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="toggle_cron_job",
        description="Toggle a cron job between enabled and disabled.",
    )
    def toggle_cron_job(job_id: str) -> dict[str, Any]:
        """
        Toggle a cron job enabled/disabled.

        Args:
            job_id: The cron job ID
        """
        try:
            job = cron_storage.toggle_job(job_id)
            if not job:
                return {"success": False, "error": f"Cron job not found: {job_id}"}
            state = "enabled" if job.enabled else "disabled"
            return {"success": True, "job": job.to_brief(), "state": state}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="delete_cron_job",
        description="Delete a cron job and its run history.",
    )
    def delete_cron_job(job_id: str) -> dict[str, Any]:
        """
        Delete a cron job.

        Args:
            job_id: The cron job ID
        """
        try:
            success = cron_storage.delete_job(job_id)
            if not success:
                return {"success": False, "error": f"Cron job not found: {job_id}"}
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="run_cron_job",
        description="Trigger immediate execution of a cron job, bypassing its schedule.",
    )
    async def run_cron_job(job_id: str) -> dict[str, Any]:
        """
        Run a cron job immediately.

        Args:
            job_id: The cron job ID
        """
        try:
            if cron_scheduler is not None:
                run = await cron_scheduler.run_now(job_id)
                if not run:
                    return {"success": False, "error": f"Cron job not found: {job_id}"}
                return {"success": True, "run": run.to_dict()}

            # Fallback: create run record without execution
            job = cron_storage.get_job(job_id)
            if not job:
                return {"success": False, "error": f"Cron job not found: {job_id}"}
            run = cron_storage.create_run(job.id)
            return {"success": True, "run": run.to_dict(), "note": "Scheduler not running; run created but not executed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="list_cron_runs",
        description="List run history for a cron job.",
    )
    def list_cron_runs(
        job_id: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        List cron run history.

        Args:
            job_id: The cron job ID
            limit: Maximum number of runs to return
        """
        try:
            runs = cron_storage.list_runs(job_id, limit=limit)
            return {
                "success": True,
                "runs": [r.to_dict() for r in runs],
                "count": len(runs),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    return registry
