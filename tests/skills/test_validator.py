"""Tests for skill validation functions."""

import pytest

from gobby.skills.validator import (
    ValidationResult,
    validate_skill_category,
    validate_skill_compatibility,
    validate_skill_description,
    validate_skill_name,
    validate_skill_tags,
    validate_skill_version,
)


class TestValidationResult:
    """Tests for ValidationResult class."""

    def test_default_is_valid(self):
        """Test that default result is valid."""
        result = ValidationResult()
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_add_error_marks_invalid(self):
        """Test that adding an error marks result invalid."""
        result = ValidationResult()
        result.add_error("Test error")
        assert result.valid is False
        assert "Test error" in result.errors

    def test_add_warning_keeps_valid(self):
        """Test that warnings don't affect validity."""
        result = ValidationResult()
        result.add_warning("Test warning")
        assert result.valid is True
        assert "Test warning" in result.warnings

    def test_merge_combines_results(self):
        """Test merging two results."""
        r1 = ValidationResult()
        r1.add_error("Error 1")
        r1.add_warning("Warning 1")

        r2 = ValidationResult()
        r2.add_error("Error 2")

        r1.merge(r2)
        assert r1.valid is False
        assert len(r1.errors) == 2
        assert "Error 1" in r1.errors
        assert "Error 2" in r1.errors

    def test_to_dict(self):
        """Test dictionary conversion."""
        result = ValidationResult()
        result.add_error("Error")
        result.add_warning("Warning")

        d = result.to_dict()
        assert d["valid"] is False
        assert "Error" in d["errors"]
        assert "Warning" in d["warnings"]


class TestValidateSkillName:
    """Tests for validate_skill_name function."""

    def test_valid_simple_name(self):
        """Test valid simple names."""
        assert validate_skill_name("commit-message").valid is True
        assert validate_skill_name("git").valid is True
        assert validate_skill_name("code-review").valid is True
        assert validate_skill_name("my-skill-name").valid is True

    def test_valid_name_with_numbers(self):
        """Test valid names with numbers."""
        assert validate_skill_name("skill2").valid is True
        assert validate_skill_name("my-skill-v2").valid is True
        assert validate_skill_name("pr123-reviewer").valid is True

    def test_rejects_empty_name(self):
        """Test that empty names are rejected."""
        result = validate_skill_name("")
        assert result.valid is False
        assert any("required" in e.lower() for e in result.errors)

    def test_rejects_none_name(self):
        """Test that None names are rejected."""
        result = validate_skill_name(None)
        assert result.valid is False
        assert any("required" in e.lower() for e in result.errors)

    def test_rejects_uppercase(self):
        """Test that uppercase letters are rejected."""
        result = validate_skill_name("CommitMessage")
        assert result.valid is False
        assert any("lowercase" in e.lower() for e in result.errors)

        result = validate_skill_name("SKILL")
        assert result.valid is False

        result = validate_skill_name("mySkill")
        assert result.valid is False

    def test_rejects_leading_hyphen(self):
        """Test that leading hyphens are rejected."""
        result = validate_skill_name("-skill")
        assert result.valid is False
        assert any("start with" in e.lower() for e in result.errors)

    def test_rejects_trailing_hyphen(self):
        """Test that trailing hyphens are rejected."""
        result = validate_skill_name("skill-")
        assert result.valid is False
        assert any("end with" in e.lower() for e in result.errors)

    def test_rejects_consecutive_hyphens(self):
        """Test that consecutive hyphens are rejected."""
        result = validate_skill_name("my--skill")
        assert result.valid is False
        assert any("consecutive" in e.lower() for e in result.errors)

        result = validate_skill_name("skill---name")
        assert result.valid is False

    def test_rejects_too_long_name(self):
        """Test that names over 64 chars are rejected."""
        long_name = "a" * 65
        result = validate_skill_name(long_name)
        assert result.valid is False
        assert any("64" in e for e in result.errors)

    def test_accepts_max_length_name(self):
        """Test that 64-char names are accepted."""
        max_name = "a" * 64
        assert validate_skill_name(max_name).valid is True

    def test_rejects_special_characters(self):
        """Test that special characters are rejected."""
        assert validate_skill_name("my_skill").valid is False
        assert validate_skill_name("my.skill").valid is False
        assert validate_skill_name("my skill").valid is False
        assert validate_skill_name("my@skill").valid is False

    def test_rejects_starting_with_number(self):
        """Test that names starting with numbers are rejected."""
        result = validate_skill_name("2skill")
        assert result.valid is False


