"""Comprehensive tests for the Codex CLI installer module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


class TestInstallCodexNotify:
    """Tests for install_codex_notify function."""

    @pytest.fixture
    def mock_home(self, temp_dir: Path):
        """Mock Path.home() to return temp directory."""
        with patch.object(Path, "home", return_value=temp_dir):
            yield temp_dir

    @pytest.fixture
    def mock_install_dir(self, temp_dir: Path):
        """Create a mock install directory with source files."""
        install_dir = temp_dir / "install"
        codex_hooks = install_dir / "codex" / "hooks"
        codex_hooks.mkdir(parents=True)

        # Create the source hook_dispatcher.py
        hook_dispatcher = codex_hooks / "hook_dispatcher.py"
        hook_dispatcher.write_text("#!/usr/bin/env python3\n# Hook dispatcher\n")

        with patch("gobby.cli.installers.codex.get_install_dir", return_value=install_dir):
            yield install_dir

    @pytest.fixture
    def mock_shared_content(self):
        """Mock the shared content installation functions."""
        with (
            patch("gobby.cli.installers.codex.install_shared_content") as mock_shared,
            patch("gobby.cli.installers.codex.install_cli_content") as mock_cli,
        ):
            mock_shared.return_value = {
                "workflows": ["workflow1.yaml"],
                "plugins": ["plugin1.py"],
            }
            mock_cli.return_value = {
                "workflows": ["codex-workflow.yaml"],
                "commands": ["cmd1"],
            }
            yield mock_shared, mock_cli

    @pytest.fixture
    def mock_mcp_configure(self):
        """Mock the MCP server configuration."""
        with patch("gobby.cli.installers.codex.configure_mcp_server_toml") as mock:
            mock.return_value = {"success": True, "added": True, "already_configured": False}
            yield mock

    def test_install_success_new_config(
        self,
        mock_home: Path,
        mock_install_dir: Path,
        mock_shared_content,
        mock_mcp_configure,
    ) -> None:
        """Test successful installation with a new config file."""
        from gobby.cli.installers.codex import install_codex_notify

        result = install_codex_notify()

        assert result["success"] is True
        assert result["error"] is None
        assert len(result["files_installed"]) == 1
        assert "hook_dispatcher.py" in result["files_installed"][0]
        assert result["config_updated"] is True
        assert result["mcp_configured"] is True

        # Verify hook file was installed
        hook_path = mock_home / ".gobby" / "hooks" / "codex" / "hook_dispatcher.py"
        assert hook_path.exists()

        # Verify config was created
        config_path = mock_home / ".codex" / "config.toml"
        assert config_path.exists()
        config_content = config_path.read_text()
        assert "notify" in config_content

    def test_install_success_existing_config_no_notify(
        self,
        mock_home: Path,
        mock_install_dir: Path,
        mock_shared_content,
        mock_mcp_configure,
    ) -> None:
        """Test installation when config exists but has no notify line."""
        from gobby.cli.installers.codex import install_codex_notify

        # Create existing config without notify
        codex_dir = mock_home / ".codex"
        codex_dir.mkdir(parents=True)
        config_path = codex_dir / "config.toml"
        config_path.write_text('model = "gpt-4"\n')

        result = install_codex_notify()

        assert result["success"] is True
        assert result["config_updated"] is True

        # Verify notify was added
        config_content = config_path.read_text()
        assert "notify" in config_content
        assert 'model = "gpt-4"' in config_content

        # Verify backup was created
        backup_path = config_path.with_suffix(".toml.bak")
        assert backup_path.exists()

    def test_install_success_existing_config_with_notify(
        self,
        mock_home: Path,
        mock_install_dir: Path,
        mock_shared_content,
        mock_mcp_configure,
    ) -> None:
        """Test installation when config already has a notify line."""
        from gobby.cli.installers.codex import install_codex_notify

        # Create existing config with old notify
        codex_dir = mock_home / ".codex"
        codex_dir.mkdir(parents=True)
        config_path = codex_dir / "config.toml"
        config_path.write_text('notify = ["old", "command"]\n')

        result = install_codex_notify()

        assert result["success"] is True
        assert result["config_updated"] is True

        # Verify notify was updated (not duplicated)
        config_content = config_path.read_text()
        assert config_content.count("notify") == 1
        assert "hook_dispatcher.py" in config_content

    def test_install_replaces_existing_hook(
        self,
        mock_home: Path,
        mock_install_dir: Path,
        mock_shared_content,
        mock_mcp_configure,
    ) -> None:
        """Test that existing hook file is replaced."""
        from gobby.cli.installers.codex import install_codex_notify

        # Create existing hook file
        hook_dir = mock_home / ".gobby" / "hooks" / "codex"
        hook_dir.mkdir(parents=True)
        existing_hook = hook_dir / "hook_dispatcher.py"
        existing_hook.write_text("# Old hook content")

        result = install_codex_notify()

        assert result["success"] is True

        # Verify hook was replaced
        new_content = existing_hook.read_text()
        assert "# Hook dispatcher" in new_content

    def test_install_missing_source_file(self, mock_home: Path, temp_dir: Path) -> None:
        """Test installation fails when source file is missing."""
        from gobby.cli.installers.codex import install_codex_notify

        # Create empty install directory without hook_dispatcher.py
        install_dir = temp_dir / "empty_install"
        install_dir.mkdir(parents=True)

        with patch("gobby.cli.installers.codex.get_install_dir", return_value=install_dir):
            result = install_codex_notify()

        assert result["success"] is False
        assert "Missing source file" in result["error"]

    def test_install_mcp_config_failure_non_fatal(
        self,
        mock_home: Path,
        mock_install_dir: Path,
        mock_shared_content,
    ) -> None:
        """Test that MCP config failure is non-fatal."""
        from gobby.cli.installers.codex import install_codex_notify

        with patch("gobby.cli.installers.codex.configure_mcp_server_toml") as mock_mcp:
            mock_mcp.return_value = {"success": False, "error": "MCP config error"}

            result = install_codex_notify()

        assert result["success"] is True
        assert result["mcp_configured"] is False

    def test_install_mcp_already_configured(
        self,
        mock_home: Path,
        mock_install_dir: Path,
        mock_shared_content,
    ) -> None:
        """Test detection of already configured MCP server."""
        from gobby.cli.installers.codex import install_codex_notify

        with patch("gobby.cli.installers.codex.configure_mcp_server_toml") as mock_mcp:
            mock_mcp.return_value = {
                "success": True,
                "added": False,
                "already_configured": True,
            }

            result = install_codex_notify()

        assert result["success"] is True
        assert result["mcp_configured"] is False
        assert result["mcp_already_configured"] is True

    def test_install_workflows_merged(
        self,
        mock_home: Path,
        mock_install_dir: Path,
        mock_mcp_configure,
    ) -> None:
        """Test that shared and CLI-specific workflows are merged."""
        from gobby.cli.installers.codex import install_codex_notify

        with (
            patch("gobby.cli.installers.codex.install_shared_content") as mock_shared,
            patch("gobby.cli.installers.codex.install_cli_content") as mock_cli,
        ):
            mock_shared.return_value = {
                "workflows": ["shared-workflow"],
                "plugins": ["plugin.py"],
            }
            mock_cli.return_value = {
                "workflows": ["cli-workflow"],
                "commands": ["command1"],
            }

            result = install_codex_notify()

        assert result["success"] is True
        assert result["workflows_installed"] == ["shared-workflow", "cli-workflow"]
        assert result["commands_installed"] == ["command1"]
        assert result["plugins_installed"] == ["plugin.py"]

    def test_install_config_write_exception(
        self,
        mock_home: Path,
        mock_install_dir: Path,
        mock_shared_content,
        mock_mcp_configure,
    ) -> None:
        """Test handling of config write exception."""
        from gobby.cli.installers.codex import install_codex_notify

        # Create config directory first
        codex_dir = mock_home / ".codex"
        codex_dir.mkdir(parents=True)

        # Make the config path a directory to cause a write error
        config_path = codex_dir / "config.toml"
        config_path.mkdir()

        result = install_codex_notify()

        assert result["success"] is False
        assert "Failed to update Codex config" in result["error"]

    def test_install_hook_file_permissions(
        self,
        mock_home: Path,
        mock_install_dir: Path,
        mock_shared_content,
        mock_mcp_configure,
    ) -> None:
        """Test that installed hook file has executable permissions."""
        import stat

        from gobby.cli.installers.codex import install_codex_notify

        result = install_codex_notify()

        assert result["success"] is True

        hook_path = mock_home / ".gobby" / "hooks" / "codex" / "hook_dispatcher.py"
        mode = hook_path.stat().st_mode
        assert mode & stat.S_IXUSR  # Owner execute permission


class TestUninstallCodexNotify:
    """Tests for uninstall_codex_notify function."""

    @pytest.fixture
    def mock_home(self, temp_dir: Path):
        """Mock Path.home() to return temp directory."""
        with patch.object(Path, "home", return_value=temp_dir):
            yield temp_dir

    @pytest.fixture
    def mock_mcp_remove(self):
        """Mock the MCP server removal function."""
        with patch("gobby.cli.installers.codex.remove_mcp_server_toml") as mock:
            mock.return_value = {"success": True, "removed": True}
            yield mock

    def test_uninstall_success_full(self, mock_home: Path, mock_mcp_remove) -> None:
        """Test successful uninstallation with all components present."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        # Set up installed files
        hook_dir = mock_home / ".gobby" / "hooks" / "codex"
        hook_dir.mkdir(parents=True)
        hook_file = hook_dir / "hook_dispatcher.py"
        hook_file.write_text("# Hook content")

        config_dir = mock_home / ".codex"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"
        config_path.write_text('notify = ["python3", "/path/to/hook"]\nmodel = "gpt-4"\n')

        result = uninstall_codex_notify()

        assert result["success"] is True
        assert result["error"] is None
        assert len(result["files_removed"]) == 1
        assert "hook_dispatcher.py" in result["files_removed"][0]
        assert result["config_updated"] is True
        assert result["mcp_removed"] is True

        # Verify hook file was removed
        assert not hook_file.exists()

        # Verify notify line was removed but other config preserved
        config_content = config_path.read_text()
        assert "notify" not in config_content
        assert 'model = "gpt-4"' in config_content

    def test_uninstall_no_hook_file(self, mock_home: Path, mock_mcp_remove) -> None:
        """Test uninstallation when hook file doesn't exist."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        # Only set up config, no hook file
        config_dir = mock_home / ".codex"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"
        config_path.write_text('notify = ["python3", "/path/to/hook"]\n')

        result = uninstall_codex_notify()

        assert result["success"] is True
        assert len(result["files_removed"]) == 0
        assert result["config_updated"] is True

    def test_uninstall_no_config_file(self, mock_home: Path, mock_mcp_remove) -> None:
        """Test uninstallation when config file doesn't exist."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        # Only set up hook file, no config
        hook_dir = mock_home / ".gobby" / "hooks" / "codex"
        hook_dir.mkdir(parents=True)
        hook_file = hook_dir / "hook_dispatcher.py"
        hook_file.write_text("# Hook content")

        result = uninstall_codex_notify()

        assert result["success"] is True
        assert len(result["files_removed"]) == 1
        assert result["config_updated"] is False

    def test_uninstall_config_without_notify(self, mock_home: Path, mock_mcp_remove) -> None:
        """Test uninstallation when config exists but has no notify line."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        config_dir = mock_home / ".codex"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"
        config_path.write_text('model = "gpt-4"\n')

        result = uninstall_codex_notify()

        assert result["success"] is True
        assert result["config_updated"] is False

        # Verify config was not modified
        config_content = config_path.read_text()
        assert config_content == 'model = "gpt-4"\n'

    def test_uninstall_removes_empty_parent_dir(self, mock_home: Path, mock_mcp_remove) -> None:
        """Test that empty parent directories are removed after uninstall."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        # Set up hook file as only item in directory
        hook_dir = mock_home / ".gobby" / "hooks" / "codex"
        hook_dir.mkdir(parents=True)
        hook_file = hook_dir / "hook_dispatcher.py"
        hook_file.write_text("# Hook content")

        result = uninstall_codex_notify()

        assert result["success"] is True

        # Verify hook directory was removed since it's now empty
        assert not hook_dir.exists()

    def test_uninstall_rmdir_exception_ignored(self, mock_home: Path, mock_mcp_remove) -> None:
        """Test that rmdir exceptions are silently ignored."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        # Set up hook file
        hook_dir = mock_home / ".gobby" / "hooks" / "codex"
        hook_dir.mkdir(parents=True)
        hook_file = hook_dir / "hook_dispatcher.py"
        hook_file.write_text("# Hook content")

        # Create a file in the directory that would prevent rmdir
        # We simulate the exception by mocking rmdir to raise
        with patch("pathlib.Path.rmdir", side_effect=OSError("Cannot remove")):
            result = uninstall_codex_notify()

        # Should still succeed despite rmdir failure
        assert result["success"] is True
        assert len(result["files_removed"]) == 1

    def test_uninstall_keeps_non_empty_parent_dir(self, mock_home: Path, mock_mcp_remove) -> None:
        """Test that non-empty parent directories are preserved."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        # Set up hook file with other files in directory
        hook_dir = mock_home / ".gobby" / "hooks" / "codex"
        hook_dir.mkdir(parents=True)
        hook_file = hook_dir / "hook_dispatcher.py"
        hook_file.write_text("# Hook content")
        other_file = hook_dir / "other_file.py"
        other_file.write_text("# Other content")

        result = uninstall_codex_notify()

        assert result["success"] is True

        # Verify hook directory still exists
        assert hook_dir.exists()
        assert other_file.exists()

    def test_uninstall_creates_backup(self, mock_home: Path, mock_mcp_remove) -> None:
        """Test that config backup is created before modification."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        config_dir = mock_home / ".codex"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"
        original_content = 'notify = ["python3", "/path/to/hook"]\nmodel = "gpt-4"\n'
        config_path.write_text(original_content)

        result = uninstall_codex_notify()

        assert result["success"] is True

        # Verify backup was created
        backup_path = config_path.with_suffix(".toml.bak")
        assert backup_path.exists()
        assert backup_path.read_text() == original_content

    def test_uninstall_cleans_multiple_blank_lines(self, mock_home: Path, mock_mcp_remove) -> None:
        """Test that multiple blank lines are cleaned up after removal."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        config_dir = mock_home / ".codex"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"
        config_path.write_text('model = "gpt-4"\n\n\nnotify = ["cmd"]\n\n\nother = "value"\n')

        result = uninstall_codex_notify()

        assert result["success"] is True

        # Verify multiple blank lines were reduced
        config_content = config_path.read_text()
        assert "\n\n\n" not in config_content

    def test_uninstall_config_read_exception(self, mock_home: Path, mock_mcp_remove) -> None:
        """Test handling of config read exception."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        config_dir = mock_home / ".codex"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"
        # Create a directory instead of file to cause read error
        config_path.mkdir()

        result = uninstall_codex_notify()

        assert result["success"] is False
        assert "Failed to update Codex config" in result["error"]

    def test_uninstall_nothing_installed(self, mock_home: Path, mock_mcp_remove) -> None:
        """Test uninstallation when nothing is installed."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        result = uninstall_codex_notify()

        assert result["success"] is True
        assert len(result["files_removed"]) == 0
        assert result["config_updated"] is False

    def test_uninstall_mcp_removal_failure_non_fatal(self, mock_home: Path) -> None:
        """Test that MCP removal failure is non-fatal."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        with patch("gobby.cli.installers.codex.remove_mcp_server_toml") as mock_mcp:
            mock_mcp.return_value = {"success": False, "error": "MCP removal error"}

            result = uninstall_codex_notify()

        assert result["success"] is True
        assert result["mcp_removed"] is False


class TestNotifyLineFormat:
    """Tests for the notify line format in config.toml."""

    @pytest.fixture
    def mock_home(self, temp_dir: Path):
        """Mock Path.home() to return temp directory."""
        with patch.object(Path, "home", return_value=temp_dir):
            yield temp_dir

    @pytest.fixture
    def mock_install_dir(self, temp_dir: Path):
        """Create a mock install directory with source files."""
        install_dir = temp_dir / "install"
        codex_hooks = install_dir / "codex" / "hooks"
        codex_hooks.mkdir(parents=True)

        hook_dispatcher = codex_hooks / "hook_dispatcher.py"
        hook_dispatcher.write_text("# Hook")

        with patch("gobby.cli.installers.codex.get_install_dir", return_value=install_dir):
            yield install_dir

    @pytest.fixture
    def mock_deps(self):
        """Mock shared content and MCP configuration."""
        with (
            patch("gobby.cli.installers.codex.install_shared_content") as mock_shared,
            patch("gobby.cli.installers.codex.install_cli_content") as mock_cli,
            patch("gobby.cli.installers.codex.configure_mcp_server_toml") as mock_mcp,
        ):
            mock_shared.return_value = {"workflows": [], "plugins": []}
            mock_cli.return_value = {"workflows": [], "commands": []}
            mock_mcp.return_value = {"success": True, "added": True}
            yield

    def test_notify_line_is_valid_json(
        self,
        mock_home: Path,
        mock_install_dir: Path,
        mock_deps,
    ) -> None:
        """Test that the notify line contains valid JSON array."""
        from gobby.cli.installers.codex import install_codex_notify

        result = install_codex_notify()

        assert result["success"] is True

        config_path = mock_home / ".codex" / "config.toml"
        config_content = config_path.read_text()

        # Extract the notify value
        for line in config_content.split("\n"):
            if line.startswith("notify"):
                _, value = line.split(" = ", 1)
                parsed = json.loads(value)
                assert isinstance(parsed, list)
                assert len(parsed) == 2
                assert parsed[0] == "python3"
                assert "hook_dispatcher.py" in parsed[1]
                break

    def test_notify_line_contains_absolute_path(
        self,
        mock_home: Path,
        mock_install_dir: Path,
        mock_deps,
    ) -> None:
        """Test that the notify line contains an absolute path to the hook."""
        from gobby.cli.installers.codex import install_codex_notify

        result = install_codex_notify()

        assert result["success"] is True

        config_path = mock_home / ".codex" / "config.toml"
        config_content = config_path.read_text()

        # Verify the path in notify is absolute
        for line in config_content.split("\n"):
            if line.startswith("notify"):
                assert str(mock_home) in line
                break


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.fixture
    def mock_home(self, temp_dir: Path):
        """Mock Path.home() to return temp directory."""
        with patch.object(Path, "home", return_value=temp_dir):
            yield temp_dir

    def test_install_with_unicode_in_path(self, mock_home: Path, temp_dir: Path) -> None:
        """Test installation with unicode characters in paths."""
        from gobby.cli.installers.codex import install_codex_notify

        # Create install dir with unicode
        install_dir = temp_dir / "install"
        codex_hooks = install_dir / "codex" / "hooks"
        codex_hooks.mkdir(parents=True)
        hook_dispatcher = codex_hooks / "hook_dispatcher.py"
        hook_dispatcher.write_text("# Hook with unicode comment")

        with (
            patch("gobby.cli.installers.codex.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.codex.install_shared_content") as mock_shared,
            patch("gobby.cli.installers.codex.install_cli_content") as mock_cli,
            patch("gobby.cli.installers.codex.configure_mcp_server_toml") as mock_mcp,
        ):
            mock_shared.return_value = {"workflows": [], "plugins": []}
            mock_cli.return_value = {"workflows": [], "commands": []}
            mock_mcp.return_value = {"success": True, "added": True}

            result = install_codex_notify()

        assert result["success"] is True

    def test_install_with_empty_existing_config(self, mock_home: Path, temp_dir: Path) -> None:
        """Test installation with an empty existing config file."""
        from gobby.cli.installers.codex import install_codex_notify

        install_dir = temp_dir / "install"
        codex_hooks = install_dir / "codex" / "hooks"
        codex_hooks.mkdir(parents=True)
        hook_dispatcher = codex_hooks / "hook_dispatcher.py"
        hook_dispatcher.write_text("# Hook")

        # Create empty config
        codex_dir = mock_home / ".codex"
        codex_dir.mkdir(parents=True)
        config_path = codex_dir / "config.toml"
        config_path.write_text("")

        with (
            patch("gobby.cli.installers.codex.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.codex.install_shared_content") as mock_shared,
            patch("gobby.cli.installers.codex.install_cli_content") as mock_cli,
            patch("gobby.cli.installers.codex.configure_mcp_server_toml") as mock_mcp,
        ):
            mock_shared.return_value = {"workflows": [], "plugins": []}
            mock_cli.return_value = {"workflows": [], "commands": []}
            mock_mcp.return_value = {"success": True, "added": True}

            result = install_codex_notify()

        assert result["success"] is True
        assert result["config_updated"] is True

        # Verify config has notify line
        config_content = config_path.read_text()
        assert "notify" in config_content

    def test_install_with_whitespace_only_config(self, mock_home: Path, temp_dir: Path) -> None:
        """Test installation with a config file containing only whitespace."""
        from gobby.cli.installers.codex import install_codex_notify

        install_dir = temp_dir / "install"
        codex_hooks = install_dir / "codex" / "hooks"
        codex_hooks.mkdir(parents=True)
        hook_dispatcher = codex_hooks / "hook_dispatcher.py"
        hook_dispatcher.write_text("# Hook")

        # Create whitespace-only config
        codex_dir = mock_home / ".codex"
        codex_dir.mkdir(parents=True)
        config_path = codex_dir / "config.toml"
        config_path.write_text("   \n\n  \n")

        with (
            patch("gobby.cli.installers.codex.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.codex.install_shared_content") as mock_shared,
            patch("gobby.cli.installers.codex.install_cli_content") as mock_cli,
            patch("gobby.cli.installers.codex.configure_mcp_server_toml") as mock_mcp,
        ):
            mock_shared.return_value = {"workflows": [], "plugins": []}
            mock_cli.return_value = {"workflows": [], "commands": []}
            mock_mcp.return_value = {"success": True, "added": True}

            result = install_codex_notify()

        assert result["success"] is True
        config_content = config_path.read_text()
        # Should have just the notify line
        assert "notify" in config_content

    def test_uninstall_with_notify_at_different_positions(self, mock_home: Path) -> None:
        """Test uninstallation with notify line at different positions in config."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        config_dir = mock_home / ".codex"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"

        with patch("gobby.cli.installers.codex.remove_mcp_server_toml") as mock_mcp:
            mock_mcp.return_value = {"success": True, "removed": True}

            # Test notify at beginning
            config_path.write_text('notify = ["cmd"]\nmodel = "gpt-4"\n')
            result = uninstall_codex_notify()
            assert result["success"] is True
            assert "notify" not in config_path.read_text()

            # Test notify at end
            config_path.write_text('model = "gpt-4"\nnotify = ["cmd"]\n')
            result = uninstall_codex_notify()
            assert result["success"] is True
            assert "notify" not in config_path.read_text()

            # Test notify in middle
            config_path.write_text('model = "gpt-4"\nnotify = ["cmd"]\nother = "value"\n')
            result = uninstall_codex_notify()
            assert result["success"] is True
            assert "notify" not in config_path.read_text()

    def test_uninstall_with_indented_notify_line(self, mock_home: Path) -> None:
        """Test uninstallation with an indented notify line."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        config_dir = mock_home / ".codex"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"
        config_path.write_text('model = "gpt-4"\n  notify = ["cmd"]\n')

        with patch("gobby.cli.installers.codex.remove_mcp_server_toml") as mock_mcp:
            mock_mcp.return_value = {"success": True, "removed": True}

            result = uninstall_codex_notify()

        assert result["success"] is True
        assert result["config_updated"] is True
        # Indented notify line should be removed
        assert "notify" not in config_path.read_text()

    def test_install_updates_existing_notify_preserving_other_content(
        self, mock_home: Path, temp_dir: Path
    ) -> None:
        """Test that updating notify preserves other config content."""
        from gobby.cli.installers.codex import install_codex_notify

        install_dir = temp_dir / "install"
        codex_hooks = install_dir / "codex" / "hooks"
        codex_hooks.mkdir(parents=True)
        hook_dispatcher = codex_hooks / "hook_dispatcher.py"
        hook_dispatcher.write_text("# Hook")

        # Create config with various settings
        codex_dir = mock_home / ".codex"
        codex_dir.mkdir(parents=True)
        config_path = codex_dir / "config.toml"
        original_config = """# Comment at top
