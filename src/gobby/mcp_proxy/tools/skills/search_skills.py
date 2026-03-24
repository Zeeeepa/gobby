"""Handler for the search_skills tool and search indexing."""

from __future__ import annotations

import logging
from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.skills._context import SkillsContext
from gobby.skills.search import SearchFilters
from gobby.storage.skills import ChangeEvent

logger = logging.getLogger(__name__)

# Upper bound for skill index queries -- high enough to get all installed
# skills without unbounded queries. Actual counts are typically < 200.
_MAX_SKILL_INDEX = 10_000


def _setup_indexing(ctx: SkillsContext) -> None:
    """Index all skills and wire up change-driven re-indexing."""

    def _index_skills() -> None:
        """Index all skills for search."""
        skills = ctx.storage.list_skills(
            project_id=ctx.project_id,
            limit=_MAX_SKILL_INDEX,
            include_global=True,
        )
        ctx.search.index_skills(skills)

    # Index on registry creation
    _index_skills()

    # Wire up change notifier to re-index on any skill mutation
    def _on_skill_change(event: ChangeEvent) -> None:
        """Re-index skills when any skill is created, updated, or deleted."""
        _index_skills()

    ctx.notifier.add_listener(_on_skill_change)


def register(ctx: SkillsContext, registry: InternalToolRegistry) -> None:
    """Register the search_skills tool on the registry and set up indexing."""
    _setup_indexing(ctx)

    @registry.tool(
        name="search_skills",
        description="Search for skills by query. Returns ranked results with relevance scores. Supports filtering by category and tags.",
    )
    async def search_skills(
        query: str,
        category: str | None = None,
        tags_any: list[str] | None = None,
        tags_all: list[str] | None = None,
        top_k: int = 10,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Search for skills by natural language query.

        Returns ranked results with relevance scores.

        Args:
            query: Search query (required, non-empty)
            category: Optional category filter
            tags_any: Optional tags filter - match any of these tags
            tags_all: Optional tags filter - match all of these tags
            top_k: Maximum results to return (default 10)

        Returns:
            Dict with success status and ranked search results
        """
        try:
            # Validate query
            if not query or not query.strip():
                return {"success": False, "error": "Query is required and cannot be empty"}

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
                    pass

            # Build filters
            filters = None
            if category or tags_any or tags_all or active_names is not None:
                filters = SearchFilters(
                    category=category,
                    tags_any=tags_any,
                    tags_all=tags_all,
                    allowed_names=active_names,
                )

            # Perform search
            results = await ctx.search.search_async(query=query, top_k=top_k, filters=filters)

            # Format results with skill metadata
            result_list = []
            for r in results:
                # Look up skill to get description, category, tags
                skill = None
                try:
                    skill = ctx.storage.get_skill(r.skill_id)
                except ValueError:
                    pass

                # Get category and tags from metadata
                category_value = None
                tags = []
                if skill and skill.metadata and isinstance(skill.metadata, dict):
                    skillport = skill.metadata.get("skillport", {})
                    if isinstance(skillport, dict):
                        category_value = skillport.get("category")
                        tags = skillport.get("tags", [])

                result_list.append(
                    {
                        "skill_id": r.skill_id,
                        "skill_name": r.skill_name,
                        "description": skill.description if skill else None,
                        "category": category_value,
                        "tags": tags,
                        "score": r.similarity,
                    }
                )

            return {
                "success": True,
                "count": len(result_list),
                "results": result_list,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
