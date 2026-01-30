"""YAML frontmatter parser for SKILL.md files.

This module parses skill files following the Agent Skills specification format:
- YAML frontmatter delimited by ---
- Markdown content body

Example SKILL.md format:
```markdown
---
name: commit-message
description: Generate conventional commit messages
license: MIT
compatibility: Requires git CLI
metadata:
  author: anthropic
  version: "1.0"
  skillport:
    category: git
    tags: [git, commits]
    alwaysApply: false
  gobby:
    triggers: ["/commit"]
allowed-tools: Bash(git:*)
---

# Commit Message Generator

Instructions for the skill...
```
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Pattern to extract YAML frontmatter (content between --- delimiters)
# Allows empty frontmatter (---\n---) or content between delimiters
# Supports both LF (\n) and CRLF (\r\n) line endings
FRONTMATTER_PATTERN = re.compile(
    r"^---[ \t]*\r?\n(.*?)^---[ \t]*\r?\n?",
    re.DOTALL | re.MULTILINE,
)


@dataclass
class ParsedSkill:
    """Parsed skill data from a SKILL.md file.

    Attributes:
        name: Skill name (required)
        description: Skill description (required)
        content: Markdown body content
        version: Version string (from metadata.version or top-level)
        license: License identifier
        compatibility: Compatibility notes
        allowed_tools: List of allowed tool patterns
        metadata: Full metadata dict (includes skillport/gobby namespaces)
        source_path: Path the skill was loaded from
        source_type: Source type (local, github, zip, etc.)
        source_ref: Git ref for GitHub imports
        scripts: List of script file paths (relative to skill dir)
        references: List of reference file paths (relative to skill dir)
        assets: List of asset file paths (relative to skill dir)
        always_apply: Whether skill should always be injected at session start
        injection_format: How to inject skill (summary, full, content)
    """

    name: str
    description: str
    content: str
    version: str | None = None
    license: str | None = None
    compatibility: str | None = None
    allowed_tools: list[str] | None = None
    metadata: dict[str, Any] | None = None
    source_path: str | None = None
    source_type: str | None = None
    source_ref: str | None = None
    scripts: list[str] | None = None
    references: list[str] | None = None
    assets: list[str] | None = None
    always_apply: bool = False
    injection_format: str = "summary"

    def get_category(self) -> str | None:
        """Get category from top-level or metadata.skillport.category."""
        if not self.metadata:
            return None
        # Check top-level first (from frontmatter)
        result = self.metadata.get("category")
        if result is not None:
            return str(result)
        # Fall back to nested skillport.category
        skillport = self.metadata.get("skillport", {})
        result = skillport.get("category")
        return str(result) if result is not None else None

    def get_tags(self) -> list[str]:
        """Get tags from metadata.skillport.tags."""
        if not self.metadata:
            return []
        skillport = self.metadata.get("skillport", {})
        tags = skillport.get("tags", [])
        if isinstance(tags, list):
            return tags
        if isinstance(tags, str):
            return [tags]
        return []

    def is_always_apply(self) -> bool:
        """Check if this is a core skill (alwaysApply=true).

        Supports both top-level alwaysApply and nested metadata.skillport.alwaysApply.
        Top-level takes precedence.
        """
        if not self.metadata:
            return False
        # Check top-level first (from frontmatter)
        top_level = self.metadata.get("alwaysApply")
        if top_level is not None:
            return bool(top_level)
        # Fall back to nested skillport.alwaysApply
        skillport = self.metadata.get("skillport", {})
        return bool(skillport.get("alwaysApply", False))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "version": self.version,
            "license": self.license,
            "compatibility": self.compatibility,
            "allowed_tools": self.allowed_tools,
            "metadata": self.metadata,
            "source_path": self.source_path,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "scripts": self.scripts,
            "references": self.references,
            "assets": self.assets,
            "always_apply": self.always_apply,
            "injection_format": self.injection_format,
        }


class SkillParseError(Exception):
    """Error parsing a skill file."""

    def __init__(self, message: str, path: str | None = None):
        self.path = path
        super().__init__(f"{message}" + (f" in {path}" if path else ""))


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from text.

    Args:
        text: Full text content with frontmatter

    Returns:
        Tuple of (frontmatter dict, content body)

    Raises:
        SkillParseError: If frontmatter is missing or invalid
    """
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        raise SkillParseError("Missing or invalid YAML frontmatter (must start with ---)")

    frontmatter_yaml = match.group(1)
    content = text[match.end() :].strip()

    try:
        frontmatter = yaml.safe_load(frontmatter_yaml)
    except yaml.YAMLError as e:
        raise SkillParseError(f"Invalid YAML in frontmatter: {e}") from e

    if frontmatter is None:
        frontmatter = {}

    if not isinstance(frontmatter, dict):
        raise SkillParseError("Frontmatter must be a YAML mapping")

    return frontmatter, content


