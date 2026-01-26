"""
Internal MCP tools for Skill management.

Exposes functionality for:
- list_skills(): List all skills with lightweight metadata
- get_skill(): Get skill by ID or name with full content
- search_skills(): Search skills by query with relevance ranking
- update_skill(): Update an existing skill by refreshing from source
- install_skill(): Install skill from local path, GitHub URL, or ZIP archive
- remove_skill(): Remove a skill by name or ID

These tools use LocalSkillManager for storage and SkillSearch for search.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.skills.loader import SkillLoader, SkillLoadError
from gobby.skills.search import SearchFilters, SkillSearch
from gobby.skills.updater import SkillUpdater
from gobby.storage.skills import ChangeEvent, LocalSkillManager, SkillChangeNotifier

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol

__all__ = ["create_skills_registry", "SkillsToolRegistry"]


class SkillsToolRegistry(InternalToolRegistry):
    """Registry for skill management tools with test-friendly get_tool method."""

    search: SkillSearch  # Assigned dynamically in create_skills_registry

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
        description="Skill management - list_skills, get_skill, search_skills, install_skill, update_skill, remove_skill",
    )

    # Initialize change notifier and storage
    notifier = SkillChangeNotifier()
    storage = LocalSkillManager(db, notifier=notifier)

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

                skill_list.append(
                    {
                        "id": skill.id,
                        "name": skill.name,
                        "description": skill.description,
                        "category": category_value,
                        "tags": tags,
                        "enabled": skill.enabled,
                    }
                )

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

    # --- search_skills tool ---

    # Initialize search and index skills
    search = SkillSearch()
    # Expose search instance on registry for testing/manual indexing
    registry.search = search

    def _index_skills() -> None:
        """Index all skills for search."""
        skills = storage.list_skills(
            project_id=project_id,
            limit=10000,
            include_global=True,
        )
        search.index_skills(skills)

    # Index on registry creation
    _index_skills()

    # Wire up change notifier to re-index on any skill mutation
    def _on_skill_change(event: ChangeEvent) -> None:
        """Re-index skills when any skill is created, updated, or deleted."""
        _index_skills()

    notifier.add_listener(_on_skill_change)

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
                return {
                    "success": False,
                    "error": "Query is required and cannot be empty",
                }

            # Build filters
            filters = None
            if category or tags_any or tags_all:
                filters = SearchFilters(
                    category=category,
                    tags_any=tags_any,
                    tags_all=tags_all,
                )

            # Perform search
            results = await search.search_async(query=query, top_k=top_k, filters=filters)

            # Format results with skill metadata
            result_list = []
            for r in results:
                # Look up skill to get description, category, tags
                skill = None
                try:
                    skill = storage.get_skill(r.skill_id)
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
            return {
                "success": False,
                "error": str(e),
            }

    # --- remove_skill tool ---

    @registry.tool(
        name="remove_skill",
        description="Remove a skill by name or ID. Returns success status and removed skill name.",
    )
    async def remove_skill(
        name: str | None = None,
        skill_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Remove a skill from the database.

        Args:
            name: Skill name (used if skill_id not provided)
            skill_id: Skill ID (takes precedence over name)

        Returns:
            Dict with success status and removed skill info
        """
        try:
            # Validate input
            if not skill_id and not name:
                return {
                    "success": False,
                    "error": "Either name or skill_id is required",
                }

            # Find the skill first to get its name
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

            # Store the name before deletion
            skill_name = skill.name

            # Delete the skill (notifier triggers re-indexing automatically)
            storage.delete_skill(skill.id)

            return {
                "success": True,
                "removed": True,
                "skill_name": skill_name,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    # --- update_skill tool ---

    # Initialize updater
    updater = SkillUpdater(storage)

    @registry.tool(
        name="update_skill",
        description="Update a skill by refreshing from its source. Returns whether the skill was updated.",
    )
    async def update_skill(
        name: str | None = None,
        skill_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Update a skill by refreshing from its source path.

        Args:
            name: Skill name (used if skill_id not provided)
            skill_id: Skill ID (takes precedence over name)

        Returns:
            Dict with success status and update info
        """
        try:
            # Validate input
            if not skill_id and not name:
                return {
                    "success": False,
                    "error": "Either name or skill_id is required",
                }

            # Find the skill first
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

            # Use SkillUpdater to refresh from source
            # (notifier triggers re-indexing automatically if updated)
            result = updater.update_skill(skill.id)

            return {
                "success": result.success,
                "updated": result.updated,
                "skipped": result.skipped,
                "skip_reason": result.skip_reason,
                "error": result.error,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    # --- install_skill tool ---

    # Initialize loader
    loader = SkillLoader()

    @registry.tool(
        name="install_skill",
        description="Install a skill from a local path, GitHub URL, or ZIP archive. Auto-detects source type.",
    )
    async def install_skill(
        source: str | None = None,
        project_scoped: bool = False,
    ) -> dict[str, Any]:
        """
        Install a skill from a source location.

        Auto-detects source type:
        - Local directory or SKILL.md file
        - GitHub URL (owner/repo, github:owner/repo, https://github.com/...)
        - ZIP archive (.zip file)

        Args:
            source: Path or URL to the skill source (required)
            project_scoped: If True, install skill scoped to the project

        Returns:
            Dict with success status, skill_id, skill_name, and source_type
        """
        try:
            # Validate input
            if not source or not source.strip():
                return {
                    "success": False,
                    "error": "source parameter is required",
                }

            source = source.strip()

            # Determine source type and load skill
            from gobby.storage.skills import SkillSourceType

            parsed_skill = None
            source_type: SkillSourceType | None = None

            # Check if it's a GitHub URL/reference
            # Pattern for owner/repo format (e.g., "anthropic/claude-code")
            # Must match owner/repo pattern without path traversal or absolute paths
            github_owner_repo_pattern = re.compile(
                r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(/[A-Za-z0-9_./-]*)?$"
            )

            # Explicit GitHub references (always treated as GitHub, no filesystem check)
            is_explicit_github = (
                source.startswith("github:")
                or source.startswith("https://github.com/")
                or source.startswith("http://github.com/")
            )

            # For implicit owner/repo patterns, check local filesystem first
            is_implicit_github_pattern = (
                not is_explicit_github
                and github_owner_repo_pattern.match(source)
                and not source.startswith("/")
                and ".." not in source  # Reject path traversal
            )

            # Determine if this is a GitHub reference:
            # - Explicit refs are always GitHub
            # - Implicit patterns are GitHub only if local path doesn't exist
            is_github_ref = is_explicit_github or (
                is_implicit_github_pattern and not Path(source).exists()
            )
            if is_github_ref:
                # GitHub URL
                try:
                    parsed_skill = loader.load_from_github(source)
                    source_type = "github"
                except SkillLoadError as e:
                    return {
                        "success": False,
                        "error": f"Failed to load from GitHub: {e}",
                    }

            # Check if it's a ZIP file
            elif source.endswith(".zip"):
                zip_path = Path(source)
                if not zip_path.exists():
                    return {
                        "success": False,
                        "error": f"ZIP file not found: {source}",
                    }
                try:
                    parsed_skill = loader.load_from_zip(zip_path)
                    source_type = "zip"
                except SkillLoadError as e:
                    return {
                        "success": False,
                        "error": f"Failed to load from ZIP: {e}",
                    }

            # Assume it's a local path
            else:
                local_path = Path(source)
                if not local_path.exists():
                    return {
                        "success": False,
                        "error": f"Path not found: {source}",
                    }
                try:
                    parsed_skill = loader.load_skill(local_path)
                    source_type = "local"
                except SkillLoadError as e:
                    return {
                        "success": False,
                        "error": f"Failed to load skill: {e}",
                    }

            if parsed_skill is None:
                return {
                    "success": False,
                    "error": "Failed to load skill from source",
                }

            # Handle case where load_from_github/load_from_zip returns a list
            if isinstance(parsed_skill, list):
                if len(parsed_skill) == 0:
                    return {
                        "success": False,
                        "error": "No skills found in source",
                    }
                # Use the first skill if multiple were found
                parsed_skill = parsed_skill[0]

            # Determine project ID for the skill
            skill_project_id = project_id if project_scoped else None

            # Store the skill
            skill = storage.create_skill(
                name=parsed_skill.name,
                description=parsed_skill.description,
                content=parsed_skill.content,
                version=parsed_skill.version,
                license=parsed_skill.license,
                compatibility=parsed_skill.compatibility,
                allowed_tools=parsed_skill.allowed_tools,
                metadata=parsed_skill.metadata,
                source_path=parsed_skill.source_path,
                source_type=source_type,
                source_ref=getattr(parsed_skill, "source_ref", None),
                project_id=skill_project_id,
                enabled=True,
            )
            # Notifier triggers re-indexing automatically via create_skill

            return {
                "success": True,
                "installed": True,
                "skill_id": skill.id,
                "skill_name": skill.name,
                "source_type": source_type,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    return registry
