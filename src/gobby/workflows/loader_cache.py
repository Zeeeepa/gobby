"""Cache dataclasses and helpers for WorkflowLoader.

Extracted from loader.py as part of Strangler Fig decomposition (Wave 2).
DB-only runtime: file staleness checks removed (all entries use path=None).
"""

from dataclasses import dataclass, field
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
    """Cache entry for a single workflow definition."""

    definition: WorkflowDefinition | PipelineDefinition
    path: Path | None  # None for DB / inline workflows
    mtime: float  # Unused; kept for dataclass compat


@dataclass
class _CachedDiscovery:
    """Cache entry for workflow discovery results."""

    results: list[DiscoveredWorkflow]
    file_mtimes: dict[str, float] = field(default_factory=dict)
    dir_mtimes: dict[str, float] = field(default_factory=dict)


def clear_cache(
    cache: dict[str, _CachedEntry],
    discovery_cache: dict[str, _CachedDiscovery],
) -> None:
    """Clear the workflow definitions and discovery cache."""
    cache.clear()
    discovery_cache.clear()
