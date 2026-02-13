"""Workflow discovery functions for WorkflowLoader.

Extracted from loader.py as part of Strangler Fig decomposition (Wave 2).
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles
import yaml

from .definitions import PipelineDefinition, WorkflowDefinition
from .loader_cache import DiscoveredWorkflow, _CachedDiscovery, _is_discovery_stale

if TYPE_CHECKING:
    from .loader import WorkflowLoader

logger = logging.getLogger(__name__)


async def discover_workflows(
    loader: WorkflowLoader, project_path: Path | str | None = None
) -> list[DiscoveredWorkflow]:
    """
    Discover all workflows from project and global directories.

    Scans root workflow directories.
    Returns workflows sorted by:
    1. Project workflows first (is_project=True), then global
    2. Within each group: by priority (ascending), then alphabetically by name

    Project workflows shadow global workflows with the same name.
    """
    cache_key = f"unified:{project_path}" if project_path else "unified:global"

    # Check cache
    if cache_key in loader._discovery_cache:
        cached = loader._discovery_cache[cache_key]
        if not _is_discovery_stale(cached):
            return cached.results
        del loader._discovery_cache[cache_key]

    discovered: dict[str, DiscoveredWorkflow] = {}  # name -> workflow (for shadowing)
    failed: dict[str, str] = {}  # name -> error message for failed workflows
    file_mtimes: dict[str, float] = {}
    dir_mtimes: dict[str, float] = {}

    # 1. Scan bundled directories first (lowest priority, shadowed by all)
    if loader._bundled_dir is not None and loader._bundled_dir.is_dir():
        await _scan_directory(
            loader,
            loader._bundled_dir,
            is_project=False,
            discovered=discovered,
            file_mtimes=file_mtimes,
            dir_mtimes=dir_mtimes,
        )

    # 2. Scan global directories (shadows bundled)
    for global_dir in loader.global_dirs:
        await _scan_directory(
            loader,
            global_dir,
            is_project=False,
            discovered=discovered,
            file_mtimes=file_mtimes,
            dir_mtimes=dir_mtimes,
        )

    # 3. Scan project directories (shadows global)
    if project_path:
        project_wf_dir = Path(project_path) / ".gobby" / "workflows"
        await _scan_directory(
            loader,
            project_wf_dir,
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
                    "Project workflow failed to load, using global instead",
                    extra={
                        "workflow": name,
                        "path": str(discovered[name].path),
                        "is_project": discovered[name].is_project,
                        "error": error,
                    },
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
    loader._discovery_cache[cache_key] = _CachedDiscovery(
        results=sorted_workflows, file_mtimes=file_mtimes, dir_mtimes=dir_mtimes
    )
    return sorted_workflows


async def discover_lifecycle_workflows(
    loader: WorkflowLoader, project_path: Path | str | None = None
) -> list[DiscoveredWorkflow]:
    """Deprecated: use discover_workflows() instead."""
    warnings.warn(
        "discover_lifecycle_workflows() is deprecated, use discover_workflows() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return await discover_workflows(loader, project_path)


async def discover_pipeline_workflows(
    loader: WorkflowLoader, project_path: Path | str | None = None
) -> list[DiscoveredWorkflow]:
    """
    Discover all pipeline workflows from project and global directories.

    Returns workflows sorted by:
    1. Project workflows first (is_project=True), then global
    2. Within each group: by priority (ascending), then alphabetically by name

    Project workflows shadow global workflows with the same name.
    """
    cache_key = f"pipelines:{project_path}" if project_path else "pipelines:global"

    # Check cache
    if cache_key in loader._discovery_cache:
        cached = loader._discovery_cache[cache_key]
        if not _is_discovery_stale(cached):
            return cached.results
        del loader._discovery_cache[cache_key]

    discovered: dict[str, DiscoveredWorkflow] = {}  # name -> workflow (for shadowing)
    failed: dict[str, str] = {}  # name -> error message for failed workflows
    file_mtimes: dict[str, float] = {}
    dir_mtimes: dict[str, float] = {}

    # 1. Scan bundled workflows directory first (lowest priority, shadowed by all)
    if loader._bundled_dir is not None and loader._bundled_dir.is_dir():
        await _scan_pipeline_directory(
            loader,
            loader._bundled_dir,
            is_project=False,
            discovered=discovered,
            file_mtimes=file_mtimes,
            dir_mtimes=dir_mtimes,
        )

    # 2. Scan global workflows directory (shadows bundled)
    for global_dir in loader.global_dirs:
        await _scan_pipeline_directory(
            loader,
            global_dir,
            is_project=False,
            discovered=discovered,
            file_mtimes=file_mtimes,
            dir_mtimes=dir_mtimes,
        )

    # 3. Scan project workflows directory (shadows global)
    if project_path:
        project_dir = Path(project_path) / ".gobby" / "workflows"
        await _scan_pipeline_directory(
            loader,
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
                    "Project pipeline failed to load, using global instead",
                    extra={
                        "workflow": name,
                        "path": str(discovered[name].path),
                        "is_project": discovered[name].is_project,
                        "error": error,
                    },
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
    loader._discovery_cache[cache_key] = _CachedDiscovery(
        results=sorted_pipelines, file_mtimes=file_mtimes, dir_mtimes=dir_mtimes
    )
    return sorted_pipelines


async def _scan_pipeline_directory(
    loader: WorkflowLoader,
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
                    parent = await loader.load_pipeline(
                        parent_name,
                        _inheritance_chain=[name],
                    )
                    if parent:
                        data = loader._merge_workflows(parent.model_dump(), data)
                except ValueError as e:
                    logger.warning(
                        "Skipping pipeline due to inheritance error",
                        extra={"workflow": name, "error": str(e)},
                    )
                    if failed is not None:
                        failed[name] = str(e)
                    continue

            # Validate references before creating definition
            loader._validate_pipeline_references(data)

            definition = PipelineDefinition(**data)

            # Get priority from data settings or default to 100
            # (PipelineDefinition doesn't have settings field, use raw data)
            priority: Any = 100
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
            logger.warning(
                "Failed to load pipeline",
                extra={"workflow": name, "path": str(yaml_path), "error": str(e)},
            )
            if failed is not None:
                failed[name] = str(e)


async def _scan_directory(
    loader: WorkflowLoader,
    directory: Path,
    is_project: bool,
    discovered: dict[str, DiscoveredWorkflow],
    failed: dict[str, str] | None = None,
    file_mtimes: dict[str, float] | None = None,
    dir_mtimes: dict[str, float] | None = None,
) -> None:
    """
    Scan a directory for workflow YAML files and add to discovered dict.
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

            # Skip pipeline-type files — they are handled by _scan_pipeline_directory
            if data.get("type") == "pipeline":
                continue

            # Handle inheritance with cycle detection
            if "extends" in data:
                parent_name = data["extends"]
                try:
                    parent = await loader.load_workflow(
                        parent_name,
                        _inheritance_chain=[name],
                    )
                    if parent:
                        data = loader._merge_workflows(parent.model_dump(), data)
                except ValueError as e:
                    logger.warning(
                        "Skipping workflow due to inheritance error",
                        extra={"workflow": name, "error": str(e)},
                    )
                    if failed is not None:
                        failed[name] = str(e)
                    continue

            # Backward compat: derive enabled from deprecated type field
            if "type" in data and "enabled" not in data:
                data["enabled"] = data["type"] == "lifecycle"

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
            logger.warning(
                "Failed to load workflow",
                extra={"workflow": name, "path": str(yaml_path), "error": str(e)},
            )
            if failed is not None:
                failed[name] = str(e)
