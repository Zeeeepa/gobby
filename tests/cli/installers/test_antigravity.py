"""Comprehensive tests for the Antigravity installer module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gobby.cli.installers.antigravity import install_antigravity


class TestInstallAntigravity:
    """Tests for the install_antigravity function."""

    @pytest.fixture
    def temp_project(self, temp_dir: Path) -> Path:
        """Create a temporary project directory."""
        project_path = temp_dir / "test-project"
        project_path.mkdir(parents=True)
        return project_path

    @pytest.fixture
    def mock_install_dir(self, temp_dir: Path) -> Path:
        """Create a mock install directory with required files."""
        install_dir = temp_dir / "install"
        antigravity_dir = install_dir / "antigravity"
        hooks_dir = antigravity_dir / "hooks"
        hooks_dir.mkdir(parents=True)

        # Create hook dispatcher
        dispatcher = hooks_dir / "hook_dispatcher.py"
        dispatcher.write_text("#!/usr/bin/env python\n# Mock dispatcher\n")

        # Create hooks template
        template = antigravity_dir / "hooks-template.json"
        template_content = {
            "hooks": {
                "SessionStart": [
                    {
                        "hooks": [
                            {
                                "name": "gobby-session-start",
                                "type": "command",
                                "command": 'uv run python "$PROJECT_PATH/.gemini/hooks/hook_dispatcher.py" --type=SessionStart',
                                "timeout": 30000,
                            }
                        ]
                    }
                ],
                "SessionEnd": [
                    {
                        "hooks": [
                            {
                                "name": "gobby-session-end",
                                "type": "command",
                                "command": 'uv run python "$PROJECT_PATH/.gemini/hooks/hook_dispatcher.py" --type=SessionEnd',
                                "timeout": 30000,
                            }
                        ]
                    }
                ],
            }
        }
        template.write_text(json.dumps(template_content))

        return install_dir

    @pytest.fixture
    def mock_shared_content(self) -> dict:
        """Mock return value for install_shared_content."""
        return {
            "workflows": ["workflow.yaml"],
            "plugins": ["plugin.py"],
        }

    @pytest.fixture
    def mock_cli_content(self) -> dict:
        """Mock return value for install_cli_content."""
        return {
            "workflows": ["cli-workflow.yaml"],
            "commands": ["command1.md"],
        }

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_successful_installation(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_install_dir: Path,
        mock_shared_content: dict,
        mock_cli_content: dict,
    ):
        """Test successful Antigravity installation."""
        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = mock_install_dir
        mock_shared.return_value = mock_shared_content
        mock_cli.return_value = mock_cli_content
        mock_mcp.return_value = {"success": True, "added": True, "already_configured": False}

        result = install_antigravity(temp_project)

        assert result["success"] is True
        assert result["error"] is None
        assert "SessionStart" in result["hooks_installed"]
        assert "SessionEnd" in result["hooks_installed"]
        assert result["workflows_installed"] == ["workflow.yaml", "cli-workflow.yaml"]
        assert result["commands_installed"] == ["command1.md"]
        assert result["plugins_installed"] == ["plugin.py"]
        assert result["mcp_configured"] is True
        assert result["mcp_already_configured"] is False

        # Verify directories were created
        assert (temp_project / ".antigravity").exists()
        assert (temp_project / ".antigravity" / "hooks").exists()

        # Verify dispatcher was copied
        assert (temp_project / ".antigravity" / "hooks" / "hook_dispatcher.py").exists()

        # Verify settings.json was created
        assert (temp_project / ".antigravity" / "settings.json").exists()

    @patch("gobby.cli.installers.antigravity.get_install_dir")
    def test_missing_hook_dispatcher(
        self,
        mock_get_install_dir: MagicMock,
        temp_project: Path,
        temp_dir: Path,
    ):
        """Test error when hook dispatcher is missing."""
        # Create install dir without dispatcher
        install_dir = temp_dir / "install"
        antigravity_dir = install_dir / "antigravity"
        hooks_dir = antigravity_dir / "hooks"
        hooks_dir.mkdir(parents=True)

        # Create template but not dispatcher
        template = antigravity_dir / "hooks-template.json"
        template.write_text("{}")

        mock_get_install_dir.return_value = install_dir

        result = install_antigravity(temp_project)

        assert result["success"] is False
        assert "Missing hook dispatcher" in result["error"]

    @patch("gobby.cli.installers.antigravity.get_install_dir")
    def test_missing_hooks_template(
        self,
        mock_get_install_dir: MagicMock,
        temp_project: Path,
        temp_dir: Path,
    ):
        """Test error when hooks template is missing."""
        # Create install dir with dispatcher but without template
        install_dir = temp_dir / "install"
        antigravity_dir = install_dir / "antigravity"
        hooks_dir = antigravity_dir / "hooks"
        hooks_dir.mkdir(parents=True)

        # Create dispatcher but not template
        dispatcher = hooks_dir / "hook_dispatcher.py"
        dispatcher.write_text("# dispatcher")

        mock_get_install_dir.return_value = install_dir

        result = install_antigravity(temp_project)

        assert result["success"] is False
        assert "Missing hooks template" in result["error"]

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_existing_settings_json_backup(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_install_dir: Path,
    ):
        """Test that existing settings.json is backed up."""
        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = mock_install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": False, "already_configured": True}

        # Create existing settings.json
        antigravity_path = temp_project / ".antigravity"
        antigravity_path.mkdir(parents=True)
        settings_file = antigravity_path / "settings.json"
        original_content = {"existing": "config", "other": "data"}
        settings_file.write_text(json.dumps(original_content))

        result = install_antigravity(temp_project)

        assert result["success"] is True

        # Verify backup was created
        backup_files = list(antigravity_path.glob("settings.json.*.backup"))
        assert len(backup_files) == 1

        # Verify backup contains original content
        backup_content = json.loads(backup_files[0].read_text())
        assert backup_content == original_content

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_merge_hooks_with_existing_settings(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_install_dir: Path,
    ):
        """Test that Gobby hooks merge with existing settings."""
        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = mock_install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": True}

        # Create existing settings.json with hooks
        antigravity_path = temp_project / ".antigravity"
        antigravity_path.mkdir(parents=True)
        settings_file = antigravity_path / "settings.json"
        existing_settings = {
            "general": {"someOtherSetting": True},
            "hooks": {
                "CustomHook": [{"name": "custom", "type": "command", "command": "echo hello"}]
            },
        }
        settings_file.write_text(json.dumps(existing_settings))

        result = install_antigravity(temp_project)

        assert result["success"] is True

        # Verify settings were merged
        final_settings = json.loads(settings_file.read_text())
        assert final_settings["general"]["enableHooks"] is True
        assert "SessionStart" in final_settings["hooks"]
        assert "SessionEnd" in final_settings["hooks"]
        # Custom hook should be overwritten (merged by key, not appended)

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_uv_path_fallback(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_install_dir: Path,
    ):
        """Test uv path falls back to 'uv' when not found in PATH."""
        mock_which.return_value = None  # uv not found
        mock_get_install_dir.return_value = mock_install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": True}

        result = install_antigravity(temp_project)

        assert result["success"] is True

        # Verify settings use bare 'uv' (no path replacement)
        settings = json.loads((temp_project / ".antigravity" / "settings.json").read_text())
        hook_cmd = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        assert "uv run python" in hook_cmd

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_uv_path_substitution(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_install_dir: Path,
    ):
        """Test uv path is substituted when found in a non-default location."""
        mock_which.return_value = "/custom/path/to/uv"
        mock_get_install_dir.return_value = mock_install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": True}

        result = install_antigravity(temp_project)

        assert result["success"] is True

        # Verify settings use custom uv path
        settings = json.loads((temp_project / ".antigravity" / "settings.json").read_text())
        hook_cmd = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        assert "/custom/path/to/uv run python" in hook_cmd

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_project_path_substitution(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_install_dir: Path,
    ):
        """Test $PROJECT_PATH is substituted with absolute project path."""
        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = mock_install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": True}

        result = install_antigravity(temp_project)

        assert result["success"] is True

        # Verify $PROJECT_PATH is replaced with actual path
        settings = json.loads((temp_project / ".antigravity" / "settings.json").read_text())
        hook_cmd = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        assert str(temp_project.resolve()) in hook_cmd
        assert "$PROJECT_PATH" not in hook_cmd

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_dispatcher_is_executable(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_install_dir: Path,
    ):
        """Test that copied hook dispatcher is made executable."""
        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = mock_install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": True}

        result = install_antigravity(temp_project)

        assert result["success"] is True

        dispatcher = temp_project / ".antigravity" / "hooks" / "hook_dispatcher.py"
        assert dispatcher.exists()
        # Check executable bit is set (mode 755 = 0o755)
        assert dispatcher.stat().st_mode & 0o755 == 0o755

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_existing_dispatcher_replaced(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_install_dir: Path,
    ):
        """Test that existing dispatcher is replaced."""
        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = mock_install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": True}

        # Create existing dispatcher
        hooks_dir = temp_project / ".antigravity" / "hooks"
        hooks_dir.mkdir(parents=True)
        existing_dispatcher = hooks_dir / "hook_dispatcher.py"
        existing_dispatcher.write_text("# old dispatcher content")

        result = install_antigravity(temp_project)

        assert result["success"] is True

        # Verify dispatcher was replaced
        dispatcher = hooks_dir / "hook_dispatcher.py"
        assert dispatcher.read_text() == "#!/usr/bin/env python\n# Mock dispatcher\n"

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_mcp_already_configured(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_install_dir: Path,
    ):
        """Test handling when MCP is already configured."""
        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = mock_install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": False, "already_configured": True}

        result = install_antigravity(temp_project)

        assert result["success"] is True
        assert result["mcp_configured"] is False
        assert result["mcp_already_configured"] is True

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_mcp_configuration_failure_non_fatal(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_install_dir: Path,
    ):
        """Test that MCP configuration failure is non-fatal."""
        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = mock_install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": False, "error": "Permission denied"}

        result = install_antigravity(temp_project)

        # Installation should still succeed
        assert result["success"] is True
        assert result["mcp_configured"] is False
        assert result["mcp_already_configured"] is False

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_invalid_existing_settings_json(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_install_dir: Path,
    ):
        """Test handling of invalid JSON in existing settings.json."""
        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = mock_install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": True}

        # Create invalid settings.json
        antigravity_path = temp_project / ".antigravity"
        antigravity_path.mkdir(parents=True)
        settings_file = antigravity_path / "settings.json"
        settings_file.write_text("{ invalid json }")

        result = install_antigravity(temp_project)

        # Should succeed, treating invalid JSON as empty
        assert result["success"] is True

        # Verify settings has been overwritten with valid content
        final_settings = json.loads(settings_file.read_text())
        assert "hooks" in final_settings
        assert final_settings["general"]["enableHooks"] is True

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_enables_hooks_in_general_settings(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_install_dir: Path,
    ):
        """Test that enableHooks is set to True in general settings."""
        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = mock_install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": True}

        result = install_antigravity(temp_project)

        assert result["success"] is True

        settings = json.loads((temp_project / ".antigravity" / "settings.json").read_text())
        assert settings["general"]["enableHooks"] is True

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_result_structure(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_install_dir: Path,
    ):
        """Test that result dictionary has all expected keys."""
        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = mock_install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": True}

        result = install_antigravity(temp_project)

        # Check all expected keys exist
        expected_keys = {
            "success",
            "hooks_installed",
            "workflows_installed",
            "commands_installed",
            "plugins_installed",
            "mcp_configured",
            "mcp_already_configured",
            "error",
        }
        assert set(result.keys()) == expected_keys

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_empty_shared_plugins(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_install_dir: Path,
    ):
        """Test handling when shared content has no plugins key."""
        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = mock_install_dir
        # Return dict without plugins key
        mock_shared.return_value = {"workflows": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": True}

        result = install_antigravity(temp_project)

        assert result["success"] is True
        # plugins_installed should be None/empty when not provided
        assert result.get("plugins_installed") is None or result.get("plugins_installed") == []


class TestInstallAntigravityMCPPath:
    """Tests for MCP configuration path in install_antigravity."""

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_mcp_config_path(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_dir: Path,
    ):
        """Test that MCP config uses correct path."""
        project_path = temp_dir / "project"
        project_path.mkdir()

        install_dir = temp_dir / "install"
        antigravity_dir = install_dir / "antigravity"
        hooks_dir = antigravity_dir / "hooks"
        hooks_dir.mkdir(parents=True)

        # Create required files
        (hooks_dir / "hook_dispatcher.py").write_text("# dispatcher")
        (antigravity_dir / "hooks-template.json").write_text('{"hooks": {}}')

        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": True}

        install_antigravity(project_path)

        # Verify configure_mcp_server_json was called with correct path
        mock_mcp.assert_called_once()
        call_args = mock_mcp.call_args[0]
        expected_path = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
        assert call_args[0] == expected_path


class TestInstallAntigravityEdgeCases:
    """Edge case tests for install_antigravity."""

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_deeply_nested_project_path(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_dir: Path,
    ):
        """Test installation in deeply nested project path."""
        # Create deeply nested project
        project_path = temp_dir / "a" / "b" / "c" / "d" / "project"
        project_path.mkdir(parents=True)

        install_dir = temp_dir / "install"
        antigravity_dir = install_dir / "antigravity"
        hooks_dir = antigravity_dir / "hooks"
        hooks_dir.mkdir(parents=True)

        (hooks_dir / "hook_dispatcher.py").write_text("# dispatcher")
        template_content = {"hooks": {"Test": [{"hooks": [{"command": "$PROJECT_PATH/test"}]}]}}
        (antigravity_dir / "hooks-template.json").write_text(json.dumps(template_content))

        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": True}

        result = install_antigravity(project_path)

        assert result["success"] is True
        assert (project_path / ".antigravity" / "settings.json").exists()

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_project_path_with_spaces(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_dir: Path,
    ):
        """Test installation in project path with spaces."""
        project_path = temp_dir / "my project with spaces"
        project_path.mkdir(parents=True)

        install_dir = temp_dir / "install"
        antigravity_dir = install_dir / "antigravity"
        hooks_dir = antigravity_dir / "hooks"
        hooks_dir.mkdir(parents=True)

        (hooks_dir / "hook_dispatcher.py").write_text("# dispatcher")
        template_content = {"hooks": {"Test": [{"hooks": [{"command": "$PROJECT_PATH/test"}]}]}}
        (antigravity_dir / "hooks-template.json").write_text(json.dumps(template_content))

        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": True}

        result = install_antigravity(project_path)

        assert result["success"] is True

        # Verify path with spaces is properly embedded in settings
        settings = json.loads((project_path / ".antigravity" / "settings.json").read_text())
        hook_cmd = settings["hooks"]["Test"][0]["hooks"][0]["command"]
        assert "my project with spaces" in hook_cmd

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_cli_content")
    @patch("gobby.cli.installers.antigravity.install_shared_content")
    @patch("gobby.cli.installers.antigravity.get_install_dir")
    @patch("gobby.cli.installers.antigravity.which")
    def test_multiple_hook_types(
        self,
        mock_which: MagicMock,
        mock_get_install_dir: MagicMock,
        mock_shared: MagicMock,
        mock_cli: MagicMock,
        mock_mcp: MagicMock,
        temp_dir: Path,
    ):
        """Test installation with multiple hook types."""
        project_path = temp_dir / "project"
        project_path.mkdir()

        install_dir = temp_dir / "install"
        antigravity_dir = install_dir / "antigravity"
        hooks_dir = antigravity_dir / "hooks"
        hooks_dir.mkdir(parents=True)

        (hooks_dir / "hook_dispatcher.py").write_text("# dispatcher")

        # Template with many hook types
        template_content = {
            "hooks": {
                "SessionStart": [{"hooks": [{"name": "h1", "command": "cmd1"}]}],
                "SessionEnd": [{"hooks": [{"name": "h2", "command": "cmd2"}]}],
                "BeforeAgent": [{"hooks": [{"name": "h3", "command": "cmd3"}]}],
                "AfterAgent": [{"hooks": [{"name": "h4", "command": "cmd4"}]}],
                "BeforeTool": [{"hooks": [{"name": "h5", "command": "cmd5"}]}],
            }
        }
        (antigravity_dir / "hooks-template.json").write_text(json.dumps(template_content))

        mock_which.return_value = "/usr/bin/uv"
        mock_get_install_dir.return_value = install_dir
        mock_shared.return_value = {"workflows": [], "plugins": []}
        mock_cli.return_value = {"workflows": [], "commands": []}
        mock_mcp.return_value = {"success": True, "added": True}

        result = install_antigravity(project_path)

        assert result["success"] is True
        assert len(result["hooks_installed"]) == 5
        assert "SessionStart" in result["hooks_installed"]
        assert "SessionEnd" in result["hooks_installed"]
        assert "BeforeAgent" in result["hooks_installed"]
        assert "AfterAgent" in result["hooks_installed"]
        assert "BeforeTool" in result["hooks_installed"]
