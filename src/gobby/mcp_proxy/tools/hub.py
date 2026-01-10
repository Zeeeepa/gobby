"""
Internal MCP tools for Hub (cross-project) queries.

Exposes functionality for:
- list_all_projects(): List all unique projects in hub database
- list_cross_project_tasks(status?): Query tasks across all projects
- list_cross_project_sessions(limit?): Recent sessions across all projects
- hub_stats(): Aggregate statistics from hub database

These tools query the hub database directly (not the project db).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.storage.database import LocalDatabase

__all__ = ["create_hub_registry", "HubToolRegistry"]


class HubToolRegistry(InternalToolRegistry):
    """Registry for hub query tools with test-friendly get_tool method."""

    def get_tool(self, name: str) -> Callable[..., Any] | None:
        """Get a tool function by name (for testing)."""
        tool = self._tools.get(name)
        return tool.func if tool else None


def create_hub_registry(
    hub_db_path: Path,
) -> HubToolRegistry:
    """
    Create a hub query tool registry with cross-project tools.

    Args:
        hub_db_path: Path to the hub database file

    Returns:
        InternalToolRegistry with hub query tools registered
    """
    registry = HubToolRegistry(
        name="gobby-hub",
        description="Hub (cross-project) queries - list_all_projects, list_cross_project_tasks, list_cross_project_sessions, hub_stats",
    )

    def _get_hub_db() -> LocalDatabase | None:
        """Get hub database connection if it exists."""
        if not hub_db_path.exists():
            return None
        return LocalDatabase(hub_db_path)

    @registry.tool(
        name="list_all_projects",
        description="List all unique projects in the hub database.",
    )
    async def list_all_projects() -> dict[str, Any]:
        """
        List all unique projects stored in the hub database.

        Returns project IDs with task and session counts.
        """
        hub_db = _get_hub_db()
        if hub_db is None:
            return {
                "success": False,
                "error": f"Hub database not found: {hub_db_path}",
            }

        try:
            # Query unique projects from tasks table
            task_projects = hub_db.fetchall(
                """
                SELECT project_id, COUNT(*) as task_count
                FROM tasks
                WHERE project_id IS NOT NULL
                GROUP BY project_id
                """
            )

            # Query unique projects from sessions table
            session_projects = hub_db.fetchall(
                """
                SELECT project_id, COUNT(*) as session_count
                FROM sessions
                WHERE project_id IS NOT NULL
                GROUP BY project_id
                """
            )

            # Merge results
            projects: dict[str, dict[str, int]] = {}
            for row in task_projects:
                project_id = row["project_id"]
                if project_id:
                    projects[project_id] = {
                        "task_count": row["task_count"],
                        "session_count": 0,
                    }

            for row in session_projects:
                project_id = row["project_id"]
                if project_id:
                    if project_id in projects:
                        projects[project_id]["session_count"] = row["session_count"]
                    else:
                        projects[project_id] = {
                            "task_count": 0,
                            "session_count": row["session_count"],
                        }

            return {
                "success": True,
                "project_count": len(projects),
                "projects": [
                    {
                        "project_id": pid,
                        "task_count": data["task_count"],
                        "session_count": data["session_count"],
                    }
                    for pid, data in sorted(projects.items())
                ],
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    @registry.tool(
        name="list_cross_project_tasks",
        description="Query tasks across all projects in the hub database.",
    )
    async def list_cross_project_tasks(
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        List tasks across all projects in the hub.

        Args:
            status: Optional status filter (open, closed, in_progress)
            limit: Maximum number of tasks to return (default 50)
        """
        hub_db = _get_hub_db()
        if hub_db is None:
            return {
                "success": False,
                "error": f"Hub database not found: {hub_db_path}",
            }

        try:
            if status:
                rows = hub_db.fetchall(
                    """
                    SELECT id, project_id, title, status, task_type, priority, created_at, updated_at
                    FROM tasks
                    WHERE status = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (status, limit),
                )
            else:
                rows = hub_db.fetchall(
                    """
                    SELECT id, project_id, title, status, task_type, priority, created_at, updated_at
                    FROM tasks
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )

            tasks = [
                {
                    "id": row["id"],
                    "project_id": row["project_id"],
                    "title": row["title"],
                    "status": row["status"],
                    "task_type": row["task_type"],
                    "priority": row["priority"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

            return {
                "success": True,
                "count": len(tasks),
                "tasks": tasks,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    @registry.tool(
        name="list_cross_project_sessions",
        description="List recent sessions across all projects in the hub database.",
    )
    async def list_cross_project_sessions(
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        List recent sessions across all projects in the hub.

        Args:
            limit: Maximum number of sessions to return (default 20)
        """
        hub_db = _get_hub_db()
        if hub_db is None:
            return {
                "success": False,
                "error": f"Hub database not found: {hub_db_path}",
            }

        try:
            rows = hub_db.fetchall(
                """
                SELECT id, project_id, source, status, machine_id, created_at, updated_at
                FROM sessions
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )

            sessions = [
                {
                    "id": row["id"],
                    "project_id": row["project_id"],
                    "source": row["source"],
                    "status": row["status"],
                    "machine_id": row["machine_id"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

            return {
                "success": True,
                "count": len(sessions),
                "sessions": sessions,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    @registry.tool(
        name="hub_stats",
        description="Get aggregate statistics from the hub database.",
    )
    async def hub_stats() -> dict[str, Any]:
        """
        Get aggregate statistics from the hub database.

        Returns counts of projects, tasks, sessions, memories, etc.
        """
        hub_db = _get_hub_db()
        if hub_db is None:
            return {
                "success": False,
                "error": f"Hub database not found: {hub_db_path}",
            }

        try:
            stats: dict[str, Any] = {}

            # Count unique projects
            project_count_result = hub_db.fetchone(
                """
                SELECT COUNT(DISTINCT project_id) as count
                FROM (
                    SELECT project_id FROM tasks WHERE project_id IS NOT NULL
                    UNION
                    SELECT project_id FROM sessions WHERE project_id IS NOT NULL
                )
                """
            )
            stats["project_count"] = project_count_result["count"] if project_count_result else 0

            # Count tasks by status
            task_stats = hub_db.fetchall(
                """
                SELECT status, COUNT(*) as count
                FROM tasks
                GROUP BY status
                """
            )
            stats["tasks"] = {
                "total": sum(row["count"] for row in task_stats),
                "by_status": {row["status"]: row["count"] for row in task_stats},
            }

            # Count sessions by status
            session_stats = hub_db.fetchall(
                """
                SELECT status, COUNT(*) as count
                FROM sessions
                GROUP BY status
                """
            )
            stats["sessions"] = {
                "total": sum(row["count"] for row in session_stats),
                "by_status": {row["status"]: row["count"] for row in session_stats},
            }

            # Count memories if table exists
            try:
                memory_count = hub_db.fetchone("SELECT COUNT(*) as count FROM memories")
                stats["memories"] = memory_count["count"] if memory_count else 0
            except Exception:
                stats["memories"] = 0

            return {
                "success": True,
                "stats": stats,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    return registry
