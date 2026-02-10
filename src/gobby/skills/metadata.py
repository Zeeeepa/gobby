"""Skill metadata helpers.

Utilities for reading and manipulating nested metadata dictionaries
on skill objects. Extracted from src/gobby/cli/skills.py as part of
the Strangler Fig decomposition.
"""

from typing import Any, Protocol


class SkillLike(Protocol):
    """Protocol for objects that look like a Skill."""

    metadata: dict[str, Any] | None


def get_skill_tags(skill: SkillLike) -> list[str]:
    """Extract tags from skill metadata."""
    if skill.metadata and isinstance(skill.metadata, dict):
        skillport = skill.metadata.get("skillport", {})
        if isinstance(skillport, dict):
            tags = skillport.get("tags", [])
            return list(tags) if isinstance(tags, list) else []
    return []


def get_skill_category(skill: SkillLike) -> str | None:
    """Extract category from skill metadata."""
    if skill.metadata and isinstance(skill.metadata, dict):
        skillport = skill.metadata.get("skillport", {})
        if isinstance(skillport, dict):
            return skillport.get("category")
    return None


def get_nested_value(data: dict[str, Any], key: str) -> Any:
    """Get a nested value from a dict using dot notation."""
    keys = key.split(".")
    current = data
    for k in keys:
        if not isinstance(current, dict) or k not in current:
            return None
        current = current[k]
    return current


def set_nested_value(data: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    """Set a nested value in a dict using dot notation.

    Returns a new dict with the value set. Note that only dictionaries along
    the key path are copied; sibling branches remain shared with the original
    structure, so this is not a full deep copy.
    """
    keys = key.split(".")
    result = data.copy() if data else {}
    current = result

    # Navigate to parent, creating dicts as needed
    for k in keys[:-1]:
        if k not in current or not isinstance(current[k], dict):
            current[k] = {}
        else:
            current[k] = current[k].copy()
        current = current[k]

    # Set the final key
    current[keys[-1]] = value
    return result


def unset_nested_value(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Remove a nested value from a dict using dot notation."""
    if not data:
        return {}

    keys = key.split(".")
    result = data.copy()

    if len(keys) == 1:
        # Simple key
        result.pop(keys[0], None)
        return result

    # Navigate to parent
    current = result
    parents: list[tuple[dict[str, Any], str]] = []

    for k in keys[:-1]:
        if not isinstance(current, dict) or k not in current:
            return result  # Key doesn't exist, nothing to do
        parents.append((current, k))
        if isinstance(current[k], dict):
            current[k] = current[k].copy()
        current = current[k]

    # Remove the final key
    if isinstance(current, dict) and keys[-1] in current:
        del current[keys[-1]]

    return result
