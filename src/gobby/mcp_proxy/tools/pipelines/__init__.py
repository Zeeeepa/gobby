"""
Internal MCP tools for Gobby Pipeline System.

Exposes functionality for:
- list_pipelines: Discover available pipeline definitions
- Dynamic pipeline tools: Pipelines with expose_as_tool=True are exposed as MCP tools

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool, list_tools, get_tool_schema).
"""

import logging
from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.pipelines._discovery import list_pipelines
from gobby.mcp_proxy.tools.pipelines._execution import (
    approve_pipeline,
    get_pipeline_status,
    reject_pipeline,
    run_pipeline,
)

logger = logging.getLogger(__name__)

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

    # Register dynamic tools for pipelines with expose_as_tool=True
    _register_exposed_pipeline_tools(registry, _loader, _executor)

    @registry.tool(
        name="list_pipelines",
        description="List available pipeline definitions from project and global directories.",
    )
    async def _list_pipelines(
        project_path: str | None = None,
    ) -> dict[str, Any]:
        return await list_pipelines(_loader, project_path)

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

    @registry.tool(
        name="approve_pipeline",
        description="Approve a pipeline execution that is waiting for approval.",
    )
    async def _approve_pipeline(
        token: str,
        approved_by: str | None = None,
    ) -> dict[str, Any]:
        return await approve_pipeline(
            executor=_executor,
            token=token,
            approved_by=approved_by,
        )

    @registry.tool(
        name="reject_pipeline",
        description="Reject a pipeline execution that is waiting for approval.",
    )
    async def _reject_pipeline(
        token: str,
        rejected_by: str | None = None,
    ) -> dict[str, Any]:
        return await reject_pipeline(
            executor=_executor,
            token=token,
            rejected_by=rejected_by,
        )

    @registry.tool(
        name="get_pipeline_status",
        description="Get the status of a pipeline execution including step details.",
    )
    def _get_pipeline_status(
        execution_id: str,
    ) -> dict[str, Any]:
        return get_pipeline_status(
            execution_manager=_execution_manager,
            execution_id=execution_id,
        )

    return registry


def _register_exposed_pipeline_tools(
    registry: InternalToolRegistry,
    loader: Any | None,
    executor: Any | None,
) -> None:
    """
    Register dynamic tools for pipelines with expose_as_tool=True.

    Each exposed pipeline becomes an MCP tool named "pipeline:<pipeline_name>".

    Args:
        registry: The registry to add tools to
        loader: WorkflowLoader for discovering pipelines
        executor: PipelineExecutor for running pipelines
    """
    if loader is None:
        logger.debug("Skipping dynamic pipeline tools: no loader")
        return

    try:
        discovered = loader.discover_pipeline_workflows_sync()
    except Exception:
        logger.warning("Failed to discover pipelines for dynamic tools", exc_info=True)
        return

    for workflow in discovered:
        pipeline = workflow.definition

        # Only expose pipelines with expose_as_tool=True
        if not getattr(pipeline, "expose_as_tool", False):
            continue

        _create_pipeline_tool(registry, pipeline, loader, executor)


def _create_pipeline_tool(
    registry: InternalToolRegistry,
    pipeline: Any,
    loader: Any,
    executor: Any | None,
) -> None:
    """
    Create a dynamic tool for a single pipeline.

    Args:
        registry: The registry to add the tool to
        pipeline: The PipelineDefinition to expose
        loader: WorkflowLoader for loading pipelines
        executor: PipelineExecutor for running pipelines
    """
    tool_name = f"pipeline:{pipeline.name}"
    description = pipeline.description or f"Run the {pipeline.name} pipeline"

    # Build input schema from pipeline inputs
    input_schema = _build_input_schema(pipeline)

    # Create closure to capture pipeline name
    pipeline_name = pipeline.name

    async def _execute_pipeline(**kwargs: Any) -> dict[str, Any]:
        return await run_pipeline(
            loader=loader,
            executor=executor,
            name=pipeline_name,
            inputs=kwargs,
            project_id="",
        )

    # Register the tool with the schema
    registry.register(
        name=tool_name,
        description=description,
        func=_execute_pipeline,
        input_schema=input_schema,
    )

    logger.debug(f"Registered dynamic pipeline tool: {tool_name}")


def _build_input_schema(pipeline: Any) -> dict[str, Any]:
    """
    Build JSON Schema for pipeline inputs.

    Args:
        pipeline: The PipelineDefinition

    Returns:
        JSON Schema dict for the pipeline's inputs
    """
    properties = {}
    required = []

    for name, input_def in pipeline.inputs.items():
        if isinstance(input_def, dict):
            # Input is already a schema-like dict
            prop = {}
            if "type" in input_def:
                prop["type"] = input_def["type"]
            else:
                prop["type"] = "string"

            if "description" in input_def:
                prop["description"] = input_def["description"]

            if "default" in input_def:
                prop["default"] = input_def["default"]
            else:
                # No default means required
                required.append(name)

            properties[name] = prop
        else:
            # Input is a simple default value
            properties[name] = {
                "type": "string",
                "default": input_def,
            }

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }

    if required:
        schema["required"] = required

    return schema
