"""Tests for AgentRunner and AgentRunContext."""

from unittest.mock import MagicMock

import pytest

from gobby.agents.runner import AgentConfig, AgentRunContext


class TestAgentRunContext:
    """Tests for AgentRunContext dataclass."""

    def test_default_values(self):
        """All fields default to None."""
        ctx = AgentRunContext()

        assert ctx.session is None
        assert ctx.run is None
        assert ctx.workflow_state is None
        assert ctx.workflow_config is None

    def test_session_id_property(self):
        """session_id property returns session.id."""
        mock_session = MagicMock()
        mock_session.id = "sess-123"

        ctx = AgentRunContext(session=mock_session)

        assert ctx.session_id == "sess-123"

    def test_session_id_none_when_no_session(self):
        """session_id returns None when session is None."""
        ctx = AgentRunContext()

        assert ctx.session_id is None

    def test_run_id_property(self):
        """run_id property returns run.id."""
        mock_run = MagicMock()
        mock_run.id = "run-456"

        ctx = AgentRunContext(run=mock_run)

        assert ctx.run_id == "run-456"

    def test_run_id_none_when_no_run(self):
        """run_id returns None when run is None."""
        ctx = AgentRunContext()

        assert ctx.run_id is None

    def test_all_fields_settable(self):
        """All fields can be set."""
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_state = MagicMock()
        mock_workflow = MagicMock()

        ctx = AgentRunContext(
            session=mock_session,
            run=mock_run,
            workflow_state=mock_state,
            workflow_config=mock_workflow,
        )

        assert ctx.session is mock_session
        assert ctx.run is mock_run
        assert ctx.workflow_state is mock_state
        assert ctx.workflow_config is mock_workflow


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""

    def test_prompt_required(self):
        """prompt is the only required field."""
        config = AgentConfig(prompt="Do something")

        assert config.prompt == "Do something"

    def test_default_values(self):
        """Default values are set correctly."""
        config = AgentConfig(prompt="test")

        assert config.parent_session_id is None
        assert config.project_id is None
        assert config.machine_id is None
        assert config.source == "claude"
        assert config.workflow is None
        assert config.task is None
        assert config.session_context == "summary_markdown"
        assert config.mode == "in_process"
        assert config.terminal == "auto"
        assert config.worktree_id is None
        assert config.provider == "claude"
        assert config.model is None
        assert config.max_turns == 10
        assert config.timeout == 120.0

    def test_get_effective_workflow_prefers_workflow(self):
        """get_effective_workflow prefers 'workflow' over 'workflow_name'."""
        config = AgentConfig(
            prompt="test",
            workflow="new-workflow",
            workflow_name="old-workflow",
        )

        assert config.get_effective_workflow() == "new-workflow"

    def test_get_effective_workflow_fallback(self):
        """get_effective_workflow falls back to workflow_name."""
        config = AgentConfig(
            prompt="test",
            workflow_name="legacy-workflow",
        )

        assert config.get_effective_workflow() == "legacy-workflow"

    def test_get_effective_workflow_none(self):
        """get_effective_workflow returns None when neither set."""
        config = AgentConfig(prompt="test")

        assert config.get_effective_workflow() is None
