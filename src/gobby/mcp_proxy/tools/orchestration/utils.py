"""Shared utilities for orchestration tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gobby.utils.project_context import get_project_context

if TYPE_CHECKING:
    pass


def get_current_project_id() -> str | None:
    """Get the current project ID from context."""
    context = get_project_context()
    return context.get("id") if context else None
