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

    @pytest.fixture
    def mock_shared_skills(self) -> list[str]:
        """Mock return value for install_shared_skills."""
        return ["skill1", "skill2"]

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_shared_skills")
    def test_successful_installation(
        self,
        mock_skills: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
        mock_shared_skills: list[str],
    ):
        """Test successful Antigravity installation."""
        mock_skills.return_value = mock_shared_skills
        mock_mcp.return_value = {"success": True, "added": True, "already_configured": False}

        result = install_antigravity(temp_project)

        assert result["success"] is True
        assert result["error"] is None
        assert result["hooks_installed"] == []  # Antigravity does not support hooks
        assert result["workflows_installed"] == []
        assert result["commands_installed"] == ["skill1 (skill)", "skill2 (skill)"]
        assert result["mcp_configured"] is True
        assert result["mcp_already_configured"] is False

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_shared_skills")
    def test_mcp_already_configured(
        self,
        mock_skills: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
    ):
        """Test handling when MCP is already configured."""
        mock_skills.return_value = []
        mock_mcp.return_value = {"success": True, "added": False, "already_configured": True}

        result = install_antigravity(temp_project)

        assert result["success"] is True
        assert result["mcp_configured"] is False
        assert result["mcp_already_configured"] is True

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_shared_skills")
    def test_mcp_configuration_failure_fatal(
        self,
        mock_skills: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
    ):
        """Test that MCP configuration failure is fatal (unlike hooks which are optional)."""
        mock_skills.return_value = []
        mock_mcp.return_value = {"success": False, "error": "Permission denied"}

        result = install_antigravity(temp_project)

        assert result["success"] is False
        assert result["mcp_configured"] is False
        assert "Permission denied" in result["error"]

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_shared_skills")
    def test_shared_skills_failure_non_fatal(
        self,
        mock_skills: MagicMock,
        mock_mcp: MagicMock,
        temp_project: Path,
    ):
        """Test that shared skills installation failure is non-fatal."""
        mock_skills.side_effect = Exception("Skills copy failed")
        mock_mcp.return_value = {"success": True, "added": True}

        result = install_antigravity(temp_project)

        # Should still succeed as skills are optional/secondary to MCP
        assert result["success"] is True
        assert result["commands_installed"] == []
        assert result["mcp_configured"] is True


class TestInstallAntigravityMCPPath:
    """Tests for MCP configuration path in install_antigravity."""

    @patch("gobby.cli.installers.antigravity.configure_mcp_server_json")
    @patch("gobby.cli.installers.antigravity.install_shared_skills")
    def test_mcp_config_path(
        self,
        mock_skills: MagicMock,
        mock_mcp: MagicMock,
        temp_dir: Path,
    ):
        """Test that MCP config uses correct path."""
        project_path = temp_dir / "project"
        project_path.mkdir()

        mock_skills.return_value = []
        mock_mcp.return_value = {"success": True, "added": True}

        install_antigravity(project_path)

        # Verify configure_mcp_server_json was called with correct path
        mock_mcp.assert_called_once()
        call_args = mock_mcp.call_args[0]
        expected_path = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
        assert call_args[0] == expected_path
