"""Handlers for the get_skill and get_skill_file tools."""

from __future__ import annotations

import logging
from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.skills._context import SkillsContext

logger = logging.getLogger(__name__)


def register(ctx: SkillsContext, registry: InternalToolRegistry) -> None:
    """Register the get_skill and get_skill_file tools on the registry."""

    @registry.tool(
        name="get_skill",
        description="Get full skill content by name or ID. Returns complete skill including content, allowed_tools, etc.",
    )
    async def get_skill(
        name: str | None = None,
        skill_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Get a skill by name or ID with full content.

        Returns all skill fields including content, allowed_tools, compatibility.
        Use this after list_skills to get the full skill when needed.

        Args:
            name: Skill name (used if skill_id not provided)
            skill_id: Skill ID (takes precedence over name)
            session_id: Optional session ID (accepts #N, N, UUID, or prefix) to record skill usage

        Returns:
            Dict with success status and full skill data
        """
        try:
            # Validate input
            if not skill_id and not name:
                return {"success": False, "error": "Either name or skill_id is required"}

            # Get skill by ID or name
            skill = None
            if skill_id:
                try:
                    skill = ctx.storage.get_skill(skill_id)
                except ValueError:
                    pass

            if skill is None and name:
                skill = ctx.storage.get_by_name(name, project_id=ctx.project_id)

            if skill is None:
                return {"success": False, "error": f"Skill not found: {skill_id or name}"}

            # Record skill usage when session_id is provided
            if session_id:
                try:
                    resolved_id = ctx.session_manager.resolve_session_reference(
                        session_id, project_id=ctx.project_id
                    )
                    ctx.session_manager.record_skills_used(resolved_id, [skill.name])
                except Exception:
                    pass  # Best-effort tracking; don't fail the skill lookup

            # Build response
            skill_data: dict[str, Any] = {
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
                "source": skill.source,
                "source_path": skill.source_path,
                "source_type": skill.source_type,
                "source_ref": skill.source_ref,
            }

            # Include file metadata if files exist
            try:
                skill_files = ctx.storage.get_skill_files(skill.id)
                if skill_files:
                    skill_data["files"] = [f.to_dict() for f in skill_files]
            except Exception as e:
                logger.debug(f"Failed to get files for skill {skill.name}: {e}")

            return {
                "success": True,
                "skill": skill_data,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="get_skill_file",
        description="Get a single file's content from a multi-file skill. Use after get_skill() shows available files.",
    )
    async def get_skill_file_tool(
        path: str,
        name: str | None = None,
        skill_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Fetch a single file from a skill on demand.

        Progressive disclosure: get_skill() shows file metadata (path, type, size),
        this tool fetches the actual content for a specific file.

        Args:
            path: Relative file path within the skill (e.g. "references/api.md")
            name: Skill name (used if skill_id not provided)
            skill_id: Skill ID (takes precedence over name)

        Returns:
            Dict with success status and file content
        """
        try:
            if not path:
                return {"success": False, "error": "path is required"}
            if not skill_id and not name:
                return {"success": False, "error": "Either name or skill_id is required"}

            # Resolve skill
            skill = None
            if skill_id:
                try:
                    skill = ctx.storage.get_skill(skill_id)
                except ValueError:
                    pass
            if skill is None and name:
                skill = ctx.storage.get_by_name(name, project_id=ctx.project_id)
            if skill is None:
                return {"success": False, "error": f"Skill not found: {skill_id or name}"}

            # Get the file
            skill_file = ctx.storage.get_skill_file(skill.id, path)
            if skill_file is None:
                return {"success": False, "error": f"File not found: {path}"}

            return {
                "success": True,
                "file": skill_file.to_dict(include_content=True),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
