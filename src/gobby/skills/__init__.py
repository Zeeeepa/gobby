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
from gobby.skills.search import (
    SearchFilters,
    SkillSearch,
    SkillSearchResult,
)
from gobby.skills.validator import (
    SkillValidator,
    ValidationResult,
    validate_skill_category,
    validate_skill_compatibility,
    validate_skill_description,
    validate_skill_name,
    validate_skill_tags,
    validate_skill_version,
)

__all__ = [
    # Parser
    "ParsedSkill",
    "SkillParseError",
    "parse_frontmatter",
    "parse_skill_file",
    "parse_skill_text",
    # Search
    "SearchFilters",
    "SkillSearch",
    "SkillSearchResult",
    # Validator
    "SkillValidator",
    "ValidationResult",
    "validate_skill_category",
    "validate_skill_compatibility",
    "validate_skill_description",
    "validate_skill_name",
    "validate_skill_tags",
    "validate_skill_version",
]
