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
from gobby.storage.skills import LocalSkillManager

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

    # Initialize storage
    storage = LocalSkillManager(db)

    # --- list_skills tool ---

    @registry.tool(
        name="list_skills",
        description="List all skills with lightweight metadata. Supports filtering by category and enabled status.",
    )
    async def list_skills(
        category: str | None = None,
        enabled: bool | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        List skills with lightweight metadata.

        Returns ~100 tokens per skill: name, description, category, tags, enabled.
        Does NOT include content, allowed_tools, or compatibility.

        Args:
            category: Optional category filter
            enabled: Optional enabled status filter (True/False/None for all)
            limit: Maximum skills to return (default 50)

        Returns:
            Dict with success status and list of skill metadata
        """
        try:
            skills = storage.list_skills(
                project_id=project_id,
                category=category,
                enabled=enabled,
                limit=limit,
                include_global=True,
            )

            # Extract lightweight metadata only
            skill_list = []
            for skill in skills:
                # Get category and tags from metadata
                category_value = None
                tags = []
                if skill.metadata and isinstance(skill.metadata, dict):
                    skillport = skill.metadata.get("skillport", {})
                    if isinstance(skillport, dict):
                        category_value = skillport.get("category")
                        tags = skillport.get("tags", [])

                skill_list.append({
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description,
                    "category": category_value,
                    "tags": tags,
                    "enabled": skill.enabled,
                })

            return {
                "success": True,
                "count": len(skill_list),
                "skills": skill_list,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    # --- get_skill tool ---

    @registry.tool(
        name="get_skill",
        description="Get full skill content by name or ID. Returns complete skill including content, allowed_tools, etc.",
    )
    async def get_skill(
        name: str | None = None,
        skill_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Get a skill by name or ID with full content.

        Returns all skill fields including content, allowed_tools, compatibility.
        Use this after list_skills to get the full skill when needed.

        Args:
            name: Skill name (used if skill_id not provided)
            skill_id: Skill ID (takes precedence over name)

        Returns:
            Dict with success status and full skill data
        """
        try:
            # Validate input
            if not skill_id and not name:
                return {
                    "success": False,
                    "error": "Either name or skill_id is required",
                }

            # Get skill by ID or name
            skill = None
            if skill_id:
                try:
                    skill = storage.get_skill(skill_id)
                except ValueError:
                    pass

            if skill is None and name:
                skill = storage.get_by_name(name, project_id=project_id)

            if skill is None:
                return {
                    "success": False,
                    "error": f"Skill not found: {skill_id or name}",
                }

            # Return full skill data
            return {
                "success": True,
                "skill": {
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description,
                    "content": skill.content,
                    "version": skill.version,
                    "license": skill.license,
                    "compatibility": skill.compatibility,
                    "allowed_tools": skill.allowed_tools,
                    "metadata": skill.metadata,
                    "enabled": skill.enabled,
                    "source_path": skill.source_path,
                    "source_type": skill.source_type,
                    "source_ref": skill.source_ref,
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    return registry
