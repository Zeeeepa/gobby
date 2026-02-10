"""Skill formatting helpers.

Functions for rendering skill lists as JSON or markdown tables.
Extracted from src/gobby/cli/skills.py as part of the Strangler Fig
decomposition.
"""

import json
from collections.abc import Sequence
from typing import Any, Protocol

from gobby.skills.metadata import get_skill_category, get_skill_tags


class SkillLike(Protocol):
    """Protocol for objects that look like a Skill."""

    name: str
    description: str
    enabled: bool
    version: str | None
    metadata: dict[str, Any] | None


def format_skills_json(skills_list: Sequence[SkillLike]) -> str:
    """Format a skills list as a JSON string."""
    output = []
    for skill in skills_list:
        item = {
            "name": skill.name,
            "description": skill.description,
            "enabled": skill.enabled,
            "version": skill.version,
            "category": get_skill_category(skill),
            "tags": get_skill_tags(skill),
        }
        output.append(item)
    return json.dumps(output, indent=2)


def format_skills_markdown_table(skills_list: list[Any]) -> str:
    """Format a skills list as a markdown table."""
    lines = [
        "# Installed Skills",
        "",
        "| Name | Description | Category | Enabled |",
        "|------|-------------|----------|---------|",
    ]

    for skill in skills_list:
        category = (get_skill_category(skill) or "-").replace("|", "\\|")
        enabled = "\u2713" if skill.enabled else "\u2717"
        desc_full = skill.description or ""
        desc = desc_full[:50] + "..." if len(desc_full) > 50 else desc_full
        # Escape pipe characters for valid markdown table
        name_safe = skill.name.replace("|", "\\|")
        desc_safe = desc.replace("|", "\\|")
        lines.append(f"| {name_safe} | {desc_safe} | {category} | {enabled} |")

    return "\n".join(lines)
