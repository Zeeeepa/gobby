"""Comprehensive tests for the project_context utilities."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gobby.utils.project_context import (
    find_project_root,
    get_project_context,
    get_project_mcp_config_path,
    get_project_mcp_dir,
    get_verification_config,
)


class TestFindProjectRoot:
    """Tests for find_project_root function."""

    def test_find_project_root_from_project_dir(self, tmp_path: Path):
        """Test finding project root when starting from project directory."""
        # Create project structure
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        (gobby_dir / "project.json").write_text('{"id": "test-id"}')

        result = find_project_root(tmp_path)
        assert result is not None
        # Handle macOS symlinks (/var -> /private/var)
        assert result.resolve() == tmp_path.resolve()

    def test_find_project_root_from_nested_subdir(self, tmp_path: Path):
        """Test finding project root from deeply nested subdirectory."""
        # Create project structure
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        (gobby_dir / "project.json").write_text('{"id": "test-id"}')

        # Create deep nested directory
        deep_subdir = tmp_path / "src" / "lib" / "utils" / "helpers"
        deep_subdir.mkdir(parents=True)

        result = find_project_root(deep_subdir)
        assert result is not None
        assert result.resolve() == tmp_path.resolve()

    def test_find_project_root_not_found(self, tmp_path: Path):
        """Test finding project root when no .gobby/project.json exists."""
        result = find_project_root(tmp_path)
        assert result is None

    def test_find_project_root_with_none_uses_cwd(self):
        """Test that None cwd defaults to current working directory."""
        with patch("pathlib.Path.cwd") as mock_cwd:
            mock_path = MagicMock(spec=Path)
            mock_path.resolve.return_value = mock_path
            mock_path.parents = []
            mock_path.__truediv__ = MagicMock(return_value=MagicMock())
            # Make the project.json check return False (not found)
            project_json_mock = MagicMock()
            project_json_mock.exists.return_value = False
            mock_path.__truediv__.return_value.__truediv__ = MagicMock(
                return_value=project_json_mock
            )

            mock_cwd.return_value = mock_path

            result = find_project_root(None)

            mock_cwd.assert_called_once()
            assert result is None

    def test_find_project_root_gobby_dir_exists_but_no_project_json(self, tmp_path: Path):
        """Test that .gobby dir without project.json is not considered a project root."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        # No project.json file

        result = find_project_root(tmp_path)
        assert result is None

    def test_find_project_root_at_filesystem_root(self, tmp_path: Path):
        """Test finding project root traverses up to filesystem root without error."""
        # Create directory without .gobby
        subdir = tmp_path / "some" / "path"
        subdir.mkdir(parents=True)

        # Should return None after traversing to filesystem root
        result = find_project_root(subdir)
        assert result is None


