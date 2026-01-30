"""
Import and cache tools for workflows.
"""

import logging
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from gobby.utils.project_context import get_workflow_project_path
from gobby.workflows.loader import WorkflowLoader

logger = logging.getLogger(__name__)


def import_workflow(
    loader: WorkflowLoader,
    source_path: str,
    workflow_name: str | None = None,
    is_global: bool = False,
    project_path: str | None = None,
) -> dict[str, Any]:
    """
    Import a workflow from a file.

    Args:
        loader: WorkflowLoader instance
        source_path: Path to the workflow YAML file
        workflow_name: Override the workflow name (defaults to name in file)
        is_global: Install to global ~/.gobby/workflows instead of project
        project_path: Project directory path. Auto-discovered from cwd if not provided.

    Returns:
        Success status and destination path
    """
    source = Path(source_path)
    if not source.exists():
        return {"success": False, "error": f"File not found: {source_path}"}

    if source.suffix != ".yaml":
        return {"success": False, "error": "Workflow file must have .yaml extension"}

    try:
        with open(source, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "name" not in data:
            return {"success": False, "error": "Invalid workflow: missing 'name' field"}

    except yaml.YAMLError as e:
        return {"success": False, "error": f"Invalid YAML: {e}"}

    raw_name = workflow_name or data.get("name", source.stem)
    # Sanitize name to prevent path traversal: strip path components, allow only safe chars
    safe_name = Path(raw_name).name  # Strip any path components
    safe_name = re.sub(r"[^a-zA-Z0-9_\-.]", "_", safe_name)  # Replace unsafe chars
    safe_name = safe_name.strip("._")  # Remove leading/trailing dots and underscores
    if not safe_name:
        safe_name = source.stem  # Fallback to source filename
    filename = f"{safe_name}.yaml"

    if is_global:
        dest_dir = Path.home() / ".gobby" / "workflows"
    else:
        # Auto-discover project path if not provided
        if not project_path:
            discovered = get_workflow_project_path()
            if discovered:
                project_path = str(discovered)

        proj = Path(project_path) if project_path else None
        if not proj:
            return {
                "success": False,
                "error": "project_path required when not using is_global (could not auto-discover)",
            }
        dest_dir = proj / ".gobby" / "workflows"

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    shutil.copy(source, dest_path)

    # Clear loader cache so new workflow is discoverable
    loader.clear_cache()

    return {
        "success": True,
        "workflow_name": safe_name,
        "destination": str(dest_path),
        "is_global": is_global,
    }


def reload_cache(loader: WorkflowLoader) -> dict[str, Any]:
    """
    Clear the workflow loader cache.

    This forces the daemon to re-read workflow YAML files from disk
    on the next access. Use this when you've modified workflow files
    and want the changes to take effect immediately without restarting
    the daemon.

    Returns:
        Success status
    """
    loader.clear_cache()
    logger.info("Workflow cache cleared via reload_cache tool")
    return {"message": "Workflow cache cleared"}
