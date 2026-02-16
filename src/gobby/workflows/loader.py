import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .definitions import PipelineDefinition, WorkflowDefinition
from .loader_cache import (
    DiscoveredWorkflow,
    _CachedDiscovery,
    _CachedEntry,
    clear_cache,
)
from .loader_discovery import (
    discover_lifecycle_workflows,
    discover_pipeline_workflows,
    discover_workflows,
)
from .loader_sync import WorkflowLoaderSyncMixin
from .loader_validation import (
    _check_refs,
    _extract_step_refs,
    _validate_pipeline_references,
)

__all__ = ["WorkflowLoader"]

if TYPE_CHECKING:
    from gobby.agents.definitions import WorkflowSpec
    from gobby.storage.database import DatabaseProtocol
    from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager

logger = logging.getLogger(__name__)


class WorkflowLoader(WorkflowLoaderSyncMixin):
    def __init__(
        self,
        db: "DatabaseProtocol | None" = None,
        # Legacy parameters kept for backward compatibility with tests
        workflow_dirs: list[Path] | None = None,
        bundled_dir: Path | None = None,
    ):
        # Legacy directory fields — unused at runtime but kept so tests that
        # pass workflow_dirs= still instantiate without errors.
        self.global_dirs = workflow_dirs or [Path.home() / ".gobby" / "workflows"]
        self._bundled_dir = bundled_dir
        self._cache: dict[str, _CachedEntry] = {}
        # Cache for discovered workflows per project path
        self._discovery_cache: dict[str, _CachedDiscovery] = {}
        # Database for DB-first workflow lookup (the only runtime source)
        self.db: DatabaseProtocol | None = db
        self._def_manager: LocalWorkflowDefinitionManager | None = None

    @property
    def def_manager(self) -> "LocalWorkflowDefinitionManager | None":
        """Lazy-init the workflow definition manager."""
        if self._def_manager is None and self.db is not None:
            from gobby.storage.workflow_definitions import LocalWorkflowDefinitionManager

            self._def_manager = LocalWorkflowDefinitionManager(self.db)
        return self._def_manager

    def _load_from_db(
        self, name: str, project_id: str | None = None
    ) -> WorkflowDefinition | PipelineDefinition | None:
        """Try to load a workflow definition from the database.

        Returns the parsed definition if found in DB, None otherwise.
        """
        mgr = self.def_manager
        if mgr is None:
            return None
        row = mgr.get_by_name(name, project_id=project_id)
        if row is None:
            return None
        try:
            data = json.loads(row.definition_json)

            # Resolve extends from DB
            if "extends" in data:
                parent_name = data["extends"]
                parent_def = self._load_from_db(parent_name, project_id=project_id)
                if parent_def:
                    data = self._merge_workflows(parent_def.model_dump(), data)
                else:
                    logger.warning(f"Parent workflow '{parent_name}' not found in DB for '{name}'")

            # Resolve imports from DB
            if data.get("imports"):
                data = self._resolve_imports_from_db(data)

            if row.workflow_type == "pipeline" or data.get("type") == "pipeline":
                self._validate_pipeline_references(data)
                return PipelineDefinition(**data)
            else:
                if "type" in data and "enabled" not in data:
                    data["enabled"] = data["type"] == "lifecycle"
                return WorkflowDefinition(**data)
        except Exception as e:
            logger.error(f"Failed to parse DB workflow '{name}': {e}", exc_info=True)
            return None

    def _resolve_imports_from_db(self, data: dict[str, Any]) -> dict[str, Any]:
        """Resolve 'imports' by loading rule definitions from the DB.

        Each import name is looked up via RuleStore.get_rules_by_source_file()
        (matching against the original YAML filename).  Imported rules are
        merged first, then file-local rule_definitions override.
        """
        imports = data.get("imports", [])
        if not imports:
            return data

        from gobby.storage.rules import RuleStore

        if self.db is None:
            logger.warning("Cannot resolve imports without database")
            return data

        store = RuleStore(self.db)
        merged_rules: dict[str, Any] = {}

        # Cache bundled rules once to avoid O(n*m) repeated DB queries
        all_bundled = store.list_rules(tier="bundled")

        for import_name in imports:
            # Search by source_file suffix matching the import name
            # Import names are like "safety" matching ".../safety.yaml"
            for rule in all_bundled:
                sf = rule.get("source_file", "") or ""
                # Match if source_file ends with /{import_name}.yaml
                if sf.endswith(f"/{import_name}.yaml") or sf.endswith(f"\\{import_name}.yaml"):
                    merged_rules[rule["name"]] = rule["definition"]

        # File-local rule_definitions override imported
        local_rules = data.get("rule_definitions", {})
        merged_rules.update(local_rules)

        data["rule_definitions"] = merged_rules
        return data

    async def load_workflow(
        self,
        name: str,
        project_path: Path | str | None = None,
        _inheritance_chain: list[str] | None = None,
    ) -> WorkflowDefinition | PipelineDefinition | None:
        """
        Load a workflow by name.

        DB-only at runtime.  YAML files are imported to the database
        during ``gobby install``.

        Qualified names (agent:workflow) are resolved by loading the inline
        workflow from the agent definition.

        Args:
            name: Workflow name, or qualified name (agent:workflow)
            project_path: Optional project directory for scoped lookup.
            _inheritance_chain: Internal parameter for cycle detection.

        Raises:
            ValueError: If circular inheritance is detected or pipeline
                        references are invalid.
        """
        # Cycle detection
        if _inheritance_chain is None:
            _inheritance_chain = []

        if name in _inheritance_chain:
            cycle_path = " -> ".join(_inheritance_chain + [name])
            logger.error(f"Circular workflow inheritance detected: {cycle_path}")
            raise ValueError(f"Circular workflow inheritance detected: {cycle_path}")

        # Cache check
        cache_key = f"{project_path or 'global'}:{name}"
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            return entry.definition

        # Check for qualified name (agent:workflow)
        if ":" in name:
            agent_workflow = await self._load_from_agent_definition(name, project_path)
            if agent_workflow:
                self._cache[cache_key] = _CachedEntry(
                    definition=agent_workflow, path=None, mtime=0.0
                )
                return agent_workflow

        # DB lookup (the only runtime source)
        project_id = str(project_path) if project_path else None
        db_definition = self._load_from_db(name, project_id=project_id)
        if db_definition is not None:
            self._cache[cache_key] = _CachedEntry(definition=db_definition, path=None, mtime=0.0)
            return db_definition

        logger.debug(f"Workflow '{name}' not found in database")
        return None

    async def load_pipeline(
        self,
        name: str,
        project_path: Path | str | None = None,
        _inheritance_chain: list[str] | None = None,
    ) -> PipelineDefinition | None:
        """
        Load a pipeline workflow by name.
        Only returns workflows with type='pipeline'.

        DB-only at runtime.

        Args:
            name: Pipeline name
            project_path: Optional project directory for scoped lookup.
            _inheritance_chain: Internal parameter for cycle detection.

        Returns:
            PipelineDefinition if found and type is 'pipeline', None otherwise.
        """
        if _inheritance_chain is None:
            _inheritance_chain = []

        if name in _inheritance_chain:
            cycle_path = " -> ".join(_inheritance_chain + [name])
            logger.error(f"Circular pipeline inheritance detected: {cycle_path}")
            raise ValueError(f"Circular pipeline inheritance detected: {cycle_path}")

        # Cache check
        cache_key = f"pipeline:{project_path or 'global'}:{name}"
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if isinstance(entry.definition, PipelineDefinition):
                return entry.definition
            return None

        # DB lookup
        project_id = str(project_path) if project_path else None
        db_definition = self._load_from_db(name, project_id=project_id)
        if db_definition is not None:
            if isinstance(db_definition, PipelineDefinition):
                self._cache[cache_key] = _CachedEntry(
                    definition=db_definition, path=None, mtime=0.0
                )
                return db_definition
            logger.debug(f"'{name}' is not a pipeline (type={getattr(db_definition, 'type', '?')})")
            return None

        logger.debug(f"Pipeline '{name}' not found in database")
        return None

    async def _load_from_agent_definition(
        self,
        qualified_name: str,
        project_path: Path | str | None = None,
    ) -> WorkflowDefinition | PipelineDefinition | None:
        """
        Load an inline workflow from an agent definition.

        Qualified names like "meeseeks:worker" are parsed to extract the agent name
        and workflow name, then the workflow is loaded from the agent's workflows map.
        """
        if ":" not in qualified_name:
            return None

        agent_name, workflow_name = qualified_name.split(":", 1)

        from gobby.agents.definitions import AgentDefinitionLoader

        agent_loader = AgentDefinitionLoader()
        agent_def = agent_loader.load(agent_name)

        if not agent_def:
            logger.debug(
                f"Agent definition '{agent_name}' not found for workflow '{qualified_name}'"
            )
            return None

        if not agent_def.workflows:
            logger.debug(f"Agent '{agent_name}' has no workflows defined")
            return None

        spec = agent_def.workflows.get(workflow_name)
        if not spec:
            logger.debug(f"Workflow '{workflow_name}' not found in agent '{agent_name}'")
            return None

        # If it's a file reference, load from the file
        if spec.is_file_reference():
            file_name = spec.file or ""
            workflow_file = file_name.removesuffix(".yaml")
            logger.debug(
                f"Loading file-referenced workflow '{workflow_file}' for '{qualified_name}'"
            )
            return await self.load_workflow(workflow_file, project_path)

        # It's an inline workflow - build definition from spec
        if spec.is_inline():
            return self._build_definition_from_spec(spec, qualified_name)

        logger.debug(f"WorkflowSpec for '{qualified_name}' is neither file reference nor inline")
        return None

    def _build_definition_from_spec(
        self,
        spec: "WorkflowSpec",
        name: str,
    ) -> WorkflowDefinition | PipelineDefinition:
        """Build a WorkflowDefinition or PipelineDefinition from a WorkflowSpec."""
        data = spec.model_dump(exclude_none=True, exclude_unset=True)

        if "name" not in data or data.get("name") is None:
            data["name"] = name

        data.pop("file", None)

        if data.get("type") == "pipeline":
            self._validate_pipeline_references(data)
            return PipelineDefinition(**data)
        else:
            if "type" in data and "enabled" not in data:
                data["enabled"] = data["type"] == "lifecycle"
            return WorkflowDefinition(**data)

    def _validate_pipeline_references(self, data: dict[str, Any]) -> None:
        """Validate that all $step_id.output references in a pipeline refer to earlier steps."""
        _validate_pipeline_references(data)

    def _extract_step_refs(self, text: str) -> set[str]:
        """Extract step IDs from $step_id.output patterns in text."""
        return _extract_step_refs(text)

    def _check_refs(
        self,
        refs: set[str],
        valid_refs: set[str],
        all_step_ids: list[str],
        current_step: str,
        field_name: str,
    ) -> None:
        """Check that all references are valid."""
        _check_refs(refs, valid_refs, all_step_ids, current_step, field_name)

    def _merge_workflows(self, parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
        """
        Deep merge parent and child workflow dicts.
        Child overrides parent.
        """
        merged = parent.copy()

        for key, value in child.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._merge_workflows(merged[key], value)
            elif key in ("phases", "steps") and ("phases" in merged or "steps" in merged):
                parent_list = merged.get("phases") or merged.get("steps", [])
                merged_key = "phases" if "phases" in merged else "steps"
                merged[merged_key] = self._merge_steps(parent_list, value)
            else:
                merged[key] = value

        return merged

    def _merge_steps(self, parent_steps: list[Any], child_steps: list[Any]) -> list[Any]:
        """
        Merge step lists by step name or id.
        Supports both workflow steps (name key) and pipeline steps (id key).
        """
        key_field = "id" if (parent_steps and "id" in parent_steps[0]) else "name"
        if not parent_steps and child_steps:
            key_field = "id" if "id" in child_steps[0] else "name"

        parent_map: dict[str, dict[str, Any]] = {}
        for s in parent_steps:
            if key_field not in s:
                logger.warning(f"Skipping parent step without '{key_field}' key")
                continue
            parent_map[s[key_field]] = dict(s)

        for child_step in child_steps:
            if key_field not in child_step:
                logger.warning(f"Skipping child step without '{key_field}' key")
                continue
            name = child_step[key_field]
            if name in parent_map:
                parent_map[name].update(child_step)
            else:
                parent_map[name] = dict(child_step)

        return list(parent_map.values())

    async def discover_workflows(
        self, project_path: Path | str | None = None
    ) -> list[DiscoveredWorkflow]:
        """Discover all workflows from the database."""
        return await discover_workflows(self, project_path)

    async def discover_lifecycle_workflows(
        self, project_path: Path | str | None = None
    ) -> list[DiscoveredWorkflow]:
        """Deprecated: use discover_workflows() instead."""
        return await discover_lifecycle_workflows(self, project_path)

    async def discover_pipeline_workflows(
        self, project_path: Path | str | None = None
    ) -> list[DiscoveredWorkflow]:
        """Discover all pipeline workflows from the database."""
        return await discover_pipeline_workflows(self, project_path)

    def clear_cache(self) -> None:
        """
        Clear the workflow definitions and discovery cache.
        """
        clear_cache(self._cache, self._discovery_cache)

    def register_inline_workflow(
        self,
        name: str,
        data: dict[str, Any],
        project_path: Path | str | None = None,
    ) -> WorkflowDefinition | PipelineDefinition:
        """
        Register an inline workflow definition in the cache.

        Inline workflows are embedded in agent definitions and registered
        at spawn time with qualified names like "agent:workflow".

        Note: Inline workflows are NOT written to disk. Child agents can load
        them directly from agent definitions via load_workflow() which handles
        qualified names (agent:workflow) by parsing the agent YAML.
        """
        cache_key = f"{project_path or 'global'}:{name}"

        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if isinstance(entry.definition, (WorkflowDefinition, PipelineDefinition)):
                return entry.definition

        if "name" not in data or data.get("name") is None:
            data["name"] = name

        try:
            if data.get("type") == "pipeline":
                self._validate_pipeline_references(data)
                definition: WorkflowDefinition | PipelineDefinition = PipelineDefinition(**data)
            else:
                if "type" in data and "enabled" not in data:
                    data["enabled"] = data["type"] == "lifecycle"
                definition = WorkflowDefinition(**data)

            self._cache[cache_key] = _CachedEntry(definition=definition, path=None, mtime=0.0)

            logger.debug(f"Registered inline workflow '{name}' (type={definition.type})")
            return definition

        except Exception as e:
            logger.error(f"Failed to register inline workflow '{name}': {e}")
            raise ValueError(f"Invalid inline workflow '{name}': {e}") from e

    async def validate_workflow_for_agent(
        self,
        workflow_name: str,
        project_path: Path | str | None = None,
    ) -> tuple[bool, str | None]:
        """
        Validate that a workflow can be used for agent spawning.

        Lifecycle workflows run automatically via hooks and cannot be
        explicitly activated for agents. Only step workflows are valid.
        """
        try:
            workflow = await self.load_workflow(workflow_name, project_path=project_path)
        except ValueError as e:
            return False, f"Failed to load workflow '{workflow_name}': {e}"

        if not workflow:
            return True, None

        if isinstance(workflow, WorkflowDefinition) and workflow.enabled:
            return False, (
                f"Cannot use always-on workflow '{workflow_name}' for agent spawning. "
                f"Always-on workflows run automatically on events. "
                f"Use an on-demand workflow (enabled: false) instead."
            )

        return True, None
