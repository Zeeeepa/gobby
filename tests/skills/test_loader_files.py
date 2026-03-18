"""Tests for multi-file skill loading in SkillLoader."""

from pathlib import Path

import pytest

from gobby.skills.loader import LoadedSkillFile, SkillLoader, _classify_file, _is_binary_file


# ===========================================================================
# 1. Load skill files from directory
# ===========================================================================


def _write_skill_dir(base: Path) -> Path:
    """Create a minimal multi-file skill directory under *base* and return it."""
    skill_dir = base / "my-skill"
    skill_dir.mkdir()

    # Main skill file
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: my-skill\n"
        "description: A test skill\n"
        "version: 1.0.0\n"
        "---\n"
        "# My Skill\n"
        "Do the thing.\n"
    )

    # References
    refs = skill_dir / "references"
    refs.mkdir()
    (refs / "guide.md").write_text("# Guide\nSome guidance.")

    # Scripts
    scripts = skill_dir / "scripts"
    scripts.mkdir()
    (scripts / "run.py").write_text("print('hello')")

    return skill_dir


def test_load_skill_files_from_directory(tmp_path: Path) -> None:
    skill_dir = _write_skill_dir(tmp_path)

    loader = SkillLoader()
    parsed = loader.load_skill(skill_dir, validate=False)

    assert parsed.loaded_files is not None
    assert len(parsed.loaded_files) == 2  # guide.md + run.py (SKILL.md excluded)

    by_path = {f.path: f for f in parsed.loaded_files}

    ref_file = by_path.get("references/guide.md")
    assert ref_file is not None
    assert ref_file.file_type == "reference"
    assert ref_file.content == "# Guide\nSome guidance."
    assert ref_file.size_bytes == len("# Guide\nSome guidance.".encode())
    assert ref_file.content_hash  # non-empty

    script_file = by_path.get("scripts/run.py")
    assert script_file is not None
    assert script_file.file_type == "script"


# ===========================================================================
# 2. File type classification
# ===========================================================================


class TestClassifyFile:
    def test_scripts_dir(self) -> None:
        assert _classify_file("scripts/build.sh", "build.sh") == "script"

    def test_references_dir(self) -> None:
        assert _classify_file("references/api.md", "api.md") == "reference"

    def test_reference_dir(self) -> None:
        assert _classify_file("reference/notes.md", "notes.md") == "reference"

    def test_assets_dir(self) -> None:
        assert _classify_file("assets/logo.txt", "logo.txt") == "asset"

    def test_license_file(self) -> None:
        assert _classify_file("LICENSE", "LICENSE") == "license"

    def test_license_txt(self) -> None:
        assert _classify_file("LICENSE.txt", "LICENSE.txt") == "license"

    def test_licence_variant(self) -> None:
        assert _classify_file("LICENCE.md", "LICENCE.md") == "license"

    def test_other_file_is_resource(self) -> None:
        assert _classify_file("helpers.py", "helpers.py") == "resource"

    def test_nested_resource(self) -> None:
        assert _classify_file("lib/utils.py", "utils.py") == "resource"


# ===========================================================================
# 3. Binary file detection
# ===========================================================================


def test_binary_files_skipped(tmp_path: Path) -> None:
    """Binary files (.png) should not appear in loaded_files."""
    skill_dir = _write_skill_dir(tmp_path)

    # Add a binary file
    (skill_dir / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    loader = SkillLoader()
    parsed = loader.load_skill(skill_dir, validate=False)

    assert parsed.loaded_files is not None
    paths = [f.path for f in parsed.loaded_files]
    assert "logo.png" not in paths


# ===========================================================================
# 4. Dotfiles skipped
# ===========================================================================


def test_dotfiles_skipped(tmp_path: Path) -> None:
    """Hidden files (dotfiles) should not appear in loaded_files."""
    skill_dir = _write_skill_dir(tmp_path)

    # Add a dotfile
    (skill_dir / ".hidden").write_text("secret")

    # Add a file inside a dotdir
    dot_dir = skill_dir / ".config"
    dot_dir.mkdir()
    (dot_dir / "settings.json").write_text("{}")

    loader = SkillLoader()
    parsed = loader.load_skill(skill_dir, validate=False)

    assert parsed.loaded_files is not None
    paths = [f.path for f in parsed.loaded_files]
    assert ".hidden" not in paths
    assert ".config/settings.json" not in paths
