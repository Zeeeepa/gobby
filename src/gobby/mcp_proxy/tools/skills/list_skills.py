"""Handler for the list_skills tool."""

from __future__ import annotations

import logging
from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.skills._context import SkillsContext

logger = logging.getLogger(__name__)


def register(ctx: SkillsContext, registry: InternalToolRegistry) -> None:
    """Register the list_skills tool on the registry."""

    @registry.tool(
        name="list_skills",
        description="List all skills with lightweight metadata. Supports filtering by category and enabled status.",
    )
    async def list_skills(
        category: str | None = None,
        enabled: bool | None = None,
        limit: int = 50,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        List skills with lightweight metadata.

        Returns ~100 tokens per skill: name, description, category, tags, enabled, source.
        Does NOT include content, allowed_tools, or compatibility.

        Args:
            category: Optional category filter
            enabled: Optional enabled status filter (True/False/None for all)
            limit: Maximum skills to return (default 50)
            session_id: Optional session ID for filtering by active skills in the session

        Returns:
            Dict with success status and list of skill metadata
        """
        try:
            active_names = None
            if session_id:
                try:
                    from gobby.workflows.state_manager import SessionVariableManager

                    resolved_id = ctx.session_manager.resolve_session_reference(
                        session_id, project_id=ctx.project_id
                    )
                    sv_mgr = SessionVariableManager(ctx.db)
                    sv = sv_mgr.get_variables(resolved_id)
                    active_names = sv.get("_active_skill_names") if sv else None
                except Exception:
                    logger.debug(f"Failed to resolve active skill names for session {session_id}")

            skills = ctx.storage.list_skills(
                project_id=ctx.project_id,
                category=category,
                enabled=enabled,
                # Over-fetch by 5x when filtering by active_names, since the DB
                # query doesn't know about the session-scoped allowlist and we
                # need enough candidates to fill `limit` after filtering.
                limit=limit * 5 if active_names is not None else limit,
                include_global=True,
            )

            if active_names is not None:
                active_set = set(active_names)
                skills = [s for s in skills if s.name in active_set][:limit]

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

                skill_list.append(
                    {
                        "id": skill.id,
                        "name": skill.name,
                        "description": skill.description,
                        "category": category_value,
                        "tags": tags,
                        "enabled": skill.enabled,
                        "source": skill.source,
                    }
                )

            return {
                "success": True,
                "count": len(skill_list),
                "skills": skill_list,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
