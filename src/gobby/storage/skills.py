"""Skill storage and management.

This module provides the Skill dataclass and LocalSkillManager for storing
and retrieving skills from SQLite, following the Agent Skills specification
(agentskills.io) with SkillPort feature parity plus Gobby-specific extensions.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from gobby.storage.database import DatabaseProtocol
from gobby.utils.id import generate_prefixed_id

__all__ = ["ChangeEvent", "Skill", "SkillChangeNotifier", "LocalSkillManager"]

logger = logging.getLogger(__name__)

# Sentinel for distinguishing "not provided" from explicit None
_UNSET: Any = object()

# Valid source types for skills
SkillSourceType = Literal["local", "github", "url", "zip", "filesystem"]


@dataclass
class Skill:
    """A skill following the Agent Skills specification.

    Skills provide structured instructions for AI agents to follow when
    performing specific tasks. The format follows the Agent Skills spec
    (agentskills.io) with additional Gobby-specific extensions.

    Required fields per spec:
        - id: Unique identifier (prefixed with 'skl-')
        - name: Skill name (max 64 chars, lowercase+hyphens)
        - description: What the skill does (max 1024 chars)
        - content: The markdown body with instructions

    Optional spec fields:
        - version: Semantic version string
        - license: License identifier (e.g., "MIT")
        - compatibility: Compatibility notes (max 500 chars)
        - allowed_tools: List of allowed tool patterns
        - metadata: Free-form extension data (includes skillport/gobby namespaces)

    Source tracking:
        - source_path: Original file path or URL
        - source_type: 'local', 'github', 'url', 'zip', 'filesystem'
        - source_ref: Git ref for updates (branch/tag/commit)

    Hub Tracking:
        - hub_name: Name of the hub the skill originated from
        - hub_slug: Slug of the hub the skill originated from
        - hub_version: Version of the skill as reported by the hub

    Gobby-specific:
        - enabled: Toggle skill on/off without removing
        - project_id: NULL for global, else project-scoped

    Timestamps:
        - created_at: ISO format creation timestamp
        - updated_at: ISO format last update timestamp
    """

    # Identity
    id: str
    name: str

    # Agent Skills Spec Fields
    description: str
    content: str
    version: str | None = None
    license: str | None = None
    compatibility: str | None = None
    allowed_tools: list[str] | None = None
    metadata: dict[str, Any] | None = None

    # Source Tracking
    source_path: str | None = None
    source_type: SkillSourceType | None = None
    source_ref: str | None = None

    # Hub Tracking
    hub_name: str | None = None
    hub_slug: str | None = None
    hub_version: str | None = None

    # Gobby-specific
    enabled: bool = True
    always_apply: bool = False
    injection_format: str = "summary"  # "summary", "full", "content"
    project_id: str | None = None

    # Timestamps
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Skill":
        """Create a Skill from a database row.

        Args:
            row: SQLite row with skill data

        Returns:
            Skill instance populated from the row
        """
        # Parse JSON fields
        allowed_tools_json = row["allowed_tools"]
        allowed_tools = json.loads(allowed_tools_json) if allowed_tools_json else None

        metadata_json = row["metadata"]
        metadata = json.loads(metadata_json) if metadata_json else None

        return cls(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            content=row["content"],
            version=row["version"],
            license=row["license"],
            compatibility=row["compatibility"],
            allowed_tools=allowed_tools,
            metadata=metadata,
            source_path=row["source_path"],
            source_type=row["source_type"],
            source_ref=row["source_ref"],
            hub_name=row["hub_name"] if "hub_name" in row.keys() else None,
            hub_slug=row["hub_slug"] if "hub_slug" in row.keys() else None,
            hub_version=row["hub_version"] if "hub_version" in row.keys() else None,
            enabled=bool(row["enabled"]),
            always_apply=bool(row["always_apply"]) if "always_apply" in row.keys() else False,
            injection_format=row["injection_format"]
            if "injection_format" in row.keys()
            else "summary",
            project_id=row["project_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert skill to a dictionary representation.

        Returns:
            Dictionary with all skill fields
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "version": self.version,
            "license": self.license,
            "compatibility": self.compatibility,
            "allowed_tools": self.allowed_tools,
            "metadata": self.metadata,
            "source_path": self.source_path,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "hub_name": self.hub_name,
            "hub_slug": self.hub_slug,
            "hub_version": self.hub_version,
            "enabled": self.enabled,
            "always_apply": self.always_apply,
            "injection_format": self.injection_format,
            "project_id": self.project_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def get_category(self) -> str | None:
        """Get the skill category from top-level or metadata.skillport.category.

        Supports both top-level category and nested metadata.skillport.category.
        Top-level takes precedence.
        """
        if not self.metadata:
            return None
        # Check top-level first
        result = self.metadata.get("category")
        if result is not None:
            return str(result)
        # Fall back to nested skillport.category
        skillport = self.metadata.get("skillport", {})
        result = skillport.get("category")
        return str(result) if result is not None else None

    def get_tags(self) -> list[str]:
        """Get the skill tags from metadata.skillport.tags."""
        if not self.metadata:
            return []
        skillport = self.metadata.get("skillport", {})
        tags = skillport.get("tags", [])
        return list(tags) if isinstance(tags, list) else []

    def is_always_apply(self) -> bool:
        """Check if this is a core skill that should always be applied.

        Reads from the always_apply column first (set during sync from frontmatter).
        Falls back to metadata for backwards compatibility with older records.
        """
        # Primary: read from column (set during sync)
        if self.always_apply:
            return True
        # Fallback: check metadata for backwards compatibility
        if not self.metadata:
            return False
        # Check top-level first
        top_level = self.metadata.get("alwaysApply")
        if top_level is not None:
            return bool(top_level)
        # Fall back to nested skillport.alwaysApply
        skillport = self.metadata.get("skillport", {})
        return bool(skillport.get("alwaysApply", False))


# Change event types
ChangeEventType = Literal["create", "update", "delete"]


@dataclass
class ChangeEvent:
    """A change event fired when a skill is created, updated, or deleted.

    This event is passed to registered listeners when mutations occur,
    allowing components like search indexes to stay synchronized.

    Attributes:
        event_type: Type of change ('create', 'update', 'delete')
        skill_id: ID of the affected skill
        skill_name: Name of the affected skill (for logging/indexing)
        timestamp: ISO format timestamp of the event
        metadata: Optional additional context about the change
    """

    event_type: ChangeEventType
    skill_id: str
    skill_name: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary representation."""
        return {
            "event_type": self.event_type,
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


# Type alias for change listeners
ChangeListener = Any  # Callable[[ChangeEvent], None], but avoiding import issues


class SkillChangeNotifier:
    """Notifies registered listeners when skills are mutated.

    This implements the observer pattern to allow components like
    search indexes to stay synchronized with skill changes.

    Listeners are wrapped in try/except to prevent one failing listener
    from blocking others or the main mutation.

    Example usage:
        ```python
        notifier = SkillChangeNotifier()

        def on_skill_change(event: ChangeEvent):
            print(f"Skill {event.skill_name} was {event.event_type}d")

        notifier.add_listener(on_skill_change)

        manager = LocalSkillManager(db, notifier=notifier)
        manager.create_skill(...)  # Triggers the listener
        ```
    """

    def __init__(self) -> None:
        """Initialize the notifier with an empty listener list."""
        self._listeners: list[ChangeListener] = []

    def add_listener(self, listener: ChangeListener) -> None:
        """Register a listener to receive change events.

        Args:
            listener: Callable that accepts a ChangeEvent
        """
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: ChangeListener) -> bool:
        """Unregister a listener.

        Args:
            listener: The listener to remove

        Returns:
            True if removed, False if not found
        """
        try:
            self._listeners.remove(listener)
            return True
        except ValueError:
            return False

    def fire_change(
        self,
        event_type: ChangeEventType,
        skill_id: str,
        skill_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Fire a change event to all registered listeners.

        Each listener is called in a try/except block to prevent
        one failing listener from blocking others.

        Args:
            event_type: Type of change ('create', 'update', 'delete')
            skill_id: ID of the affected skill
            skill_name: Name of the affected skill
            metadata: Optional additional context
        """
        event = ChangeEvent(
            event_type=event_type,
            skill_id=skill_id,
            skill_name=skill_name,
            metadata=metadata,
        )

        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(
                    f"Error in skill change listener {listener}: {e}",
                    exc_info=True,
                )

    def clear_listeners(self) -> None:
        """Remove all registered listeners."""
        self._listeners.clear()

    @property
    def listener_count(self) -> int:
        """Return the number of registered listeners."""
        return len(self._listeners)


class LocalSkillManager:
    """Manages skill storage in SQLite.

    Provides CRUD operations for skills with support for:
    - Project-scoped uniqueness (UNIQUE(name, project_id))
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
        hub_name: str | None = None,
        hub_slug: str | None = None,
        hub_version: str | None = None,
        enabled: bool = True,
        always_apply: bool = False,
        injection_format: str = "summary",
        project_id: str | None = None,
    ) -> Skill:
        """Create a new skill.

        Args:
            name: Skill name (max 64 chars, lowercase+hyphens)
            description: Skill description (max 1024 chars)
            content: Full markdown content
            version: Optional version string
            license: Optional license identifier
            compatibility: Optional compatibility notes (max 500 chars)
            allowed_tools: Optional list of allowed tool patterns
            metadata: Optional free-form metadata
            source_path: Original file path or URL
            source_type: Source type ('local', 'github', 'url', 'zip', 'filesystem')
            source_ref: Git ref for updates
            hub_name: Optional hub name
            hub_slug: Optional hub slug
            hub_version: Optional hub version
            enabled: Whether skill is active
            always_apply: Whether skill should always be injected at session start
            injection_format: How to inject skill (summary, full, content)
            project_id: Project scope (None for global)

        Returns:
            The created Skill

        Raises:
            ValueError: If a skill with the same name exists in the project scope
        """
        now = datetime.now(UTC).isoformat()
        skill_id = generate_prefixed_id("skl", f"{name}:{project_id or 'global'}")

        # Check if skill already exists in this project scope
        existing = self.get_by_name(name, project_id=project_id)
        if existing:
            raise ValueError(
                f"Skill '{name}' already exists"
                + (f" in project {project_id}" if project_id else " globally")
            )

        # Serialize JSON fields
        allowed_tools_json = json.dumps(allowed_tools) if allowed_tools else None
        metadata_json = json.dumps(metadata) if metadata else None

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO skills (
                    id, name, description, content, version, license,
                    compatibility, allowed_tools, metadata, source_path,
                    source_type, source_ref, hub_name, hub_slug, hub_version,
                    enabled, always_apply, injection_format, project_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    skill_id,
                    name,
                    description,
                    content,
                    version,
                    license,
                    compatibility,
                    allowed_tools_json,
                    metadata_json,
                    source_path,
                    source_type,
                    source_ref,
                    hub_name,
                    hub_slug,
                    hub_version,
                    enabled,
                    always_apply,
                    injection_format,
                    project_id,
                    now,
                    now,
                ),
            )

        skill = self.get_skill(skill_id)
        self._notify_change("create", skill_id, name)
        return skill

    def get_skill(self, skill_id: str) -> Skill:
        """Get a skill by ID.

        Args:
            skill_id: The skill ID

        Returns:
            The Skill

        Raises:
            ValueError: If skill not found
        """
        row = self.db.fetchone("SELECT * FROM skills WHERE id = ?", (skill_id,))
        if not row:
            raise ValueError(f"Skill {skill_id} not found")
        return Skill.from_row(row)

    def get_by_name(
        self,
        name: str,
        project_id: str | None = None,
        include_global: bool = True,
    ) -> Skill | None:
        """Get a skill by name within a project scope.

        Args:
            name: The skill name
            project_id: Project scope (None for global)
            include_global: Include global skills when project_id is set.
                           When True and project_id is set, first looks for
                           project-scoped skill, then falls back to global.

        Returns:
            The Skill if found, None otherwise
        """
        if project_id:
            # First try project-scoped skill
            row = self.db.fetchone(
                "SELECT * FROM skills WHERE name = ? AND project_id = ?",
                (name, project_id),
            )
            # If not found and include_global, try global
            if row is None and include_global:
                row = self.db.fetchone(
                    "SELECT * FROM skills WHERE name = ? AND project_id IS NULL",
                    (name,),
                )
        else:
            row = self.db.fetchone(
                "SELECT * FROM skills WHERE name = ? AND project_id IS NULL",
                (name,),
            )
        return Skill.from_row(row) if row else None

    def update_skill(
        self,
        skill_id: str,
        name: str | None = None,
        description: str | None = None,
        content: str | None = None,
        version: str | None = _UNSET,
        license: str | None = _UNSET,
        compatibility: str | None = _UNSET,
        allowed_tools: list[str] | None = _UNSET,
        metadata: dict[str, Any] | None = _UNSET,
        source_path: str | None = _UNSET,
        source_type: SkillSourceType | None = _UNSET,
        source_ref: str | None = _UNSET,
        hub_name: str | None = _UNSET,
        hub_slug: str | None = _UNSET,
        hub_version: str | None = _UNSET,
        enabled: bool | None = None,
        always_apply: bool | None = None,
        injection_format: str | None = None,
    ) -> Skill:
        """Update an existing skill.

        Args:
            skill_id: The skill ID to update
            name: New name (optional)
            description: New description (optional)
            content: New content (optional)
            version: New version (use _UNSET to leave unchanged, None to clear)
            license: New license (use _UNSET to leave unchanged, None to clear)
            compatibility: New compatibility (use _UNSET to leave unchanged, None to clear)
            allowed_tools: New allowed tools (use _UNSET to leave unchanged, None to clear)
            metadata: New metadata (use _UNSET to leave unchanged, None to clear)
            source_path: New source path (use _UNSET to leave unchanged, None to clear)
            source_type: New source type (use _UNSET to leave unchanged, None to clear)
            source_ref: New source ref (use _UNSET to leave unchanged, None to clear)
            hub_name: New hub name (use _UNSET to leave unchanged, None to clear)
            hub_slug: New hub slug (use _UNSET to leave unchanged, None to clear)
            hub_version: New hub version (use _UNSET to leave unchanged, None to clear)
            enabled: New enabled state (optional)
            always_apply: New always_apply state (optional)
            injection_format: New injection format (optional)

        Returns:
            The updated Skill

        Raises:
            ValueError: If skill not found
        """
        updates = []
        params: list[Any] = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if version is not _UNSET:
            updates.append("version = ?")
            params.append(version)
        if license is not _UNSET:
            updates.append("license = ?")
            params.append(license)
        if compatibility is not _UNSET:
            updates.append("compatibility = ?")
            params.append(compatibility)
        if allowed_tools is not _UNSET:
            updates.append("allowed_tools = ?")
            params.append(json.dumps(allowed_tools) if allowed_tools else None)
        if metadata is not _UNSET:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata) if metadata else None)
        if source_path is not _UNSET:
            updates.append("source_path = ?")
            params.append(source_path)
        if source_type is not _UNSET:
            updates.append("source_type = ?")
            params.append(source_type)
        if source_ref is not _UNSET:
            updates.append("source_ref = ?")
            params.append(source_ref)
        if hub_name is not _UNSET:
            updates.append("hub_name = ?")
            params.append(hub_name)
        if hub_slug is not _UNSET:
            updates.append("hub_slug = ?")
            params.append(hub_slug)
        if hub_version is not _UNSET:
            updates.append("hub_version = ?")
            params.append(hub_version)
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(enabled)
        if always_apply is not None:
            updates.append("always_apply = ?")
            params.append(always_apply)
        if injection_format is not None:
            updates.append("injection_format = ?")
            params.append(injection_format)

        if not updates:
            return self.get_skill(skill_id)

        updates.append("updated_at = ?")
        params.append(datetime.now(UTC).isoformat())
        params.append(skill_id)

        # nosec B608: SET clause built from hardcoded column names, values parameterized
        sql = f"UPDATE skills SET {', '.join(updates)} WHERE id = ?"  # nosec B608

        with self.db.transaction() as conn:
            cursor = conn.execute(sql, tuple(params))
            if cursor.rowcount == 0:
                raise ValueError(f"Skill {skill_id} not found")

        skill = self.get_skill(skill_id)
        self._notify_change("update", skill_id, skill.name)
        return skill

    def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill by ID.

        Args:
            skill_id: The skill ID to delete

        Returns:
            True if deleted, False if not found
        """
        # Get skill name before deletion for notification
        try:
            skill = self.get_skill(skill_id)
            skill_name = skill.name
        except ValueError:
            return False

        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
            if cursor.rowcount == 0:
                return False

        self._notify_change("delete", skill_id, skill_name)
        return True

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
            project_id: Filter by project (None for global only)
            enabled: Filter by enabled state
            category: Filter by category (from metadata.skillport.category)
            limit: Maximum number of results
            offset: Number of results to skip
            include_global: Include global skills when project_id is set

        Returns:
            List of matching Skills
        """
        query = "SELECT * FROM skills WHERE 1=1"
        params: list[Any] = []

        if project_id:
            if include_global:
                query += " AND (project_id = ? OR project_id IS NULL)"
                params.append(project_id)
            else:
                query += " AND project_id = ?"
                params.append(project_id)
        else:
            query += " AND project_id IS NULL"

        if enabled is not None:
            query += " AND enabled = ?"
            params.append(enabled)

        # Filter by category using JSON extraction in SQL to avoid under-filled results
        # Check both top-level $.category and nested $.skillport.category
        if category:
            query += """ AND (
                json_extract(metadata, '$.category') = ?
                OR json_extract(metadata, '$.skillport.category') = ?
            )"""
            params.extend([category, category])

        query += " ORDER BY name ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.db.fetchall(query, tuple(params))
        return [Skill.from_row(row) for row in rows]

    def search_skills(
        self,
        query_text: str,
        project_id: str | None = None,
        limit: int = 20,
    ) -> list[Skill]:
        """Search skills by name and description.

        This is a simple text search. For advanced search with TF-IDF
        and embeddings, use SkillSearch from the skills module.

        Args:
            query_text: Text to search for
            project_id: Optional project scope
            limit: Maximum number of results

        Returns:
            List of matching Skills
        """
        # Escape LIKE wildcards
        escaped_query = query_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        sql = """
            SELECT * FROM skills
            WHERE (name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')
        """
        params: list[Any] = [f"%{escaped_query}%", f"%{escaped_query}%"]

        if project_id:
            sql += " AND (project_id = ? OR project_id IS NULL)"
            params.append(project_id)

        sql += " ORDER BY name ASC LIMIT ?"
        params.append(limit)

        rows = self.db.fetchall(sql, tuple(params))
        return [Skill.from_row(row) for row in rows]

    def list_core_skills(self, project_id: str | None = None) -> list[Skill]:
        """List skills with always_apply=true (efficiently via column query).

        Args:
            project_id: Optional project scope

        Returns:
            List of core skills (always-apply skills)
        """
        query = "SELECT * FROM skills WHERE always_apply = 1 AND enabled = 1"
        params: list[Any] = []

        if project_id:
            query += " AND (project_id = ? OR project_id IS NULL)"
            params.append(project_id)
        else:
            query += " AND project_id IS NULL"

        query += " ORDER BY name ASC"

        rows = self.db.fetchall(query, tuple(params))
        return [Skill.from_row(row) for row in rows]

    def skill_exists(self, skill_id: str) -> bool:
        """Check if a skill with the given ID exists.

        Args:
            skill_id: The skill ID to check

        Returns:
            True if exists, False otherwise
        """
        row = self.db.fetchone("SELECT 1 FROM skills WHERE id = ?", (skill_id,))
        return row is not None

    def count_skills(
        self,
        project_id: str | None = None,
        enabled: bool | None = None,
    ) -> int:
        """Count skills matching criteria.

        Args:
            project_id: Filter by project
            enabled: Filter by enabled state

        Returns:
            Number of matching skills
        """
        query = "SELECT COUNT(*) as count FROM skills WHERE 1=1"
        params: list[Any] = []

        if project_id:
            query += " AND (project_id = ? OR project_id IS NULL)"
            params.append(project_id)

        if enabled is not None:
            query += " AND enabled = ?"
            params.append(enabled)

        row = self.db.fetchone(query, tuple(params))
        return row["count"] if row else 0
