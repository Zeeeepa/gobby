"""
Child session management for subagent spawning.

This module provides utilities for creating and managing child sessions
that are spawned by agents. Child sessions are linked to their parent
sessions and track agent depth for safety limits.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.storage.sessions import LocalSessionManager, Session

logger = logging.getLogger(__name__)


@dataclass
class ChildSessionConfig:
    """Configuration for creating a child session."""

    parent_session_id: str
    """ID of the parent session spawning this child."""

    project_id: str
    """Project ID the session belongs to."""

    machine_id: str
    """Machine identifier."""

    source: str
    """CLI source (e.g., 'claude', 'gemini', 'codex')."""

    agent_id: str | None = None
    """ID of the agent that spawned this session."""

    workflow_name: str | None = None
    """Name of the workflow being executed."""

    title: str | None = None
    """Optional session title."""

    git_branch: str | None = None
    """Git branch for the session."""


class ChildSessionManager:
    """
    Manages child session creation and lifecycle.

    Child sessions are spawned by agents running in parent sessions.
    They track:
    - Parent-child relationships via parent_session_id
    - Agent depth (0 = human-initiated, 1+ = agent-spawned)
    - Which agent spawned them (for tracking and cleanup)

    Thread-safe: Uses the underlying LocalSessionManager's thread safety.
    """

    def __init__(
        self,
        session_storage: LocalSessionManager,
        max_agent_depth: int = 1,
    ) -> None:
        """
        Initialize ChildSessionManager.

        Args:
            session_storage: LocalSessionManager for SQLite operations.
            max_agent_depth: Maximum allowed nesting depth (default: 1).
                Depth 0 = human-initiated session.
                Depth 1 = agent can spawn, but child cannot spawn further.
        """
        self._storage = session_storage
        self.max_agent_depth = max_agent_depth
        self.logger = logger

    def get_session_depth(self, session_id: str) -> int:
        """
        Get the agent depth of a session.

        Depth is determined by counting parent links:
        - 0: No parent (human-initiated)
        - 1: Has parent that is depth 0
        - N: Has parent that is depth N-1

        Args:
            session_id: The session ID to check.

        Returns:
            Agent depth (0 for human sessions, 1+ for agent sessions).
        """
        depth = 0
        current_id = session_id

        while current_id:
            session = self._storage.get(current_id)
            if not session or not session.parent_session_id:
                break
            depth += 1
            current_id = session.parent_session_id

            # Safety limit to prevent infinite loops
            if depth > 10:
                self.logger.warning(f"Session depth exceeded safety limit for {session_id}")
                break

        return depth

    def can_spawn_child(self, parent_session_id: str) -> tuple[bool, str]:
        """
        Check if a session can spawn a child agent.

        Args:
            parent_session_id: The session attempting to spawn.

        Returns:
            Tuple of (can_spawn, reason).
        """
        parent = self._storage.get(parent_session_id)
        if not parent:
            return False, f"Parent session {parent_session_id} not found"

        current_depth = self.get_session_depth(parent_session_id)
        if current_depth >= self.max_agent_depth:
            return False, (
                f"Max agent depth ({self.max_agent_depth}) exceeded. "
                f"Current depth: {current_depth}"
            )

        return True, "OK"

    def create_child_session(
        self,
        config: ChildSessionConfig,
    ) -> Session:
        """
        Create a child session linked to a parent.

        Args:
            config: Configuration for the child session.

        Returns:
            The created child Session.

        Raises:
            ValueError: If max_agent_depth would be exceeded.
        """
        # Check depth limit
        can_spawn, reason = self.can_spawn_child(config.parent_session_id)
        if not can_spawn:
            raise ValueError(reason)

        # Calculate child's agent depth (parent depth + 1)
        parent_depth = self.get_session_depth(config.parent_session_id)
        child_depth = parent_depth + 1

        # Generate a unique external_id for the child
        external_id = f"agent-{uuid.uuid4().hex[:12]}"

        # Create title if not provided
        title = config.title
        if not title:
            if config.workflow_name:
                title = f"Agent: {config.workflow_name}"
            else:
                title = "Agent session"

        # Register the child session
        child = self._storage.register(
            external_id=external_id,
            machine_id=config.machine_id,
            source=config.source,
            project_id=config.project_id,
            title=title,
            git_branch=config.git_branch,
            parent_session_id=config.parent_session_id,
            agent_depth=child_depth,
            spawned_by_agent_id=config.agent_id,
        )

        self.logger.info(
            f"Created child session {child.id} "
            f"(parent={config.parent_session_id}, agent={config.agent_id})"
        )

        return child

    def get_child_sessions(self, parent_session_id: str) -> list[Session]:
        """
        Get all child sessions of a parent.

        Args:
            parent_session_id: The parent session ID.

        Returns:
            List of child Session objects.
        """
        return self._storage.find_children(parent_session_id)

    def get_session_lineage(self, session_id: str) -> list[Session]:
        """
        Get the full lineage of a session (from root to current).

        Args:
            session_id: The session to trace.

        Returns:
            List of sessions from root (human-initiated) to current.
        """
        lineage: list[Session] = []
        current_id: str | None = session_id

        while current_id:
            session = self._storage.get(current_id)
            if not session:
                break
            lineage.append(session)
            current_id = session.parent_session_id

            # Safety limit
            if len(lineage) > 10:
                self.logger.warning(f"Lineage exceeded safety limit for {session_id}")
                break

        # Reverse to get root-to-current order
        lineage.reverse()
        return lineage
