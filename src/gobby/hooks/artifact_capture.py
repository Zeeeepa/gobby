"""
Artifact capture hook for extracting and storing artifacts from messages.

Processes assistant messages to extract:
- Code blocks (with language metadata)
- File path references
- Other classified content

Uses artifact_classifier for type detection and LocalArtifactManager for storage.
Tracks content hashes to prevent duplicate storage using a bounded LRU cache.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import OrderedDict
from typing import TYPE_CHECKING

from gobby.storage.artifact_classifier import ArtifactType, classify_artifact

if TYPE_CHECKING:
    from gobby.storage.artifacts import Artifact, LocalArtifactManager

logger = logging.getLogger(__name__)

__all__ = ["ArtifactCaptureHook"]

# Maximum number of content hashes to track for duplicate detection
MAX_HASH_CACHE = 10000

# Pattern to extract markdown code blocks
_CODE_BLOCK_PATTERN = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)

# Pattern to extract backtick-wrapped file paths
_FILE_REF_PATTERN = re.compile(r"`([^\s`]+\.[a-zA-Z0-9]+)`")

# Pattern to extract bare file paths (Unix-style)
_UNIX_PATH_PATTERN = re.compile(r"(?:^|\s)(/[^\s]+\.[a-zA-Z0-9]+)(?:\s|$)")


class ArtifactCaptureHook:
    """
    Hook for capturing artifacts from assistant messages.

    Extracts code blocks, file references, and other artifacts from messages,
    classifies them using artifact_classifier, and stores via LocalArtifactManager.

    Tracks content hashes to prevent storing duplicate artifacts.
    """

    def __init__(self, artifact_manager: LocalArtifactManager):
        """
        Initialize the artifact capture hook.

        Args:
            artifact_manager: LocalArtifactManager instance for storing artifacts
        """
        self._artifact_manager = artifact_manager
        # Use OrderedDict as LRU cache for bounded duplicate tracking
        self._seen_hashes: OrderedDict[str, None] = OrderedDict()

    def _compute_hash(self, content: str) -> str:
        """Compute a hash for content deduplication."""
        return hashlib.sha256(content.encode()).hexdigest()

    def _is_duplicate(self, content: str) -> bool:
        """Check if content has already been seen.

        Uses a bounded LRU cache to prevent unbounded memory growth.
        """
        content_hash = self._compute_hash(content)
        if content_hash in self._seen_hashes:
            # Move to end (most recently used)
            self._seen_hashes.move_to_end(content_hash)
            return True

        # Add new hash, evict oldest if over capacity
        self._seen_hashes[content_hash] = None
        if len(self._seen_hashes) > MAX_HASH_CACHE:
            # Remove oldest entry (first item)
            self._seen_hashes.popitem(last=False)

        return False

    def reset_duplicate_tracking(self) -> None:
        """Clear the duplicate tracking cache.

        Useful to reset between sessions or when memory needs to be freed.
        """
        self._seen_hashes.clear()

    def _extract_code_blocks(self, content: str) -> list[tuple[str, str]]:
        """
        Extract code blocks from content.

        Args:
            content: Message content to extract from

        Returns:
            List of (language, code) tuples
        """
        blocks = []
        for match in _CODE_BLOCK_PATTERN.finditer(content):
            language = match.group(1).lower() if match.group(1) else ""
            code = match.group(2).strip()
            if code:
                blocks.append((language, code))
        return blocks

    def _extract_file_references(self, content: str) -> list[str]:
        """
        Extract file path references from content.

        Args:
            content: Message content to extract from

        Returns:
            List of file paths
        """
        paths = set()

        # Extract backtick-wrapped file paths
        for match in _FILE_REF_PATTERN.finditer(content):
            path = match.group(1)
            # Filter out obvious non-paths
            if "/" in path or "\\" in path:
                paths.add(path)

        # Extract Unix-style paths
        for match in _UNIX_PATH_PATTERN.finditer(content):
            paths.add(match.group(1))

        return list(paths)

    def process_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> list[Artifact] | None:
        """
        Process a message and extract artifacts.

        Only processes assistant messages. Extracts code blocks and file
        references, classifies them, and stores them as artifacts.

        Args:
            session_id: ID of the session this message belongs to
            role: Message role ("assistant" or "user")
            content: Message content

        Returns:
            List of created Artifact objects, or None/empty if none created
        """
        # Only process assistant messages
        if role != "assistant":
            return None

        if not content or not content.strip():
            return []

        artifacts: list[Artifact] = []

        # Extract and store code blocks
        code_blocks = self._extract_code_blocks(content)
        for language, code in code_blocks:
            if self._is_duplicate(code):
                continue

            # Use classifier to get type and metadata
            result = classify_artifact(f"```{language}\n{code}\n```")
            metadata = result.metadata.copy()

            # Ensure language is in metadata
            if language and "language" not in metadata:
                metadata["language"] = language

            try:
                artifact = self._artifact_manager.create_artifact(
                    session_id=session_id,
                    artifact_type=result.artifact_type.value,
                    content=code,
                    metadata=metadata,
                )
                artifacts.append(artifact)
            except Exception as e:
                logger.error(f"Failed to create code artifact: {e}")

        # Extract and store file references
        file_paths = self._extract_file_references(content)
        for path in file_paths:
            if self._is_duplicate(path):
                continue

            # Use classifier to verify it's a file path
            result = classify_artifact(path)
            if result.artifact_type != ArtifactType.FILE_PATH:
                continue

            try:
                artifact = self._artifact_manager.create_artifact(
                    session_id=session_id,
                    artifact_type=ArtifactType.FILE_PATH.value,
                    content=path,
                    metadata=result.metadata,
                )
                artifacts.append(artifact)
            except Exception as e:
                logger.error(f"Failed to create file path artifact: {e}")

        return artifacts
