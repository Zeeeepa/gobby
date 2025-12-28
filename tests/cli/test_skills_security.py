import pytest

from gobby.cli.skills import _read_safe_file


def test_read_safe_file_valid_relative(tmp_path):
    # Setup
    valid_file = tmp_path / "instructions.md"
    valid_file.write_text("Valid content")

    # Execute
    content = _read_safe_file("instructions.md", base_dir=tmp_path)

    # Verify
    assert content == "Valid content"


def test_read_safe_file_traversal_attempt(tmp_path):
    # Setup
    base_dir = tmp_path / "base"
    base_dir.mkdir()

    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("Secret")

    # Execute & Verify
    with pytest.raises(ValueError, match="Path traversal detected"):
        _read_safe_file("../secret.txt", base_dir=base_dir)


def test_read_safe_file_absolute_path_outside(tmp_path):
    # Setup
    base_dir = tmp_path / "base"
    base_dir.mkdir()

    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("Secret")

    # Execute & Verify
    # Absolute path to file outside base_dir
    with pytest.raises(ValueError, match="Path traversal detected"):
        _read_safe_file(str(outside_file), base_dir=base_dir)


def test_read_safe_file_absolute_path_inside(tmp_path):
    # Setup
    base_dir = tmp_path / "base"
    base_dir.mkdir()

    inside_file = base_dir / "safe.txt"
    inside_file.write_text("Safe")

    # Execute
    content = _read_safe_file(str(inside_file), base_dir=base_dir)

    # Verify
    assert content == "Safe"


def test_read_safe_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        _read_safe_file("nonexistent.txt", base_dir=tmp_path)
