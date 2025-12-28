from gobby.storage.memories import Memory


def _strip_leading_bullet(content: str) -> str:
    """Strip leading bullet points (- or *) from content."""
    content = content.strip()
    if content.startswith("- "):
        return content[2:]
    elif content.startswith("* "):
        return content[2:]
    return content


def build_memory_context(memories: list[Memory]) -> str:
    """
    Build a formatted markdown context string from memories.

    Args:
        memories: List of Memory objects to include

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
            parts.append(f"- {content}")
        parts.append("")

    # 3. Patterns
    if pattern_memories:
        parts.append("## Patterns\n")
        for mem in pattern_memories:
            content = _strip_leading_bullet(mem.content)
            parts.append(f"- {content}")
        parts.append("")

    # 4. Facts/Other
    if fact_memories:
        parts.append("## Facts\n")
        for mem in fact_memories:
            content = _strip_leading_bullet(mem.content)
            parts.append(f"- {content}")
        parts.append("")

    parts.append("</project-memory>")

    return "\n".join(parts)
