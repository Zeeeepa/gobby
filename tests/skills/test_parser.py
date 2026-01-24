"""Tests for SKILL.md frontmatter parser."""

import pytest

from gobby.skills.parser import (
    ParsedSkill,
    SkillParseError,
    parse_frontmatter,
    parse_skill_file,
    parse_skill_text,
)


class TestParseFrontmatter:
    """Tests for parse_frontmatter function."""

    def test_basic_frontmatter(self):
        """Test parsing basic frontmatter."""
        text = """---
name: test-skill
description: A test skill
---

# Content here
"""
        frontmatter, content = parse_frontmatter(text)

        assert frontmatter["name"] == "test-skill"
        assert frontmatter["description"] == "A test skill"
        assert content == "# Content here"

    def test_complex_frontmatter(self):
        """Test parsing complex nested frontmatter."""
        text = """---
name: commit-message
description: Generate commit messages
license: MIT
metadata:
  author: anthropic
  version: "1.0.0"
  skillport:
    category: git
    tags: [git, commits]
    alwaysApply: true
  gobby:
    triggers: ["/commit"]
---

Body content
"""
        frontmatter, content = parse_frontmatter(text)

        assert frontmatter["name"] == "commit-message"
        assert frontmatter["license"] == "MIT"
        assert frontmatter["metadata"]["author"] == "anthropic"
        assert frontmatter["metadata"]["skillport"]["category"] == "git"
        assert frontmatter["metadata"]["skillport"]["tags"] == ["git", "commits"]
        assert frontmatter["metadata"]["gobby"]["triggers"] == ["/commit"]
        assert content == "Body content"

    def test_missing_frontmatter(self):
        """Test that missing frontmatter raises error."""
        text = "# Just content, no frontmatter"
        with pytest.raises(SkillParseError, match="Missing"):
            parse_frontmatter(text)

    def test_invalid_yaml(self):
        """Test that invalid YAML raises error."""
        text = """---
name: test
invalid: yaml: here:
---

Content
"""
        with pytest.raises(SkillParseError, match="Invalid YAML"):
            parse_frontmatter(text)

    def test_empty_frontmatter(self):
        """Test parsing empty frontmatter."""
        text = """---
---

Content
"""
        frontmatter, content = parse_frontmatter(text)
        assert frontmatter == {}
        assert content == "Content"

    def test_frontmatter_must_be_mapping(self):
        """Test that non-mapping frontmatter raises error."""
        text = """---
- list
- item
---

Content
"""
        with pytest.raises(SkillParseError, match="mapping"):
            parse_frontmatter(text)


class TestParseSkillText:
    """Tests for parse_skill_text function."""

    def test_minimal_skill(self):
        """Test parsing minimal valid skill."""
        text = """---
name: minimal-skill
description: A minimal test skill
---

# Minimal Skill

Instructions here.
"""
        skill = parse_skill_text(text)

        assert skill.name == "minimal-skill"
        assert skill.description == "A minimal test skill"
        assert "# Minimal Skill" in skill.content
        assert skill.version is None
        assert skill.license is None
        assert skill.metadata is None

    def test_full_skill(self):
        """Test parsing skill with all fields."""
        text = """---
name: full-skill
description: A fully specified skill
license: MIT
compatibility: Requires Python 3.11+
version: "2.0.0"
allowed-tools: Bash, Read, Write
metadata:
  author: test
  skillport:
    category: testing
    tags: [test, example]
    alwaysApply: false
  gobby:
    triggers: ["/test"]
---

# Full Skill

Complete instructions.
"""
        skill = parse_skill_text(text)

        assert skill.name == "full-skill"
        assert skill.description == "A fully specified skill"
        assert skill.license == "MIT"
        assert skill.compatibility == "Requires Python 3.11+"
        assert skill.version == "2.0.0"
        assert skill.allowed_tools == ["Bash", "Read", "Write"]
        assert skill.metadata["author"] == "test"
        assert skill.metadata["skillport"]["category"] == "testing"
        assert skill.metadata["skillport"]["tags"] == ["test", "example"]

    def test_version_in_metadata(self):
        """Test that version can be in metadata."""
        text = """---
name: version-test
description: Test version in metadata
metadata:
  version: "1.5.0"
---

Content
"""
        skill = parse_skill_text(text)
        assert skill.version == "1.5.0"

    def test_version_at_top_level_takes_precedence(self):
        """Test that top-level version overrides metadata version."""
        text = """---
name: version-test
description: Test version precedence
version: "2.0.0"
metadata:
  version: "1.0.0"
---

Content
"""
        skill = parse_skill_text(text)
        assert skill.version == "2.0.0"

    def test_numeric_version_converted_to_string(self):
        """Test that numeric versions are converted to strings."""
        text = """---
name: numeric-version
description: Test numeric version
version: 1.0
---

Content
"""
        skill = parse_skill_text(text)
        assert skill.version == "1.0"
        assert isinstance(skill.version, str)

    def test_allowed_tools_as_list(self):
        """Test allowed-tools as YAML list."""
        text = """---
name: tools-list
description: Test tools as list
allowed-tools:
  - Bash
  - Read
  - Write
---

Content
"""
        skill = parse_skill_text(text)
        assert skill.allowed_tools == ["Bash", "Read", "Write"]

    def test_allowed_tools_underscore(self):
        """Test allowed_tools (underscore variant)."""
        text = """---
name: tools-underscore
description: Test underscore variant
allowed_tools: Bash, Read
---

Content
"""
        skill = parse_skill_text(text)
        assert skill.allowed_tools == ["Bash", "Read"]

    def test_missing_name_raises_error(self):
        """Test that missing name raises error."""
        text = """---
description: Has description but no name
---

Content
"""
        with pytest.raises(SkillParseError, match="name"):
            parse_skill_text(text)

    def test_missing_description_raises_error(self):
        """Test that missing description raises error."""
        text = """---
name: has-name-no-description
---

Content
"""
        with pytest.raises(SkillParseError, match="description"):
            parse_skill_text(text)

    def test_source_path_preserved(self):
        """Test that source path is preserved."""
        text = """---
name: path-test
description: Test path
---

Content
"""
        skill = parse_skill_text(text, source_path="/path/to/skill.md")
        assert skill.source_path == "/path/to/skill.md"


