import asyncio
import concurrent.futures
import logging
import threading
import warnings
from collections.abc import Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

import aiofiles
import yaml

from .definitions import PipelineDefinition, WorkflowDefinition

if TYPE_CHECKING:
    from gobby.agents.definitions import WorkflowSpec

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


@dataclass
class DiscoveredWorkflow:
    """A discovered workflow with metadata for ordering."""

    name: str
    definition: WorkflowDefinition | PipelineDefinition
    priority: int  # Lower = higher priority (runs first)
    is_project: bool  # True if from project, False if global
    path: Path


@dataclass
class _CachedEntry:
    """Cache entry for a single workflow definition with mtime tracking."""

    definition: WorkflowDefinition | PipelineDefinition
    path: Path | None  # None for inline/agent workflows
    mtime: float  # os.stat().st_mtime, 0.0 for inline


@dataclass
class _CachedDiscovery:
    """Cache entry for workflow discovery results with mtime tracking."""

    results: list[DiscoveredWorkflow]
    file_mtimes: dict[str, float]  # yaml file path -> mtime
    dir_mtimes: dict[str, float]  # scanned directory path -> mtime


_BUNDLED_WORKFLOWS_DIR = Path(__file__).parent.parent / "install" / "shared" / "workflows"


class WorkflowLoader:
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
        if entry.path is None:
            return False  # Inline workflows have no file to check
        if entry.mtime == 0.0:
            return False  # Could not stat at cache time; skip check
        try:
            return entry.path.stat().st_mtime != entry.mtime
        except OSError:
            return True  # File deleted = stale

    def _is_discovery_stale(self, entry: _CachedDiscovery) -> bool:
        """Check if discovery cache is stale (any file/dir changed)."""
        for dir_path, mtime in entry.dir_mtimes.items():
            try:
                if Path(dir_path).stat().st_mtime != mtime:
                    return True  # Dir changed (file added/removed)
            except OSError:
                return True
        for file_path, mtime in entry.file_mtimes.items():
            try:
                if Path(file_path).stat().st_mtime != mtime:
                    return True  # File content changed
            except OSError:
                return True  # File deleted
        return False

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

        # Default to step workflow if type not specified
        if "type" not in data:
            data["type"] = "step"

        if data.get("type") == "pipeline":
            self._validate_pipeline_references(data)
            return PipelineDefinition(**data)
        else:
            return WorkflowDefinition(**data)

    def _validate_pipeline_references(self, data: dict[str, Any]) -> None:
        """
        Validate that all $step_id.output references in a pipeline refer to earlier steps.

        Args:
            data: Pipeline data dictionary

        Raises:
            ValueError: If a reference points to a non-existent or later step
        """
        steps = data.get("steps", [])
        step_ids = [s.get("id") for s in steps if s.get("id")]

        # Build set of valid step IDs that can be referenced at each position
        valid_at_position: dict[int, set[str]] = {}
        for i in range(len(step_ids)):
            # Steps at position i can only reference steps 0..i-1
            valid_at_position[i] = set(step_ids[:i])

        # Validate references in each step
        for i, step in enumerate(steps):
            step_id = step.get("id", f"step_{i}")
            valid_refs = valid_at_position.get(i, set())

            # Check prompt field
            if "prompt" in step and step["prompt"]:
                refs = self._extract_step_refs(step["prompt"])
                self._check_refs(refs, valid_refs, step_ids, step_id, "prompt")

            # Check condition field
            if "condition" in step and step["condition"]:
                refs = self._extract_step_refs(step["condition"])
                self._check_refs(refs, valid_refs, step_ids, step_id, "condition")

            # Check input field
            if "input" in step and step["input"]:
                refs = self._extract_step_refs(step["input"])
                self._check_refs(refs, valid_refs, step_ids, step_id, "input")

            # Check exec field (might have embedded references)
            if "exec" in step and step["exec"]:
                refs = self._extract_step_refs(step["exec"])
                self._check_refs(refs, valid_refs, step_ids, step_id, "exec")

        # Validate references in pipeline outputs (can reference any step)
        all_step_ids = set(step_ids)
        outputs = data.get("outputs", {})
        for output_name, output_value in outputs.items():
            if isinstance(output_value, str):
                refs = self._extract_step_refs(output_value)
                for ref in refs:
                    if ref not in all_step_ids:
                        raise ValueError(
                            f"Pipeline output '{output_name}' references unknown step '{ref}'. "
                            f"Valid steps: {sorted(all_step_ids)}"
                        )

    def _extract_step_refs(self, text: str) -> set[str]:
        """
        Extract step IDs from $step_id.output patterns in text.

        Args:
            text: Text to search for references

        Returns:
            Set of step IDs referenced
        """
        import re

        # Match $step_id.output or $step_id.output.field patterns
        # Exclude $inputs.* which are input references, not step references
        pattern = r"\$([a-zA-Z_][a-zA-Z0-9_]*)\.(output|approved)"
        matches = re.findall(pattern, text)
        # Filter out 'inputs' which is a special reference
        return {m[0] for m in matches if m[0] != "inputs"}

    def _check_refs(
        self,
        refs: set[str],
        valid_refs: set[str],
        all_step_ids: list[str],
        current_step: str,
        field_name: str,
    ) -> None:
        """
        Check that all references are valid.

        Args:
            refs: Set of referenced step IDs
            valid_refs: Set of step IDs that can be referenced (earlier steps)
            all_step_ids: List of all step IDs in the pipeline
            current_step: Current step ID (for error messages)
            field_name: Field name being checked (for error messages)

        Raises:
            ValueError: If any reference is invalid
        """
        for ref in refs:
            if ref not in valid_refs:
                if ref in all_step_ids:
                    # It's a forward reference
                    raise ValueError(
                        f"Step '{current_step}' {field_name} references step '{ref}' "
                        f"which appears later in the pipeline. Steps can only reference "
                        f"earlier steps. Valid references: {sorted(valid_refs) if valid_refs else '(none)'}"
                    )
                else:
                    # It's a non-existent step
                    raise ValueError(
                        f"Step '{current_step}' {field_name} references unknown step '{ref}'. "
                        f"Valid steps: {sorted(all_step_ids)}"
                    )

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
        """
        Discover all workflows from project and global directories.

        Scans both root workflow directories and lifecycle/ subdirectories.
        Returns workflows sorted by:
        1. Project workflows first (is_project=True), then global
        2. Within each group: by priority (ascending), then alphabetically by name

        Project workflows shadow global workflows with the same name.

        Args:
            project_path: Optional project directory. If provided, searches
                         {project_path}/.gobby/workflows/ first.

        Returns:
            List of DiscoveredWorkflow objects, sorted and deduplicated.
        """
        cache_key = f"unified:{project_path}" if project_path else "unified:global"

        # Check cache
        if cache_key in self._discovery_cache:
            cached = self._discovery_cache[cache_key]
            if not self._is_discovery_stale(cached):
                return cached.results
            del self._discovery_cache[cache_key]

        discovered: dict[str, DiscoveredWorkflow] = {}  # name -> workflow (for shadowing)
        failed: dict[str, str] = {}  # name -> error message for failed workflows
        file_mtimes: dict[str, float] = {}
        dir_mtimes: dict[str, float] = {}

        # 1. Scan bundled directories first (lowest priority, shadowed by all)
        if self._bundled_dir is not None and self._bundled_dir.is_dir():
            await self._scan_directory(
                self._bundled_dir,
                is_project=False,
                discovered=discovered,
                file_mtimes=file_mtimes,
                dir_mtimes=dir_mtimes,
            )
            await self._scan_directory(
                self._bundled_dir / "lifecycle",
                is_project=False,
                discovered=discovered,
                file_mtimes=file_mtimes,
                dir_mtimes=dir_mtimes,
            )

        # 2. Scan global directories (shadows bundled)
        for global_dir in self.global_dirs:
            await self._scan_directory(
                global_dir,
                is_project=False,
                discovered=discovered,
                file_mtimes=file_mtimes,
                dir_mtimes=dir_mtimes,
            )
            await self._scan_directory(
                global_dir / "lifecycle",
                is_project=False,
                discovered=discovered,
                file_mtimes=file_mtimes,
                dir_mtimes=dir_mtimes,
            )

        # 3. Scan project directories (shadows global)
        if project_path:
            project_wf_dir = Path(project_path) / ".gobby" / "workflows"
            await self._scan_directory(
                project_wf_dir,
                is_project=True,
                discovered=discovered,
                failed=failed,
                file_mtimes=file_mtimes,
                dir_mtimes=dir_mtimes,
            )
            await self._scan_directory(
                project_wf_dir / "lifecycle",
                is_project=True,
                discovered=discovered,
                failed=failed,
                file_mtimes=file_mtimes,
                dir_mtimes=dir_mtimes,
            )

            # Log errors when project workflow fails but global exists (failed shadowing)
            for name, error in failed.items():
                if name in discovered and not discovered[name].is_project:
                    logger.error(
                        f"Project workflow '{name}' failed to load, using global instead: {error}"
                    )

        # 4. Sort: project first, then by priority (asc), then by name (alpha)
        sorted_workflows = sorted(
            discovered.values(),
            key=lambda w: (
                0 if w.is_project else 1,  # Project first
                w.priority,  # Lower priority = runs first
                w.name,  # Alphabetical
            ),
        )

        # Cache and return
        self._discovery_cache[cache_key] = _CachedDiscovery(
            results=sorted_workflows, file_mtimes=file_mtimes, dir_mtimes=dir_mtimes
        )
        return sorted_workflows

    async def discover_lifecycle_workflows(
        self, project_path: Path | str | None = None
    ) -> list[DiscoveredWorkflow]:
        """Deprecated: use discover_workflows() instead.

        This is a backward-compatible alias that returns the same results
        as discover_workflows().
        """
        warnings.warn(
            "discover_lifecycle_workflows() is deprecated, use discover_workflows() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return await self.discover_workflows(project_path)

    async def discover_pipeline_workflows(
        self, project_path: Path | str | None = None
    ) -> list[DiscoveredWorkflow]:
        """
        Discover all pipeline workflows from project and global directories.

        Returns workflows sorted by:
        1. Project workflows first (is_project=True), then global
        2. Within each group: by priority (ascending), then alphabetically by name

        Project workflows shadow global workflows with the same name.

        Note: Unlike lifecycle workflows which are in lifecycle/ subdirs,
        pipelines are in the root workflows/ directory.

        Args:
            project_path: Optional project directory. If provided, searches
                         {project_path}/.gobby/workflows/ first.

        Returns:
            List of DiscoveredWorkflow objects with type='pipeline', sorted and deduplicated.
        """
        cache_key = f"pipelines:{project_path}" if project_path else "pipelines:global"

        # Check cache
        if cache_key in self._discovery_cache:
            cached = self._discovery_cache[cache_key]
            if not self._is_discovery_stale(cached):
                return cached.results
            del self._discovery_cache[cache_key]

        discovered: dict[str, DiscoveredWorkflow] = {}  # name -> workflow (for shadowing)
        failed: dict[str, str] = {}  # name -> error message for failed workflows
        file_mtimes: dict[str, float] = {}
        dir_mtimes: dict[str, float] = {}

        # 1. Scan bundled workflows directory first (lowest priority, shadowed by all)
        if self._bundled_dir is not None and self._bundled_dir.is_dir():
            await self._scan_pipeline_directory(
                self._bundled_dir,
                is_project=False,
                discovered=discovered,
                file_mtimes=file_mtimes,
                dir_mtimes=dir_mtimes,
            )

        # 2. Scan global workflows directory (shadows bundled)
        for global_dir in self.global_dirs:
            await self._scan_pipeline_directory(
                global_dir,
                is_project=False,
                discovered=discovered,
                file_mtimes=file_mtimes,
                dir_mtimes=dir_mtimes,
            )

        # 3. Scan project workflows directory (shadows global)
        if project_path:
            project_dir = Path(project_path) / ".gobby" / "workflows"
            await self._scan_pipeline_directory(
                project_dir,
                is_project=True,
                discovered=discovered,
                failed=failed,
                file_mtimes=file_mtimes,
                dir_mtimes=dir_mtimes,
            )

            # Log errors when project pipeline fails but global exists (failed shadowing)
            for name, error in failed.items():
                if name in discovered and not discovered[name].is_project:
                    logger.error(
                        f"Project pipeline '{name}' failed to load, using global instead: {error}"
                    )

        # 3. Sort: project first, then by priority (asc), then by name (alpha)
        sorted_pipelines = sorted(
            discovered.values(),
            key=lambda w: (
                0 if w.is_project else 1,  # Project first
                w.priority,  # Lower priority = runs first
                w.name,  # Alphabetical
            ),
        )

        # Cache and return
        self._discovery_cache[cache_key] = _CachedDiscovery(
            results=sorted_pipelines, file_mtimes=file_mtimes, dir_mtimes=dir_mtimes
        )
        return sorted_pipelines

    async def _scan_pipeline_directory(
        self,
        directory: Path,
        is_project: bool,
        discovered: dict[str, DiscoveredWorkflow],
        failed: dict[str, str] | None = None,
        file_mtimes: dict[str, float] | None = None,
        dir_mtimes: dict[str, float] | None = None,
    ) -> None:
        """
        Scan a directory for pipeline YAML files and add to discovered dict.

        Only includes workflows with type='pipeline'.

        Args:
            directory: Directory to scan
            is_project: Whether this is a project directory (for shadowing)
            discovered: Dict to update (name -> DiscoveredWorkflow)
            failed: Optional dict to track failed pipelines (name -> error message)
            file_mtimes: Optional dict to record scanned file mtimes for cache invalidation
            dir_mtimes: Optional dict to record scanned directory mtimes for cache invalidation
        """
        if not directory.exists():
            return

        if dir_mtimes is not None:
            try:
                dir_mtimes[str(directory)] = directory.stat().st_mtime
            except OSError:
                pass

        for yaml_path in directory.glob("*.yaml"):
            name = yaml_path.stem
            try:
                if file_mtimes is not None:
                    try:
                        file_mtimes[str(yaml_path)] = yaml_path.stat().st_mtime
                    except OSError:
                        pass

                async with aiofiles.open(yaml_path) as f:
                    content = await f.read()
                data = yaml.safe_load(content)

                if not data:
                    continue

                # Only process pipeline type workflows
                if data.get("type") != "pipeline":
                    continue

                # Handle inheritance with cycle detection
                if "extends" in data:
                    parent_name = data["extends"]
                    try:
                        parent = await self.load_pipeline(
                            parent_name,
                            _inheritance_chain=[name],
                        )
                        if parent:
                            data = self._merge_workflows(parent.model_dump(), data)
                    except ValueError as e:
                        logger.warning(f"Skipping pipeline {name}: {e}")
                        if failed is not None:
                            failed[name] = str(e)
                        continue

                # Validate references before creating definition
                self._validate_pipeline_references(data)

                definition = PipelineDefinition(**data)

                # Get priority from data settings or default to 100
                # (PipelineDefinition doesn't have settings field, use raw data)
                priority = 100
                settings = data.get("settings", {})
                if settings and "priority" in settings:
                    priority = settings["priority"]

                # Log successful shadowing when project pipeline overrides global
                if name in discovered and is_project and not discovered[name].is_project:
                    logger.info(f"Project pipeline '{name}' shadows global pipeline")

                # Project pipelines shadow global (overwrite in dict)
                # Global is scanned first, so project overwrites
                discovered[name] = DiscoveredWorkflow(
                    name=name,
                    definition=definition,
                    priority=priority,
                    is_project=is_project,
                    path=yaml_path,
                )

            except Exception as e:
                logger.warning(f"Failed to load pipeline from {yaml_path}: {e}")
                if failed is not None:
                    failed[name] = str(e)

    async def _scan_directory(
        self,
        directory: Path,
        is_project: bool,
        discovered: dict[str, DiscoveredWorkflow],
        failed: dict[str, str] | None = None,
        file_mtimes: dict[str, float] | None = None,
        dir_mtimes: dict[str, float] | None = None,
    ) -> None:
        """
        Scan a directory for workflow YAML files and add to discovered dict.

        Args:
            directory: Directory to scan
            is_project: Whether this is a project directory (for shadowing)
            discovered: Dict to update (name -> DiscoveredWorkflow)
            failed: Optional dict to track failed workflows (name -> error message)
            file_mtimes: Optional dict to record scanned file mtimes for cache invalidation
            dir_mtimes: Optional dict to record scanned directory mtimes for cache invalidation
        """
        if not directory.exists():
            return

        if dir_mtimes is not None:
            try:
                dir_mtimes[str(directory)] = directory.stat().st_mtime
            except OSError:
                pass

        for yaml_path in directory.glob("*.yaml"):
            name = yaml_path.stem
            try:
                if file_mtimes is not None:
                    try:
                        file_mtimes[str(yaml_path)] = yaml_path.stat().st_mtime
                    except OSError:
                        pass

                async with aiofiles.open(yaml_path) as f:
                    content = await f.read()
                data = yaml.safe_load(content)

                if not data:
                    continue

                # Handle inheritance with cycle detection
                if "extends" in data:
                    parent_name = data["extends"]
                    try:
                        parent = await self.load_workflow(
                            parent_name,
                            _inheritance_chain=[name],
                        )
                        if parent:
                            data = self._merge_workflows(parent.model_dump(), data)
                    except ValueError as e:
                        logger.warning(f"Skipping workflow {name}: {e}")
                        if failed is not None:
                            failed[name] = str(e)
                        continue

                # Emit deprecation warning when YAML has a 'type' field
                if "type" in data:
                    warnings.warn(
                        f"Workflow '{name}' uses deprecated 'type: {data['type']}' field. "
                        f"Migrate to 'enabled' instead "
                        f"(type: lifecycle → enabled: true, type: step → enabled: false).",
                        DeprecationWarning,
                        stacklevel=2,
                    )

                definition = WorkflowDefinition(**data)

                # Use definition.priority directly; fall back to settings.priority
                # for backward compat with YAMLs not yet migrated to top-level priority.
                priority = definition.priority
                if priority == 100 and definition.settings.get("priority") is not None:
                    priority = definition.settings["priority"]

                # Log successful shadowing when project workflow overrides global
                if name in discovered and is_project and not discovered[name].is_project:
                    logger.info(f"Project workflow '{name}' shadows global workflow")

                # Project workflows shadow global (overwrite in dict)
                # Global is scanned first, so project overwrites
                discovered[name] = DiscoveredWorkflow(
                    name=name,
                    definition=definition,
                    priority=priority,
                    is_project=is_project,
                    path=yaml_path,
                )

            except Exception as e:
                logger.warning(f"Failed to load workflow from {yaml_path}: {e}")
                if failed is not None:
                    failed[name] = str(e)

    def clear_cache(self) -> None:
        """
        Clear the workflow definitions and discovery cache.
        Call when workflows may have changed on disk.
        """
        self._cache.clear()
        self._discovery_cache.clear()

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
                # Default to step workflow
                if "type" not in data:
                    data["type"] = "step"
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

        if workflow.type == "lifecycle":
            return False, (
                f"Cannot use lifecycle workflow '{workflow_name}' for agent spawning. "
                f"Lifecycle workflows run automatically on events. "
                f"Use a step workflow like 'plan-execute' instead."
            )

        return True, None

    # ------------------------------------------------------------------
    # Synchronous wrappers for CLI / startup contexts without a running loop
    # ------------------------------------------------------------------

    _sync_executor: "concurrent.futures.ThreadPoolExecutor | None" = None
    _sync_executor_lock: threading.Lock = threading.Lock()

    @classmethod
    def _get_sync_executor(cls) -> "concurrent.futures.ThreadPoolExecutor":
        if cls._sync_executor is None:
            with cls._sync_executor_lock:
                if cls._sync_executor is None:
                    cls._sync_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        return cls._sync_executor

    @classmethod
    def shutdown_sync_executor(cls) -> None:
        """Shut down the shared ThreadPoolExecutor, if one was created."""
        with cls._sync_executor_lock:
            if cls._sync_executor is not None:
                cls._sync_executor.shutdown(wait=False)
                cls._sync_executor = None

    @staticmethod
    def _run_sync(coro: Coroutine[Any, Any, _T]) -> _T:
        """Run a coroutine synchronously, handling both loop and no-loop contexts."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is None:
            # No event loop running - safe to use asyncio.run()
            return asyncio.run(coro)

        if threading.current_thread() is threading.main_thread():
            # Same-thread with running loop - offload to a new thread
            # to avoid deadlocking the current loop.
            pool = WorkflowLoader._get_sync_executor()
            return pool.submit(asyncio.run, coro).result()

        # Worker thread with loop running elsewhere - schedule on existing loop
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()

    def load_workflow_sync(
        self,
        name: str,
        project_path: Path | str | None = None,
        _inheritance_chain: list[str] | None = None,
    ) -> WorkflowDefinition | PipelineDefinition | None:
        return self._run_sync(self.load_workflow(name, project_path, _inheritance_chain))

    def load_pipeline_sync(
        self,
        name: str,
        project_path: Path | str | None = None,
        _inheritance_chain: list[str] | None = None,
    ) -> PipelineDefinition | None:
        return self._run_sync(self.load_pipeline(name, project_path, _inheritance_chain))

    def discover_workflows_sync(
        self, project_path: Path | str | None = None
    ) -> list[DiscoveredWorkflow]:
        return self._run_sync(self.discover_workflows(project_path))

    def discover_lifecycle_workflows_sync(
        self, project_path: Path | str | None = None
    ) -> list[DiscoveredWorkflow]:
        return self._run_sync(self.discover_lifecycle_workflows(project_path))

    def discover_pipeline_workflows_sync(
        self, project_path: Path | str | None = None
    ) -> list[DiscoveredWorkflow]:
        return self._run_sync(self.discover_pipeline_workflows(project_path))

    def validate_workflow_for_agent_sync(
        self,
        workflow_name: str,
        project_path: Path | str | None = None,
    ) -> tuple[bool, str | None]:
        return self._run_sync(self.validate_workflow_for_agent(workflow_name, project_path))
