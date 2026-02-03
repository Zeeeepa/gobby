"""
Named Agent Definitions.

This module defines the schema and loading logic for named agents (Agents V2).
Named agents are reusable configurations that allow child agents to have distinct
lifecycle behavior, solving recursion loops in delegation.
"""

import logging
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from gobby.agents.sandbox import SandboxConfig
from gobby.utils.project_context import get_project_context

logger = logging.getLogger(__name__)


class WorkflowSpec(BaseModel):
    """
    Workflow specification - either a file reference or inline definition.

    Supports two modes:
    1. File reference: `file: "workflow-name.yaml"` - loads from workflow search paths
    2. Inline definition: Full workflow definition embedded in agent YAML

    Examples:
        # File reference
        workflows:
          box:
            file: meeseeks-box.yaml

        # Inline definition
        workflows:
          worker:
            type: step
            steps:
              - name: work
                description: "Do the work"
    """

    # File reference mode
    file: str | None = None

    # Inline workflow fields (subset of WorkflowDefinition)
    type: Literal["step", "lifecycle", "pipeline"] | None = None
    name: str | None = None
    description: str | None = None
    version: str = "1.0"
    variables: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    exit_condition: str | None = None
    on_premature_stop: dict[str, Any] | None = None
    settings: dict[str, Any] = Field(default_factory=dict)

    # Pipeline-specific fields
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)

    def is_file_reference(self) -> bool:
        """Check if this spec is a file reference vs inline definition."""
        return self.file is not None

    def is_inline(self) -> bool:
        """Check if this spec is an inline definition."""
        return self.file is None and (self.type is not None or len(self.steps) > 0)


class AgentDefinition(BaseModel):
    """
    Configuration for a named agent.

    Supports named workflows via the `workflows` map, allowing a single agent
    definition to contain multiple workflow configurations selectable at spawn time.

    Example:
        name: meeseeks
        workflows:
          box:
            file: meeseeks-box.yaml
          worker:
            type: step
            steps: [...]
        default_workflow: box
    """

    name: str
    description: str | None = None

    # Execution parameters
    model: str | None = None
    mode: str = "headless"  # Default to headless for stability
    provider: str = "claude"  # Provider: claude, gemini, codex, cursor, windsurf, copilot

    # Isolation configuration
    isolation: Literal["current", "worktree", "clone"] | None = None
    branch_prefix: str | None = None
    base_branch: str = "main"

    # Sandbox configuration
    sandbox: SandboxConfig | None = None

    # Named workflows map
    # Keys are workflow names, values are WorkflowSpec (file ref or inline)
    workflows: dict[str, WorkflowSpec] | None = None

    # Default workflow name (key in workflows map)
    default_workflow: str | None = None

    # Legacy: single workflow reference (for backwards compatibility)
    workflow: str | None = None

    # Lifecycle variables to override parent's lifecycle settings
    lifecycle_variables: dict[str, Any] = Field(default_factory=dict)

    # Default variables passed to the agent
    default_variables: dict[str, Any] = Field(default_factory=dict)

    # Execution limits
    timeout: float = 120.0
    max_turns: int = 10

    def get_workflow_spec(self, workflow_name: str | None = None) -> WorkflowSpec | None:
        """
        Get a workflow spec by name, or the default workflow.

        Args:
            workflow_name: Name of workflow to get. If None, returns default_workflow.

        Returns:
            WorkflowSpec if found, None otherwise.
        """
        if not self.workflows:
            return None

        name = workflow_name or self.default_workflow
        if not name:
            return None

        return self.workflows.get(name)

    def get_effective_workflow(self, workflow_name: str | None = None) -> str | None:
        """
        Get the effective workflow name/file for spawning.

        Resolution order:
        1. If workflow_name specified and in workflows map -> resolve that spec
        2. If workflow_name specified but NOT in map -> return workflow_name (external ref)
        3. If no workflow_name -> check default_workflow in workflows map
        4. Fallback to legacy `workflow` field

        Args:
            workflow_name: Explicit workflow name parameter

        Returns:
            Workflow name/file to use, or None if no workflow configured.
        """
        # Check if workflow_name matches a named workflow in the map
        if workflow_name and self.workflows and workflow_name in self.workflows:
            spec = self.workflows[workflow_name]
            if spec.is_file_reference():
                # Return the file reference (without .yaml extension if present)
                file_name = spec.file or ""
                return file_name.removesuffix(".yaml")
            else:
                # Inline workflow - return qualified name for registration
                return f"{self.name}:{workflow_name}"

        # If workflow_name specified but not in map, treat as external workflow reference
        if workflow_name:
            return workflow_name

        # Try default_workflow from map
        if self.default_workflow and self.workflows and self.default_workflow in self.workflows:
            spec = self.workflows[self.default_workflow]
            if spec.is_file_reference():
                file_name = spec.file or ""
                return file_name.removesuffix(".yaml")
            else:
                return f"{self.name}:{self.default_workflow}"

        # Fallback to legacy workflow field
        return self.workflow


class AgentDefinitionLoader:
    """
    Loads agent definitions from YAML files.

    Search priority (later overrides earlier):
    1. Built-in: src/gobby/install/shared/agents/
    2. User-level: ~/.gobby/agents/
    3. Project-level: .gobby/agents/
    """

    def __init__(self) -> None:
        # Determine paths
        # Built-in path relative to this file
        # src/gobby/agents/definitions.py -> src/gobby/install/shared/agents/
        base_dir = Path(__file__).parent.parent
        self._shared_path = base_dir / "install" / "shared" / "agents"

        # User path
        self._user_path = Path.home() / ".gobby" / "agents"

        # Project path (tried dynamically based on current context)
        self._project_path: Path | None = None

    def _get_project_path(self) -> Path | None:
        """Get current project path from context."""
        ctx = get_project_context()
        if ctx and ctx.get("project_path"):
            return Path(ctx["project_path"]) / ".gobby" / "agents"
        return None

    def _find_agent_file(self, name: str) -> Path | None:
        """Find the agent definition file in search paths."""
        filename = f"{name}.yaml"

        # Check project first (highest priority for finding logic, but technically
        # we want to load from lowest to highest if we were merging, but we just
        # want the "winner" here. Since we don't merge partial definitions,
        # finding the first one in priority order is sufficient.)

        # 1. Project
        project_agents = self._get_project_path()
        if project_agents and project_agents.exists():
            f = project_agents / filename
            if f.exists():
                return f

        # 2. User
        if self._user_path.exists():
            f = self._user_path / filename
            if f.exists():
                return f

        # 3. Built-in (Shared)
        if self._shared_path.exists():
            f = self._shared_path / filename
            if f.exists():
                return f

        return None

    def load(self, name: str) -> AgentDefinition | None:
        """
        Load an agent definition by name.

        Args:
            name: Name of the agent (e.g. "validation-runner")

        Returns:
            AgentDefinition if found, None otherwise.
        """
        path = self._find_agent_file(name)
        if not path:
            logger.debug(f"Agent definition '{name}' not found")
            return None

        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            # Ensure name matches filename/request if not specified
            if "name" not in data:
                data["name"] = name

            return AgentDefinition(**data)
        except Exception as e:
            logger.error(f"Failed to load agent definition '{name}' from {path}: {e}")
            return None
