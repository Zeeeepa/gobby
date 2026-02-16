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

AgentSource = Literal["bundled", "global", "project", "project-file", "user-file", "built-in-file", "project-db", "global-db"]

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
    mode: Literal["terminal", "embedded", "headless", "self"] = "headless"
    provider: str = "claude"  # Provider: claude, gemini, codex, cursor, windsurf, copilot
    terminal: Literal["auto", "tmux"] = "auto"  # Terminal: auto, tmux

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
        return self.mode

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
    Loads agent definitions from the database (DB-first pattern).

    The database is the sole runtime source of truth. Bundled agent YAML files
    are synced into the DB at daemon startup via sync_bundled_agents().

    Resolution order (via SQL scope precedence):
    1. Project-scoped definitions (scope='project')
    2. Global definitions (scope='global')
    3. Bundled definitions (scope='bundled')

    File-scanning methods are retained as static helpers for the import endpoint.
    """

    def __init__(self, db: "DatabaseProtocol | None" = None) -> None:
        self._db = db

    def _get_db(self) -> "DatabaseProtocol":
        """Get DB, creating a lazy fallback if none was injected."""
        if self._db is not None:
            return self._db
        from gobby.storage.database import LocalDatabase

        self._db = LocalDatabase()
        return self._db

    def _get_manager(self) -> Any:
        from gobby.storage.agent_definitions import LocalAgentDefinitionManager

        return LocalAgentDefinitionManager(self._get_db())

    def load(self, name: str, project_id: str | None = None) -> AgentDefinition | None:
        """
        Load an agent definition by name from the database.

        Uses scope precedence: project > global > bundled.

        Args:
            name: Name of the agent (e.g. "coordinator")
            project_id: Optional project ID for scope resolution

        Returns:
            AgentDefinition if found, None otherwise.
        """
        try:
            mgr = self._get_manager()
            row = mgr.get_by_name(name, project_id)
            if row:
                defn: AgentDefinition = mgr.export_to_definition(row.id)
                return defn
        except Exception as e:
            logger.error(f"Failed to load agent definition '{name}' from DB: {e}")

        logger.debug(f"Agent definition '{name}' not found")
        return None

    def list_all(self, project_id: str | None = None) -> list[AgentDefinitionInfo]:
        """
        List all agent definitions from the database, deduplicated by name.

        Higher-priority scopes shadow lower ones (project > global > bundled).

        Returns:
            Sorted list of AgentDefinitionInfo (by name).
        """
        try:
            mgr = self._get_manager()
            rows = mgr.list_all(project_id=project_id)
        except Exception as e:
            logger.warning(f"Failed to load agent definitions from DB: {e}")
            return []

        seen: dict[str, AgentDefinitionInfo] = {}
        for row in rows:
            try:
                defn = mgr.export_to_definition(row.id)
                old = seen.get(row.name)
                if old:
                    # Higher-priority scope overwrites lower
                    _SCOPE_PRIORITY = {"project": 1, "global": 2, "bundled": 3}
                    old_priority = _SCOPE_PRIORITY.get(old.source, 99)  # type: ignore[arg-type]
                    new_priority = _SCOPE_PRIORITY.get(row.scope, 99)
                    if new_priority < old_priority:
                        old.overridden_by = row.scope
                        seen[row.name] = AgentDefinitionInfo(
                            definition=defn,
                            source=row.scope,
                            source_path=row.source_path,
                            db_id=row.id,
                        )
                    # else: existing has higher priority, skip
                else:
                    seen[row.name] = AgentDefinitionInfo(
                        definition=defn,
                        source=row.scope,
                        source_path=row.source_path,
                        db_id=row.id,
                    )
            except Exception as e:
                logger.warning(f"Failed to export agent definition '{row.name}': {e}")

        return sorted(seen.values(), key=lambda x: x.definition.name)

    @staticmethod
    def load_from_file(name: str) -> AgentDefinition | None:
        """Load an agent definition from YAML files only (for import endpoint).

        Searches project, user, and built-in paths in priority order.

        Args:
            name: Name of the agent definition to find

        Returns:
            AgentDefinition if found, None otherwise.
        """
        base_dir = Path(__file__).parent.parent
        shared_path = base_dir / "install" / "shared" / "agents"
        user_path = Path.home() / ".gobby" / "agents"

        project_path: Path | None = None
        ctx = get_project_context()
        if ctx and ctx.get("project_path"):
            project_path = Path(ctx["project_path"]) / ".gobby" / "agents"

        filename = f"{name}.yaml"
        search_paths = [project_path, user_path, shared_path]

        # Pass 1: Exact filename match (fast path)
        for path in search_paths:
            if path and path.exists():
                f = path / filename
                if f.exists():
                    try:
                        with open(f, encoding="utf-8") as fh:
                            data = yaml.safe_load(fh)
                        if "name" not in data:
                            data["name"] = name
                        return AgentDefinition(**data)
                    except Exception as e:
                        logger.error(f"Failed to load agent definition '{name}' from {f}: {e}")
                        return None

        # Pass 2: Match by name field inside YAML files
        for path in search_paths:
            if path and path.exists():
                for yaml_file in path.glob("*.yaml"):
                    try:
                        with open(yaml_file, encoding="utf-8") as fh:
                            data = yaml.safe_load(fh)
                        if isinstance(data, dict) and data.get("name") == name:
                            return AgentDefinition(**data)
                    except (OSError, yaml.YAMLError):
                        continue

        return None
