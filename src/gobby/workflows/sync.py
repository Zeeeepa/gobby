"""Workflow definition synchronization re-export shim.

The implementation has been split into per-type modules:
- sync_pipelines.py — pipeline sync
- sync_rules.py — rule sync (also contains shared helpers)
- sync_variables.py — variable sync
"""

from gobby.workflows.sync_pipelines import get_bundled_pipelines_path, sync_bundled_pipelines
from gobby.workflows.sync_rules import (
    _ensure_gobby_tag_on_installed,
    _ensure_tag_on_installed,
    _propagate_to_installed,
    _resolve_sync_placeholders,
    get_bundled_rules_path,
    sync_bundled_rules,
)
from gobby.workflows.sync_variables import get_bundled_variables_path, sync_bundled_variables

__all__ = [
    "get_bundled_pipelines_path",
    "get_bundled_rules_path",
    "get_bundled_variables_path",
    "sync_bundled_pipelines",
    "sync_bundled_rules",
    "sync_bundled_variables",
    "_ensure_gobby_tag_on_installed",
    "_ensure_tag_on_installed",
    "_propagate_to_installed",
    "_resolve_sync_placeholders",
]