class TestParsedSkillHelpers:
    """Tests for ParsedSkill helper methods."""

    def test_get_category(self):
        """Test get_category extracts from metadata.skillport."""
        skill = ParsedSkill(
            name="test",
            description="Test",
            content="Content",
            metadata={"skillport": {"category": "git"}},
        )
        assert skill.get_category() == "git"

    def test_get_category_none(self):
        """Test get_category returns None when not set."""
        skill = ParsedSkill(name="test", description="Test", content="Content")
        assert skill.get_category() is None

    def test_get_tags(self):
        """Test get_tags extracts from metadata.skillport."""
        skill = ParsedSkill(
            name="test",
            description="Test",
            content="Content",
            metadata={"skillport": {"tags": ["git", "commits"]}},
        )
        assert skill.get_tags() == ["git", "commits"]

    def test_get_tags_empty(self):
        """Test get_tags returns empty list when not set."""
        skill = ParsedSkill(name="test", description="Test", content="Content")
        assert skill.get_tags() == []

    def test_is_always_apply(self):
        """Test is_always_apply checks alwaysApply flag."""
        skill_true = ParsedSkill(
            name="test",
            description="Test",
            content="Content",
            metadata={"skillport": {"alwaysApply": True}},
        )
        assert skill_true.is_always_apply() is True

        skill_false = ParsedSkill(
            name="test",
            description="Test",
            content="Content",
            metadata={"skillport": {"alwaysApply": False}},
        )
        assert skill_false.is_always_apply() is False

    def test_to_dict(self):
        """Test to_dict conversion."""
        skill = ParsedSkill(
            name="test",
            description="Test",
            content="Content",
            version="1.0.0",
            license="MIT",
        )
        d = skill.to_dict()

        assert d["name"] == "test"
        assert d["description"] == "Test"
        assert d["content"] == "Content"
        assert d["version"] == "1.0.0"
        assert d["license"] == "MIT"


class TestParseSkillFile:
    """Tests for parse_skill_file function."""

    def test_parse_existing_file(self, tmp_path):
        """Test parsing an existing skill file."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: file-test
description: Test file parsing
---

# File Test Skill

Content here.
""")

        skill = parse_skill_file(skill_file)

        assert skill.name == "file-test"
        assert skill.description == "Test file parsing"
        assert "# File Test Skill" in skill.content
        assert skill.source_path == str(skill_file)

    def test_parse_nonexistent_file(self, tmp_path):
        """Test that nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_skill_file(tmp_path / "nonexistent.md")

    def test_parse_real_skill_format(self, tmp_path):
        """Test parsing a skill in the full expected format."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: commit-message
description: Generate conventional commit messages following Angular conventions
license: MIT
compatibility: Requires git CLI
metadata:
  author: anthropic
  version: "1.0.0"
  skillport:
    category: git
    tags: [git, commits, workflow]
    alwaysApply: false
  gobby:
    triggers: ["/commit"]
    workflow_hint: "git-workflow"
allowed-tools: Bash(git:*)
---

# Commit Message Generator

## Instructions
When generating commit messages, follow these conventions:

1. Use conventional commit format
2. Keep subject line under 50 characters
3. Separate subject from body with blank line

## Examples

```
feat: add user authentication
fix: resolve memory leak in parser
docs: update API documentation
```
""")

        skill = parse_skill_file(skill_file)

        assert skill.name == "commit-message"
        assert (
            skill.description
            == "Generate conventional commit messages following Angular conventions"
        )
        assert skill.license == "MIT"
        assert skill.compatibility == "Requires git CLI"
        assert skill.version == "1.0"
        assert skill.allowed_tools == ["Bash(git:*)"]
        assert skill.metadata["author"] == "anthropic"
        assert skill.get_category() == "git"
        assert skill.get_tags() == ["git", "commits", "workflow"]
        assert skill.is_always_apply() is False
        assert skill.metadata["gobby"]["triggers"] == ["/commit"]
        assert "## Instructions" in skill.content
        assert "## Examples" in skill.content
