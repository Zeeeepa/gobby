from __future__ import annotations

import re
from typing import TYPE_CHECKING

from gobby.storage.memories import Memory

if TYPE_CHECKING:
    from gobby.compression import TextCompressor

# Pattern to match common bullet markers at start of string
_BULLET_PATTERN = re.compile(r"^[\s]*[-*•]\s*")

# Default threshold for compression (4KB)
DEFAULT_COMPRESSION_THRESHOLD = 4000


def _strip_leading_bullet(content: str) -> str:
    """
    Strip leading bullet points and whitespace from content.

    Handles common bullet markers: -, *, •
    Also strips any leading/trailing whitespace.

    Returns empty string if content is empty or only whitespace/bullets.
    """
    # Strip outer whitespace first
    content = content.strip()
    if not content:
        return ""

    # Remove leading bullet marker if present
    result = _BULLET_PATTERN.sub("", content)
    return result.strip()


def build_memory_context(
    memories: list[Memory],
    compressor: TextCompressor | None = None,
    compression_threshold: int = DEFAULT_COMPRESSION_THRESHOLD,
) -> str:
    """
    Build a formatted markdown context string from memories.

    Args:
        memories: List of Memory objects to include
        compressor: Optional TextCompressor for compressing large content.
            When provided and content exceeds compression_threshold, the inner
            content (between tags) is compressed before returning.
        compression_threshold: Character count threshold above which compression
            is applied. Defaults to 4000 characters.

    Returns:
        Formatted markdown string wrapped in <project-memory> tags
    """
    if not memories:
        return ""

    parts = ["<project-memory>"]

    # Group memories by type
    context_memories = [m for m in memories if m.memory_type == "context"]
    pref_memories = [m for m in memories if m.memory_type == "preference"]
    pattern_memories = [m for m in memories if m.memory_type == "pattern"]
    fact_memories = [m for m in memories if m.memory_type == "fact"]

    # 1. Project Context
    if context_memories:
        parts.append("## Project Context\n")
        for mem in context_memories:
            parts.append(f"{mem.content}\n")
        parts.append("")

    # 2. Preferences
    if pref_memories:
        parts.append("## Preferences\n")
        for mem in pref_memories:
            content = _strip_leading_bullet(mem.content)
            if content:  # Skip empty content
                parts.append(f"- {content}")
        parts.append("")

    # 3. Patterns
    if pattern_memories:
        parts.append("## Patterns\n")
        for mem in pattern_memories:
            content = _strip_leading_bullet(mem.content)
            if content:  # Skip empty content
                parts.append(f"- {content}")
        parts.append("")

    # 4. Facts/Other
    if fact_memories:
        parts.append("## Facts\n")
        for mem in fact_memories:
            content = _strip_leading_bullet(mem.content)
            if content:  # Skip empty content
                parts.append(f"- {content}")
        parts.append("")

    parts.append("</project-memory>")

    result = "\n".join(parts)

    # Compress if compressor provided and content exceeds threshold
    if compressor and len(result) > compression_threshold:
        # Compress only the inner content (preserve the tags)
        inner_content = "\n".join(parts[1:-1])  # Skip opening/closing tags
        compressed_inner = compressor.compress(inner_content, context_type="memory")
        result = f"<project-memory>\n{compressed_inner}\n</project-memory>"

    return result