class TestValidateSkillDescription:
    """Tests for validate_skill_description function."""

    def test_valid_description(self):
        """Test valid descriptions."""
        assert validate_skill_description("A simple skill").valid is True
        assert validate_skill_description("Generate commit messages").valid is True

    def test_rejects_empty_description(self):
        """Test that empty descriptions are rejected."""
        result = validate_skill_description("")
        assert result.valid is False
        assert any("required" in e.lower() for e in result.errors)

    def test_rejects_whitespace_only(self):
        """Test that whitespace-only descriptions are rejected."""
        result = validate_skill_description("   ")
        assert result.valid is False

        result = validate_skill_description("\t\n")
        assert result.valid is False

    def test_rejects_none_description(self):
        """Test that None descriptions are rejected."""
        result = validate_skill_description(None)
        assert result.valid is False

    def test_rejects_too_long_description(self):
        """Test that descriptions over 1024 chars are rejected."""
        long_desc = "a" * 1025
        result = validate_skill_description(long_desc)
        assert result.valid is False
        assert any("1024" in e for e in result.errors)

    def test_accepts_max_length_description(self):
        """Test that 1024-char descriptions are accepted."""
        max_desc = "a" * 1024
        assert validate_skill_description(max_desc).valid is True


class TestValidateSkillCompatibility:
    """Tests for validate_skill_compatibility function."""

    def test_valid_compatibility(self):
        """Test valid compatibility strings."""
        assert validate_skill_compatibility("Requires Python 3.11+").valid is True
        assert validate_skill_compatibility("Works with git CLI").valid is True

    def test_accepts_empty_compatibility(self):
        """Test that empty compatibility is accepted (optional field)."""
        assert validate_skill_compatibility("").valid is True
        assert validate_skill_compatibility(None).valid is True

    def test_rejects_too_long_compatibility(self):
        """Test that compatibility over 500 chars is rejected."""
        long_compat = "a" * 501
        result = validate_skill_compatibility(long_compat)
        assert result.valid is False
        assert any("500" in e for e in result.errors)

    def test_accepts_max_length_compatibility(self):
        """Test that 500-char compatibility is accepted."""
        max_compat = "a" * 500
        assert validate_skill_compatibility(max_compat).valid is True


class TestValidateSkillTags:
    """Tests for validate_skill_tags function."""

    def test_valid_tags(self):
        """Test valid tag lists."""
        assert validate_skill_tags(["git", "commits"]).valid is True
        assert validate_skill_tags(["code-review", "quality"]).valid is True

    def test_accepts_empty_tags(self):
        """Test that empty/None tags are accepted (optional)."""
        assert validate_skill_tags([]).valid is True
        assert validate_skill_tags(None).valid is True

    def test_rejects_non_list(self):
        """Test that non-list values are rejected."""
        result = validate_skill_tags("git")  # type: ignore
        assert result.valid is False
        assert any("list" in e.lower() for e in result.errors)

    def test_rejects_non_string_tags(self):
        """Test that non-string tags are rejected."""
        result = validate_skill_tags([123, "valid"])  # type: ignore
        assert result.valid is False
        assert any("string" in e.lower() for e in result.errors)

    def test_rejects_empty_string_tags(self):
        """Test that empty string tags are rejected."""
        result = validate_skill_tags(["valid", ""])
        assert result.valid is False
        assert any("empty" in e.lower() for e in result.errors)

    def test_rejects_too_long_tags(self):
        """Test that tags over 64 chars are rejected."""
        long_tag = "a" * 65
        result = validate_skill_tags([long_tag])
        assert result.valid is False
        assert any("64" in e for e in result.errors)


class TestValidateSkillVersion:
    """Tests for validate_skill_version function."""

    def test_valid_versions(self):
        """Test valid version strings."""
        assert validate_skill_version("1.0").valid is True
        assert validate_skill_version("1.0.0").valid is True
        assert validate_skill_version("2.1.3").valid is True
        assert validate_skill_version("1.0.0-beta").valid is True
        assert validate_skill_version("1.0.0-alpha.1").valid is True
        assert validate_skill_version("1.0.0+build123").valid is True

    def test_accepts_empty_version(self):
        """Test that empty/None versions are accepted (optional)."""
        assert validate_skill_version("").valid is True
        assert validate_skill_version(None).valid is True

    def test_rejects_invalid_versions(self):
        """Test that invalid version strings are rejected."""
        assert validate_skill_version("v1.0").valid is False
        assert validate_skill_version("1").valid is False
        assert validate_skill_version("latest").valid is False
        assert validate_skill_version("1.0.0.0").valid is False


class TestValidateSkillCategory:
    """Tests for validate_skill_category function."""

    def test_valid_categories(self):
        """Test valid category strings."""
        assert validate_skill_category("git").valid is True
        assert validate_skill_category("code-review").valid is True
        assert validate_skill_category("ci-cd").valid is True
        assert validate_skill_category("testing").valid is True

    def test_accepts_empty_category(self):
        """Test that empty/None categories are accepted (optional)."""
        assert validate_skill_category("").valid is True
        assert validate_skill_category(None).valid is True

    def test_rejects_uppercase_category(self):
        """Test that uppercase categories are rejected."""
        result = validate_skill_category("Git")
        assert result.valid is False

    def test_rejects_invalid_category_chars(self):
        """Test that invalid characters are rejected."""
        assert validate_skill_category("code_review").valid is False
        assert validate_skill_category("code.review").valid is False
        assert validate_skill_category("code review").valid is False

    def test_rejects_starting_with_number(self):
        """Test that categories starting with numbers are rejected."""
        result = validate_skill_category("2git")
        assert result.valid is False
