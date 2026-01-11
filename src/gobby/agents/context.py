"""
Context resolver for subagent context injection.

Resolves various context sources for injecting into subagent prompts:
- summary_markdown: Parent session's summary
- compact_markdown: Parent session's handoff context
- session_id:<id>: Lookup specific session summary
- transcript:<n>: Last N messages from parent session
- file:<path>: Read file content with security checks
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.storage.session_messages import LocalSessionMessageManager
    from gobby.storage.sessions import LocalSessionManager

logger = logging.getLogger(__name__)


class ContextResolutionError(Exception):
    """Raised when context resolution fails."""

    pass


class ContextResolver:
    """
    Resolves context from various sources for subagent injection.

    Supports the following source formats:
    - "summary_markdown": Parent session's summary_markdown field
    - "compact_markdown": Parent session's compact_markdown (handoff context)
    - "session_id:<id>": Summary from a specific session by ID
    - "transcript:<n>": Last N messages from parent session
    - "file:<path>": Read file content (project-scoped with security checks)

    Example:
        >>> resolver = ContextResolver(session_manager, message_manager, project_path)
        >>> context = await resolver.resolve("summary_markdown", "sess-abc123")
        >>> context = await resolver.resolve("transcript:10", "sess-abc123")
        >>> context = await resolver.resolve("file:docs/context.md", "sess-abc123")
    """

    # Pattern matchers for source formats
    SESSION_ID_PATTERN = re.compile(r"^session_id:(.+)$")
    TRANSCRIPT_PATTERN = re.compile(r"^transcript:(\d+)$")
    FILE_PATTERN = re.compile(r"^file:(.+)$")

    def __init__(
        self,
        session_manager: LocalSessionManager,
        message_manager: LocalSessionMessageManager,
        project_path: str | Path | None = None,
        max_file_size: int = 51200,  # 50KB default
        max_content_size: int = 51200,  # 50KB default for all content types
        max_transcript_messages: int = 100,
        truncation_suffix: str = "\n\n[truncated: {bytes} bytes remaining]",
    ):
        """
        Initialize the context resolver.

        Args:
            session_manager: Session storage manager for session lookups.
            message_manager: Message storage manager for transcript lookups.
            project_path: Project root path for file security checks.
            max_file_size: Maximum file size in bytes (default: 50KB).
            max_content_size: Maximum content size for all sources (default: 50KB).
            max_transcript_messages: Maximum transcript messages to fetch.
            truncation_suffix: Suffix template when content is truncated.
        """
        self._session_manager = session_manager
        self._message_manager = message_manager
        self._project_path = Path(project_path) if project_path else None
        self._truncation_suffix = truncation_suffix
        self._max_file_size = max_file_size
        self._max_content_size = max_content_size
        self._max_transcript_messages = max_transcript_messages

    async def resolve(self, source: str, session_id: str) -> str:
        """
        Resolve context from the specified source.

        Args:
            source: Context source specification.
            session_id: Parent session ID for context lookups.

        Returns:
            Resolved context string (uncompressed), truncated if exceeding max_content_size.

        Raises:
            ContextResolutionError: If resolution fails.
        """
        content: str = ""

        # Handle simple source types
        if source == "summary_markdown":
            content = self._resolve_summary_markdown(session_id)

        elif source == "compact_markdown":
            content = self._resolve_compact_markdown(session_id)

        # Handle parameterized source types
        elif match := self.SESSION_ID_PATTERN.match(source):
            target_session_id = match.group(1)
            content = self._resolve_session_id(target_session_id)

        elif match := self.TRANSCRIPT_PATTERN.match(source):
            count = int(match.group(1))
            content = await self._resolve_transcript(session_id, count)

        elif match := self.FILE_PATTERN.match(source):
            file_path = match.group(1)
            # File resolution has its own truncation logic
            return self._resolve_file(file_path)

        else:
            # Unknown source format
            raise ContextResolutionError(f"Unknown context source format: {source}")

        # Apply truncation to all non-file sources
        return self._truncate_content(content, self._max_content_size)

    def _resolve_summary_markdown(self, session_id: str) -> str:
        """
        Resolve summary_markdown from parent session.

        Args:
            session_id: Parent session ID.

        Returns:
            Summary markdown content, or empty string if not available.
        """
        session = self._session_manager.get(session_id)
        if not session:
            raise ContextResolutionError(f"Session not found: {session_id}")

        return session.summary_markdown or ""

    def _resolve_compact_markdown(self, session_id: str) -> str:
        """
        Resolve compact_markdown (handoff context) from parent session.

        Args:
            session_id: Parent session ID.

        Returns:
            Compact markdown content, or empty string if not available.
        """
        session = self._session_manager.get(session_id)
        if not session:
            raise ContextResolutionError(f"Session not found: {session_id}")

        return session.compact_markdown or ""

    def _resolve_session_id(self, target_session_id: str) -> str:
        """
        Resolve summary from a specific session by ID.

        Args:
            target_session_id: Target session ID to lookup.

        Returns:
            Summary markdown from the target session.

        Raises:
            ContextResolutionError: If session not found.
        """
        session = self._session_manager.get(target_session_id)
        if not session:
            raise ContextResolutionError(f"Session not found: {target_session_id}")

        return session.summary_markdown or ""

    async def _resolve_transcript(self, session_id: str, count: int) -> str:
        """
        Resolve last N messages from parent session as transcript.

        Args:
            session_id: Parent session ID.
            count: Number of recent messages to include.

        Returns:
            Formatted transcript of recent messages, or empty string if none.
        """
        # Clamp count to max
        count = min(count, self._max_transcript_messages)

        messages = await self._message_manager.get_messages(
            session_id=session_id,
            limit=count,
            offset=0,
        )

        if not messages:
            return ""

        # Format messages into transcript
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content:
                lines.append(f"**{role}**: {content}")

        return "\n\n".join(lines)

    def _resolve_file(self, file_path: str) -> str:
        """
        Resolve content from a file with security checks.

        Security checks:
        - Path must be within project directory
        - No path traversal (..)
        - No absolute paths
        - Symlinks must resolve within project
        - File must be valid UTF-8 (no binary)
        - File size must be within limit

        Args:
            file_path: Relative path to file within project.

        Returns:
            File content, possibly truncated.

        Raises:
            ContextResolutionError: If file not found, not readable, or fails security checks.
        """
        if not self._project_path:
            raise ContextResolutionError("No project path configured for file resolution")

        # Parse the path and check for security issues
        parsed_path = Path(file_path)

        # Reject absolute paths
        if parsed_path.is_absolute():
            raise ContextResolutionError(f"Absolute paths not allowed: {file_path}")

        # Reject path traversal attempts by checking path components
        if ".." in parsed_path.parts:
            raise ContextResolutionError(f"Path traversal not allowed: {file_path}")

        # Resolve the full path
        try:
            full_path = (self._project_path / file_path).resolve()
        except Exception as e:
            raise ContextResolutionError(f"Invalid file path: {file_path}") from e

        # Check path is within project
        try:
            full_path.relative_to(self._project_path.resolve())
        except ValueError:
            raise ContextResolutionError(
                f"File path outside project directory: {file_path}"
            ) from None

        # Check file exists
        if not full_path.exists():
            raise ContextResolutionError(f"File not found: {file_path}")

        if not full_path.is_file():
            raise ContextResolutionError(f"Path is not a file: {file_path}")

        # Check file size
        file_size = full_path.stat().st_size
        if file_size > self._max_file_size:
            # Read up to limit and truncate
            try:
                with open(full_path, encoding="utf-8") as f:
                    content = f.read(self._max_file_size)
                remaining = file_size - self._max_file_size
                return content + self._truncation_suffix.format(bytes=remaining)
            except UnicodeDecodeError:
                raise ContextResolutionError(
                    f"File is not valid UTF-8 (binary): {file_path}"
                ) from None

        # Read file content
        try:
            with open(full_path, encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            raise ContextResolutionError(f"File is not valid UTF-8 (binary): {file_path}") from None
        except PermissionError:
            raise ContextResolutionError(f"Permission denied: {file_path}") from None
        except Exception as e:
            raise ContextResolutionError(f"Failed to read file {file_path}: {e}") from e

    def _truncate_content(self, content: str, max_bytes: int) -> str:
        """
        Truncate content to max bytes with suffix.

        Args:
            content: Content to potentially truncate.
            max_bytes: Maximum bytes allowed.

        Returns:
            Content, possibly truncated with suffix.
        """
        encoded = content.encode("utf-8")
        if len(encoded) <= max_bytes:
            return content

        # Truncate and add suffix
        truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
        remaining = len(encoded) - max_bytes
        return truncated + self._truncation_suffix.format(bytes=remaining)


# Default template for context injection
DEFAULT_CONTEXT_TEMPLATE = """## Context from Parent Session
*Injected by Gobby subagent spawning*

{{ context }}

---

## Task

{{ prompt }}"""


def format_injected_prompt(context: str, prompt: str, template: str | None = None) -> str:
    """
    Format the injected prompt with context prepended.

    Args:
        context: Resolved context to inject.
        prompt: Original prompt for the agent.
        template: Optional custom template with {{ context }} and {{ prompt }} placeholders.
            If None, uses the default template.

    Returns:
        Formatted prompt with context, or original prompt if context is empty.
    """
    if not context or not context.strip():
        return prompt

    # Use default template if none provided
    effective_template = template or DEFAULT_CONTEXT_TEMPLATE

    # Simple string substitution for {{ context }} and {{ prompt }}
    result = effective_template
    result = result.replace("{{ context }}", context)
    result = result.replace("{{ prompt }}", prompt)

    # Also support {context} and {prompt} for Python format-style
    # but only if {{ }} placeholders are not in the template
    if "{{ context }}" not in effective_template and "{{ prompt }}" not in effective_template:
        try:
            result = effective_template.format(context=context, prompt=prompt)
        except (KeyError, IndexError):
            # If format fails due to missing placeholders or positional braces like {0},
            # return as-is
            pass

    return result
