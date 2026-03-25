"""Handler for the install_from_template tool."""

from __future__ import annotations

import logging
from typing import Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry
from gobby.mcp_proxy.tools.skills._context import SkillsContext

logger = logging.getLogger(__name__)


def register(ctx: SkillsContext, registry: InternalToolRegistry) -> None:
    """Register the install_from_template tool on the registry."""

    @registry.tool(
        name="install_from_template",
        description="Create an installed copy from a template skill. Templates are bundled skill definitions; installing creates an active copy.",
    )
    async def install_from_template(
        skill_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """
        Install a skill from a template.

        Args:
            skill_id: Template skill ID (takes precedence over name)
            name: Template skill name

        Returns:
            Dict with success status and installed skill info
        """
        try:
            if not skill_id and not name:
                return {"success": False, "error": "Either name or skill_id is required"}

            skill = None
            if skill_id:
                try:
                    found = ctx.storage.get_skill(skill_id, include_deleted=True)
                    # Only accept templates — non-template skills can't be "installed from template"
                    if found and getattr(found, "source", None) == "template":
                        skill = found
                except ValueError:
                    logger.debug("Skill lookup by id failed for %s", skill_id, exc_info=True)

            if skill is None and name:
                skill = ctx.storage.get_by_name(
                    name,
                    project_id=ctx.project_id,
                    source="template",
                    include_deleted=True,
                    include_templates=True,
                )

            if skill is None:
                return {"success": False, "error": f"Template not found: {skill_id or name}"}

            installed = ctx.storage.install_from_template(skill.id)
            return {
                "success": True,
                "installed": True,
                "skill_id": installed.id,
                "skill_name": installed.name,
                "template_id": skill.id,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
