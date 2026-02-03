"""
Tests for Agent Runner integration with Agent Definitions (Agents V2).
"""

from unittest.mock import MagicMock

import pytest

from gobby.agents.definitions import AgentDefinition
from gobby.agents.runner import AgentConfig, AgentRunner

pytestmark = pytest.mark.unit


class TestAgentRunnerDefinitions:
    """Tests for named agent definition support in AgentRunner."""

    @pytest.fixture
    def mock_deps(self):
        """Mock dependencies for AgentRunner."""
        db = MagicMock()
        session_storage = MagicMock()
        executors = {}

        # Mock loader
        loader_mock = MagicMock()

        runner = AgentRunner(
            db=db, session_storage=session_storage, executors=executors, workflow_loader=loader_mock
        )

        # Inject our definition loader mock
        runner._agent_loader = MagicMock()
        runner._child_session_manager = MagicMock()

        return runner, session_storage, runner._agent_loader

    def test_prepare_run_with_agent_loader_merges_lifecycle_variables(self, mock_deps) -> None:
        """Test that prepare_run loads agent definition and merges variables."""
        runner, session_storage, agent_loader = mock_deps

        # This will fail until we update AgentConfig
        config = AgentConfig(
            prompt="test prompt",
            parent_session_id="parent-123",
            project_id="proj-1",
            machine_id="machine-1",
            agent="validation-runner",  # Assumes we added this field
        )

        # Mock agent definition
        definition = AgentDefinition(
            name="validation-runner",
            model="haiku",
            lifecycle_variables={"validation_model": None, "require_task": False},
        )
        agent_loader.load.return_value = definition

        # Setup child session creation mock
        child_session = MagicMock()
        child_session.id = "child-123"
        # Mock the session object to have the variables we expect?
        # Actually create_child_session returns the session.
        # The Runner calls create_child_session with a config.

        runner._child_session_manager.can_spawn_child.return_value = (True, "OK", 0)
        runner._child_session_manager.create_child_session.return_value = child_session

        # Run prepare_run
        runner.prepare_run(config)

        # Verify loader was called
        agent_loader.load.assert_called_with("validation-runner")

        # Verify child session config passed to create_child_session has lifecycle variables
        call_args = runner._child_session_manager.create_child_session.call_args
        # call_args[0][0] is the ChildSessionConfig
        child_config = call_args[0][0]

        # Verify lifecycle_variables were populated in the config passed to session manager
        assert child_config.lifecycle_variables == {"validation_model": None, "require_task": False}
