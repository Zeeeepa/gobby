"""
Tests for Named Agent Definitions.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.definitions import AgentDefinition, AgentDefinitionLoader


class TestAgentDefinition:
    """Tests for AgentDefinition Pydantic model."""

    def test_basic_validation(self):
        """Test basic schema validation."""
        data: dict[str, Any] = {
            "name": "test-agent",
            "description": "A test agent",
            "model": "haiku",
            "mode": "headless",
        }
        agent = AgentDefinition(**data)
        assert agent.name == "test-agent"
        assert agent.model == "haiku"
        assert agent.mode == "headless"
        assert agent.lifecycle_variables == {}  # Default empty dict
        assert agent.workflow is None

    def test_lifecycle_variables(self):
        """Test lifecycle variables validation."""
        data: dict[str, Any] = {
            "name": "test-agent",
            "description": "test",
            "lifecycle_variables": {
                "validation_model": None,
                "require_task": False,
                "some_int": 123,
            },
        }
        agent = AgentDefinition(**data)
        assert agent.lifecycle_variables["validation_model"] is None
        assert agent.lifecycle_variables["require_task"] is False
        assert agent.lifecycle_variables["some_int"] == 123

    def test_validation_errors(self):
        """Test validation fails for missing required fields."""
        # Missing name
        with pytest.raises(ValueError):
            AgentDefinition(name=None, description="test")  # type: ignore


class TestAgentDefinitionLoader:
    """Tests for AgentDefinitionLoader."""

    @pytest.fixture
    def mock_paths(self):
        """Mock file system paths."""
        with patch("gobby.agents.definitions.Path"):
            # Setup path instances
            mock_shared = MagicMock()
            mock_user = MagicMock()
            mock_project = MagicMock()

            # Configure exists() behavior
            mock_shared.exists.return_value = True
            mock_user.exists.return_value = True
            mock_project.exists.return_value = True

            # Mock search paths
            loader = AgentDefinitionLoader()
            loader._shared_path = mock_shared
            loader._user_path = mock_user
            loader._project_path = mock_project

            yield loader, mock_shared, mock_user, mock_project

    def test_search_paths_order(self, mock_paths):
        """Test search order: Project > User > Shared."""
        loader, shared, user, project = mock_paths
        pass

    @patch("yaml.safe_load")
    @patch("builtins.open")
    def test_load_definition_found(self, mock_open, mock_yaml):
        """Test loading a definition successfully."""
        loader = AgentDefinitionLoader()

        # Mock successful file find
        agent_data: dict[str, Any] = {
            "name": "validation-runner",
            "description": "Runs validation",
            "model": "haiku",
        }
        mock_yaml.return_value = agent_data

        with patch.object(
            loader, "_find_agent_file", return_value=Path("/tmp/validation-runner.yaml")
        ):
            agent = loader.load("validation-runner")

            assert agent
            assert agent.name == "validation-runner"
            assert agent.model == "haiku"
            mock_open.assert_called_once()

    def test_load_definition_not_found(self):
        """Test loading a definition that doesn't exist."""
        loader = AgentDefinitionLoader()

        with patch.object(loader, "_find_agent_file", return_value=None):
            agent = loader.load("non-existent")
            assert agent is None

    def test_find_agent_file_priority(self):
        """Test search priority: Project > User > Shared."""
        with (
            patch("gobby.agents.definitions.Path"),
            patch.object(AgentDefinitionLoader, "_get_project_path") as mock_get_project_path,
        ):
            loader = AgentDefinitionLoader()

            # Mock file system structure
            project_path = MagicMock()
            user_path = MagicMock()
            shared_path = MagicMock()

            # Setup loader paths
            mock_get_project_path.return_value = project_path
            loader._user_path = user_path
            loader._shared_path = shared_path

            # Prepare file mocks
            project_file = MagicMock()
            user_file = MagicMock()
            shared_file = MagicMock()

            project_path.__truediv__.return_value = project_file
            user_path.__truediv__.return_value = user_file
            shared_path.__truediv__.return_value = shared_file

            # Scenario 1: Exists in project (highest priority)
            # All exist, but project should win
            project_path.exists.return_value = True
            project_file.exists.return_value = True

            found = loader._find_agent_file("my-agent")
            assert found == project_file

            # Scenario 2: Project missing, exists in User (medium priority)
            project_file.exists.return_value = False

            user_path.exists.return_value = True
            user_file.exists.return_value = True

            found = loader._find_agent_file("my-agent")
            assert found == user_file

            # Scenario 3: Project/User missing, exists in Shared (lowest priority)
            project_file.exists.return_value = False
            user_file.exists.return_value = False

            shared_path.exists.return_value = True
            shared_file.exists.return_value = True

            found = loader._find_agent_file("my-agent")
            assert found == shared_file

    def test_load_builtin_validation_runner(self):
        """Test that the built-in validation-runner agent can be loaded."""
        # Use a real loader without mocks to test actual file system
        loader = AgentDefinitionLoader()

        definition = loader.load("validation-runner")

        assert definition is not None
        assert definition.name == "validation-runner"
        assert definition.mode == "headless"
        # Check lifecycle variables
        assert definition.lifecycle_variables.get("validation_model") is None
        assert definition.lifecycle_variables.get("require_task") is False
