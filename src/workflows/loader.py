import logging
from pathlib import Path
from typing import Any

import yaml

from .definitions import WorkflowDefinition

logger = logging.getLogger(__name__)


class WorkflowLoader:
    def __init__(self, workflow_dirs: list[Path] | None = None):
        # Default global workflow directory
        self.global_dirs = workflow_dirs or [Path.home() / ".gobby" / "workflows"]
        self._cache: dict[str, WorkflowDefinition] = {}

    def load_workflow(self, name: str, project_path: Path | str | None = None) -> WorkflowDefinition | None:
        """
        Load a workflow by name (without extension).
        Supports inheritance via 'extends' field.

        Args:
            name: Workflow name (without .yaml extension)
            project_path: Optional project directory for project-specific workflows.
                         Searches: 1) {project_path}/.gobby/workflows/  2) ~/.gobby/workflows/
        """
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

            # 3. Handle inheritance
            if "extends" in data:
                parent_name = data["extends"]
                parent = self.load_workflow(parent_name)
                if parent:
                    data = self._merge_workflows(parent.dict(), data)
                else:
                    logger.error(f"Parent workflow '{parent_name}' not found for '{name}'")

            # 4. Validate and create model
            definition = WorkflowDefinition(**data)
            self._cache[cache_key] = definition
            return definition

        except Exception as e:
            logger.error(f"Failed to load workflow '{name}' from {path}: {e}", exc_info=True)
            return None

    def _find_workflow_file(self, name: str, search_dirs: list[Path]) -> Path | None:
        filename = f"{name}.yaml"
        for d in search_dirs:
            candidate = d / filename
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
            elif key == "phases" and "phases" in merged:
                # Special handling for phases: merge by name
                merged["phases"] = self._merge_phases(merged["phases"], value)
            else:
                merged[key] = value

        return merged

    def _merge_phases(self, parent_phases: list, child_phases: list) -> list:
        """
        Merge phases lists by phase name.
        """
        # Convert parent list to dict by name
        parent_map = {p["name"]: p for p in parent_phases}

        for child_phase in child_phases:
            name = child_phase["name"]
            if name in parent_map:
                # Merge existing phase (deep merge the dicts)
                # For simplicity here using a helper or just updating fields
                # Ideally we'd recursively merge the phase dicts too
                # For now, let's assume entire phase override or simple update
                # A proper implementation would merge allowed_tools, rules etc.
                # Let's do a shallow merge of the phase dict for now
                parent_map[name].update(child_phase)
            else:
                # Add new phase
                parent_map[name] = child_phase

        return list(parent_map.values())
