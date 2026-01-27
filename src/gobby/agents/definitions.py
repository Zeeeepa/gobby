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


class AgentDefinition(BaseModel):
    """
    Configuration for a named agent.
    """

    name: str
    description: str | None = None

    # Execution parameters
    model: str | None = None
    mode: str = "headless"  # Default to headless for stability
    provider: str = "claude"  # Provider: claude, gemini, codex

    # Isolation configuration
    isolation: Literal["current", "worktree", "clone"] | None = None
    branch_prefix: str | None = None
    base_branch: str = "main"

    # Sandbox configuration
    sandbox: SandboxConfig | None = None

    # Workflow configuration
    workflow: str | None = None

    # Lifecycle variables to override parent's lifecycle settings
    lifecycle_variables: dict[str, Any] = Field(default_factory=dict)

    # Default variables passed to the agent
    default_variables: dict[str, Any] = Field(default_factory=dict)

    # Execution limits
    timeout: float = 120.0
    max_turns: int = 10


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
