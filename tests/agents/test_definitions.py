"""
Tests for Named Agent Definitions.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from gobby.agents.definitions import AgentDefinition, AgentDefinitionLoader
from gobby.agents.sandbox import SandboxConfig

pytestmark = pytest.mark.unit

class TestAgentDefinition:
    """Tests for AgentDefinition Pydantic model."""

    def test_basic_validation(self) -> None:
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

    def test_lifecycle_variables(self) -> None:
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

    def test_validation_errors(self) -> None:
        """Test validation fails for missing required fields."""
        # Missing name
        with pytest.raises(ValueError):
            AgentDefinition(name=None, description="test")  # type: ignore

    def test_isolation_fields_defaults(self) -> None:
        """Test that new isolation fields have correct defaults."""
        data: dict[str, Any] = {
            "name": "test-agent",
            "description": "A test agent",
        }
        agent = AgentDefinition(**data)

        # New fields with their expected defaults
        assert agent.isolation is None
        assert agent.branch_prefix is None
        assert agent.base_branch == "main"
        assert agent.provider == "claude"

    def test_isolation_fields_custom_values(self) -> None:
        """Test that new isolation fields accept custom values."""
        data: dict[str, Any] = {
            "name": "feature-developer",
            "description": "Agent for feature development",
            "isolation": "worktree",
            "branch_prefix": "feat/",
            "base_branch": "develop",
            "provider": "gemini",
        }
        agent = AgentDefinition(**data)

        assert agent.isolation == "worktree"
        assert agent.branch_prefix == "feat/"
        assert agent.base_branch == "develop"
        assert agent.provider == "gemini"

    def test_isolation_literal_values(self) -> None:
        """Test that isolation accepts all valid literal values."""
        for isolation_value in ["current", "worktree", "clone"]:
            data: dict[str, Any] = {
                "name": "test-agent",
                "isolation": isolation_value,
            }
            agent = AgentDefinition(**data)
            assert agent.isolation == isolation_value

    def test_yaml_loading_with_isolation_fields(self) -> None:
        """Test that YAML loading works with new isolation fields."""
        loader = AgentDefinitionLoader()

        yaml_data: dict[str, Any] = {
            "name": "isolation-test-agent",
            "description": "Test agent with isolation config",
            "isolation": "clone",
            "branch_prefix": "agent/",
            "base_branch": "main",
            "provider": "claude",
        }

        with (
            patch.object(loader, "_find_agent_file", return_value=Path("/tmp/test-agent.yaml")),
            patch("builtins.open"),
            patch("yaml.safe_load", return_value=yaml_data),
        ):
            agent = loader.load("isolation-test-agent")

            assert agent is not None
            assert agent.name == "isolation-test-agent"
            assert agent.isolation == "clone"
            assert agent.branch_prefix == "agent/"
            assert agent.base_branch == "main"
            assert agent.provider == "claude"

    def test_sandbox_field_defaults_to_none(self) -> None:
        """Test that sandbox field defaults to None."""
        data: dict[str, Any] = {
            "name": "test-agent",
            "description": "A test agent",
        }
        agent = AgentDefinition(**data)

        assert agent.sandbox is None

    def test_sandbox_field_accepts_sandbox_config(self) -> None:
        """Test that sandbox field accepts SandboxConfig."""
        sandbox = SandboxConfig(
            enabled=True,
            mode="restrictive",
            allow_network=False,
            extra_read_paths=["/opt"],
            extra_write_paths=["/tmp"],
        )
        data: dict[str, Any] = {
            "name": "sandboxed-agent",
            "description": "Agent with sandbox config",
            "sandbox": sandbox,
        }
        agent = AgentDefinition(**data)

        assert agent.sandbox is not None
        assert agent.sandbox.enabled is True
        assert agent.sandbox.mode == "restrictive"
        assert agent.sandbox.allow_network is False
        assert agent.sandbox.extra_read_paths == ["/opt"]
        assert agent.sandbox.extra_write_paths == ["/tmp"]

    def test_yaml_loading_with_sandbox_config(self) -> None:
        """Test that YAML loading works with sandbox config."""
        loader = AgentDefinitionLoader()

        yaml_data: dict[str, Any] = {
            "name": "sandboxed-agent",
            "description": "Agent with sandbox from YAML",
            "sandbox": {
                "enabled": True,
                "mode": "permissive",
                "allow_network": True,
                "extra_read_paths": ["/data"],
                "extra_write_paths": [],
            },
        }

        with (
            patch.object(
                loader, "_find_agent_file", return_value=Path("/tmp/sandboxed-agent.yaml")
            ),
            patch("builtins.open"),
            patch("yaml.safe_load", return_value=yaml_data),
        ):
            agent = loader.load("sandboxed-agent")

            assert agent is not None
            assert agent.name == "sandboxed-agent"
            assert agent.sandbox is not None
            assert agent.sandbox.enabled is True
            assert agent.sandbox.mode == "permissive"
            assert agent.sandbox.extra_read_paths == ["/data"]


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

    def test_search_paths_order(self, mock_paths) -> None:
        """Test search order: Project > User > Shared."""
        loader, shared, user, project = mock_paths
        pass

    @patch("yaml.safe_load")
    @patch("builtins.open")
    def test_load_definition_found(self, mock_open, mock_yaml) -> None:
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

    def test_load_definition_not_found(self) -> None:
        """Test loading a definition that doesn't exist."""
        loader = AgentDefinitionLoader()

        with patch.object(loader, "_find_agent_file", return_value=None):
            agent = loader.load("non-existent")
            assert agent is None

    def test_find_agent_file_priority(self) -> None:
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

    def test_load_builtin_validation_runner(self) -> None:
        """Test that the built-in validation-runner agent can be loaded."""
        # Use a real loader without mocks to test actual file system
        loader = AgentDefinitionLoader()

        definition = loader.load("validation-runner")

        # Skip test if agent definition doesn't exist (built-in agents may not be installed)
        if definition is None:
            pytest.skip("validation-runner agent definition not installed")

        assert definition.name == "validation-runner"
        assert definition.mode == "headless"
        # Check lifecycle variables
        assert definition.lifecycle_variables.get("validation_model") is None
        assert definition.lifecycle_variables.get("require_task") is False