class TestGetProjectContext:
    """Tests for get_project_context function."""

    def test_get_project_context_success(self, tmp_path: Path):
        """Test getting project context with valid project.json."""
        # Create project structure
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        project_data = {
            "id": "test-id",
            "name": "test-project",
            "created_at": "2024-01-01T00:00:00Z",
        }
        (gobby_dir / "project.json").write_text(json.dumps(project_data))

        result = get_project_context(tmp_path)

        assert result is not None
        assert result["id"] == "test-id"
        assert result["name"] == "test-project"
        assert result["created_at"] == "2024-01-01T00:00:00Z"
        # project_path should be added
        assert "project_path" in result
        assert Path(result["project_path"]).resolve() == tmp_path.resolve()

    def test_get_project_context_not_found(self, tmp_path: Path):
        """Test getting project context when no project exists."""
        result = get_project_context(tmp_path)
        assert result is None

    def test_get_project_context_invalid_json(self, tmp_path: Path):
        """Test getting project context with malformed JSON."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        (gobby_dir / "project.json").write_text("this is not valid json {{{")

        result = get_project_context(tmp_path)
        assert result is None

    def test_get_project_context_empty_file(self, tmp_path: Path):
        """Test getting project context with empty project.json file."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        (gobby_dir / "project.json").write_text("")

        result = get_project_context(tmp_path)
        assert result is None

    def test_get_project_context_with_verification(self, tmp_path: Path):
        """Test getting project context that includes verification config."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        project_data = {
            "id": "test-id",
            "name": "test-project",
            "verification": {
                "unit_tests": "pytest tests/",
                "type_check": "mypy src/",
                "lint": "ruff check src/",
            },
        }
        (gobby_dir / "project.json").write_text(json.dumps(project_data))

        result = get_project_context(tmp_path)

        assert result is not None
        assert "verification" in result
        assert result["verification"]["unit_tests"] == "pytest tests/"
        assert result["verification"]["type_check"] == "mypy src/"

    def test_get_project_context_permission_error(self, tmp_path: Path):
        """Test getting project context when file read fails."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        project_file = gobby_dir / "project.json"
        project_file.write_text('{"id": "test"}')

        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            result = get_project_context(tmp_path)

        assert result is None

    def test_get_project_context_from_subdirectory(self, tmp_path: Path):
        """Test getting project context from a subdirectory."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        project_data = {"id": "parent-id", "name": "parent-project"}
        (gobby_dir / "project.json").write_text(json.dumps(project_data))

        subdir = tmp_path / "src" / "components"
        subdir.mkdir(parents=True)

        result = get_project_context(subdir)

        assert result is not None
        assert result["id"] == "parent-id"
        assert result["name"] == "parent-project"


class TestGetProjectMcpDir:
    """Tests for get_project_mcp_dir function."""

    def test_get_project_mcp_dir_simple_name(self):
        """Test getting MCP directory with simple project name."""
        result = get_project_mcp_dir("myproject")
        expected = Path.home() / ".gobby" / "projects" / "myproject"
        assert result == expected

    def test_get_project_mcp_dir_with_spaces(self):
        """Test that spaces in project name are converted to underscores."""
        result = get_project_mcp_dir("My Project Name")
        expected = Path.home() / ".gobby" / "projects" / "my_project_name"
        assert result == expected

    def test_get_project_mcp_dir_already_lowercase(self):
        """Test that lowercase names remain unchanged except spaces."""
        result = get_project_mcp_dir("test project")
        expected = Path.home() / ".gobby" / "projects" / "test_project"
        assert result == expected

    def test_get_project_mcp_dir_mixed_case(self):
        """Test that mixed case is converted to lowercase."""
        result = get_project_mcp_dir("MyProjectName")
        expected = Path.home() / ".gobby" / "projects" / "myprojectname"
        assert result == expected

    def test_get_project_mcp_dir_with_dashes(self):
        """Test that dashes are preserved in project name."""
        result = get_project_mcp_dir("my-project")
        expected = Path.home() / ".gobby" / "projects" / "my-project"
        assert result == expected

    def test_get_project_mcp_dir_with_underscores(self):
        """Test that underscores are preserved in project name."""
        result = get_project_mcp_dir("my_project")
        expected = Path.home() / ".gobby" / "projects" / "my_project"
        assert result == expected

    def test_get_project_mcp_dir_empty_string(self):
        """Test handling of empty project name."""
        result = get_project_mcp_dir("")
        expected = Path.home() / ".gobby" / "projects" / ""
        assert result == expected


class TestGetProjectMcpConfigPath:
    """Tests for get_project_mcp_config_path function."""

    def test_get_project_mcp_config_path_simple(self):
        """Test getting MCP config path with simple name."""
        result = get_project_mcp_config_path("test-project")
        expected = Path.home() / ".gobby" / "projects" / "test-project" / ".mcp.json"
        assert result == expected

    def test_get_project_mcp_config_path_with_spaces(self):
        """Test that spaces are handled in config path."""
        result = get_project_mcp_config_path("Test Project")
        expected = Path.home() / ".gobby" / "projects" / "test_project" / ".mcp.json"
        assert result == expected

    def test_get_project_mcp_config_path_uses_get_project_mcp_dir(self):
        """Test that config path is built on top of MCP dir."""
        project_name = "sample-project"
        dir_result = get_project_mcp_dir(project_name)
        config_result = get_project_mcp_config_path(project_name)

        assert config_result == dir_result / ".mcp.json"


class TestGetVerificationConfig:
    """Tests for get_verification_config function."""

    def test_get_verification_config_success(self, tmp_path: Path):
        """Test getting verification config with valid data."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        project_data = {
            "id": "test-id",
            "name": "test-project",
            "verification": {
                "unit_tests": "uv run pytest tests/ -v",
                "type_check": "uv run mypy src/",
                "lint": "uv run ruff check src/",
                "integration": "uv run pytest tests/integration/",
                "custom": {"e2e": "playwright test"},
            },
        }
        (gobby_dir / "project.json").write_text(json.dumps(project_data))

        result = get_verification_config(tmp_path)

        assert result is not None
        assert result.unit_tests == "uv run pytest tests/ -v"
        assert result.type_check == "uv run mypy src/"
        assert result.lint == "uv run ruff check src/"
        assert result.integration == "uv run pytest tests/integration/"
        assert result.custom == {"e2e": "playwright test"}

    def test_get_verification_config_partial_fields(self, tmp_path: Path):
        """Test getting verification config with only some fields populated."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        project_data = {
            "id": "test-id",
            "name": "test-project",
            "verification": {
                "unit_tests": "pytest",
            },
        }
        (gobby_dir / "project.json").write_text(json.dumps(project_data))

        result = get_verification_config(tmp_path)

        assert result is not None
        assert result.unit_tests == "pytest"
        assert result.type_check is None
        assert result.lint is None
        assert result.integration is None
        assert result.custom == {}

    def test_get_verification_config_empty_verification(self, tmp_path: Path):
        """Test getting verification config with empty verification section."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        project_data = {
            "id": "test-id",
            "name": "test-project",
            "verification": {},
        }
        (gobby_dir / "project.json").write_text(json.dumps(project_data))

        result = get_verification_config(tmp_path)

        # Empty dict is falsy, so the function returns None
        # (the code checks `if not verification_data:`)
        assert result is None

    def test_get_verification_config_no_verification_section(self, tmp_path: Path):
        """Test getting verification config when verification key is missing."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        project_data = {
            "id": "test-id",
            "name": "test-project",
        }
        (gobby_dir / "project.json").write_text(json.dumps(project_data))

        result = get_verification_config(tmp_path)
        assert result is None

    def test_get_verification_config_no_project(self, tmp_path: Path):
        """Test getting verification config when no project exists."""
        result = get_verification_config(tmp_path)
        assert result is None

    def test_get_verification_config_invalid_verification_data(self, tmp_path: Path):
        """Test getting verification config with invalid verification structure."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        project_data = {
            "id": "test-id",
            "name": "test-project",
            "verification": {
                "unit_tests": 12345,  # Should be string or None
                "custom": "not a dict",  # Should be dict
            },
        }
        (gobby_dir / "project.json").write_text(json.dumps(project_data))

        result = get_verification_config(tmp_path)
        # Pydantic validation should fail, returning None
        assert result is None

    def test_get_verification_config_null_verification(self, tmp_path: Path):
        """Test getting verification config when verification is null."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        project_data = {
            "id": "test-id",
            "name": "test-project",
            "verification": None,
        }
        (gobby_dir / "project.json").write_text(json.dumps(project_data))

        result = get_verification_config(tmp_path)
        assert result is None

    def test_get_verification_config_with_none_cwd(self):
        """Test get_verification_config with None cwd parameter."""
        with patch(
            "gobby.utils.project_context.get_project_context", return_value=None
        ) as mock_ctx:
            result = get_verification_config(None)

            mock_ctx.assert_called_once_with(None)
            assert result is None

    def test_get_verification_config_custom_commands(self, tmp_path: Path):
        """Test verification config with multiple custom commands."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        project_data = {
            "id": "test-id",
            "name": "test-project",
            "verification": {
                "custom": {
                    "security": "bandit -r src/",
                    "format": "black --check src/",
                    "docs": "mkdocs build --strict",
                },
            },
        }
        (gobby_dir / "project.json").write_text(json.dumps(project_data))

        result = get_verification_config(tmp_path)

        assert result is not None
        assert len(result.custom) == 3
        assert result.custom["security"] == "bandit -r src/"
        assert result.custom["format"] == "black --check src/"
        assert result.custom["docs"] == "mkdocs build --strict"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_project_json_is_directory(self, tmp_path: Path):
        """Test handling when project.json is a directory instead of file."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        # Create project.json as a directory
        project_json_dir = gobby_dir / "project.json"
        project_json_dir.mkdir()

        result = get_project_context(tmp_path)
        assert result is None

    def test_unicode_project_name(self, tmp_path: Path):
        """Test project context with unicode characters in name."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        project_data = {
            "id": "test-id",
            "name": "My Project with emoji and unicode characters",
        }
        (gobby_dir / "project.json").write_text(
            json.dumps(project_data, ensure_ascii=False)
        )

        result = get_project_context(tmp_path)
        assert result is not None
        assert "emoji" in result["name"]

    def test_large_project_json(self, tmp_path: Path):
        """Test handling large project.json file."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        project_data = {
            "id": "test-id",
            "name": "test-project",
            "extra_data": "x" * 100000,  # Large string
        }
        (gobby_dir / "project.json").write_text(json.dumps(project_data))

        result = get_project_context(tmp_path)
        assert result is not None
        assert result["id"] == "test-id"

    def test_symlinked_gobby_dir(self, tmp_path: Path):
        """Test finding project root with symlinked .gobby directory."""
        # Create actual .gobby dir elsewhere
        actual_gobby = tmp_path / "actual_gobby"
        actual_gobby.mkdir()
        (actual_gobby / "project.json").write_text('{"id": "symlink-test"}')

        # Create project dir with symlink
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        symlink_path = project_dir / ".gobby"
        symlink_path.symlink_to(actual_gobby)

        result = find_project_root(project_dir)
        assert result is not None
        assert result.resolve() == project_dir.resolve()

    def test_concurrent_read_simulation(self, tmp_path: Path):
        """Test that reading project context is safe even if file changes."""
        gobby_dir = tmp_path / ".gobby"
        gobby_dir.mkdir()
        project_file = gobby_dir / "project.json"
        project_file.write_text('{"id": "original"}')

        # Read should return consistent data
        result1 = get_project_context(tmp_path)
        assert result1 is not None
        assert result1["id"] == "original"

        # Update file
        project_file.write_text('{"id": "updated"}')

        # Next read should get updated data
        result2 = get_project_context(tmp_path)
        assert result2 is not None
        assert result2["id"] == "updated"

    def test_special_characters_in_path(self, tmp_path: Path):
        """Test handling paths with special characters."""
        # Create directory with special characters
        special_dir = tmp_path / "project with spaces & special (chars)"
        special_dir.mkdir()
        gobby_dir = special_dir / ".gobby"
        gobby_dir.mkdir()
        (gobby_dir / "project.json").write_text('{"id": "special"}')

        result = find_project_root(special_dir)
        assert result is not None

        context = get_project_context(special_dir)
        assert context is not None
        assert context["id"] == "special"
