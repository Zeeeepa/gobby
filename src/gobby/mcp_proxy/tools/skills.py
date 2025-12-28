"""
Internal MCP tools for Gobby Skill System.

Exposes functionality for:
- Learning skills (learn_skill_from_session)
- Listing skills (list_skills)
- Getting skills (get_skill)
- Deleting skills (delete_skill)
- Matching skills (match_skills)
- Creating skills (create_skill)
- Updating skills (update_skill)
- Applying skills (apply_skill)
- Exporting skills (export_skills)

These tools are registered with the InternalToolRegistry and accessed
via the downstream proxy pattern (call_tool).
"""

from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.memory.skills import SkillLearner
from gobby.storage.sessions import LocalSessionManager
from gobby.storage.skills import LocalSkillManager

if TYPE_CHECKING:
    from gobby.sync.memories import MemorySyncManager


def create_skills_registry(
    storage: LocalSkillManager,
    learner: SkillLearner | None = None,
    session_manager: LocalSessionManager | None = None,
    sync_manager: "MemorySyncManager | None" = None,
) -> InternalToolRegistry:
    """
    Create a skill tool registry with all skill-related tools.

    Args:
        storage: LocalSkillManager for CRUD operations
        learner: SkillLearner instance for learning/matching (optional)
        session_manager: LocalSessionManager instance (needed for creating skills from sessions)
        sync_manager: MemorySyncManager instance for export functionality (optional)

    Returns:
        InternalToolRegistry with skill tools registered
    """
    registry = InternalToolRegistry(
        name="gobby-skills",
        description="Skill management - learn, list, get, delete, match",
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
        description="Delete a skill.",
    )
    def delete_skill(skill_id: str) -> dict[str, Any]:
        """
        Delete a skill.

        Args:
            skill_id: The skill ID
        """
        try:
            success = storage.delete_skill(skill_id)
            if success:
                return {"success": True, "message": f"Skill {skill_id} deleted"}
            else:
                return {"success": False, "error": "Skill not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="match_skills",
        description="Find applicable skills for a prompt.",
    )
    async def match_skills(
        prompt: str,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Find applicable skills for a prompt.

        Args:
            prompt: User prompt/request
            project_id: Optional project context
        """
        if not learner:
            raise RuntimeError("Skill matching is not enabled (requires LLM)")

        try:
            skills = await learner.match_skills(prompt, project_id)
            return {
                "success": True,
                "matches": [s.to_dict() for s in skills],
            }
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
        name="apply_skill",
        description="Apply a skill - returns its instructions and marks it as used.",
    )
    def apply_skill(skill_id: str) -> dict[str, Any]:
        """
        Apply a skill to the current context.

        Returns the skill's instructions and increments its usage count.

        Args:
            skill_id: The skill ID to apply
        """
        try:
            skill = storage.get_skill(skill_id)
            if not skill:
                return {"success": False, "error": f"Skill {skill_id} not found"}

            # Increment usage count
            storage.increment_usage(skill_id)

            return {
                "success": True,
                "skill": {
                    "id": skill.id,
                    "name": skill.name,
                    "instructions": skill.instructions,
                    "description": skill.description,
                },
                "message": f"Applied skill '{skill.name}'. Follow the instructions above.",
            }
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="export_skills",
        description="Export skills to markdown files in the .gobby/skills directory.",
    )
    async def export_skills() -> dict[str, Any]:
        """
        Export all skills to markdown files.

        Skills are exported to .gobby/skills/ as individual markdown files
        with YAML frontmatter containing metadata.
        """
        if not sync_manager:
            return {
                "success": False,
                "error": "Memory sync is not enabled. Configure memory_sync in config.yaml.",
            }

        try:
            result = await sync_manager.export_to_files()
            return {
                "success": True,
                "exported": {
                    "skills": result.get("skills", 0),
                    "memories": result.get("memories", 0),
                },
                "message": f"Exported {result.get('skills', 0)} skills to .gobby/skills/",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    return registry
