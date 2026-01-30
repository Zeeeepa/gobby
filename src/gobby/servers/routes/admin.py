"""
Admin routes for Gobby HTTP server.

Provides status, metrics, config, and shutdown endpoints.
"""

import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING, Any

import psutil
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from gobby.utils.metrics import Counter, get_metrics_collector
from gobby.utils.version import get_version

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


def create_admin_router(server: "HTTPServer") -> APIRouter:
    """
    Create admin router with endpoints bound to server instance.

    Args:
        server: HTTPServer instance for accessing state and dependencies

    Returns:
        Configured APIRouter with admin endpoints
    """
    router = APIRouter(prefix="/admin", tags=["admin"])

    @router.get("/status")
    async def status_check() -> dict[str, Any]:
        """
        Comprehensive status check endpoint.

        Returns detailed health status including daemon state, uptime,
        memory usage, background tasks, and connection statistics.
        """
        start_time = time.perf_counter()

        # Get server uptime
        uptime_seconds = None
        if server._start_time is not None:
            uptime_seconds = time.time() - server._start_time

        # Get daemon status if available
        daemon_status = None
        if server._daemon is not None:
            try:
                daemon_status = server._daemon.status()
            except Exception as e:
                logger.warning(f"Failed to get daemon status: {e}")

        # Get process metrics
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            # Run cpu_percent in a thread executor to avoid blocking the event loop
            # (interval=0.1 would block for 100ms otherwise)
            cpu_percent = await asyncio.to_thread(process.cpu_percent, 0.1)

            process_metrics = {
                "memory_rss_mb": round(memory_info.rss / (1024 * 1024), 2),
                "memory_vms_mb": round(memory_info.vms / (1024 * 1024), 2),
                "cpu_percent": cpu_percent,
                "num_threads": process.num_threads(),
            }
        except Exception as e:
            logger.warning(f"Failed to get process metrics: {e}")
            process_metrics = None

        # Get background task status
        metrics = get_metrics_collector()
        background_tasks = {
            "active": len(server._background_tasks),
            "total": metrics._counters.get("background_tasks_total", Counter("", "")).value,
            "completed": metrics._counters.get(
                "background_tasks_completed_total", Counter("", "")
            ).value,
            "failed": metrics._counters.get("background_tasks_failed_total", Counter("", "")).value,
        }

        # Get MCP server status - include ALL configured servers
        mcp_health = {}
        if server.mcp_manager is not None:
            try:
                # Iterate over all configured servers, not just connected ones
                for config in server.mcp_manager.server_configs:
                    health = server.mcp_manager.health.get(config.name)
                    is_connected = config.name in server.mcp_manager.connections
                    mcp_health[config.name] = {
                        "connected": is_connected,
                        "status": (
                            health.state.value
                            if health
                            else ("connected" if is_connected else "not_started")
                        ),
                        "enabled": config.enabled,
                        "transport": config.transport,
                        "health": health.health.value if health else None,
                        "consecutive_failures": health.consecutive_failures if health else 0,
                        "last_health_check": (
                            health.last_health_check.isoformat()
                            if health and health.last_health_check
                            else None
                        ),
                        "response_time_ms": health.response_time_ms if health else None,
                    }
            except Exception as e:
                logger.warning(f"Failed to get MCP health: {e}")

        # Count internal tools from gobby-* registries and add them to mcp_health
        internal_tools_count = 0
        if server._internal_manager:
            for registry in server._internal_manager.get_all_registries():
                tools = registry.list_tools()
                internal_tools_count += len(tools)
                # Include internal servers in mcp_health for unified server count
                mcp_health[registry.name] = {
                    "connected": True,  # Internal servers are always available
                    "status": "connected",
                    "enabled": True,
                    "transport": "internal",
                    "health": "healthy",
                    "consecutive_failures": 0,
                    "last_health_check": None,
                    "response_time_ms": None,
                    "internal": True,  # Flag to distinguish from downstream servers
                    "tool_count": len(tools),
                }

        # Get session statistics using efficient count queries
        session_stats = {"active": 0, "paused": 0, "handoff_ready": 0, "total": 0}
        if server.session_manager is not None:
            try:
                # Use count_by_status for efficient grouped counts
                status_counts = server.session_manager.count_by_status()
                session_stats["total"] = sum(status_counts.values())
                session_stats["active"] = status_counts.get("active", 0)
                session_stats["paused"] = status_counts.get("paused", 0)
                session_stats["handoff_ready"] = status_counts.get("handoff_ready", 0)
            except Exception as e:
                logger.warning(f"Failed to get session stats: {e}")

        # Get task statistics using efficient count queries
        task_stats = {"open": 0, "in_progress": 0, "closed": 0, "ready": 0, "blocked": 0}
        if server.task_manager is not None:
            try:
                # Use count_by_status for efficient grouped counts
                status_counts = server.task_manager.count_by_status()
                task_stats["open"] = status_counts.get("open", 0)
                task_stats["in_progress"] = status_counts.get("in_progress", 0)
                task_stats["closed"] = status_counts.get("closed", 0)
                # Get ready and blocked counts using dedicated count methods
                task_stats["ready"] = server.task_manager.count_ready_tasks()
                task_stats["blocked"] = server.task_manager.count_blocked_tasks()
            except Exception as e:
                logger.warning(f"Failed to get task stats: {e}")

        # Get memory statistics
        memory_stats = {"count": 0, "avg_importance": 0.0}
        if server.memory_manager is not None:
            try:
                stats = server.memory_manager.get_stats()
                memory_stats["count"] = stats.get("total_count", 0)
                memory_stats["avg_importance"] = stats.get("avg_importance", 0.0)
            except Exception as e:
                logger.warning(f"Failed to get memory stats: {e}")

        # Get artifact statistics
        artifact_stats = {"count": 0}
        if server.session_manager is not None:
            try:
                from gobby.storage.artifacts import LocalArtifactManager

                artifact_manager = LocalArtifactManager(server.session_manager.db)
                artifact_stats["count"] = artifact_manager.count_artifacts()
            except Exception as e:
                logger.warning(f"Failed to get artifact stats: {e}")

        # Get skills statistics
        skills_stats: dict[str, Any] = {"total": 0}
        if server._internal_manager:
            try:
                for registry in server._internal_manager.get_all_registries():
                    if registry.name == "gobby-skills":
                        result = await registry.call("list_skills", {"limit": 10000})
                        if result.get("success"):
                            skills_stats["total"] = result.get("count", 0)
                        break
            except Exception as e:
                logger.warning(f"Failed to get skills stats: {e}")

        # Get plugin status
        plugin_stats: dict[str, Any] = {"enabled": False, "loaded": 0, "handlers": 0}
        if hasattr(server, "_hook_manager") and server._hook_manager is not None:
            try:
                hook_manager = server._hook_manager
                if hasattr(hook_manager, "plugin_loader") and hook_manager.plugin_loader:
                    plugin_loader = hook_manager.plugin_loader
                    plugin_stats["enabled"] = plugin_loader.config.enabled
                    plugins = plugin_loader.registry.list_plugins()
                    plugin_stats["loaded"] = len(plugins)
                    plugin_stats["handlers"] = sum(len(p.get("handlers", [])) for p in plugins)
                    plugin_stats["plugins"] = [
                        {
                            "name": p["name"],
                            "version": p["version"],
                            "handlers": len(p.get("handlers", [])),
                            "actions": len(p.get("actions", [])),
                        }
                        for p in plugins
                    ]
            except Exception as e:
                logger.warning(f"Failed to get plugin stats: {e}")

        # Calculate response time
        response_time_ms = (time.perf_counter() - start_time) * 1000

        return {
            "status": "healthy" if server._running else "degraded",
            "server": {
                "port": server.port,
                "test_mode": server.test_mode,
                "running": server._running,
                "uptime_seconds": uptime_seconds,
            },
            "daemon": daemon_status,
            "process": process_metrics,
            "background_tasks": background_tasks,
            "mcp_servers": mcp_health,
            # Count of tools from internal gobby-* registries (tasks, memory)
            "internal_tools_count": internal_tools_count,
            "sessions": session_stats,
            "tasks": task_stats,
            "memory": memory_stats,
            "artifacts": artifact_stats,
            "skills": skills_stats,
            "plugins": plugin_stats,
            "response_time_ms": response_time_ms,
        }

    @router.get("/metrics")
    async def get_metrics() -> PlainTextResponse:
        """
        Prometheus-compatible metrics endpoint.

        Returns metrics in Prometheus text exposition format including:
        - HTTP request counts and durations
        - Background task metrics
        - Daemon health metrics
        """
        metrics = get_metrics_collector()
        try:
            # Update daemon health metrics if available
            if server._daemon is not None:
                try:
                    uptime = server._daemon.uptime
                    if uptime is not None:
                        metrics.set_gauge("daemon_uptime_seconds", uptime)

                    # Get process info for daemon
                    process = psutil.Process(os.getpid())
                    memory_info = process.memory_info()
                    metrics.set_gauge("daemon_memory_usage_bytes", float(memory_info.rss))

                    cpu_percent = process.cpu_percent(interval=0)
                    metrics.set_gauge("daemon_cpu_percent", cpu_percent)
                except Exception as e:
                    logger.warning(f"Failed to update daemon metrics: {e}")

            # Update background task gauge
            metrics.set_gauge("background_tasks_active", float(len(server._background_tasks)))

            # Export in Prometheus format
            prometheus_output = metrics.export_prometheus()
            return PlainTextResponse(
                content=prometheus_output, media_type="text/plain; version=0.0.4"
            )

        except Exception as e:
            logger.error(f"Failed to export metrics: {e}", exc_info=True)
            raise

    @router.get("/config")
    async def get_config() -> dict[str, Any]:
        """
        Get daemon configuration and version information.

        Returns:
            Configuration data including ports, features, and versions
        """
        start_time = time.perf_counter()
        metrics = get_metrics_collector()
        metrics.inc_counter("http_requests_total")

        try:
            config_data = {
                "server": {
                    "port": server.port,
                    "test_mode": server.test_mode,
                    "running": server._running,
                    "version": get_version(),
                },
                "features": {
                    "session_manager": server.session_manager is not None,
                    "mcp_manager": server.mcp_manager is not None,
                },
                "endpoints": {
                    "mcp": [
                        "/mcp/{server_name}/tools/{tool_name}",
                    ],
                    "sessions": [
                        "/sessions/register",
                        "/sessions/{id}",
                    ],
                    "admin": [
                        "/admin/status",
                        "/admin/metrics",
                        "/admin/config",
                        "/admin/shutdown",
                    ],
                },
            }

            response_time_ms = (time.perf_counter() - start_time) * 1000

            return {
                "status": "success",
                "config": config_data,
                "response_time_ms": response_time_ms,
            }

        except Exception as e:
            logger.error(f"Config retrieval error: {e}", exc_info=True)
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/shutdown")
    async def shutdown() -> dict[str, Any]:
        """
        Graceful daemon shutdown endpoint.

        Returns:
            Shutdown confirmation
        """
        start_time = time.perf_counter()
        metrics = get_metrics_collector()

        metrics.inc_counter("http_requests_total")
        metrics.inc_counter("shutdown_requests_total")

        try:
            logger.debug("Shutdown requested via HTTP endpoint")

            # Create background task for shutdown
            task = asyncio.create_task(server._process_shutdown())

            server._background_tasks.add(task)
            task.add_done_callback(server._background_tasks.discard)

            response_time_ms = (time.perf_counter() - start_time) * 1000

            return {
                "status": "shutting_down",
                "message": "Graceful shutdown initiated",
                "response_time_ms": response_time_ms,
            }

        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error("Error initiating shutdown: %s", e, exc_info=True)
            return {
                "message": "Shutdown failed to initiate",
            }

    @router.post("/workflows/reload")
    async def reload_workflows() -> dict[str, Any]:
        """
        Reload workflow definitions from disk.

        Triggers the gobby-workflows.reload_cache MCP tool internally.
        """
        start_time = time.perf_counter()
        metrics = get_metrics_collector()
        metrics.inc_counter("http_requests_total")

        try:
            # Find the gobby-workflows registry
            workflows_registry = None
            if server._internal_manager:
                for registry in server._internal_manager.get_all_registries():
                    if registry.name == "gobby-workflows":
                        workflows_registry = registry
                        break

            if not workflows_registry:
                return {
                    "status": "error",
                    "message": "Workflow registry not available",
                }

            # Call reload_cache tool directly via registry.call which handles async/sync
            try:
                result = await workflows_registry.call("reload_cache", {})
            except ValueError:
                return {
                    "status": "error",
                    "message": "reload_cache tool not found",
                }
            except Exception as e:
                logger.error(f"Failed to execute reload_cache: {e}")
                return {
                    "status": "error",
                    "message": f"Failed to reload cache: {e}",
                }

            response_time_ms = (time.perf_counter() - start_time) * 1000

            return {
                "status": "success",
                "message": "Workflow cache reloaded",
                "details": result,
                "response_time_ms": response_time_ms,
            }

        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Error reloading workflows: {e}", exc_info=True)
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail=str(e)) from e

    # --- Test endpoints (for E2E testing) ---

    class TestProjectRegisterRequest(BaseModel):
        """Request model for registering a test project."""

        project_id: str
        name: str
        repo_path: str | None = None

    @router.post("/test/register-project")
    async def register_test_project(request: TestProjectRegisterRequest) -> dict[str, Any]:
        """
        Register a test project in the database.

        This endpoint is for E2E testing. It ensures the project exists
        in the projects table so sessions can be created with valid project_ids.

        Args:
            request: Project registration details

        Returns:
            Registration confirmation
        """
        from fastapi import HTTPException

        from gobby.storage.projects import LocalProjectManager

        # Guard: Only available in test mode
        if not server.test_mode:
            raise HTTPException(
                status_code=403, detail="Test endpoints only available in test mode"
            )

        start_time = time.perf_counter()
        metrics = get_metrics_collector()
        metrics.inc_counter("http_requests_total")

        try:
            # Use server's session manager database to avoid creating separate connections
            if server.session_manager is None:
                raise HTTPException(status_code=503, detail="Session manager not available")

            db = server.session_manager.db

            project_manager = LocalProjectManager(db)

            # Check if project exists
            existing = project_manager.get(request.project_id)
            if existing:
                return {
                    "status": "already_exists",
                    "project_id": existing.id,
                    "name": existing.name,
                }

            # Create the project with the specific ID
            from datetime import UTC, datetime

            now = datetime.now(UTC).isoformat()
            db.execute(
                """
                INSERT INTO projects (id, name, repo_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (request.project_id, request.name, request.repo_path, now, now),
            )

            response_time_ms = (time.perf_counter() - start_time) * 1000

            return {
                "status": "success",
                "message": f"Registered test project {request.project_id}",
                "project_id": request.project_id,
                "name": request.name,
                "response_time_ms": response_time_ms,
            }

        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Error registering test project: {e}", exc_info=True)
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail=str(e)) from e

    class TestAgentRegisterRequest(BaseModel):
        """Request model for registering a test agent."""

        run_id: str
        session_id: str
        parent_session_id: str
        mode: str = "terminal"

    @router.post("/test/register-agent")
    async def register_test_agent(request: TestAgentRegisterRequest) -> dict[str, Any]:
        """
        Register a test agent in the running agent registry.

        This endpoint is for E2E testing of inter-agent messaging.
        It allows tests to set up parent-child agent relationships
        without actually spawning agent processes.

        Args:
            request: Agent registration details

        Returns:
            Registration confirmation
        """
        from fastapi import HTTPException

        from gobby.agents.registry import RunningAgent, get_running_agent_registry

        # Guard: Only available in test mode
        if not server.test_mode:
            raise HTTPException(
                status_code=403, detail="Test endpoints only available in test mode"
            )

        start_time = time.perf_counter()
        metrics = get_metrics_collector()
        metrics.inc_counter("http_requests_total")

        try:
            registry = get_running_agent_registry()

            # Create and register the agent
            running_agent = RunningAgent(
                run_id=request.run_id,
                session_id=request.session_id,
                parent_session_id=request.parent_session_id,
                mode=request.mode,
            )
            registry.add(running_agent)

            response_time_ms = (time.perf_counter() - start_time) * 1000

            return {
                "status": "success",
                "message": f"Registered test agent {request.run_id}",
                "agent": running_agent.to_dict(),
                "response_time_ms": response_time_ms,
            }

        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Error registering test agent: {e}", exc_info=True)
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.delete("/test/unregister-agent/{run_id}")
    async def unregister_test_agent(run_id: str) -> dict[str, Any]:
        """
        Unregister a test agent from the running agent registry.

        Args:
            run_id: The agent run ID to remove

        Returns:
            Unregistration confirmation
        """
        from fastapi import HTTPException

        from gobby.agents.registry import get_running_agent_registry

        # Guard: Only available in test mode
        if not server.test_mode:
            raise HTTPException(
                status_code=403, detail="Test endpoints only available in test mode"
            )

        start_time = time.perf_counter()
        metrics = get_metrics_collector()
        metrics.inc_counter("http_requests_total")

        try:
            registry = get_running_agent_registry()
            agent = registry.remove(run_id)

            response_time_ms = (time.perf_counter() - start_time) * 1000

            if agent:
                return {
                    "status": "success",
                    "message": f"Unregistered test agent {run_id}",
                    "response_time_ms": response_time_ms,
                }
            else:
                return {
                    "status": "not_found",
                    "message": f"Agent {run_id} not found in registry",
                    "response_time_ms": response_time_ms,
                }

        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Error unregistering test agent: {e}", exc_info=True)
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail=str(e)) from e

    class TestSessionUsageRequest(BaseModel):
        """Request body for setting test session usage."""

        session_id: str
        input_tokens: int = 0
        output_tokens: int = 0
        cache_creation_tokens: int = 0
        cache_read_tokens: int = 0
        total_cost_usd: float = 0.0

    @router.post("/test/set-session-usage")
    async def set_test_session_usage(request: TestSessionUsageRequest) -> dict[str, Any]:
        """
        Set usage statistics for a test session.

        This endpoint is for E2E testing of token budget throttling.
        It allows tests to set session usage values to simulate
        budget consumption.

        Args:
            request: Session usage details

        Returns:
            Update confirmation
        """
        from fastapi import HTTPException

        # Guard: Only available in test mode
        if not server.test_mode:
            raise HTTPException(
                status_code=403, detail="Test endpoints only available in test mode"
            )

        start_time = time.perf_counter()
        metrics = get_metrics_collector()
        metrics.inc_counter("http_requests_total")

        try:
            if server.session_manager is None:
                raise HTTPException(status_code=503, detail="Session manager not available")

            success = server.session_manager.update_usage(
                session_id=request.session_id,
                input_tokens=request.input_tokens,
                output_tokens=request.output_tokens,
                cache_creation_tokens=request.cache_creation_tokens,
                cache_read_tokens=request.cache_read_tokens,
                total_cost_usd=request.total_cost_usd,
            )

            response_time_ms = (time.perf_counter() - start_time) * 1000

            if success:
                return {
                    "status": "success",
                    "session_id": request.session_id,
                    "usage_set": {
                        "input_tokens": request.input_tokens,
                        "output_tokens": request.output_tokens,
                        "cache_creation_tokens": request.cache_creation_tokens,
                        "cache_read_tokens": request.cache_read_tokens,
                        "total_cost_usd": request.total_cost_usd,
                    },
                    "response_time_ms": response_time_ms,
                }
            else:
                return {
                    "status": "not_found",
                    "message": f"Session {request.session_id} not found",
                    "response_time_ms": response_time_ms,
                }

        except Exception as e:
            metrics.inc_counter("http_requests_errors_total")
            logger.error(f"Error setting test session usage: {e}", exc_info=True)
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail=str(e)) from e

    return router