model = "gpt-4"
notify = ["old", "command"]
temperature = 0.7

[advanced]
debug = true
"""
        config_path.write_text(original_config)

        with (
            patch("gobby.cli.installers.codex.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.codex.install_shared_content") as mock_shared,
            patch("gobby.cli.installers.codex.install_cli_content") as mock_cli,
            patch("gobby.cli.installers.codex.configure_mcp_server_toml") as mock_mcp,
        ):
            mock_shared.return_value = {"workflows": [], "plugins": []}
            mock_cli.return_value = {"workflows": [], "commands": []}
            mock_mcp.return_value = {"success": True, "added": True}

            result = install_codex_notify()

        assert result["success"] is True

        new_config = config_path.read_text()
        # Verify other content is preserved
        assert "# Comment at top" in new_config
        assert 'model = "gpt-4"' in new_config
        assert "temperature = 0.7" in new_config
        assert "[advanced]" in new_config
        assert "debug = true" in new_config
        # Verify notify was updated
        assert "hook_dispatcher.py" in new_config
        # Verify old notify is gone
        assert '["old", "command"]' not in new_config

    def test_install_config_unchanged_when_notify_already_correct(
        self, mock_home: Path, temp_dir: Path
    ) -> None:
        """Test that config_updated is False when notify line is already correct."""
        from gobby.cli.installers.codex import install_codex_notify

        install_dir = temp_dir / "install"
        codex_hooks = install_dir / "codex" / "hooks"
        codex_hooks.mkdir(parents=True)
        hook_dispatcher = codex_hooks / "hook_dispatcher.py"
        hook_dispatcher.write_text("# Hook")

        # Create config with the exact notify line that would be written
        codex_dir = mock_home / ".codex"
        codex_dir.mkdir(parents=True)
        config_path = codex_dir / "config.toml"
        target_notify = mock_home / ".gobby" / "hooks" / "codex" / "hook_dispatcher.py"
        # Create the hook directory first so we know the exact path
        hook_dir = mock_home / ".gobby" / "hooks" / "codex"
        hook_dir.mkdir(parents=True)

        # Create config with existing notify that matches what would be written
        import json

        notify_command = ["python3", str(target_notify)]
        notify_line = f"notify = {json.dumps(notify_command)}\n"
        config_path.write_text(notify_line)

        with (
            patch("gobby.cli.installers.codex.get_install_dir", return_value=install_dir),
            patch("gobby.cli.installers.codex.install_shared_content") as mock_shared,
            patch("gobby.cli.installers.codex.install_cli_content") as mock_cli,
            patch("gobby.cli.installers.codex.configure_mcp_server_toml") as mock_mcp,
        ):
            mock_shared.return_value = {"workflows": [], "plugins": []}
            mock_cli.return_value = {"workflows": [], "commands": []}
            mock_mcp.return_value = {"success": True, "added": True}

            result = install_codex_notify()

        assert result["success"] is True
        # Config was not updated since notify line was already correct
        assert result["config_updated"] is False

    def test_uninstall_config_unchanged_when_removing_results_in_same_content(
        self, mock_home: Path
    ) -> None:
        """Test that config_updated is False when removal results in same content."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        # This is an edge case where the regex matches but sub results in same string
        # which is practically impossible but we test the branch anyway
        config_dir = mock_home / ".codex"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"

        # Set up hook so uninstall has something to remove
        hook_dir = mock_home / ".gobby" / "hooks" / "codex"
        hook_dir.mkdir(parents=True)
        hook_file = hook_dir / "hook_dispatcher.py"
        hook_file.write_text("# Hook")

        # Config with only whitespace and newlines - after removing nothing meaningful
        # the content might effectively be the same
        config_path.write_text('model = "gpt-4"\n')  # No notify line

        with patch("gobby.cli.installers.codex.remove_mcp_server_toml") as mock_mcp:
            mock_mcp.return_value = {"success": True, "removed": True}

            result = uninstall_codex_notify()

        assert result["success"] is True
        # Config not updated since there was no notify line to remove
        assert result["config_updated"] is False

    def test_uninstall_notify_removal_produces_identical_content(self, mock_home: Path) -> None:
        """Test edge case where regex matches but substitution produces same content.

        This tests the branch at line 166 where updated == existing after substitution.
        While this is nearly impossible in practice (regex match + no change),
        we can test it by mocking the regex pattern to achieve this.
        """
        import re

        from gobby.cli.installers.codex import uninstall_codex_notify

        config_dir = mock_home / ".codex"
        config_dir.mkdir(parents=True)
        config_path = config_dir / "config.toml"

        # Set up a config with a notify line
        original_content = 'notify = ["cmd"]\nmodel = "gpt-4"\n'
        config_path.write_text(original_content)

        # Mock re.compile to return a pattern that matches but sub returns original
        original_compile = re.compile

        class MockPattern:
            def search(self, text):
                return True  # Pretend to match

            def sub(self, replacement, text):
                return text  # But return same text

        def mock_compile(pattern, *args, **kwargs):
            if "notify" in pattern:
                return MockPattern()
            return original_compile(pattern, *args, **kwargs)

        with (
            patch("gobby.cli.installers.codex.remove_mcp_server_toml") as mock_mcp,
            patch("gobby.cli.installers.codex.re.compile", side_effect=mock_compile),
        ):
            mock_mcp.return_value = {"success": True, "removed": True}

            result = uninstall_codex_notify()

        assert result["success"] is True
        # Config should NOT be updated since sub() returned same content
        assert result["config_updated"] is False