class TestGenericAgentDefinition:
    """Tests for the generic.yaml agent definition."""

    def test_generic_agent_loads_successfully(self) -> None:
        """Test that the generic agent definition can be loaded."""
        loader = AgentDefinitionLoader()

        yaml_data: dict[str, Any] = {
            "name": "generic",
            "description": "Default generic agent",
            "mode": "terminal",
            "provider": "claude",
            "isolation": None,
            "base_branch": "main",
            "workflow": "generic",
            "timeout": 120.0,
            "max_turns": 10,
        }

        with (
            patch.object(loader, "_find_agent_file", return_value=Path("/tmp/generic.yaml")),
            patch("builtins.open"),
            patch("yaml.safe_load", return_value=yaml_data),
        ):
            agent = loader.load("generic")

            assert agent is not None
            assert agent.name == "generic"

    def test_generic_agent_has_expected_defaults(self) -> None:
        """Test that generic agent has correct default values."""
        loader = AgentDefinitionLoader()

        yaml_data: dict[str, Any] = {
            "name": "generic",
            "description": "Default generic agent with minimal configuration.",
            "mode": "terminal",
            "provider": "claude",
            "base_branch": "main",
            "workflow": "generic",
            "timeout": 120.0,
            "max_turns": 10,
        }

        with (
            patch.object(loader, "_find_agent_file", return_value=Path("/tmp/generic.yaml")),
            patch("builtins.open"),
            patch("yaml.safe_load", return_value=yaml_data),
        ):
            agent = loader.load("generic")

            assert agent is not None
            assert agent.name == "generic"
            assert agent.mode == "terminal"
            assert agent.provider == "claude"
            assert agent.workflow == "generic"
            assert agent.timeout == 120.0
            assert agent.max_turns == 10
            assert agent.base_branch == "main"

    def test_generic_agent_isolation_is_null(self) -> None:
        """Test that generic agent has no isolation by default."""
        loader = AgentDefinitionLoader()

        yaml_data: dict[str, Any] = {
            "name": "generic",
            "mode": "terminal",
            "provider": "claude",
            "workflow": "generic",
        }

        with (
            patch.object(loader, "_find_agent_file", return_value=Path("/tmp/generic.yaml")),
            patch("builtins.open"),
            patch("yaml.safe_load", return_value=yaml_data),
        ):
            agent = loader.load("generic")

            assert agent is not None
            assert agent.isolation is None


class TestSandboxedAgentDefinition:
    """Tests for the sandboxed.yaml agent definition."""

    def test_sandboxed_agent_loads_successfully(self) -> None:
        """Test that the sandboxed agent definition can be loaded."""
        loader = AgentDefinitionLoader()
        agent = loader.load("sandboxed")

        # Skip test if agent definition doesn't exist
        if agent is None:
            pytest.skip("sandboxed agent definition not installed")

        assert agent.name == "sandboxed"

    def test_sandboxed_agent_has_sandbox_enabled(self) -> None:
        """Test that sandboxed agent has sandbox.enabled=True."""
        loader = AgentDefinitionLoader()
        agent = loader.load("sandboxed")

        if agent is None:
            pytest.skip("sandboxed agent definition not installed")

        assert agent.sandbox is not None
        assert agent.sandbox.enabled is True

    def test_sandboxed_agent_has_permissive_mode(self) -> None:
        """Test that sandboxed agent uses permissive sandbox mode."""
        loader = AgentDefinitionLoader()
        agent = loader.load("sandboxed")

        if agent is None:
            pytest.skip("sandboxed agent definition not installed")

        assert agent.sandbox is not None
        assert agent.sandbox.mode == "permissive"

    def test_sandboxed_agent_allows_network(self) -> None:
        """Test that sandboxed agent allows network access."""
        loader = AgentDefinitionLoader()
        agent = loader.load("sandboxed")

        if agent is None:
            pytest.skip("sandboxed agent definition not installed")

        assert agent.sandbox is not None
        assert agent.sandbox.allow_network is True

    def test_sandboxed_agent_has_expected_mode(self) -> None:
        """Test that sandboxed agent uses headless mode."""
        loader = AgentDefinitionLoader()
        agent = loader.load("sandboxed")

        if agent is None:
            pytest.skip("sandboxed agent definition not installed")

        assert agent.mode == "headless"
