"""
Internal MCP tools for Skill management.

Exposes functionality for:
- list_skills(): List all skills
- get_skill(): Get skill by ID or name
- search_skills(): Search skills by query
- create_skill(): Create a new skill
- update_skill(): Update an existing skill
- delete_skill(): Delete a skill
- install_skill(): Install skill from GitHub/URL

These tools use the SkillManager for storage and search.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol

__all__ = ["create_skills_registry", "SkillsToolRegistry"]


class SkillsToolRegistry(InternalToolRegistry):
    """Registry for skill management tools with test-friendly get_tool method."""

    def get_tool(self, name: str) -> Callable[..., Any] | None:
        """Get a tool function by name (for testing)."""
        tool = self._tools.get(name)
        return tool.func if tool else None


def create_skills_registry(
    db: DatabaseProtocol,
    project_id: str | None = None,
) -> SkillsToolRegistry:
    """
    Create a skills management tool registry.

    Args:
        db: Database connection for storage
        project_id: Optional default project scope for skill operations

    Returns:
        SkillsToolRegistry with skill management tools registered
    """
    registry = SkillsToolRegistry(
        name="gobby-skills",
        description="Skill management - list_skills, get_skill, search_skills, create_skill, install_skill, update_skill, delete_skill",
    )

    # Tools will be added by subsequent tasks:
    # - #5883: list_skills, get_skill tools
    # - #5884: search_skills tool
    # - #5885: create_skill, update_skill, delete_skill tools
    # - etc.

    return registry
