"""Skills module for Agent Skills spec compliant skill management.

This module provides:
- YAML frontmatter parsing for SKILL.md files
- Validation against Agent Skills specification
- Search integration (TF-IDF + optional embeddings)
- Skill loading from filesystem, GitHub, and ZIP archives
- Skill updates from source
"""

from gobby.skills.parser import (
    ParsedSkill,
    SkillParseError,
    parse_frontmatter,
    parse_skill_file,
    parse_skill_text,
)
from gobby.skills.validator import (
    ValidationResult,
    validate_skill_compatibility,
    validate_skill_description,
    validate_skill_name,
)

__all__ = [
    # Parser
    "ParsedSkill",
    "SkillParseError",
    "parse_frontmatter",
    "parse_skill_file",
    "parse_skill_text",
    # Validator
    "ValidationResult",
    "validate_skill_name",
    "validate_skill_description",
    "validate_skill_compatibility",
]
