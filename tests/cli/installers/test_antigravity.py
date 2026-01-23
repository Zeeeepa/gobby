"""Comprehensive tests for the Antigravity installer module."""

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

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    def test_successful_installation(
        self,
        mock_mcp: MagicMock,
        temp_project: Path,
    ):
        """Test successful Antigravity installation."""
        mock_mcp.return_value = {"success": True, "added": True, "already_configured": False}

        result = install_antigravity(temp_project)

        assert result["success"] is True
        assert result["error"] is None
        assert result["hooks_installed"] == []  # Antigravity does not support hooks
        assert result["workflows_installed"] == []
        # Skills are now auto-synced on daemon startup, not during install
        assert result["commands_installed"] == []
        assert result["mcp_configured"] is True
        assert result["mcp_already_configured"] is False

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    def test_mcp_already_configured(
        self,
        mock_mcp: MagicMock,
        temp_project: Path,
    ):
        """Test handling when MCP is already configured."""
        mock_mcp.return_value = {"success": True, "added": False, "already_configured": True}

        result = install_antigravity(temp_project)

        assert result["success"] is True
        assert result["mcp_configured"] is False
        assert result["mcp_already_configured"] is True

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    def test_mcp_configuration_failure_fatal(
        self,
        mock_mcp: MagicMock,
        temp_project: Path,
    ):
        """Test that MCP configuration failure is fatal (unlike hooks which are optional)."""
        mock_mcp.return_value = {"success": False, "error": "Permission denied"}

        result = install_antigravity(temp_project)

        assert result["success"] is False
        assert result["mcp_configured"] is False
        assert "Permission denied" in result["error"]


class TestInstallAntigravityMCPPath:
    """Tests for MCP configuration path in install_antigravity."""

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    def test_mcp_config_path(
        self,
        mock_mcp: MagicMock,
        temp_dir: Path,
    ):
        """Test that MCP config uses correct path."""
        project_path = temp_dir / "project"
        project_path.mkdir()

        mock_mcp.return_value = {"success": True, "added": True}

        install_antigravity(project_path)

        # Verify configure_mcp_server_json was called with correct path
        mock_mcp.assert_called_once()
        call_args = mock_mcp.call_args[0]
        expected_path = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
        assert call_args[0] == expected_path
