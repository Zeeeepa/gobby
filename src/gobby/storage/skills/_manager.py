"""Skill storage and management — composed from focused modules.

LocalSkillManager combines metadata CRUD, file I/O, and template management
via mixins. All public methods are inherited; see individual modules for details:

- ``_metadata.py`` — create, get, list, update, delete, search, count
- ``_files.py`` — set_skill_files, get_skill_files, delete/restore files
- ``_templates.py`` — install_from_template, install_all_templates
"""

import logging
from typing import Any

from gobby.storage.database import DatabaseProtocol
from gobby.storage.skills._files import SkillFilesMixin
from gobby.storage.skills._metadata import SkillMetadataMixin
from gobby.storage.skills._templates import SkillTemplatesMixin

logger = logging.getLogger(__name__)


class LocalSkillManager(SkillMetadataMixin, SkillFilesMixin, SkillTemplatesMixin):
    """Manages skill storage in SQLite.

    Provides CRUD operations for skills with support for:
    - Project-scoped uniqueness (UNIQUE(name, project_id, source))
    - Template/installed pattern (mirrors workflow_definitions)
    - Soft deletes
    - Category and tag filtering
    - Change notifications for search reindexing
    """

    def __init__(
        self,
        db: DatabaseProtocol,
        notifier: Any | None = None,  # SkillChangeNotifier, avoid circular import
    ):
        """Initialize the skill manager.

        Args:
            db: Database protocol implementation
            notifier: Optional change notifier for mutations
        """
        self.db = db
        self._notifier = notifier

    def _notify_change(
        self,
        event_type: str,
        skill_id: str,
        skill_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Fire a change event if a notifier is configured.

        Args:
            event_type: Type of change ('create', 'update', 'delete')
            skill_id: ID of the affected skill
            skill_name: Name of the affected skill
            metadata: Optional additional metadata
        """
        if self._notifier is not None:
            try:
                self._notifier.fire_change(
                    event_type=event_type,
                    skill_id=skill_id,
                    skill_name=skill_name,
                    metadata=metadata,
                )
            except Exception as e:
                logger.error(f"Error in skill change notifier: {e}")
