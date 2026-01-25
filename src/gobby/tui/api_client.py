"""HTTP client for Gobby daemon API."""

from __future__ import annotations

from typing import Any

import httpx


class GobbyAPIClient:
    """HTTP client for communicating with Gobby daemon."""

    def __init__(self, base_url: str = "http://localhost:60334") -> None:
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> GobbyAPIClient:
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return self._client

    # ==================== Admin Endpoints ====================

    async def get_status(self) -> dict[str, Any]:
        """Get comprehensive daemon status."""
        response = await self.client.get("/admin/status")
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    async def get_config(self) -> dict[str, Any]:
        """Get daemon configuration."""
        response = await self.client.get("/admin/config")
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    async def get_metrics(self) -> str:
        """Get Prometheus metrics."""
        response = await self.client.get("/admin/metrics")
        response.raise_for_status()
        return response.text

    # ==================== Session Endpoints ====================

    async def list_sessions(
        self,
        status: str | None = None,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List sessions with optional filtering."""
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if project_id:
            params["project_id"] = project_id
        response = await self.client.get("/sessions", params=params)
        response.raise_for_status()
        result: list[dict[str, Any]] = response.json()
        return result

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Get session details."""
        response = await self.client.get(f"/sessions/{session_id}")
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    # ==================== MCP Tool Endpoints ====================

    async def list_mcp_servers(self) -> dict[str, Any]:
        """List available MCP servers."""
        response = await self.client.get("/mcp/servers")
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    async def list_tools(self, server_name: str) -> dict[str, Any]:
        """List tools from an MCP server."""
        response = await self.client.get(f"/mcp/{server_name}/tools")
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a tool on an MCP server."""
        response = await self.client.post(
            f"/mcp/{server_name}/tools/{tool_name}",
            json=arguments or {},
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    # ==================== Task Helpers (via MCP) ====================

    async def list_tasks(
        self,
        status: str | None = None,
        task_type: str | None = None,
        parent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List tasks with optional filtering."""
        args: dict[str, Any] = {}
        if status:
            args["status"] = status
        if task_type:
            args["task_type"] = task_type
        if parent_id:
            args["parent_id"] = parent_id
        response = await self.call_tool("gobby-tasks", "list_tasks", args)
        result = response.get("result", {})
        tasks: list[dict[str, Any]] = result.get("tasks", [])
        return tasks

    async def get_task(self, task_id: str) -> dict[str, Any]:
        """Get task details."""
        response = await self.call_tool("gobby-tasks", "get_task", {"task_id": task_id})
        result = response.get("result", {})
        task: dict[str, Any] = result.get("task", {})
        return task

    async def create_task(
        self,
        title: str,
        task_type: str = "task",
        description: str | None = None,
        priority: int = 3,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new task."""
        args: dict[str, Any] = {
            "title": title,
            "task_type": task_type,
            "priority": priority,
        }
        if description:
            args["description"] = description
        if session_id:
            args["session_id"] = session_id
        return await self.call_tool("gobby-tasks", "create_task", args)

    async def update_task(
        self,
        task_id: str,
        status: str | None = None,
        title: str | None = None,
        priority: int | None = None,
    ) -> dict[str, Any]:
        """Update task properties."""
        args: dict[str, Any] = {"task_id": task_id}
        if status:
            args["status"] = status
        if title:
            args["title"] = title
        if priority is not None:
            args["priority"] = priority
        return await self.call_tool("gobby-tasks", "update_task", args)

    async def close_task(
        self,
        task_id: str,
        commit_sha: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Close a task."""
        args: dict[str, Any] = {"task_id": task_id}
        if commit_sha:
            args["commit_sha"] = commit_sha
        if reason:
            args["reason"] = reason
        return await self.call_tool("gobby-tasks", "close_task", args)

    async def suggest_next_task(self) -> dict[str, Any]:
        """Get the recommended next task."""
        return await self.call_tool("gobby-tasks", "suggest_next_task", {})

    # ==================== Memory Helpers (via MCP) ====================

    async def recall(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search memories."""
        response = await self.call_tool(
            "gobby-memory",
            "recall",
            {"query": query, "limit": limit},
        )
        result = response.get("result", {})
        memories: list[dict[str, Any]] = result.get("memories", [])
        return memories

    async def remember(self, content: str, importance: float = 0.5) -> dict[str, Any]:
        """Store a memory."""
        return await self.call_tool(
            "gobby-memory",
            "remember",
            {"content": content, "importance": importance},
        )

    # ==================== Agent Helpers (via MCP) ====================

    async def list_agents(self) -> list[dict[str, Any]]:
        """List running agents."""
        response = await self.call_tool("gobby-agents", "list_agents", {})
        result = response.get("result", {})
        agents: list[dict[str, Any]] = result.get("agents", [])
        return agents

    async def start_agent(
        self,
        prompt: str,
        mode: str = "terminal",
        workflow: str | None = None,
        parent_session_id: str | None = None,
    ) -> dict[str, Any]:
        """Spawn a new agent."""
        args: dict[str, Any] = {"prompt": prompt, "mode": mode}
        if workflow:
            args["workflow"] = workflow
        if parent_session_id:
            args["parent_session_id"] = parent_session_id
        return await self.call_tool("gobby-agents", "start_agent", args)

    async def cancel_agent(self, run_id: str) -> dict[str, Any]:
        """Cancel a running agent."""
        return await self.call_tool("gobby-agents", "cancel_agent", {"run_id": run_id})

    # ==================== Worktree Helpers (via MCP) ====================

    async def list_worktrees(self) -> list[dict[str, Any]]:
        """List git worktrees."""
        response = await self.call_tool("gobby-worktrees", "list_worktrees", {})
        result = response.get("result", {})
        worktrees: list[dict[str, Any]] = result.get("worktrees", [])
        return worktrees

    # ==================== Workflow Helpers (via MCP) ====================

    async def get_workflow_status(self) -> dict[str, Any]:
        """Get current workflow status."""
        return await self.call_tool("gobby-workflows", "get_status", {})

    async def activate_workflow(self, name: str) -> dict[str, Any]:
        """Activate a workflow."""
        return await self.call_tool("gobby-workflows", "activate_workflow", {"name": name})

    async def set_workflow_variable(self, name: str, value: Any) -> dict[str, Any]:
        """Set a workflow variable."""
        return await self.call_tool(
            "gobby-workflows",
            "set_variable",
            {"name": name, "value": value},
        )

    # ==================== Health Check ====================

    async def is_healthy(self) -> bool:
        """Check if daemon is responsive."""
        try:
            await self.get_status()
            return True
        except Exception:
            return False
