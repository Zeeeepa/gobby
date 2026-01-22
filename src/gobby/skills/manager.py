"""SkillManager - Coordinator for skill storage and search.

This module provides the SkillManager class which coordinates:
- Storage operations (LocalSkillManager)
- Search functionality (SkillSearch)
- Change notifications for automatic reindexing
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from gobby.skills.search import SearchFilters, SkillSearch, SkillSearchResult
from gobby.storage.skills import (
    ChangeEvent,
    LocalSkillManager,
    Skill,
    SkillChangeNotifier,
    SkillSourceType,
)

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol

logger = logging.getLogger(__name__)


class SkillManager:
    """Coordinates skill storage and search operations.

    This class provides a unified interface for skill management,
    wiring together:
    - LocalSkillManager for persistent storage
    - SkillSearch for TF-IDF based search
    - SkillChangeNotifier for automatic reindex tracking

    Example usage:
        ```python
        from gobby.skills.manager import SkillManager
        from gobby.storage.database import LocalDatabase

        db = LocalDatabase("gobby-hub.db")
        manager = SkillManager(db)

        # Create a skill
        skill = manager.create_skill(
            name="commit-message",
            description="Generate commit messages",
            content="# Instructions...",
        )

        # Search for skills
        manager.reindex()
        results = manager.search("git commit")
        ```
    """

    def __init__(
        self,
        db: DatabaseProtocol,
        project_id: str | None = None,
    ):
        """Initialize the skill manager.

        Args:
            db: Database connection for storage
            project_id: Optional default project scope
        """
        self._project_id = project_id

        # Set up change notifier
        self._notifier = SkillChangeNotifier()
        self._notifier.add_listener(self._on_skill_change)

        # Initialize storage with notifier
        self._storage = LocalSkillManager(db, notifier=self._notifier)

        # Initialize search
        self._search = SkillSearch()

    @property
    def storage(self) -> LocalSkillManager:
        """Get the storage manager."""
        return self._storage

    @property
    def search(self) -> SkillSearch:
        """Get the search instance."""
        return self._search

    def _on_skill_change(self, event: ChangeEvent) -> None:
        """Handle skill change events for search tracking.

        Args:
            event: The change event
        """
        if event.event_type == "create":
            # Get the full skill for search
            try:
                skill = self._storage.get_skill(event.skill_id)
                try:
                    self._search.add_skill(skill)
                except Exception as e:
                    logger.error(
                        f"Failed to add skill to search index "
                        f"(event={event.event_type}, skill_id={event.skill_id}): {e}"
                    )
            except ValueError as e:
                logger.debug(
                    f"Failed to get skill for {event.event_type} event "
                    f"(skill_id={event.skill_id}): {e}"
                )
        elif event.event_type == "update":
            try:
                skill = self._storage.get_skill(event.skill_id)
                try:
                    self._search.update_skill(skill)
                except Exception as e:
                    logger.error(
                        f"Failed to update skill in search index "
                        f"(event={event.event_type}, skill_id={event.skill_id}): {e}"
                    )
            except ValueError as e:
                logger.debug(
                    f"Failed to get skill for {event.event_type} event "
                    f"(skill_id={event.skill_id}): {e}"
                )
        elif event.event_type == "delete":
            try:
                self._search.remove_skill(event.skill_id)
            except Exception as e:
                logger.error(
                    f"Failed to remove skill from search index "
                    f"(event={event.event_type}, skill_id={event.skill_id}): {e}"
                )

    # --- CRUD Operations ---

    def create_skill(
        self,
        name: str,
        description: str,
        content: str,
        version: str | None = None,
        license: str | None = None,
        compatibility: str | None = None,
        allowed_tools: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        source_path: str | None = None,
        source_type: SkillSourceType | None = None,
        source_ref: str | None = None,
        enabled: bool = True,
        project_id: str | None = None,
    ) -> Skill:
        """Create a new skill.

        Args:
            name: Skill name
            description: Skill description
            content: Markdown content
            version: Optional version string
            license: Optional license identifier
            compatibility: Optional compatibility notes
            allowed_tools: Optional allowed tool patterns
            metadata: Optional metadata (includes skillport/gobby namespaces)
            source_path: Original source path
            source_type: Source type
            source_ref: Git ref for updates
            enabled: Whether skill is active
            project_id: Project scope (uses default if not specified)

        Returns:
            The created Skill
        """
        return self._storage.create_skill(
            name=name,
            description=description,
            content=content,
            version=version,
            license=license,
            compatibility=compatibility,
            allowed_tools=allowed_tools,
            metadata=metadata,
            source_path=source_path,
            source_type=source_type,
            source_ref=source_ref,
            enabled=enabled,
            project_id=project_id or self._project_id,
        )

    def get_skill(self, skill_id: str) -> Skill:
        """Get a skill by ID.

        Args:
            skill_id: The skill ID

        Returns:
            The Skill

        Raises:
            ValueError: If not found
        """
        return self._storage.get_skill(skill_id)

    def get_by_name(
        self,
        name: str,
        project_id: str | None = None,
    ) -> Skill | None:
        """Get a skill by name.

        Args:
            name: Skill name
            project_id: Project scope (uses default if not specified)

        Returns:
            The Skill if found, None otherwise
        """
        return self._storage.get_by_name(
            name,
            project_id=project_id or self._project_id,
        )

    def update_skill(
        self,
        skill_id: str,
        name: str | None = None,
        description: str | None = None,
        content: str | None = None,
        **kwargs: Any,
    ) -> Skill:
        """Update a skill.

        Args:
            skill_id: ID of the skill to update
            name: New name (optional)
            description: New description (optional)
            content: New content (optional)
            **kwargs: Additional fields to update

        Returns:
            The updated Skill
        """
        return self._storage.update_skill(
            skill_id=skill_id,
            name=name,
            description=description,
            content=content,
            **kwargs,
        )

    def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill.

        Args:
            skill_id: ID of the skill to delete

        Returns:
            True if deleted, False if not found
        """
        return self._storage.delete_skill(skill_id)

    def list_skills(
        self,
        project_id: str | None = None,
        enabled: bool | None = None,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_global: bool = True,
    ) -> list[Skill]:
        """List skills with optional filtering.

        Args:
            project_id: Filter by project (uses default if not specified)
            enabled: Filter by enabled state
            category: Filter by category
            limit: Maximum results
            offset: Results to skip
            include_global: Include global skills

        Returns:
            List of matching Skills
        """
        return self._storage.list_skills(
            project_id=project_id or self._project_id,
            enabled=enabled,
            category=category,
            limit=limit,
            offset=offset,
            include_global=include_global,
        )

    # --- Search Operations ---

    def search_skills(
        self,
        query: str,
        top_k: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[SkillSearchResult]:
        """Search for skills.

        Args:
            query: Search query
            top_k: Maximum results
            filters: Optional filters

        Returns:
            List of search results
        """
        return self._search.search(query, top_k=top_k, filters=filters)

    def reindex(self, batch_size: int = 1000) -> None:
        """Rebuild the search index from storage.

        Args:
            batch_size: Number of skills to fetch per batch (default: 1000)
        """
        all_skills: list[Skill] = []
        offset = 0

        # Paginate through all skills to avoid truncation
        while True:
            batch = self._storage.list_skills(
                project_id=self._project_id,
                include_global=True,
                limit=batch_size,
                offset=offset,
            )
            if not batch:
                break
            all_skills.extend(batch)
            if len(batch) < batch_size:
                # Last batch, no more results
                break
            offset += batch_size

        self._search.index_skills(all_skills)

    def needs_reindex(self) -> bool:
        """Check if search index needs rebuilding.

        Returns:
            True if reindex() should be called
        """
        return self._search.needs_reindex()

    # --- Core Skills ---

    def list_core_skills(self, project_id: str | None = None) -> list[Skill]:
        """List skills with alwaysApply=true.

        Core skills are automatically included in agent prompts.

        Args:
            project_id: Project scope (uses default if not specified)

        Returns:
            List of core skills
        """
        return self._storage.list_core_skills(project_id=project_id or self._project_id)

    # --- Utility ---

    def count_skills(
        self,
        project_id: str | None = None,
        enabled: bool | None = None,
    ) -> int:
        """Count skills matching criteria.

        Args:
            project_id: Project scope
            enabled: Filter by enabled state

        Returns:
            Number of matching skills
        """
        return self._storage.count_skills(
            project_id=project_id or self._project_id,
            enabled=enabled,
        )
