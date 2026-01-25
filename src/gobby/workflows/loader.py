import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .definitions import WorkflowDefinition

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredWorkflow:
    """A discovered workflow with metadata for ordering."""

    name: str
    definition: WorkflowDefinition
    priority: int  # Lower = higher priority (runs first)
    is_project: bool  # True if from project, False if global
    path: Path


class WorkflowLoader:
    def __init__(self, workflow_dirs: list[Path] | None = None):
        # Default global workflow directory
        self.global_dirs = workflow_dirs or [Path.home() / ".gobby" / "workflows"]
        self._cache: dict[str, WorkflowDefinition] = {}
        # Cache for discovered workflows per project path
        self._discovery_cache: dict[str, list[DiscoveredWorkflow]] = {}

    def load_workflow(
        self,
        name: str,
        project_path: Path | str | None = None,
        _inheritance_chain: list[str] | None = None,
    ) -> WorkflowDefinition | None:
        """
        Load a workflow by name (without extension).
        Supports inheritance via 'extends' field with cycle detection.

        Args:
            name: Workflow name (without .yaml extension)
            project_path: Optional project directory for project-specific workflows.
                         Searches: 1) {project_path}/.gobby/workflows/  2) ~/.gobby/workflows/
            _inheritance_chain: Internal parameter for cycle detection. Do not pass directly.

        Raises:
            ValueError: If circular inheritance is detected.
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
            return self._cache[cache_key]

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

            # 4. Validate and create model
            definition = WorkflowDefinition(**data)
            self._cache[cache_key] = definition
            return definition

        except ValueError:
            # Re-raise ValueError (used for cycle detection)
            raise
        except Exception as e:
            logger.error(f"Failed to load workflow '{name}' from {path}: {e}", exc_info=True)
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
        Merge step lists by step name.
        """
        # Convert parent list to dict by name, creating copies to avoid mutating originals
        parent_map: dict[str, dict[str, Any]] = {}
        for s in parent_steps:
            if "name" not in s:
                logger.warning("Skipping parent step without 'name' key")
                continue
            # Create a shallow copy to avoid mutating the original
            parent_map[s["name"]] = dict(s)

        for child_step in child_steps:
            if "name" not in child_step:
                logger.warning("Skipping child step without 'name' key")
                continue
            name = child_step["name"]
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
