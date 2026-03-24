"""Skill template management (sync, install, list templates)."""

from __future__ import annotations

import logging

from gobby.storage.skills._models import Skill

logger = logging.getLogger(__name__)


class SkillTemplatesMixin:
    """Mixin providing skill template management operations.

    Requires methods from ``SkillMetadataMixin`` and ``SkillFilesMixin``.
    """

    def install_from_template(self, skill_id: str) -> Skill:
        """Create an installed copy from a template skill.

        Copies all fields from the template, sets source='installed' and enabled=True.

        Args:
            skill_id: ID of the template skill

        Returns:
            The newly created installed Skill

        Raises:
            ValueError: If template not found or installed copy already exists
        """
        template = self.get_skill(skill_id, include_deleted=True)
        if template.source != "template":
            raise ValueError(f"Skill {skill_id} is not a template (source={template.source})")

        # Check if installed copy already exists
        existing = self.get_by_name(
            template.name, project_id=template.project_id, source="installed"
        )
        if existing:
            raise ValueError(
                f"Installed copy of '{template.name}' already exists (id={existing.id})"
            )

        installed = self.create_skill(
            name=template.name,
            description=template.description,
            content=template.content,
            version=template.version,
            license=template.license,
            compatibility=template.compatibility,
            allowed_tools=template.allowed_tools,
            metadata=template.metadata,
            source_path=template.source_path,
            source_type=template.source_type,
            source_ref=template.source_ref,
            hub_name=template.hub_name,
            hub_slug=template.hub_slug,
            hub_version=template.hub_version,
            enabled=True,
            always_apply=template.always_apply,
            injection_format=template.injection_format,
            project_id=template.project_id,
            source="installed",
        )

        # Copy files from template to installed copy
        template_files = self.get_skill_files(skill_id, include_content=True, exclude_license=False)
        if template_files:
            for f in template_files:
                f.skill_id = installed.id
            self.set_skill_files(installed.id, template_files)

        return installed

    def install_all_templates(self, project_id: str | None = None) -> int:
        """Install all eligible template skills that don't have installed copies.

        Args:
            project_id: Project scope (None for global)

        Returns:
            Number of templates installed
        """
        # Get all non-deleted templates
        templates = self.list_skills(
            project_id=project_id,
            include_templates=True,
            include_deleted=False,
            source="template",
            limit=10000,
        )

        installed_count = 0
        for template in templates:
            # Check if installed copy already exists
            existing = self.get_by_name(
                template.name, project_id=template.project_id, source="installed"
            )
            if existing:
                continue

            try:
                self.install_from_template(template.id)
                installed_count += 1
            except Exception as e:
                logger.warning(f"Failed to install template '{template.name}': {e}")

        return installed_count
