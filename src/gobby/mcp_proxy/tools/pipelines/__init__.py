"""
Internal MCP tools for Gobby Pipeline System.

Exposes functionality for:
- list_pipelines: Discover available pipeline definitions

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool, list_tools, get_tool_schema).
"""

from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.pipelines._discovery import list_pipelines
from gobby.mcp_proxy.tools.pipelines._execution import run_pipeline

__all__ = [
    "create_pipelines_registry",
]


def create_pipelines_registry(
    loader: Any | None = None,
    executor: Any | None = None,
    execution_manager: Any | None = None,
) -> InternalToolRegistry:
    """
    Create a pipeline tool registry with all pipeline-related tools.

    Args:
        loader: WorkflowLoader instance for discovering pipelines
        executor: PipelineExecutor instance for running pipelines
        execution_manager: LocalPipelineExecutionManager for tracking executions

    Returns:
        InternalToolRegistry with pipeline tools registered
    """
    _loader = loader
    _executor = executor
    _execution_manager = execution_manager

    registry = InternalToolRegistry(
        name="gobby-pipelines",
        description="Pipeline management - list, run, and monitor pipeline executions",
    )

    @registry.tool(
        name="list_pipelines",
        description="List available pipeline definitions from project and global directories.",
    )
    def _list_pipelines(
        project_path: str | None = None,
    ) -> dict[str, Any]:
        return list_pipelines(_loader, project_path)

    @registry.tool(
        name="run_pipeline",
        description="Run a pipeline by name with given inputs.",
    )
    async def _run_pipeline(
        name: str,
        inputs: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        return await run_pipeline(
            loader=_loader,
            executor=_executor,
            name=name,
            inputs=inputs or {},
            project_id=project_id or "",
        )

    return registry
