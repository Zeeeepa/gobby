"""Cache dataclasses and helpers for WorkflowLoader.

Extracted from loader.py as part of Strangler Fig decomposition (Wave 2).
"""

from dataclasses import dataclass
from pathlib import Path

from .definitions import PipelineDefinition, WorkflowDefinition


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


def _is_stale(entry: _CachedEntry) -> bool:
    """Check if a cached workflow entry is stale (file changed on disk)."""
    if entry.path is None:
        return False  # Inline workflows have no file to check
    if entry.mtime == 0.0:
        return False  # Could not stat at cache time; skip check
    try:
        return entry.path.stat().st_mtime != entry.mtime
    except OSError:
        return True  # File deleted = stale


def _is_discovery_stale(entry: _CachedDiscovery) -> bool:
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


def clear_cache(
    cache: dict[str, _CachedEntry],
    discovery_cache: dict[str, _CachedDiscovery],
) -> None:
    """Clear the workflow definitions and discovery cache.

    Call when workflows may have changed on disk.
    """
    cache.clear()
    discovery_cache.clear()