def parse_skill_text(text: str, source_path: str | None = None) -> ParsedSkill:
    """Parse a skill from text content.

    Args:
        text: Full skill file content (frontmatter + markdown)
        source_path: Optional path for error messages

    Returns:
        ParsedSkill with extracted data

    Raises:
        SkillParseError: If parsing fails or required fields missing
    """
    try:
        frontmatter, content = parse_frontmatter(text)
    except SkillParseError as e:
        # Create a new exception with the path included in the message
        raise SkillParseError(str(e), path=source_path) from e

    # Extract required fields
    name = frontmatter.get("name")
    if not name:
        raise SkillParseError("Missing required field: name", source_path)

    description = frontmatter.get("description")
    if not description:
        raise SkillParseError("Missing required field: description", source_path)

    # Extract optional fields
    license_str = frontmatter.get("license")
    compatibility = frontmatter.get("compatibility")

    # Handle allowed-tools (can be string or list)
    allowed_tools_raw = frontmatter.get("allowed-tools") or frontmatter.get("allowed_tools")
    allowed_tools: list[str] | None = None
    if allowed_tools_raw:
        if isinstance(allowed_tools_raw, str):
            # Single tool or comma-separated
            allowed_tools = [t.strip() for t in allowed_tools_raw.split(",")]
        elif isinstance(allowed_tools_raw, list):
            allowed_tools = [str(t) for t in allowed_tools_raw]

    # Extract metadata (may contain version, skillport, gobby namespaces)
    metadata = frontmatter.get("metadata")

    # Handle top-level alwaysApply and category by including them in metadata
    # This allows both top-level and nested formats to work
    top_level_always_apply = frontmatter.get("alwaysApply")
    top_level_category = frontmatter.get("category")
    top_level_injection_format = frontmatter.get("injectionFormat")

    if top_level_always_apply is not None or top_level_category is not None:
        if metadata is None:
            metadata = {}
        # Store at top level of metadata (not nested in skillport)
        if top_level_always_apply is not None:
            metadata["alwaysApply"] = top_level_always_apply
        if top_level_category is not None:
            metadata["category"] = top_level_category

    # Version can be at top level or in metadata
    version = frontmatter.get("version")
    if version is None and metadata and isinstance(metadata, dict):
        version = metadata.get("version")

    # Convert version to string if it's a number (e.g., 1.0 parsed as float)
    if version is not None:
        version = str(version)

    # Extract always_apply: check top-level first, then metadata.skillport.alwaysApply
    always_apply = False
    if top_level_always_apply is not None:
        always_apply = bool(top_level_always_apply)
    elif metadata and isinstance(metadata, dict):
        skillport = metadata.get("skillport", {})
        if isinstance(skillport, dict) and skillport.get("alwaysApply"):
            always_apply = bool(skillport["alwaysApply"])

    # Extract injection_format: check top-level first, default to "summary"
    injection_format = "summary"
    if top_level_injection_format is not None:
        injection_format = str(top_level_injection_format)

    return ParsedSkill(
        name=name,
        description=description,
        content=content,
        version=version,
        license=license_str,
        compatibility=compatibility,
        allowed_tools=allowed_tools,
        metadata=metadata,
        source_path=source_path,
        always_apply=always_apply,
        injection_format=injection_format,
    )


def parse_skill_file(path: str | Path) -> ParsedSkill:
    """Parse a skill from a file path.

    Args:
        path: Path to SKILL.md file

    Returns:
        ParsedSkill with extracted data

    Raises:
        FileNotFoundError: If file doesn't exist
        SkillParseError: If parsing fails (propagated from parse_skill_text)
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Skill file not found: {path}")

    text = path.read_text(encoding="utf-8")
    return parse_skill_text(text, source_path=str(path))