class TestResultStructure:
    """Tests for the result dictionary structure."""

    @pytest.fixture
    def mock_home(self, temp_dir: Path):
        """Mock Path.home() to return temp directory."""
        with patch.object(Path, "home", return_value=temp_dir):
            yield temp_dir

    @pytest.fixture
    def mock_install_dir(self, temp_dir: Path):
        """Create a mock install directory with source files."""
        install_dir = temp_dir / "install"
        codex_hooks = install_dir / "codex" / "hooks"
        codex_hooks.mkdir(parents=True)
        hook_dispatcher = codex_hooks / "hook_dispatcher.py"
        hook_dispatcher.write_text("# Hook")

        with patch("gobby.cli.installers.codex.get_install_dir", return_value=install_dir):
            yield install_dir

    def test_install_result_has_all_keys(self, mock_home: Path, mock_install_dir: Path) -> None:
        """Test that install result contains all expected keys."""
        from gobby.cli.installers.codex import install_codex_notify

        with (
            patch("gobby.cli.installers.codex.install_shared_content") as mock_shared,
            patch("gobby.cli.installers.codex.install_cli_content") as mock_cli,
            patch("gobby.cli.installers.codex.configure_mcp_server_toml") as mock_mcp,
        ):
            mock_shared.return_value = {"workflows": [], "plugins": []}
            mock_cli.return_value = {"workflows": [], "commands": []}
            mock_mcp.return_value = {"success": True, "added": True}

            result = install_codex_notify()

        expected_keys = {
            "success",
            "files_installed",
            "workflows_installed",
            "commands_installed",
            "plugins_installed",
            "config_updated",
            "mcp_configured",
            "mcp_already_configured",
            "error",
        }
        assert set(result.keys()) >= expected_keys

    def test_uninstall_result_has_all_keys(self, mock_home: Path) -> None:
        """Test that uninstall result contains all expected keys."""
        from gobby.cli.installers.codex import uninstall_codex_notify

        with patch("gobby.cli.installers.codex.remove_mcp_server_toml") as mock_mcp:
            mock_mcp.return_value = {"success": True, "removed": True}

            result = uninstall_codex_notify()

        expected_keys = {
            "success",
            "files_removed",
            "config_updated",
            "mcp_removed",
            "error",
        }
        assert set(result.keys()) == expected_keys
