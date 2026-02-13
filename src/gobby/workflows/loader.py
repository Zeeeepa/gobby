import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles
import yaml

from .definitions import PipelineDefinition, WorkflowDefinition
from .loader_cache import (
    DiscoveredWorkflow,
    _CachedDiscovery,
    _CachedEntry,
    _is_discovery_stale,
    _is_stale,
    clear_cache,
)
from .loader_discovery import (
    _scan_directory,
    _scan_pipeline_directory,
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

# Re-export for backward compatibility
__all__ = ["DiscoveredWorkflow", "WorkflowLoader"]

if TYPE_CHECKING:
    from gobby.agents.definitions import WorkflowSpec

logger = logging.getLogger(__name__)


_BUNDLED_WORKFLOWS_DIR = Path(__file__).parent.parent / "install" / "shared" / "workflows"


class WorkflowLoader(WorkflowLoaderSyncMixin):
    def __init__(
        self,
        workflow_dirs: list[Path] | None = None,
        bundled_dir: Path | None = None,
    ):
        # Default global workflow directory
        self.global_dirs = workflow_dirs or [Path.home() / ".gobby" / "workflows"]
        # Bundled workflows shipped with the package (lowest priority fallback).
        # When custom workflow_dirs are provided (e.g. tests), disable bundled
        # fallback unless explicitly passed, to keep test isolation.
        self._bundled_dir: Path | None
        if bundled_dir is not None:
            self._bundled_dir = bundled_dir
        elif workflow_dirs is not None:
            self._bundled_dir = None  # Disabled for test isolation
        else:
            self._bundled_dir = _BUNDLED_WORKFLOWS_DIR
        self._cache: dict[str, _CachedEntry] = {}
        # Cache for discovered workflows per project path
        self._discovery_cache: dict[str, _CachedDiscovery] = {}

    def _is_stale(self, entry: _CachedEntry) -> bool:
        """Check if a cached workflow entry is stale (file changed on disk)."""
        return _is_stale(entry)

    def _is_discovery_stale(self, entry: _CachedDiscovery) -> bool:
        """Check if discovery cache is stale (any file/dir changed)."""
        return _is_discovery_stale(entry)

    async def load_workflow(
        self,
        name: str,
        project_path: Path | str | None = None,
        _inheritance_chain: list[str] | None = None,
    ) -> WorkflowDefinition | PipelineDefinition | None:
        """
        Load a workflow by name (without extension).
        Supports inheritance via 'extends' field with cycle detection.
        Auto-detects pipeline type and returns PipelineDefinition for type='pipeline'.

        Qualified names (agent:workflow) are resolved by loading the inline workflow
        from the agent definition.

        Args:
            name: Workflow name (without .yaml extension), or qualified name (agent:workflow)
            project_path: Optional project directory for project-specific workflows.
                         Searches: 1) {project_path}/.gobby/workflows/  2) ~/.gobby/workflows/
            _inheritance_chain: Internal parameter for cycle detection. Do not pass directly.

        Raises:
            ValueError: If circular inheritance is detected or pipeline references are invalid.
        """
        # Initialize or check inheritance chain for cycle detection
        if _inheritance_chain is None:
            _inheritance_chain = []

        if name in _inheritance_chain:
            cycle_path = " -> ".join(_inheritance_chain + [name])
            logger.error(f"Circular workflow inheritance detected: {cycle_path}")
            raise ValueError(f"Circular workflow inheritance detected: {cycle_path}")

        # Build cache key including project path for project-specific caching
        cache_key = f"{project_path or 'global'}:{name}"
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if self._is_stale(entry):
                del self._cache[cache_key]
            else:
                return entry.definition

        # Check for qualified name (agent:workflow) - try to load from agent definition first
        if ":" in name:
            agent_workflow = await self._load_from_agent_definition(name, project_path)
            if agent_workflow:
                self._cache[cache_key] = _CachedEntry(
                    definition=agent_workflow, path=None, mtime=0.0
                )
                return agent_workflow
            # Fall through to file-based lookup (for backwards compatibility with
            # persisted inline workflows like meeseeks-worker.yaml)

        # Build search directories: project-specific first, then global, then bundled
        search_dirs = list(self.global_dirs)
        if project_path:
            project_dir = Path(project_path) / ".gobby" / "workflows"
            search_dirs.insert(0, project_dir)
        if self._bundled_dir is not None and self._bundled_dir.is_dir():
            search_dirs.append(self._bundled_dir)

        # 1. Find file
        path = self._find_workflow_file(name, search_dirs)
        if not path:
            logger.warning(f"Workflow '{name}' not found in {search_dirs}")
            return None

        try:
            # 2. Parse YAML
            async with aiofiles.open(path) as f:
                content = await f.read()
            data = yaml.safe_load(content)

            # 3. Handle inheritance with cycle detection
            if "extends" in data:
                parent_name = data["extends"]
                # Add current workflow to chain before loading parent
                parent = await self.load_workflow(
                    parent_name,
                    project_path=project_path,
                    _inheritance_chain=_inheritance_chain + [name],
                )
                if parent:
                    data = self._merge_workflows(parent.model_dump(), data)
                else:
                    logger.error(f"Parent workflow '{parent_name}' not found for '{name}'")

            # 4. Resolve rule imports (before creating definition)
            if data.get("imports"):
                data = await self._resolve_imports(data, project_path)

            # 5. Auto-detect pipeline type
            if data.get("type") == "pipeline":
                # Validate step references for pipelines
                self._validate_pipeline_references(data)
                definition: WorkflowDefinition | PipelineDefinition = PipelineDefinition(**data)
            else:
                # Backward compat: derive enabled from deprecated type field
                if "type" in data and "enabled" not in data:
                    data["enabled"] = data["type"] == "lifecycle"
                definition = WorkflowDefinition(**data)

            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            self._cache[cache_key] = _CachedEntry(definition=definition, path=path, mtime=mtime)
            return definition

        except ValueError:
            # Re-raise ValueError (used for cycle detection and reference validation)
            raise
        except Exception as e:
            logger.error(f"Failed to load workflow '{name}' from {path}: {e}", exc_info=True)
            return None

    async def load_pipeline(
        self,
        name: str,
        project_path: Path | str | None = None,
        _inheritance_chain: list[str] | None = None,
    ) -> PipelineDefinition | None:
        """
        Load a pipeline workflow by name (without extension).
        Only returns workflows with type='pipeline'.

        Args:
            name: Pipeline name (without .yaml extension)
            project_path: Optional project directory for project-specific pipelines.
                         Searches: 1) {project_path}/.gobby/workflows/  2) ~/.gobby/workflows/
            _inheritance_chain: Internal parameter for cycle detection. Do not pass directly.

        Returns:
            PipelineDefinition if found and type is 'pipeline', None otherwise.
        """
        # Initialize or check inheritance chain for cycle detection
        if _inheritance_chain is None:
            _inheritance_chain = []

        if name in _inheritance_chain:
            cycle_path = " -> ".join(_inheritance_chain + [name])
            logger.error(f"Circular pipeline inheritance detected: {cycle_path}")
            raise ValueError(f"Circular pipeline inheritance detected: {cycle_path}")

        # Build cache key including project path for project-specific caching
        cache_key = f"pipeline:{project_path or 'global'}:{name}"
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if self._is_stale(entry):
                del self._cache[cache_key]
            elif isinstance(entry.definition, PipelineDefinition):
                return entry.definition
            else:
                return None

        # Build search directories: project-specific first, then global, then bundled
        search_dirs = list(self.global_dirs)
        if project_path:
            project_dir = Path(project_path) / ".gobby" / "workflows"
            search_dirs.insert(0, project_dir)
        if self._bundled_dir is not None and self._bundled_dir.is_dir():
            search_dirs.append(self._bundled_dir)

        # 1. Find file
        path = self._find_workflow_file(name, search_dirs)
        if not path:
            logger.debug(f"Pipeline '{name}' not found in {search_dirs}")
            return None

        try:
            # 2. Parse YAML
            async with aiofiles.open(path) as f:
                content = await f.read()
            data = yaml.safe_load(content)

            # 3. Check if this is a pipeline type
            if data.get("type") != "pipeline":
                logger.debug(f"'{name}' is not a pipeline (type={data.get('type')})")
                return None

            # 4. Handle inheritance with cycle detection
            if "extends" in data:
                parent_name = data["extends"]
                # Add current pipeline to chain before loading parent
                parent = await self.load_pipeline(
                    parent_name,
                    project_path=project_path,
                    _inheritance_chain=_inheritance_chain + [name],
                )
                if parent:
                    data = self._merge_workflows(parent.model_dump(), data)
                else:
                    logger.error(f"Parent pipeline '{parent_name}' not found for '{name}'")

            # 5. Validate step references
            self._validate_pipeline_references(data)

            # 6. Validate and create model
            definition = PipelineDefinition(**data)
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            self._cache[cache_key] = _CachedEntry(definition=definition, path=path, mtime=mtime)
            return definition

        except ValueError:
            # Re-raise ValueError (used for cycle detection)
            raise
        except Exception as e:
            logger.error(f"Failed to load pipeline '{name}' from {path}: {e}", exc_info=True)
            return None

    def _find_rule_file(
        self,
        name: str,
        project_path: Path | str | None = None,
    ) -> Path | None:
        """Find a rule definition file by name across search paths.

        Search order (first match wins):
        1. Project: {project_path}/.gobby/rules/
        2. User: ~/.gobby/rules/ (from global_dirs parent)
        3. Bundled: install/shared/rules/

        Args:
            name: Rule file name (without .yaml extension).
            project_path: Optional project directory.

        Returns:
            Path to the YAML file, or None if not found.
        """
        search_dirs: list[Path] = []

        # Project rules (highest priority)
        if project_path:
            search_dirs.append(Path(project_path) / ".gobby" / "rules")

        # User rules (from global workflow dirs, sibling rules/ dir)
        for gdir in self.global_dirs:
            search_dirs.append(gdir.parent / "rules")

        # Bundled rules (lowest priority)
        if self._bundled_dir is not None:
            search_dirs.append(self._bundled_dir.parent / "rules")

        filename = f"{name}.yaml"
        for d in search_dirs:
            candidate = d / filename
            if candidate.exists():
                return candidate

        return None

    async def _load_rule_definitions(self, path: Path) -> dict[str, Any]:
        """Load rule_definitions from a YAML rule file.

        Args:
            path: Path to the rule YAML file.

        Returns:
            Dict of rule_name -> rule definition dict.
        """
        async with aiofiles.open(path) as f:
            content = await f.read()
        data = yaml.safe_load(content)
        if not data or not isinstance(data, dict):
            return {}
        result: dict[str, Any] = data.get("rule_definitions", {})
        return result

    async def _resolve_imports(
        self,
        data: dict[str, Any],
        project_path: Path | str | None = None,
    ) -> dict[str, Any]:
        """Resolve the 'imports' field by loading and merging rule definitions.

        Imported rules are merged first, then file-local rule_definitions
        override any imported rules with the same name.

        Args:
            data: Parsed workflow YAML data dict.
            project_path: Optional project directory for rule file search.

        Returns:
            The data dict with rule_definitions merged from imports.

        Raises:
            ValueError: If an imported rule file is not found.
        """
        imports = data.get("imports", [])
        if not imports:
            return data

        merged_rules: dict[str, Any] = {}

        for import_name in imports:
            path = self._find_rule_file(import_name, project_path)
            if path is None:
                raise ValueError(
                    f"Imported rule file '{import_name}' not found. "
                    f"Searched in project, user, and bundled rule directories."
                )
            imported = await self._load_rule_definitions(path)
            # Later imports override earlier imports
            merged_rules.update(imported)

        # File-local rule_definitions override imported
        local_rules = data.get("rule_definitions", {})
        merged_rules.update(local_rules)

        data["rule_definitions"] = merged_rules
        return data

    def _find_workflow_file(self, name: str, search_dirs: list[Path]) -> Path | None:
        # Try both the original name and converted name (for inline workflows)
        # "meeseeks:worker" -> also try "meeseeks-worker"
        filenames = [f"{name}.yaml"]
        if ":" in name:
            filenames.append(f"{name.replace(':', '-')}.yaml")

        for d in search_dirs:
            for filename in filenames:
                # Check root directory
                candidate = d / filename
                if candidate.exists():
                    return candidate
                # Check subdirectories (lifecycle/, etc.)
                for subdir in d.iterdir() if d.exists() else []:
                    if subdir.is_dir():
                        candidate = subdir / filename
                        if candidate.exists():
                            return candidate
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

        Args:
            qualified_name: Qualified workflow name (e.g., "meeseeks:worker")
            project_path: Project path for agent definition lookup

        Returns:
            WorkflowDefinition or PipelineDefinition if found, None otherwise
        """
        if ":" not in qualified_name:
            return None

        agent_name, workflow_name = qualified_name.split(":", 1)

        # Import here to avoid circular imports
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
            # Remove .yaml extension if present for load_workflow call
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
        """
        Build a WorkflowDefinition or PipelineDefinition from a WorkflowSpec.

        Args:
            spec: The WorkflowSpec from an agent definition
            name: The qualified workflow name (e.g., "meeseeks:worker")

        Returns:
            WorkflowDefinition or PipelineDefinition
        """
        # Convert spec to dict for definition creation
        data = spec.model_dump(exclude_none=True, exclude_unset=True)

        # Ensure name is set
        if "name" not in data or data.get("name") is None:
            data["name"] = name

        # Remove 'file' field if present (it's not part of WorkflowDefinition)
        data.pop("file", None)

        if data.get("type") == "pipeline":
            self._validate_pipeline_references(data)
            return PipelineDefinition(**data)
        else:
            # Backward compat: derive enabled from deprecated type field
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
                # Special handling for steps/phases: merge by name
                # Support both 'steps' (new) and 'phases' (legacy YAML)
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
        # Determine which key to use: 'id' for pipelines, 'name' for workflows
        key_field = "id" if (parent_steps and "id" in parent_steps[0]) else "name"
        if not parent_steps and child_steps:
            key_field = "id" if "id" in child_steps[0] else "name"

        # Convert parent list to dict by key, creating copies to avoid mutating originals
        parent_map: dict[str, dict[str, Any]] = {}
        for s in parent_steps:
            if key_field not in s:
                logger.warning(f"Skipping parent step without '{key_field}' key")
                continue
            # Create a shallow copy to avoid mutating the original
            parent_map[s[key_field]] = dict(s)

        for child_step in child_steps:
            if key_field not in child_step:
                logger.warning(f"Skipping child step without '{key_field}' key")
                continue
            name = child_step[key_field]
            if name in parent_map:
                # Merge existing step by updating the copy with child values
                parent_map[name].update(child_step)
            else:
                # Add new step as a copy
                parent_map[name] = dict(child_step)

        return list(parent_map.values())

    async def discover_workflows(
        self, project_path: Path | str | None = None
    ) -> list[DiscoveredWorkflow]:
        """Discover all workflows from project and global directories."""
        return await discover_workflows(self, project_path)

    async def discover_lifecycle_workflows(
        self, project_path: Path | str | None = None
    ) -> list[DiscoveredWorkflow]:
        """Deprecated: use discover_workflows() instead."""
        return await discover_lifecycle_workflows(self, project_path)

    async def discover_pipeline_workflows(
        self, project_path: Path | str | None = None
    ) -> list[DiscoveredWorkflow]:
        """Discover all pipeline workflows from project and global directories."""
        return await discover_pipeline_workflows(self, project_path)

    async def _scan_pipeline_directory(
        self,
        directory: Path,
        is_project: bool,
        discovered: dict[str, DiscoveredWorkflow],
        failed: dict[str, str] | None = None,
        file_mtimes: dict[str, float] | None = None,
        dir_mtimes: dict[str, float] | None = None,
    ) -> None:
        """Scan a directory for pipeline YAML files and add to discovered dict."""
        await _scan_pipeline_directory(
            self, directory, is_project, discovered, failed, file_mtimes, dir_mtimes
        )

    async def _scan_directory(
        self,
        directory: Path,
        is_project: bool,
        discovered: dict[str, DiscoveredWorkflow],
        failed: dict[str, str] | None = None,
        file_mtimes: dict[str, float] | None = None,
        dir_mtimes: dict[str, float] | None = None,
    ) -> None:
        """Scan a directory for workflow YAML files and add to discovered dict."""
        await _scan_directory(
            self, directory, is_project, discovered, failed, file_mtimes, dir_mtimes
        )

    def clear_cache(self) -> None:
        """
        Clear the workflow definitions and discovery cache.
        Call when workflows may have changed on disk.
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

        Args:
            name: Qualified workflow name (e.g., "meeseeks:worker")
            data: Workflow definition data dict
            project_path: Project path for cache key scoping

        Returns:
            The created WorkflowDefinition or PipelineDefinition

        Raises:
            ValueError: If the workflow definition is invalid
        """
        cache_key = f"{project_path or 'global'}:{name}"

        # Already registered?
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if isinstance(entry.definition, (WorkflowDefinition, PipelineDefinition)):
                return entry.definition

        # Ensure name is set in data (handle both missing and None)
        if "name" not in data or data.get("name") is None:
            data["name"] = name

        # Create definition based on type
        try:
            if data.get("type") == "pipeline":
                self._validate_pipeline_references(data)
                definition: WorkflowDefinition | PipelineDefinition = PipelineDefinition(**data)
            else:
                # Backward compat: derive enabled from deprecated type field
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

        Args:
            workflow_name: Name of the workflow to validate
            project_path: Optional project path for workflow resolution

        Returns:
            Tuple of (is_valid, error_message).
            If valid, returns (True, None).
            If invalid, returns (False, error_message).
        """
        try:
            workflow = await self.load_workflow(workflow_name, project_path=project_path)
        except ValueError as e:
            # Circular inheritance or other workflow loading errors
            return False, f"Failed to load workflow '{workflow_name}': {e}"

        if not workflow:
            # Workflow not found - let the caller decide if this is an error
            return True, None

        if isinstance(workflow, WorkflowDefinition) and workflow.enabled:
            return False, (
                f"Cannot use always-on workflow '{workflow_name}' for agent spawning. "
                f"Always-on workflows run automatically on events. "
                f"Use an on-demand workflow (enabled: false) instead."
            )

        return True, None
