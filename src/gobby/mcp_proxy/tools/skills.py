"""
Internal MCP tools for Gobby Skill System.

Exposes functionality for:
- Learning skills (learn_skill_from_session)
- Listing skills (list_skills)
- Getting skills (get_skill)
- Deleting skills (delete_skill)
- Creating skills (create_skill)
- Updating skills (update_skill)
- Exporting skills (export_skills)

Skills are exported to .claude/skills/<name>/ in Claude Code native format,
making them automatically available to Claude Code sessions.

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool).
"""

from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.skills import SkillLearner
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.skills import LocalSkillManager

if TYPE_CHECKING:
    from gobby.sync.skills import SkillSyncManager


def create_skills_registry(
    storage: LocalSkillManager,
    learner: SkillLearner | None = None,
    session_manager: LocalSessionManager | None = None,
    sync_manager: "SkillSyncManager | None" = None,
) -> InternalToolRegistry:
    """
    Create a skill tool registry with all skill-related tools.

    Args:
        storage: LocalSkillManager for CRUD operations
        learner: SkillLearner instance for learning/matching (optional)
        session_manager: LocalSessionManager instance (needed for creating skills from sessions)
        sync_manager: SkillSyncManager instance for export functionality (optional)

    Returns:
        InternalToolRegistry with skill tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-skills",
        description="Skill management - learn, list, get, delete, create, update, export",
    )

    @registry.tool(
        name="learn_skill_from_session",
        description="Learn skills from a completed session.",
    )
    async def learn_skill_from_session(session_id: str) -> dict[str, Any]:
        """
        Learn skills from a completed session.

        Args:
            session_id: The ID of the session to learn from
        """
        if not learner:
            raise RuntimeError("Skill learner is not enabled (requires LLM)")

        if not session_manager:
            return {
                "success": False,
                "error": "Session manager not available for skill learning",
            }

        try:
            session = session_manager.get(session_id)
            if not session:
                return {"success": False, "error": f"Session {session_id} not found"}

            skills = await learner.learn_from_session(session)
            return {
                "success": True,
                "skills": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "description": s.description,
                    }
                    for s in skills
                ],
                "count": len(skills),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="list_skills",
        description="List available skills.",
    )
    def list_skills(
        project_id: str | None = None,
        tag: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        List available skills.

        Args:
            project_id: Filter by project
            tag: Filter by tag
            limit: Max results
        """
        try:
            skills = storage.list_skills(
                project_id=project_id,
                tag=tag,
                limit=limit,
            )
            return {
                "success": True,
                "skills": [s.to_dict() for s in skills],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="get_skill",
        description="Get details of a specific skill.",
    )
    def get_skill(skill_id: str) -> dict[str, Any]:
        """
        Get details of a specific skill.

        Args:
            skill_id: The skill ID
        """
        try:
            skill = storage.get_skill(skill_id)
            if skill:
                return {"success": True, "skill": skill.to_dict()}
            else:
                return {"success": False, "error": "Skill not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="delete_skill",
        description="Delete a skill and remove from exported directory.",
    )
    def delete_skill(skill_id: str) -> dict[str, Any]:
        """
        Delete a skill.

        Args:
            skill_id: The skill ID
        """
        import shutil
        from pathlib import Path

        try:
            # Get skill first to know its name for cleanup
            try:
                skill = storage.get_skill(skill_id)
                skill_name = skill.name if skill else None
            except ValueError:
                skill_name = None

            success = storage.delete_skill(skill_id)
            if success:
                result: dict[str, Any] = {"success": True, "message": f"Skill {skill_id} deleted"}

                # Also remove from exported directory if it exists
                if skill_name:
                    safe_name = "".join(c for c in skill_name if c.isalnum() or c in "-_").lower()
                    if safe_name:
                        # Use absolute path relative to current working directory (project root)
                        base_skills_dir = (Path.cwd() / ".claude" / "skills").resolve()
                        skill_dir = (base_skills_dir / safe_name).resolve()

                        # Security check: Ensure skill_dir is inside base_skills_dir
                        if (
                            skill_dir.is_relative_to(base_skills_dir)
                            and skill_dir.exists()
                            and skill_dir.is_dir()
                        ):
                            # Log the absolute path being removed for safety/determinism
                            import logging

                            logger = logging.getLogger(__name__)
                            logger.info(f"Removing exported skill directory: {skill_dir}")
                            shutil.rmtree(skill_dir)
                            result["uninstalled"] = str(skill_dir)

                return result
            else:
                return {"success": False, "error": "Skill not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="create_skill",
        description="Create a new skill directly with provided instructions.",
    )
    def create_skill(
        name: str,
        instructions: str,
        project_id: str | None = None,
        description: str | None = None,
        trigger_pattern: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new skill directly.

        Args:
            name: The skill name
            instructions: The skill instructions/content
            project_id: Optional project to associate with
            description: Optional description
            trigger_pattern: Optional regex pattern for auto-matching
            tags: Optional list of tags
        """
        try:
            skill = storage.create_skill(
                name=name,
                instructions=instructions,
                project_id=project_id,
                description=description,
                trigger_pattern=trigger_pattern,
                tags=tags,
            )
            return {"success": True, "skill": skill.to_dict()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="update_skill",
        description="Update an existing skill's properties.",
    )
    def update_skill(
        skill_id: str,
        name: str | None = None,
        instructions: str | None = None,
        description: str | None = None,
        trigger_pattern: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Update an existing skill.

        Args:
            skill_id: The skill ID to update
            name: New name (optional)
            instructions: New instructions (optional)
            description: New description (optional)
            trigger_pattern: New trigger pattern (optional)
            tags: New list of tags (optional)
        """
        try:
            skill = storage.update_skill(
                skill_id=skill_id,
                name=name,
                instructions=instructions,
                description=description,
                trigger_pattern=trigger_pattern,
                tags=tags,
            )
            return {"success": True, "skill": skill.to_dict()}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="export_skills",
        description="Export skills to all CLI formats (Claude Code, Codex, Gemini).",
    )
    async def export_skills() -> dict[str, Any]:
        """
        Export all skills to supported CLI formats.

        Exports to:
        - Claude Code: .gobby/skills/<name>/SKILL.md (project directory)
        - Codex: ~/.codex/skills/<name>/SKILL.md
        - Gemini: ~/.gemini/commands/skills/<name>.toml (as custom commands)
        """
        if not sync_manager:
            return {
                "success": False,
                "error": "Skill sync is not enabled. Configure skill_sync in config.yaml.",
            }

        try:
            results = await sync_manager.export_to_all_formats()
            total = sum(results.values())
            return {
                "success": True,
                "exported": total,
                "by_format": results,
                "message": f"Exported {total} skills to all formats",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    return registry
