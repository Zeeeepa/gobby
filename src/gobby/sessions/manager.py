"""
Session Manager for multi-CLI session management (local-first).

Handles:
- Session registration with local SQLite storage
- Parent session lookup for context handoff
- Session status updates (active, expired, handoff_ready)
- Summary file reading (fallback when database is unavailable)

This module is CLI-agnostic and can be used by any CLI integration.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.config.app import DaemonConfig
    from gobby.storage.artifacts import Artifact
    from gobby.storage.sessions import LocalSessionManager as SessionStorage

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages session lifecycle for AI coding assistants (local-first).

    Provides:
    - Session registration and lookup
    - Parent session discovery for context handoff
    - Status management (active, expired, handoff_ready)
    - Summary file reading (failover for database)

    Thread-safe: Uses locks for session metadata and mapping caches.

    Design Note:
        `source` is a REQUIRED parameter on all session methods, not stored as instance variable.
        Each adapter (Claude, Gemini, Codex) passes its source explicitly.
    """

    def __init__(
        self,
        session_storage: SessionStorage,
        logger_instance: logging.Logger | None = None,
        config: DaemonConfig | None = None,
    ) -> None:
        """
        Initialize SessionManager.

        Args:
            session_storage: LocalSessionManager for SQLite operations
            logger_instance: Optional logger instance
            config: Optional DaemonConfig for summary file path
        """
        self._storage = session_storage
        self.logger = logger_instance or logger
        self._config = config

        # Session caches with locks
        # Key is (external_id, source) tuple to prevent cross-CLI collisions
        self._session_mapping: dict[
            tuple[str, str], str
        ] = {}  # (external_id, source) -> session_id
        self._session_mapping_lock = threading.Lock()
        self._session_metadata: dict[str, dict[str, Any]] = {}  # session_id -> metadata
        self._session_metadata_lock = threading.Lock()

    def register_session(
        self,
        external_id: str,
        machine_id: str,
        source: str,
        project_id: str,
        parent_session_id: str | None = None,
        jsonl_path: str | None = None,
        title: str | None = None,
        git_branch: str | None = None,
        project_path: str | None = None,
        terminal_context: dict[str, Any] | None = None,
        workflow_name: str | None = None,
        agent_depth: int = 0,
    ) -> str:
        """
        Register new session with local storage.

        Args:
            external_id: External session identifier (e.g., Claude Code session ID)
            machine_id: Machine identifier
            source: CLI source identifier (e.g., "claude", "gemini", "codex") - REQUIRED
            project_id: Project ID (required - sessions must belong to a project)
            parent_session_id: Optional parent session ID for handoff
            jsonl_path: Optional path to session transcript JSONL file
            title: Optional session title/summary
            git_branch: Optional git branch name
            project_path: Optional project path (for git extraction if git_branch not provided)
            terminal_context: Optional terminal context for correlation
            workflow_name: Optional workflow to auto-activate for this session
            agent_depth: Depth in agent hierarchy (0 = root session)

        Returns:
            session_id (database UUID)
        """
        working_dir = project_path or str(Path.cwd())

        # Extract git_branch from project_path if not provided
        if not git_branch:
            try:
                from gobby.utils.git import get_git_branch

                git_branch = get_git_branch(working_dir)
                if git_branch:
                    self.logger.debug(f"Extracted git_branch from project_path: {git_branch}")
            except Exception as e:
                self.logger.debug(f"Could not extract git_branch: {e}")

        try:
            # Register with local storage
            session = self._storage.register(
                external_id=external_id,
                machine_id=machine_id,
                source=source,
                project_id=project_id,
                title=title,
                jsonl_path=jsonl_path,
                git_branch=git_branch,
                parent_session_id=parent_session_id,
                terminal_context=terminal_context,
                workflow_name=workflow_name,
                agent_depth=agent_depth,
            )

            session_id: str = session.id

            # Cache session mapping and metadata
            with self._session_mapping_lock:
                self._session_mapping[(external_id, source)] = session_id

            with self._session_metadata_lock:
                self._session_metadata[session_id] = {
                    "external_id": external_id,
                    "machine_id": machine_id,
                    "source": source,
                    "parent_session_id": parent_session_id,
                    "jsonl_path": jsonl_path,
                    "project_id": project_id,
                    "title": title,
                    "git_branch": git_branch,
                    "workflow_name": workflow_name,
                    "agent_depth": agent_depth,
                }

            self.logger.debug(f"Registered session {session_id} (external_id={external_id})")
            return session_id

        except Exception as e:
            self.logger.error(f"Failed to register session: {e}", exc_info=True)
            # Return a temporary session ID to allow hooks to continue
            import uuid

            return str(uuid.uuid4())

    def find_parent_session(
        self,
        machine_id: str,
        source: str,
        project_id: str,
        max_attempts: int = 30,
    ) -> tuple[str, str | None] | None:
        """
        Find parent session marked as 'handoff_ready' for this machine and project.

        Polls for up to max_attempts seconds waiting for the session-end hook
        to mark the previous session as handoff_ready.

        Args:
            machine_id: Machine identifier
            source: CLI source identifier (e.g., "claude", "gemini", "codex") - REQUIRED
            project_id: Project ID (required for matching)
            max_attempts: Maximum polling attempts (1 per second)

        Returns:
            Tuple of (parent_session_id, summary_markdown) or None if not found
        """
        attempt = 0

        while attempt < max_attempts:
            try:
                # Find parent using local storage
                session = self._storage.find_parent(
                    machine_id=machine_id,
                    source=source,
                    project_id=project_id,
                )

                if session:
                    self.logger.debug(
                        f"Found parent session {session.id} (attempt {attempt + 1}/{max_attempts})"
                    )
                    return (session.id, session.summary_markdown)

                # Not found yet, wait and retry
                attempt += 1
                if attempt < max_attempts:
                    self.logger.debug(
                        f"No handoff_ready session yet, retrying in 1s (attempt {attempt}/{max_attempts})"
                    )
                    time.sleep(1)

            except Exception as e:
                self.logger.warning(
                    f"Error polling for parent session (attempt {attempt + 1}): {e}"
                )
                attempt += 1
                if attempt < max_attempts:
                    time.sleep(1)
                else:
                    self.logger.error(f"Exhausted retries finding parent session: {e}")
                    return None

        # Exhausted retries
        self.logger.debug(f"No handoff_ready session found after {max_attempts} attempts")
        return None

    def mark_session_expired(self, session_id: str) -> bool:
        """
        Mark a session as 'expired' after successful handoff.

        Args:
            session_id: Session ID to mark as expired

        Returns:
            True if updated successfully, False otherwise
        """
        return self.update_session_status(session_id, "expired")

    def update_session_status(
        self,
        session_id: str,
        status: str,
    ) -> bool:
        """
        Update session status in database.

        Args:
            session_id: Internal database UUID (sessions.id)
            status: New status value (active, paused, expired, archived, handoff_ready)

        Returns:
            True if updated successfully, False otherwise
        """
        try:
            session = self._storage.update_status(session_id, status)
            if session:
                self.logger.debug(f"Session status updated: {session_id} -> {status}")
                return True
            else:
                self.logger.warning(f"Session not found for status update: {session_id}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to update session status: {e}", exc_info=True)
            return False

    def lookup_session_id(
        self, external_id: str, source: str, machine_id: str, project_id: str
    ) -> str | None:
        """
        Look up session_id from database by full composite key.

        Args:
            external_id: External session identifier
            source: CLI source identifier (e.g., "claude", "gemini", "codex")
            machine_id: Machine identifier
            project_id: Project identifier

        Returns:
            session_id (database PK) or None if not found
        """
        try:
            # Check cache first (keyed by (external_id, source) to prevent cross-CLI collisions)
            cache_key = (external_id, source)
            with self._session_mapping_lock:
                if cache_key in self._session_mapping:
                    return self._session_mapping[cache_key]

            # Find session using full composite key (safe lookup)
            session = self._storage.find_by_external_id(external_id, machine_id, project_id, source)

            if session:
                session_id: str = session.id
                self.logger.debug(
                    f"Looked up session_id {session_id} for external_id {external_id}"
                )
                # Cache it
                with self._session_mapping_lock:
                    self._session_mapping[cache_key] = session_id
                return session_id

            return None

        except Exception as e:
            self.logger.debug(f"Failed to lookup session_id from database: {e}", exc_info=True)
            return None

    def read_summary_file(self, session_id: str) -> str | None:
        """
        Read session summary from file (failover if database is empty).

        Searches for file matching pattern: session_*_{session_id}.md

        Args:
            session_id: Session ID to read summary for

        Returns:
            Summary markdown or None if not found
        """
        # Get summary directory from config or use default
        if self._config and self._config.session_summary:
            summary_dir = Path(self._config.session_summary.summary_file_path).expanduser()
        else:
            summary_dir = Path.home() / ".gobby" / "session_summaries"

        # Search for files matching session_*_{session_id}.md pattern
        if summary_dir.exists():
            for summary_file in summary_dir.glob(f"session_*_{session_id}.md"):
                try:
                    return summary_file.read_text()
                except Exception as e:
                    self.logger.error(
                        f"Failed to read summary file {summary_file}: {e}", exc_info=True
                    )

        return None

    def get_session_id(self, external_id: str, source: str) -> str | None:
        """
        Get cached session_id for an external_id and source.

        Args:
            external_id: External session identifier
            source: CLI source identifier (e.g., "claude", "gemini", "codex")

        Returns:
            session_id or None if not cached
        """
        with self._session_mapping_lock:
            return self._session_mapping.get((external_id, source))

    def cache_session_mapping(self, external_id: str, source: str, session_id: str) -> None:
        """
        Cache an (external_id, source) -> session_id mapping.

        Args:
            external_id: External session identifier
            source: CLI source identifier (e.g., "claude", "gemini", "codex")
            session_id: Database session ID
        """
        with self._session_mapping_lock:
            self._session_mapping[(external_id, source)] = session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """
        Get session data by ID.

        Args:
            session_id: Database session ID

        Returns:
            Session dict or None if not found
        """
        session = self._storage.get(session_id)
        if session:
            return {
                "id": session.id,
                "external_id": session.external_id,
                "machine_id": session.machine_id,
                "source": session.source,
                "project_id": session.project_id,
                "title": session.title,
                "status": session.status,
                "jsonl_path": session.jsonl_path,
                "summary_path": session.summary_path,
                "git_branch": session.git_branch,
                "parent_session_id": session.parent_session_id,
            }
        return None

    def get_session_artifacts(
        self,
        session_id: str,
        artifact_type: str | None = None,
        limit: int | None = None,
        include_parent: bool | None = None,
        max_lineage_depth: int | None = None,
    ) -> list[Artifact]:
        """
        Get artifacts for a session using LocalArtifactManager.

        Args:
            session_id: Session ID to get artifacts for
            artifact_type: Optional filter by artifact type
            limit: Maximum number of artifacts to return (default from config)
            include_parent: Whether to include parent session artifacts (default from config)
            max_lineage_depth: Maximum depth to traverse session lineage (default from config)

        Returns:
            List of Artifact objects
        """
        from gobby.storage.artifacts import LocalArtifactManager

        # Get defaults from config
        config = self._config.artifact_handoff if self._config else None
        if limit is None:
            limit = config.max_artifacts_in_handoff if config else 10
        if include_parent is None:
            include_parent = config.include_parent_artifacts if config else True
        if max_lineage_depth is None:
            max_lineage_depth = config.max_lineage_depth if config else 3

        # Get artifact manager using storage's database
        artifact_manager = LocalArtifactManager(self._storage.db)

        all_artifacts = []

        # Get artifacts for this session
        artifacts = artifact_manager.list_artifacts(
            session_id=session_id,
            artifact_type=artifact_type,
            limit=limit,
        )
        all_artifacts.extend(artifacts)

        # If include_parent, traverse full session lineage up to max_lineage_depth
        if include_parent:
            current_session = self._storage.get(session_id)
            depth = 0

            while (
                current_session and current_session.parent_session_id and depth < max_lineage_depth
            ):
                parent_id = current_session.parent_session_id
                parent_artifacts = artifact_manager.list_artifacts(
                    session_id=parent_id,
                    artifact_type=artifact_type,
                    limit=limit,
                )
                all_artifacts.extend(parent_artifacts)

                # Move up the lineage chain
                current_session = self._storage.get(parent_id)
                depth += 1

        # Sort by created_at (newest first) and apply limit
        all_artifacts.sort(key=lambda a: a.created_at, reverse=True)
        return all_artifacts[:limit]

    def generate_handoff_context(
        self,
        session_id: str,
        max_artifacts: int | None = None,
        max_context_size: int | None = None,
        include_parent_artifacts: bool | None = None,
    ) -> str:
        """
        Generate handoff context including artifacts for a session.

        Args:
            session_id: Session ID to generate context for
            max_artifacts: Maximum number of artifacts to include (default from config)
            max_context_size: Maximum context size in characters (default from config)
            include_parent_artifacts: Whether to include parent session artifacts (default from config)

        Returns:
            Formatted context string with artifacts
        """
        # Get defaults from config
        config = self._config.artifact_handoff if self._config else None
        if max_artifacts is None:
            max_artifacts = config.max_artifacts_in_handoff if config else 10
        if max_context_size is None:
            max_context_size = config.max_context_size if config else 50000
        if include_parent_artifacts is None:
            include_parent_artifacts = config.include_parent_artifacts if config else True

        # Get session info
        session = self.get_session(session_id)
        if not session:
            return ""

        context_parts = []

        # Add session header
        context_parts.append(f"## Session Context: {session.get('title', session_id)}")
        if session.get("git_branch"):
            context_parts.append(f"Branch: {session['git_branch']}")

        # Get artifacts
        artifacts = self.get_session_artifacts(
            session_id=session_id,
            limit=max_artifacts,
            include_parent=include_parent_artifacts,
        )

        if artifacts:
            context_parts.append("\n## Session Artifacts\n")

            current_size = sum(len(p) for p in context_parts)

            for artifact in artifacts:
                artifact_text = self._format_artifact(artifact)

                # Check size limit
                if current_size + len(artifact_text) > max_context_size:
                    context_parts.append("\n_[Artifacts truncated due to size limit]_")
                    break

                context_parts.append(artifact_text)
                current_size += len(artifact_text)

        return "\n".join(context_parts)

    def _format_artifact(self, artifact: Artifact) -> str:
        """
        Format an artifact for inclusion in handoff context.

        Args:
            artifact: Artifact object to format

        Returns:
            Formatted artifact string
        """
        parts = []

        # Header with type and source
        header = f"### {artifact.artifact_type.upper()}"
        if artifact.source_file:
            location = artifact.source_file
            if artifact.line_start:
                location += f":{artifact.line_start}"
                if artifact.line_end and artifact.line_end != artifact.line_start:
                    location += f"-{artifact.line_end}"
            header += f" - {location}"
        parts.append(header)

        # Format content based on type
        if artifact.artifact_type == "code":
            # Use language from metadata if available
            language = ""
            if artifact.metadata and "language" in artifact.metadata:
                language = artifact.metadata["language"]
            parts.append(f"```{language}")
            parts.append(artifact.content)
            parts.append("```")
        elif artifact.artifact_type == "diff":
            parts.append("```diff")
            parts.append(artifact.content)
            parts.append("```")
        elif artifact.artifact_type == "error":
            parts.append("```")
            parts.append(artifact.content)
            parts.append("```")
        else:
            # Plain text for other types
            parts.append(artifact.content)

        parts.append("")  # Empty line after artifact
        return "\n".join(parts)
