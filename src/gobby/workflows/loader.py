import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .definitions import PipelineDefinition, WorkflowDefinition

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredWorkflow:
    """A discovered workflow with metadata for ordering."""

    name: str
    definition: WorkflowDefinition | PipelineDefinition
    priority: int  # Lower = higher priority (runs first)
    is_project: bool  # True if from project, False if global
    path: Path


class WorkflowLoader:
    def __init__(self, workflow_dirs: list[Path] | None = None):
        # Default global workflow directory
        self.global_dirs = workflow_dirs or [Path.home() / ".gobby" / "workflows"]
        self._cache: dict[str, WorkflowDefinition | PipelineDefinition] = {}
        # Cache for discovered workflows per project path
        self._discovery_cache: dict[str, list[DiscoveredWorkflow]] = {}

    def load_workflow(
        self,
        name: str,
        project_path: Path | str | None = None,
        _inheritance_chain: list[str] | None = None,
    ) -> WorkflowDefinition | PipelineDefinition | None:
        """
        Load a workflow by name (without extension).
        Supports inheritance via 'extends' field with cycle detection.
        Auto-detects pipeline type and returns PipelineDefinition for type='pipeline'.

        Args:
            name: Workflow name (without .yaml extension)
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
            cached = self._cache[cache_key]
            if isinstance(cached, (WorkflowDefinition, PipelineDefinition)):
                return cached
            return None

        # Build search directories: project-specific first, then global
        search_dirs = list(self.global_dirs)
        if project_path:
            project_dir = Path(project_path) / ".gobby" / "workflows"
            search_dirs.insert(0, project_dir)

        # 1. Find file
        path = self._find_workflow_file(name, search_dirs)
        if not path:
            logger.warning(f"Workflow '{name}' not found in {search_dirs}")
            return None

        try:
            # 2. Parse YAML
            with open(path) as f:
                data = yaml.safe_load(f)

            # 3. Handle inheritance with cycle detection
            if "extends" in data:
                parent_name = data["extends"]
                # Add current workflow to chain before loading parent
                parent = self.load_workflow(
                    parent_name,
                    project_path=project_path,
                    _inheritance_chain=_inheritance_chain + [name],
                )
                if parent:
                    data = self._merge_workflows(parent.model_dump(), data)
                else:
                    logger.error(f"Parent workflow '{parent_name}' not found for '{name}'")

            # 4. Auto-detect pipeline type
            if data.get("type") == "pipeline":
                # Validate step references for pipelines
                self._validate_pipeline_references(data)
                definition: WorkflowDefinition | PipelineDefinition = PipelineDefinition(**data)
            else:
                definition = WorkflowDefinition(**data)

            self._cache[cache_key] = definition
            return definition

        except ValueError:
            # Re-raise ValueError (used for cycle detection and reference validation)
            raise
        except Exception as e:
            logger.error(f"Failed to load workflow '{name}' from {path}: {e}", exc_info=True)
            return None

    def load_pipeline(
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
            cached = self._cache[cache_key]
            if isinstance(cached, PipelineDefinition):
                return cached
            return None

        # Build search directories: project-specific first, then global
        search_dirs = list(self.global_dirs)
        if project_path:
            project_dir = Path(project_path) / ".gobby" / "workflows"
            search_dirs.insert(0, project_dir)

        # 1. Find file
        path = self._find_workflow_file(name, search_dirs)
        if not path:
            logger.debug(f"Pipeline '{name}' not found in {search_dirs}")
            return None

        try:
            # 2. Parse YAML
            with open(path) as f:
                data = yaml.safe_load(f)

            # 3. Check if this is a pipeline type
            if data.get("type") != "pipeline":
                logger.debug(f"'{name}' is not a pipeline (type={data.get('type')})")
                return None

            # 4. Handle inheritance with cycle detection
            if "extends" in data:
                parent_name = data["extends"]
                # Add current pipeline to chain before loading parent
                parent = self.load_pipeline(
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
            self._cache[cache_key] = definition
            return definition

        except ValueError:
            # Re-raise ValueError (used for cycle detection)
            raise
        except Exception as e:
            logger.error(f"Failed to load pipeline '{name}' from {path}: {e}", exc_info=True)
            return None

    def _find_workflow_file(self, name: str, search_dirs: list[Path]) -> Path | None:
        filename = f"{name}.yaml"
        for d in search_dirs:
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

    def discover_lifecycle_workflows(
        self, project_path: Path | str | None = None
    ) -> list[DiscoveredWorkflow]:
        """
        Discover all lifecycle workflows from project and global directories.

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
        cache_key = str(project_path) if project_path else "global"

        # Check cache
        if cache_key in self._discovery_cache:
            return self._discovery_cache[cache_key]

        discovered: dict[str, DiscoveredWorkflow] = {}  # name -> workflow (for shadowing)
        failed: dict[str, str] = {}  # name -> error message for failed workflows

        # 1. Scan global lifecycle directory first (will be shadowed by project)
        for global_dir in self.global_dirs:
            self._scan_directory(global_dir / "lifecycle", is_project=False, discovered=discovered)

        # 2. Scan project lifecycle directory (shadows global)
        if project_path:
            project_dir = Path(project_path) / ".gobby" / "workflows" / "lifecycle"
            self._scan_directory(project_dir, is_project=True, discovered=discovered, failed=failed)

            # Log errors when project workflow fails but global exists (failed shadowing)
            for name, error in failed.items():
                if name in discovered and not discovered[name].is_project:
                    logger.error(
                        f"Project workflow '{name}' failed to load, using global instead: {error}"
                    )

        # 3. Filter to lifecycle workflows only
        lifecycle_workflows = [w for w in discovered.values() if w.definition.type == "lifecycle"]

        # 4. Sort: project first, then by priority (asc), then by name (alpha)
        sorted_workflows = sorted(
            lifecycle_workflows,
            key=lambda w: (
                0 if w.is_project else 1,  # Project first
                w.priority,  # Lower priority = runs first
                w.name,  # Alphabetical
            ),
        )

        # Cache and return
        self._discovery_cache[cache_key] = sorted_workflows
        return sorted_workflows

    def discover_pipeline_workflows(
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
            return self._discovery_cache[cache_key]

        discovered: dict[str, DiscoveredWorkflow] = {}  # name -> workflow (for shadowing)
        failed: dict[str, str] = {}  # name -> error message for failed workflows

        # 1. Scan global workflows directory first (will be shadowed by project)
        for global_dir in self.global_dirs:
            self._scan_pipeline_directory(global_dir, is_project=False, discovered=discovered)

        # 2. Scan project workflows directory (shadows global)
        if project_path:
            project_dir = Path(project_path) / ".gobby" / "workflows"
            self._scan_pipeline_directory(
                project_dir, is_project=True, discovered=discovered, failed=failed
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
        self._discovery_cache[cache_key] = sorted_pipelines
        return sorted_pipelines

    def _scan_pipeline_directory(
        self,
        directory: Path,
        is_project: bool,
        discovered: dict[str, DiscoveredWorkflow],
        failed: dict[str, str] | None = None,
    ) -> None:
        """
        Scan a directory for pipeline YAML files and add to discovered dict.

        Only includes workflows with type='pipeline'.

        Args:
            directory: Directory to scan
            is_project: Whether this is a project directory (for shadowing)
            discovered: Dict to update (name -> DiscoveredWorkflow)
            failed: Optional dict to track failed pipelines (name -> error message)
        """
        if not directory.exists():
            return

        for yaml_path in directory.glob("*.yaml"):
            name = yaml_path.stem
            try:
                with open(yaml_path) as f:
                    data = yaml.safe_load(f)

                if not data:
                    continue

                # Only process pipeline type workflows
                if data.get("type") != "pipeline":
                    continue

                # Handle inheritance with cycle detection
                if "extends" in data:
                    parent_name = data["extends"]
                    try:
                        parent = self.load_pipeline(
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

    def _scan_directory(
        self,
        directory: Path,
        is_project: bool,
        discovered: dict[str, DiscoveredWorkflow],
        failed: dict[str, str] | None = None,
    ) -> None:
        """
        Scan a directory for workflow YAML files and add to discovered dict.

        Args:
            directory: Directory to scan
            is_project: Whether this is a project directory (for shadowing)
            discovered: Dict to update (name -> DiscoveredWorkflow)
            failed: Optional dict to track failed workflows (name -> error message)
        """
        if not directory.exists():
            return

        for yaml_path in directory.glob("*.yaml"):
            name = yaml_path.stem
            try:
                with open(yaml_path) as f:
                    data = yaml.safe_load(f)

                if not data:
                    continue

                # Handle inheritance with cycle detection
                if "extends" in data:
                    parent_name = data["extends"]
                    try:
                        parent = self.load_workflow(
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

                definition = WorkflowDefinition(**data)

                # Get priority from workflow settings or default to 100
                priority = 100
                if definition.settings and "priority" in definition.settings:
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
        Register an inline workflow definition from agent YAML.

        Inline workflows are embedded in agent definitions and registered
        at spawn time with qualified names like "agent:workflow".

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
            cached = self._cache[cache_key]
            if isinstance(cached, (WorkflowDefinition, PipelineDefinition)):
                return cached

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

            self._cache[cache_key] = definition
            logger.debug(f"Registered inline workflow '{name}' (type={definition.type})")
            return definition

        except Exception as e:
            logger.error(f"Failed to register inline workflow '{name}': {e}")
            raise ValueError(f"Invalid inline workflow '{name}': {e}") from e

    def validate_workflow_for_agent(
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
            workflow = self.load_workflow(workflow_name, project_path=project_path)
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
