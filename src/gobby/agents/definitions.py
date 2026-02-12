"""
Named Agent Definitions.

This module defines the schema and loading logic for named agents (Agents V2).
Named agents are reusable configurations that allow child agents to have distinct
lifecycle behavior, solving recursion loops in delegation.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import yaml
from pydantic import BaseModel, Field

from gobby.agents.sandbox import SandboxConfig
from gobby.utils.project_context import get_project_context

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol

AgentSource = Literal["project-file", "user-file", "built-in-file", "project-db", "global-db"]

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
            file: coordinator.yaml

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

    # Execution mode override for this workflow
    # Allows per-workflow control over how the workflow is executed
    mode: Literal["terminal", "embedded", "headless", "self"] | None = None

    # Internal workflows can only be spawned by sessions running the agent's orchestrator.
    # Use this for worker workflows that should not be directly invoked by callers.
    internal: bool = False

    def is_file_reference(self) -> bool:
        """Check if this spec is a file reference vs inline definition."""
        return self.file is not None

    def is_inline(self) -> bool:
        """Check if this spec is an inline definition."""
        return self.file is None and (self.type is not None or len(self.steps) > 0)


class SkillProfileConfig(BaseModel):
    """Typed skill injection profile for agent definitions.

    Controls which skills are injected and in what format
    when context_aware filtering is active.
    """

    audience: str | None = None
    include_skills: list[str] = Field(default_factory=list)
    exclude_skills: list[str] = Field(default_factory=list)
    default_format: str | None = None


class AgentDefinition(BaseModel):
    """
    Configuration for a named agent.

    Supports named workflows via the `workflows` map, allowing a single agent
    definition to contain multiple workflow configurations selectable at spawn time.

    Example:
        name: coordinator
        workflows:
          coordinator:
            file: coordinator.yaml
            mode: self
          worker:
            type: step
            steps: [...]
        default_workflow: coordinator
    """

    name: str
    description: str | None = None

    # Structured prompt fields (composed into preamble at spawn time)
    role: str | None = None  # One-liner identity/persona
    goal: str | None = None  # What success looks like
    personality: str | None = None  # Communication style, tone, anti-patterns
    instructions: str | None = None  # Detailed rules, constraints, approach

    # Execution parameters
    model: str | None = None
    mode: str = "headless"  # Default to headless for stability
    provider: str = "claude"  # Provider: claude, gemini, codex, cursor, windsurf, copilot
    terminal: str = "auto"  # Terminal: auto, tmux

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

    # Lifecycle variables to override parent's lifecycle settings
    lifecycle_variables: dict[str, Any] = Field(default_factory=dict)

    # Default variables passed to the agent
    default_variables: dict[str, Any] = Field(default_factory=dict)

    # Skill injection profile — controls which skills are injected and in what format
    # when context_aware filtering is active.
    skill_profile: SkillProfileConfig | None = None

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

        return None

    def get_effective_mode(
        self, workflow_name: str | None = None
    ) -> Literal["terminal", "embedded", "headless", "self"]:
        """
        Get the effective execution mode for a workflow.

        Resolution:
        1. Check if specified workflow has a mode in its WorkflowSpec
        2. Fall back to agent-level mode

        Args:
            workflow_name: Workflow name to check

        Returns:
            Execution mode to use
        """
        # Check workflow-specific mode
        spec = self.get_workflow_spec(workflow_name)
        if spec and spec.mode:
            return spec.mode

        # Fall back to agent-level mode
        return self.mode  # type: ignore[return-value]

    def get_orchestrator_workflow(self) -> str | None:
        """
        Get the orchestrator workflow name if this agent has one.

        An orchestrator workflow is a default workflow with mode: self,
        meaning it activates in the caller's session rather than spawning
        a new agent. Non-default workflows should only be spawned by
        sessions that have the orchestrator workflow active.

        Returns:
            Workflow name if agent has an orchestrator, None otherwise.
        """
        if not self.default_workflow or not self.workflows:
            return None

        default_spec = self.workflows.get(self.default_workflow)
        if default_spec and default_spec.mode == "self":
            return self.default_workflow

        return None

    def build_prompt_preamble(self) -> str | None:
        """Build structured prompt preamble from role/goal/personality/instructions."""
        parts = []
        if self.role:
            parts.append(f"## Role\n{self.role}")
        if self.goal:
            parts.append(f"## Goal\n{self.goal}")
        if self.personality:
            parts.append(f"## Personality\n{self.personality}")
        if self.instructions:
            parts.append(f"## Instructions\n{self.instructions}")
        return "\n\n".join(parts) if parts else None


class AgentDefinitionInfo(BaseModel):
    """Wrapper that pairs an AgentDefinition with its source metadata."""

    definition: AgentDefinition
    source: AgentSource
    source_path: str | None = None  # filesystem path for file sources
    db_id: str | None = None  # database ID for DB sources
    overridden_by: str | None = None  # if a higher-priority source shadows this

    def to_api_dict(self) -> dict[str, Any]:
        """Serialize for API response, summarizing inline workflow steps."""
        d = self.definition.model_dump()
        # Summarize workflows — strip full step arrays, keep metadata
        if d.get("workflows"):
            for wf_name, wf in d["workflows"].items():
                if isinstance(wf, dict) and "steps" in wf:
                    d["workflows"][wf_name] = {
                        **{k: v for k, v in wf.items() if k != "steps"},
                        "step_count": len(wf["steps"]),
                    }
        return {
            "definition": d,
            "source": self.source,
            "source_path": self.source_path,
            "db_id": self.db_id,
            "overridden_by": self.overridden_by,
        }


class AgentDefinitionLoader:
    """
    Loads agent definitions from YAML files and (optionally) the database.

    Resolution order (highest priority first):
    1. Project .gobby/agents/*.yaml
    2. User ~/.gobby/agents/*.yaml
    3. Built-in src/gobby/install/shared/agents/*.yaml
    4. Project-scoped DB definitions (tied to project_id)
    5. Global DB templates (project_id IS NULL)
    """

    def __init__(self, db: "DatabaseProtocol | None" = None) -> None:
        self._db = db

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
        """Find the agent definition file in search paths.

        Resolution order per search path (project > user > built-in):
        1. Exact filename match: {name}.yaml
        2. YAML name-field match: scan *.yaml files for `name: {name}`
        """
        filename = f"{name}.yaml"

        search_paths = [
            self._get_project_path(),
            self._user_path,
            self._shared_path,
        ]

        # Pass 1: Exact filename match (fast path)
        for path in search_paths:
            if path and path.exists():
                f = path / filename
                if f.exists():
                    return f

        # Pass 2: Match by name field inside YAML files (fallback)
        for path in search_paths:
            if path and path.exists():
                result = self._find_by_yaml_name(path, name)
                if result:
                    return result

        return None

    def _find_by_yaml_name(self, directory: Path, name: str) -> Path | None:
        """Scan YAML files in a directory for one whose 'name' field matches."""
        import yaml

        for yaml_file in directory.glob("*.yaml"):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict) and data.get("name") == name:
                    return yaml_file
            except (OSError, yaml.YAMLError):
                continue
        return None

    def load(self, name: str, project_id: str | None = None) -> AgentDefinition | None:
        """
        Load an agent definition by name.

        Resolution order (highest priority first):
        1. Project/User/Built-in YAML files (via _find_agent_file)
        2. Project-scoped DB definition
        3. Global DB template

        Args:
            name: Name of the agent (e.g. "coordinator")
            project_id: Optional project ID for DB lookups

        Returns:
            AgentDefinition if found, None otherwise.
        """
        path = self._find_agent_file(name)
        if path:
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

        # Fall back to database
        if self._db:
            try:
                from gobby.storage.agent_definitions import (
                    LocalAgentDefinitionManager,
                )

                mgr = LocalAgentDefinitionManager(self._db)
                row = mgr.get_by_name(name, project_id)
                if row:
                    defn: AgentDefinition = mgr.export_to_definition(row.id)
                    return defn
            except Exception as e:
                logger.error(f"Failed to load agent definition '{name}' from DB: {e}")

        logger.debug(f"Agent definition '{name}' not found")
        return None

    def _scan_directory(
        self,
        directory: Path | None,
        source: AgentSource,
        seen: dict[str, AgentDefinitionInfo],
    ) -> None:
        """Scan a directory for YAML agent definitions."""
        if not directory or not directory.exists():
            return
        for yaml_file in sorted(directory.glob("*.yaml")):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    continue
                name = data.get("name", yaml_file.stem)
                data["name"] = name
                defn = AgentDefinition(**data)
                old = seen.get(name)
                if old:
                    old.overridden_by = source
                seen[name] = AgentDefinitionInfo(
                    definition=defn,
                    source=source,
                    source_path=str(yaml_file),
                )
            except Exception as e:
                logger.warning(f"Failed to load agent definition from {yaml_file}: {e}")

    def list_all(self, project_id: str | None = None) -> list[AgentDefinitionInfo]:
        """
        List all agent definitions from all sources, merged by priority.

        Scans in reverse priority order (lowest first); higher-priority
        sources overwrite lower ones.  Each overridden entry gets tagged
        with ``overridden_by``.

        Returns:
            Sorted list of AgentDefinitionInfo (by name).
        """
        seen: dict[str, AgentDefinitionInfo] = {}

        # 5. Global DB templates (lowest priority)
        if self._db:
            try:
                from gobby.storage.agent_definitions import (
                    LocalAgentDefinitionManager,
                )

                mgr = LocalAgentDefinitionManager(self._db)
                for row in mgr.list_global():
                    defn = mgr.export_to_definition(row.id)
                    seen[row.name] = AgentDefinitionInfo(
                        definition=defn, source="global-db", db_id=row.id
                    )
            except Exception as e:
                logger.warning(f"Failed to load global DB definitions: {e}")

        # 4. Project DB definitions
        if self._db and project_id:
            try:
                from gobby.storage.agent_definitions import (
                    LocalAgentDefinitionManager,
                )

                mgr = LocalAgentDefinitionManager(self._db)
                for row in mgr.list_by_project(project_id):
                    defn = mgr.export_to_definition(row.id)
                    old = seen.get(row.name)
                    if old:
                        old.overridden_by = "project-db"
                    seen[row.name] = AgentDefinitionInfo(
                        definition=defn, source="project-db", db_id=row.id
                    )
            except Exception as e:
                logger.warning(f"Failed to load project DB definitions: {e}")

        # 3. Built-in files
        self._scan_directory(self._shared_path, "built-in-file", seen)

        # 2. User files
        self._scan_directory(self._user_path, "user-file", seen)

        # 1. Project files (highest priority)
        project_path = self._get_project_path()
        if project_path:
            self._scan_directory(project_path, "project-file", seen)

        return sorted(seen.values(), key=lambda x: x.definition.name)
