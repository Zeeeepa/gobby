"""Tests for skill directory structure support (TDD - written before implementation).

Tests that SkillLoader properly detects and records scripts/, references/, assets/
subdirectories when loading skills from directories.
"""

from pathlib import Path

import pytest

from gobby.skills.loader import SkillLoader
from gobby.skills.parser import ParsedSkill


@pytest.fixture
def skill_with_directories(tmp_path: Path) -> Path:
    """Create a skill directory with all subdirectories."""
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()

    # Create SKILL.md
    (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: A skill with directory structure
version: "1.0"
---

# My Skill

Instructions here.
""")

    # Create subdirectories with files
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "validate.sh").write_text("#!/bin/bash\necho 'validating'")
    (scripts_dir / "build.py").write_text("print('building')")

    references_dir = skill_dir / "references"
    references_dir.mkdir()
    (references_dir / "spec.md").write_text("# Specification")
    (references_dir / "examples.md").write_text("# Examples")

    assets_dir = skill_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "template.txt").write_text("Template content")
    (assets_dir / "icon.svg").write_text("<svg></svg>")

    return skill_dir


@pytest.fixture
def skill_without_directories(tmp_path: Path) -> Path:
    """Create a skill directory without subdirectories."""
    skill_dir = tmp_path / "simple-skill"
    skill_dir.mkdir()

    (skill_dir / "SKILL.md").write_text("""---
name: simple-skill
description: A simple skill without extras
---

# Simple Skill

Just instructions, no extras.
""")

    return skill_dir


@pytest.fixture
def skill_with_partial_directories(tmp_path: Path) -> Path:
    """Create a skill directory with only some subdirectories."""
    skill_dir = tmp_path / "partial-skill"
    skill_dir.mkdir()

    (skill_dir / "SKILL.md").write_text("""---
name: partial-skill
description: A skill with partial directory structure
---

# Partial Skill

Has scripts but no assets or references.
""")

    # Only scripts directory
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "run.sh").write_text("#!/bin/bash\necho 'running'")

    return skill_dir


class TestParsedSkillDirectoryFields:
    """Tests for ParsedSkill dataclass directory fields."""

    def test_parsed_skill_has_scripts_field(self):
        """Test that ParsedSkill has scripts field."""
        skill = ParsedSkill(
            name="test",
            description="Test skill",
            content="Content",
            scripts=["scripts/validate.sh"],
        )
        assert skill.scripts == ["scripts/validate.sh"]

    def test_parsed_skill_has_references_field(self):
        """Test that ParsedSkill has references field."""
        skill = ParsedSkill(
            name="test",
            description="Test skill",
            content="Content",
            references=["references/spec.md"],
        )
        assert skill.references == ["references/spec.md"]

    def test_parsed_skill_has_assets_field(self):
        """Test that ParsedSkill has assets field."""
        skill = ParsedSkill(
            name="test",
            description="Test skill",
            content="Content",
            assets=["assets/icon.svg"],
        )
        assert skill.assets == ["assets/icon.svg"]

    def test_parsed_skill_directory_fields_default_to_none(self):
        """Test that directory fields default to None."""
        skill = ParsedSkill(
            name="test",
            description="Test skill",
            content="Content",
        )
        assert skill.scripts is None
        assert skill.references is None
        assert skill.assets is None

    def test_parsed_skill_to_dict_includes_directory_fields(self):
        """Test that to_dict includes directory fields."""
        skill = ParsedSkill(
            name="test",
            description="Test skill",
            content="Content",
            scripts=["scripts/run.sh"],
            references=["references/spec.md"],
            assets=["assets/icon.svg"],
        )
        d = skill.to_dict()
        assert d["scripts"] == ["scripts/run.sh"]
        assert d["references"] == ["references/spec.md"]
        assert d["assets"] == ["assets/icon.svg"]


class TestSkillLoaderDirectoryDetection:
    """Tests for SkillLoader directory detection."""

    def test_load_skill_detects_scripts_directory(self, skill_with_directories):
        """Test that load_skill detects scripts directory."""
        loader = SkillLoader()
        skill = loader.load_skill(skill_with_directories)

        assert skill.scripts is not None
        assert len(skill.scripts) == 2
        assert "scripts/validate.sh" in skill.scripts
        assert "scripts/build.py" in skill.scripts

    def test_load_skill_detects_references_directory(self, skill_with_directories):
        """Test that load_skill detects references directory."""
        loader = SkillLoader()
        skill = loader.load_skill(skill_with_directories)

        assert skill.references is not None
        assert len(skill.references) == 2
        assert "references/spec.md" in skill.references
        assert "references/examples.md" in skill.references

    def test_load_skill_detects_assets_directory(self, skill_with_directories):
        """Test that load_skill detects assets directory."""
        loader = SkillLoader()
        skill = loader.load_skill(skill_with_directories)

        assert skill.assets is not None
        assert len(skill.assets) == 2
        assert "assets/template.txt" in skill.assets
        assert "assets/icon.svg" in skill.assets

    def test_load_skill_returns_none_for_missing_directories(self, skill_without_directories):
        """Test that missing directories result in None values."""
        loader = SkillLoader()
        skill = loader.load_skill(skill_without_directories)

        assert skill.scripts is None
        assert skill.references is None
        assert skill.assets is None

    def test_load_skill_partial_directories(self, skill_with_partial_directories):
        """Test loading skill with only some directories present."""
        loader = SkillLoader()
        skill = loader.load_skill(skill_with_partial_directories)

        assert skill.scripts is not None
        assert len(skill.scripts) == 1
        assert "scripts/run.sh" in skill.scripts

        # Missing directories should be None
        assert skill.references is None
        assert skill.assets is None

    def test_load_skill_from_file_ignores_directories(self, skill_with_directories):
        """Test that loading from SKILL.md file directly ignores directories."""
        loader = SkillLoader()
        skill_file = skill_with_directories / "SKILL.md"
        skill = loader.load_skill(skill_file)

        # When loading directly from file (not directory), we don't scan for subdirs
        # Directory detection only happens when loading from a directory
        assert skill.name == "my-skill"

        # Directory fields should be None when loading directly from file
        assert skill.scripts is None
        assert skill.references is None
        assert skill.assets is None

    def test_load_skill_empty_directories_result_in_none(self, tmp_path: Path):
        """Test that empty subdirectories result in None (no files)."""
        skill_dir = tmp_path / "empty-dirs-skill"
        skill_dir.mkdir()

        (skill_dir / "SKILL.md").write_text("""---
name: empty-dirs-skill
description: Skill with empty subdirectories
---

# Empty Dirs Skill
""")

        # Create empty subdirectories
        (skill_dir / "scripts").mkdir()
        (skill_dir / "references").mkdir()
        (skill_dir / "assets").mkdir()

        loader = SkillLoader()
        skill = loader.load_skill(skill_dir)

        # Empty directories should result in None (no files to list)
        assert skill.scripts is None
        assert skill.references is None
        assert skill.assets is None

    def test_load_skill_nested_files_in_directories(self, tmp_path: Path):
        """Test that nested files in subdirectories are detected."""
        skill_dir = tmp_path / "nested-skill"
        skill_dir.mkdir()

        (skill_dir / "SKILL.md").write_text("""---
name: nested-skill
description: Skill with nested files
---

# Nested Skill
""")

        # Create nested structure
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "run.sh").write_text("#!/bin/bash")
        nested_scripts = scripts_dir / "nested"
        nested_scripts.mkdir()
        (nested_scripts / "deep.sh").write_text("#!/bin/bash")

        loader = SkillLoader()
        skill = loader.load_skill(skill_dir)

        # Should include nested files with relative paths
        assert skill.scripts is not None
        assert len(skill.scripts) >= 2
        assert "scripts/run.sh" in skill.scripts
        assert "scripts/nested/deep.sh" in skill.scripts


class TestSkillDirectoryStructureWithZip:
    """Tests for directory structure detection with ZIP archives."""

    def test_load_from_zip_detects_directories(self, tmp_path: Path):
        """Test that loading from ZIP detects skill directories."""
        import zipfile

        # Create skill directory structure
        skill_dir = tmp_path / "zip-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("""---
name: zip-skill
description: Skill from ZIP with directories
---

# ZIP Skill
""")

        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "setup.sh").write_text("#!/bin/bash\nsetup")

        assets_dir = skill_dir / "assets"
        assets_dir.mkdir()
        (assets_dir / "config.json").write_text("{}")

        # Create ZIP
        zip_path = tmp_path / "skill.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(skill_dir / "SKILL.md", "zip-skill/SKILL.md")
            zf.write(scripts_dir / "setup.sh", "zip-skill/scripts/setup.sh")
            zf.write(assets_dir / "config.json", "zip-skill/assets/config.json")

        loader = SkillLoader()
        skill = loader.load_from_zip(zip_path)

        assert skill.name == "zip-skill"
        assert skill.scripts is not None
        assert "scripts/setup.sh" in skill.scripts
        assert skill.assets is not None
        assert "assets/config.json" in skill.assets
