"""Comprehensive unit tests for context_actions.py.

Tests for context injection, message injection, handoff extraction,
and markdown formatting functions.
"""

import json
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from gobby.workflows.context_actions import (
    extract_handoff_context,
    format_handoff_as_markdown,
    inject_context,
    inject_message,
    restore_context,
)
from gobby.workflows.definitions import WorkflowState

# --- Fixtures ---


@pytest.fixture
def mock_session_manager():
    """Create a mock session manager."""
    return MagicMock()


@pytest.fixture
def mock_template_engine():
    """Create a mock template engine.

    Default behavior returns "rendered:{template}".
    Tests can override with engine.render.return_value or engine.render.side_effect.
    """
    engine = MagicMock()
    # Use return_value as default - tests can override
    engine.render.return_value = "rendered_content"
    return engine


@pytest.fixture
def workflow_state():
    """Create a workflow state for testing."""
    return WorkflowState(
        session_id="test-session-id",
        workflow_name="test-workflow",
        step="test-step",
        artifacts={"plan": "/path/to/plan.md"},
        observations=[{"type": "user_action", "data": "clicked button"}],
        variables={"key": "value"},
    )


@pytest.fixture
def mock_session():
    """Create a mock session object."""
    session = MagicMock()
    session.id = "test-session-id"
    session.parent_session_id = None
    session.summary_markdown = None
    session.compact_markdown = None
    session.jsonl_path = None
    session.project_id = "test-project-id"
    return session


@pytest.fixture
def mock_parent_session():
    """Create a mock parent session object."""
    parent = MagicMock()
    parent.id = "parent-session-id"
    parent.summary_markdown = "Parent session summary content"
    return parent


# --- Tests for inject_context ---


class TestInjectContext:
    """Tests for the inject_context function."""

    def test_returns_none_when_session_manager_is_none(self, workflow_state, mock_template_engine):
        """Should return None and log warning when session_manager is None."""
        result = inject_context(
            session_manager=None,
            session_id="test-session",
            state=workflow_state,
            template_engine=mock_template_engine,
            source="handoff",
        )
        assert result is None

    def test_returns_none_when_state_is_none(self, mock_session_manager, mock_template_engine):
        """Should return None and log warning when state is None."""
        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=None,
            template_engine=mock_template_engine,
            source="handoff",
        )
        assert result is None

    def test_returns_none_when_template_engine_is_none(self, mock_session_manager, workflow_state):
        """Should return None and log warning when template_engine is None."""
        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=workflow_state,
            template_engine=None,
            source="handoff",
        )
        assert result is None

    def test_returns_none_when_session_id_is_empty(
        self, mock_session_manager, workflow_state, mock_template_engine
    ):
        """Should return None when session_id is empty."""
        result = inject_context(
            session_manager=mock_session_manager,
            session_id="",
            state=workflow_state,
            template_engine=mock_template_engine,
            source="handoff",
        )
        assert result is None

    def test_returns_none_when_session_id_is_none(
        self, mock_session_manager, workflow_state, mock_template_engine
    ):
        """Should return None when session_id is None."""
        result = inject_context(
            session_manager=mock_session_manager,
            session_id=None,
            state=workflow_state,
            template_engine=mock_template_engine,
            source="handoff",
        )
        assert result is None

    def test_returns_none_when_source_is_none(
        self, mock_session_manager, workflow_state, mock_template_engine
    ):
        """Should return None when source is None."""
        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=workflow_state,
            template_engine=mock_template_engine,
            source=None,
        )
        assert result is None

    def test_returns_none_when_source_is_empty(
        self, mock_session_manager, workflow_state, mock_template_engine
    ):
        """Should return None when source is empty string."""
        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=workflow_state,
            template_engine=mock_template_engine,
            source="",
        )
        assert result is None

    def test_previous_session_summary_returns_parent_summary(
        self,
        mock_session_manager,
        workflow_state,
        mock_template_engine,
        mock_session,
        mock_parent_session,
    ):
        """Should return parent session summary for previous_session_summary source."""
        mock_session.parent_session_id = "parent-session-id"
        mock_session_manager.get.side_effect = lambda sid: (
            mock_session if sid == "test-session-id" else mock_parent_session
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=workflow_state,
            template_engine=mock_template_engine,
            source="previous_session_summary",
        )

        assert result is not None
        assert result["inject_context"] == "Parent session summary content"
        assert workflow_state.context_injected is True

    def test_handoff_source_returns_parent_summary(
        self,
        mock_session_manager,
        workflow_state,
        mock_template_engine,
        mock_session,
        mock_parent_session,
    ):
        """Should return parent session summary for handoff source."""
        mock_session.parent_session_id = "parent-session-id"
        mock_session_manager.get.side_effect = lambda sid: (
            mock_session if sid == "test-session-id" else mock_parent_session
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=workflow_state,
            template_engine=mock_template_engine,
            source="handoff",
        )

        assert result is not None
        assert result["inject_context"] == "Parent session summary content"

    def test_returns_none_when_session_not_found(
        self, mock_session_manager, workflow_state, mock_template_engine
    ):
        """Should return None when current session is not found."""
        mock_session_manager.get.return_value = None

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="nonexistent-session",
            state=workflow_state,
            template_engine=mock_template_engine,
            source="previous_session_summary",
        )

        assert result is None

    def test_returns_none_when_no_parent_session(
        self, mock_session_manager, workflow_state, mock_template_engine, mock_session
    ):
        """Should return None when current session has no parent."""
        mock_session.parent_session_id = None
        mock_session_manager.get.return_value = mock_session

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=workflow_state,
            template_engine=mock_template_engine,
            source="previous_session_summary",
        )

        assert result is None

    def test_returns_none_when_parent_has_no_summary(
        self, mock_session_manager, workflow_state, mock_template_engine, mock_session
    ):
        """Should return None when parent session has no summary."""
        mock_session.parent_session_id = "parent-session-id"
        parent = MagicMock()
        parent.summary_markdown = None

        mock_session_manager.get.side_effect = lambda sid: (
            mock_session if sid == "test-session-id" else parent
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=workflow_state,
            template_engine=mock_template_engine,
            source="previous_session_summary",
        )

        assert result is None

    def test_artifacts_source_with_artifacts(self, mock_session_manager, mock_template_engine):
        """Should format artifacts as markdown when source is artifacts."""
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test",
            step="test",
            artifacts={"plan": "/path/plan.md", "report": "/path/report.txt"},
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=state,
            template_engine=mock_template_engine,
            source="artifacts",
        )

        assert result is not None
        assert "## Captured Artifacts" in result["inject_context"]
        assert "- plan: /path/plan.md" in result["inject_context"]
        assert "- report: /path/report.txt" in result["inject_context"]

    def test_artifacts_source_with_empty_artifacts(
        self, mock_session_manager, mock_template_engine
    ):
        """Should return None when artifacts is empty."""
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test",
            step="test",
            artifacts={},
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=state,
            template_engine=mock_template_engine,
            source="artifacts",
        )

        assert result is None

    def test_observations_source_with_observations(
        self, mock_session_manager, mock_template_engine
    ):
        """Should format observations as JSON when source is observations."""
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test",
            step="test",
            observations=[{"event": "click"}, {"event": "scroll"}],
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=state,
            template_engine=mock_template_engine,
            source="observations",
        )

        assert result is not None
        assert "## Observations" in result["inject_context"]
        assert '"event": "click"' in result["inject_context"]

    def test_observations_source_with_empty_observations(
        self, mock_session_manager, mock_template_engine
    ):
        """Should return None when observations is empty."""
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test",
            step="test",
            observations=[],
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=state,
            template_engine=mock_template_engine,
            source="observations",
        )

        assert result is None

    def test_workflow_state_source(self, mock_session_manager, mock_template_engine):
        """Should format workflow state as JSON."""
        state = WorkflowState(
            session_id="test-session",
            workflow_name="my-workflow",
            step="planning",
            variables={"count": 5},
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=state,
            template_engine=mock_template_engine,
            source="workflow_state",
        )

        assert result is not None
        assert "## Workflow State" in result["inject_context"]
        assert '"workflow_name": "my-workflow"' in result["inject_context"]
        assert '"step": "planning"' in result["inject_context"]

    def test_workflow_state_with_dict_method_fallback(
        self, mock_session_manager, mock_template_engine
    ):
        """Should use .dict() method when .model_dump() is not available."""

        # Create a concrete helper class that has dict() but not model_dump
        class TestState:
            def __init__(self):
                self.artifacts = {}
                self.observations = []
                self.dict_called = False

            def dict(self, exclude=None):
                self.dict_called = True
                return {"workflow_name": "test", "step": "step1"}

        test_state = TestState()
        # Verify no model_dump attribute
        assert not hasattr(test_state, "model_dump")

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=test_state,
            template_engine=mock_template_engine,
            source="workflow_state",
        )

        assert result is not None
        assert "## Workflow State" in result["inject_context"]
        assert test_state.dict_called is True

    def test_compact_handoff_source(self, mock_session_manager, mock_template_engine, mock_session):
        """Should return compact_markdown from current session."""
        mock_session.compact_markdown = "# Compact handoff content"
        mock_session_manager.get.return_value = mock_session

        state = WorkflowState(
            session_id="test-session-id",
            workflow_name="test",
            step="test",
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=state,
            template_engine=mock_template_engine,
            source="compact_handoff",
        )

        assert result is not None
        assert result["inject_context"] == "# Compact handoff content"

    def test_compact_handoff_with_no_markdown(
        self, mock_session_manager, mock_template_engine, mock_session
    ):
        """Should return None when compact_markdown is not set."""
        mock_session.compact_markdown = None
        mock_session_manager.get.return_value = mock_session

        state = WorkflowState(
            session_id="test-session-id",
            workflow_name="test",
            step="test",
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=state,
            template_engine=mock_template_engine,
            source="compact_handoff",
        )

        assert result is None

    def test_with_template_rendering_for_handoff(
        self, mock_session_manager, workflow_state, mock_session, mock_parent_session
    ):
        """Should render template with context for handoff source."""
        mock_session.parent_session_id = "parent-session-id"
        mock_session_manager.get.side_effect = lambda sid: (
            mock_session if sid == "test-session-id" else mock_parent_session
        )
        template_engine = MagicMock()
        template_engine.render.return_value = "Rendered content"

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=workflow_state,
            template_engine=template_engine,
            source="handoff",
            template="## Context\n{{ summary }}",
        )

        assert result is not None
        assert result["inject_context"] == "Rendered content"
        template_engine.render.assert_called_once()
        call_args = template_engine.render.call_args
        assert call_args[0][0] == "## Context\n{{ summary }}"
        assert "summary" in call_args[0][1]
        assert "handoff" in call_args[0][1]

    def test_with_template_rendering_for_artifacts(self, mock_session_manager):
        """Should render template with artifacts_list for artifacts source."""
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test",
            step="test",
            artifacts={"plan": "/path/plan.md"},
        )
        template_engine = MagicMock()
        template_engine.render.return_value = "Rendered artifacts"

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=state,
            template_engine=template_engine,
            source="artifacts",
            template="Artifacts: {{ artifacts_list }}",
        )

        assert result is not None
        assert result["inject_context"] == "Rendered artifacts"
        call_args = template_engine.render.call_args
        assert "artifacts_list" in call_args[0][1]

    def test_with_template_rendering_for_observations(self, mock_session_manager):
        """Should render template with observations_text for observations source."""
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test",
            step="test",
            observations=[{"event": "click"}],
        )
        template_engine = MagicMock()
        template_engine.render.return_value = "Rendered observations"

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=state,
            template_engine=template_engine,
            source="observations",
            template="Obs: {{ observations_text }}",
        )

        assert result is not None
        call_args = template_engine.render.call_args
        assert "observations_text" in call_args[0][1]

    def test_with_template_rendering_for_workflow_state(self, mock_session_manager):
        """Should render template with workflow_state_text for workflow_state source."""
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test",
            step="test",
        )
        template_engine = MagicMock()
        template_engine.render.return_value = "Rendered state"

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=state,
            template_engine=template_engine,
            source="workflow_state",
            template="State: {{ workflow_state_text }}",
        )

        assert result is not None
        call_args = template_engine.render.call_args
        assert "workflow_state_text" in call_args[0][1]

    def test_with_template_rendering_for_compact_handoff(self, mock_session_manager, mock_session):
        """Should render template with handoff for compact_handoff source."""
        mock_session.compact_markdown = "Compact content"
        mock_session_manager.get.return_value = mock_session
        template_engine = MagicMock()
        template_engine.render.return_value = "Rendered compact"

        state = WorkflowState(
            session_id="test-session-id",
            workflow_name="test",
            step="test",
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=state,
            template_engine=template_engine,
            source="compact_handoff",
            template="Handoff: {{ handoff }}",
        )

        assert result is not None
        call_args = template_engine.render.call_args
        assert "handoff" in call_args[0][1]
        assert call_args[0][1]["handoff"] == "Compact content"

    def test_template_rendering_with_previous_session_summary_source(
        self, mock_session_manager, mock_session, mock_parent_session
    ):
        """Should set summary and handoff in render context for previous_session_summary."""
        mock_session.parent_session_id = "parent-id"
        mock_session_manager.get.side_effect = lambda sid: (
            mock_session if sid == "test-session-id" else mock_parent_session
        )
        template_engine = MagicMock()
        template_engine.render.return_value = "Rendered with summary"

        state = WorkflowState(
            session_id="test-session-id",
            workflow_name="test",
            step="test",
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=state,
            template_engine=template_engine,
            source="previous_session_summary",
            template="Template: {{ summary }} - {{ handoff.notes }}",
        )

        assert result is not None
        call_args = template_engine.render.call_args[0][1]
        assert call_args["summary"] == "Parent session summary content"
        assert call_args["handoff"]["notes"] == "Parent session summary content"

    def test_require_blocks_when_no_content(self, mock_session_manager, mock_template_engine):
        """Should return block decision when require=True and no content found."""
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test",
            step="test",
            artifacts={},
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=state,
            template_engine=mock_template_engine,
            source="artifacts",
            require=True,
        )

        assert result is not None
        assert result["decision"] == "block"
        assert "Required handoff context not found" in result["reason"]

    def test_require_false_returns_none_when_no_content(
        self, mock_session_manager, mock_template_engine
    ):
        """Should return None when require=False and no content found."""
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test",
            step="test",
            artifacts={},
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=state,
            template_engine=mock_template_engine,
            source="artifacts",
            require=False,
        )

        assert result is None

    def test_unknown_source_returns_none(self, mock_session_manager, mock_template_engine):
        """Should return None for unknown source type."""
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test",
            step="test",
        )

        result = inject_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=state,
            template_engine=mock_template_engine,
            source="unknown_source",
        )

        assert result is None


# --- Tests for inject_message ---


class TestInjectMessage:
    """Tests for the inject_message function."""

    def test_returns_none_when_content_is_none(
        self, mock_session_manager, workflow_state, mock_template_engine
    ):
        """Should return None when content is None."""
        result = inject_message(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=workflow_state,
            template_engine=mock_template_engine,
            content=None,
        )
        assert result is None

    def test_returns_none_when_content_is_empty(
        self, mock_session_manager, workflow_state, mock_template_engine
    ):
        """Should return None when content is empty string."""
        result = inject_message(
            session_manager=mock_session_manager,
            session_id="test-session",
            state=workflow_state,
            template_engine=mock_template_engine,
            content="",
        )
        assert result is None

    def test_renders_and_returns_message(self, mock_session_manager, workflow_state, mock_session):
        """Should render template and return inject_message dict."""
        mock_session_manager.get.return_value = mock_session
        template_engine = MagicMock()
        template_engine.render.return_value = "Hello, world!"

        result = inject_message(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=workflow_state,
            template_engine=template_engine,
            content="Hello, {{ name }}!",
        )

        assert result is not None
        assert result["inject_message"] == "Hello, world!"
        template_engine.render.assert_called_once()

    def test_includes_state_in_render_context(
        self, mock_session_manager, workflow_state, mock_template_engine, mock_session
    ):
        """Should include state data in template render context."""
        mock_session_manager.get.return_value = mock_session
        mock_template_engine.render.return_value = "rendered"

        inject_message(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=workflow_state,
            template_engine=mock_template_engine,
            content="template",
        )

        call_args = mock_template_engine.render.call_args[0][1]
        assert "session" in call_args
        assert "state" in call_args
        assert "artifacts" in call_args
        assert "step_action_count" in call_args
        assert "variables" in call_args

    def test_includes_extra_kwargs_in_render_context(
        self, mock_session_manager, workflow_state, mock_template_engine, mock_session
    ):
        """Should include extra kwargs in template render context."""
        mock_session_manager.get.return_value = mock_session
        mock_template_engine.render.return_value = "rendered"

        inject_message(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=workflow_state,
            template_engine=mock_template_engine,
            content="template",
            custom_var="custom_value",
            another_var=123,
        )

        call_args = mock_template_engine.render.call_args[0][1]
        assert call_args["custom_var"] == "custom_value"
        assert call_args["another_var"] == 123

    def test_handles_none_variables_in_state(
        self, mock_session_manager, mock_template_engine, mock_session
    ):
        """Should handle None variables in state gracefully."""
        state = WorkflowState(
            session_id="test-session",
            workflow_name="test",
            step="test",
        )
        # Manually set variables to None to test edge case
        state.variables = None

        mock_session_manager.get.return_value = mock_session
        mock_template_engine.render.return_value = "rendered"

        result = inject_message(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=state,
            template_engine=mock_template_engine,
            content="template",
        )

        assert result is not None
        call_args = mock_template_engine.render.call_args[0][1]
        assert call_args["variables"] == {}


# --- Tests for restore_context ---


class TestRestoreContext:
    """Tests for the restore_context function."""

    def test_returns_none_when_session_not_found(
        self, mock_session_manager, workflow_state, mock_template_engine
    ):
        """Should return None when current session not found."""
        mock_session_manager.get.return_value = None

        result = restore_context(
            session_manager=mock_session_manager,
            session_id="nonexistent",
            state=workflow_state,
            template_engine=mock_template_engine,
        )

        assert result is None

    def test_returns_none_when_no_parent_session_id(
        self, mock_session_manager, workflow_state, mock_template_engine, mock_session
    ):
        """Should return None when current session has no parent."""
        mock_session.parent_session_id = None
        mock_session_manager.get.return_value = mock_session

        result = restore_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=workflow_state,
            template_engine=mock_template_engine,
        )

        assert result is None

    def test_returns_none_when_parent_not_found(
        self, mock_session_manager, workflow_state, mock_template_engine, mock_session
    ):
        """Should return None when parent session not found."""
        mock_session.parent_session_id = "parent-id"
        mock_session_manager.get.side_effect = lambda sid: (
            mock_session if sid == "test-session-id" else None
        )

        result = restore_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=workflow_state,
            template_engine=mock_template_engine,
        )

        assert result is None

    def test_returns_none_when_parent_has_no_summary(
        self, mock_session_manager, workflow_state, mock_template_engine, mock_session
    ):
        """Should return None when parent has no summary_markdown."""
        mock_session.parent_session_id = "parent-id"
        parent = MagicMock()
        parent.summary_markdown = None

        mock_session_manager.get.side_effect = lambda sid: (
            mock_session if sid == "test-session-id" else parent
        )

        result = restore_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=workflow_state,
            template_engine=mock_template_engine,
        )

        assert result is None

    def test_returns_parent_summary_without_template(
        self,
        mock_session_manager,
        workflow_state,
        mock_template_engine,
        mock_session,
        mock_parent_session,
    ):
        """Should return parent summary directly when no template provided."""
        mock_session.parent_session_id = "parent-id"
        mock_session_manager.get.side_effect = lambda sid: (
            mock_session if sid == "test-session-id" else mock_parent_session
        )

        result = restore_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=workflow_state,
            template_engine=mock_template_engine,
        )

        assert result is not None
        assert result["inject_context"] == "Parent session summary content"

    def test_renders_template_with_summary(
        self, mock_session_manager, workflow_state, mock_session, mock_parent_session
    ):
        """Should render template with summary when template provided."""
        mock_session.parent_session_id = "parent-id"
        mock_session_manager.get.side_effect = lambda sid: (
            mock_session if sid == "test-session-id" else mock_parent_session
        )
        template_engine = MagicMock()
        template_engine.render.return_value = "Rendered restored context"

        result = restore_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
            state=workflow_state,
            template_engine=template_engine,
            template="Restored: {{ summary }}",
        )

        assert result is not None
        assert result["inject_context"] == "Rendered restored context"
        call_args = template_engine.render.call_args[0][1]
        assert call_args["summary"] == "Parent session summary content"
        assert call_args["handoff"]["notes"] == "Restored summary"


# --- Tests for extract_handoff_context ---


class TestExtractHandoffContext:
    """Tests for the extract_handoff_context function."""

    def test_skips_when_compact_handoff_disabled(self, mock_session_manager):
        """Should skip extraction when compact_handoff is disabled."""
        config = MagicMock()
        config.compact_handoff.enabled = False

        result = extract_handoff_context(
            session_manager=mock_session_manager,
            session_id="test-session",
            config=config,
        )

        assert result == {"skipped": True, "reason": "compact_handoff disabled"}

    def test_returns_error_when_session_not_found(self, mock_session_manager):
        """Should return error when session not found."""
        mock_session_manager.get.return_value = None

        result = extract_handoff_context(
            session_manager=mock_session_manager,
            session_id="nonexistent",
        )

        assert result == {"error": "Session not found"}

    def test_returns_error_when_no_transcript_path(self, mock_session_manager, mock_session):
        """Should return error when session has no jsonl_path."""
        mock_session.jsonl_path = None
        mock_session_manager.get.return_value = mock_session

        result = extract_handoff_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
        )

        assert result == {"error": "No transcript path"}

    def test_returns_error_when_transcript_file_not_found(
        self, mock_session_manager, mock_session, tmp_path
    ):
        """Should return error when transcript file doesn't exist."""
        mock_session.jsonl_path = str(tmp_path / "nonexistent.jsonl")
        mock_session_manager.get.return_value = mock_session

        result = extract_handoff_context(
            session_manager=mock_session_manager,
            session_id="test-session-id",
        )

        assert result == {"error": "Transcript file not found"}

    def test_extracts_context_and_saves_markdown(
        self, mock_session_manager, mock_session, tmp_path
    ):
        """Should extract context from transcript and save markdown to session."""
        # Create transcript file
        transcript_path = tmp_path / "transcript.jsonl"
        turns = [
            {"type": "user", "message": {"content": "Fix the bug"}},
            {"type": "assistant", "message": {"content": "I'll fix it"}},
        ]
        with open(transcript_path, "w") as f:
            for turn in turns:
                f.write(json.dumps(turn) + "\n")

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        # Mock the TranscriptAnalyzer at its source location
        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            mock_ctx = MagicMock()
            mock_ctx.active_gobby_task = None
            mock_ctx.active_worktree = None
            mock_ctx.todo_state = []
            mock_ctx.git_commits = []
            mock_ctx.git_status = ""
            mock_ctx.files_modified = []
            mock_ctx.initial_goal = "Fix the bug"
            mock_ctx.recent_activity = []
            MockAnalyzer.return_value.extract_handoff_context.return_value = mock_ctx

            with patch("gobby.workflows.context_actions.get_git_status", return_value="No changes"):
                with patch(
                    "gobby.workflows.context_actions.get_recent_git_commits", return_value=[]
                ):
                    result = extract_handoff_context(
                        session_manager=mock_session_manager,
                        session_id="test-session-id",
                    )

        assert result is not None
        assert result.get("handoff_context_extracted") is True
        assert "markdown_length" in result
        mock_session_manager.update_compact_markdown.assert_called_once()

    def test_enriches_with_git_status_when_empty(
        self, mock_session_manager, mock_session, tmp_path
    ):
        """Should enrich with git status when not provided by analyzer."""
        transcript_path = tmp_path / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write('{"type": "user", "message": {"content": "test"}}\n')

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            mock_ctx = MagicMock()
            mock_ctx.git_status = ""  # Empty - should be enriched
            mock_ctx.git_commits = []
            mock_ctx.active_gobby_task = None
            mock_ctx.active_worktree = None
            mock_ctx.todo_state = []
            mock_ctx.files_modified = []
            mock_ctx.initial_goal = ""
            mock_ctx.recent_activity = []
            MockAnalyzer.return_value.extract_handoff_context.return_value = mock_ctx

            with patch(
                "gobby.workflows.context_actions.get_git_status", return_value="M file.py"
            ) as mock_status:
                with patch(
                    "gobby.workflows.context_actions.get_recent_git_commits", return_value=[]
                ):
                    extract_handoff_context(
                        session_manager=mock_session_manager,
                        session_id="test-session-id",
                    )

                    mock_status.assert_called_once()
                    assert mock_ctx.git_status == "M file.py"

    def test_enriches_with_git_commits(self, mock_session_manager, mock_session, tmp_path):
        """Should enrich with recent git commits."""
        transcript_path = tmp_path / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write('{"type": "user", "message": {"content": "test"}}\n')

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            mock_ctx = MagicMock()
            mock_ctx.git_status = "clean"
            mock_ctx.git_commits = []
            mock_ctx.active_gobby_task = None
            mock_ctx.active_worktree = None
            mock_ctx.todo_state = []
            mock_ctx.files_modified = []
            mock_ctx.initial_goal = ""
            mock_ctx.recent_activity = []
            MockAnalyzer.return_value.extract_handoff_context.return_value = mock_ctx

            commits = [{"hash": "abc123", "message": "feat: add feature"}]
            with patch("gobby.workflows.context_actions.get_git_status", return_value=""):
                with patch(
                    "gobby.workflows.context_actions.get_recent_git_commits", return_value=commits
                ):
                    extract_handoff_context(
                        session_manager=mock_session_manager,
                        session_id="test-session-id",
                    )

                    assert mock_ctx.git_commits == commits

    def test_enriches_with_worktree_context_via_manager(
        self, mock_session_manager, mock_session, tmp_path
    ):
        """Should enrich with worktree context when worktree_manager provided."""
        transcript_path = tmp_path / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write('{"type": "user", "message": {"content": "test"}}\n')

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        # Create mock worktree
        mock_worktree = MagicMock()
        mock_worktree.id = "wt-123"
        mock_worktree.branch_name = "feature/auth"
        mock_worktree.worktree_path = "/path/to/worktree"
        mock_worktree.base_branch = "main"
        mock_worktree.task_id = "gt-abc"
        mock_worktree.status = "active"

        mock_wt_manager = MagicMock()
        mock_wt_manager.list.return_value = [mock_worktree]

        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            mock_ctx = MagicMock()
            mock_ctx.git_status = ""
            mock_ctx.git_commits = []
            mock_ctx.active_gobby_task = None
            mock_ctx.active_worktree = None
            mock_ctx.todo_state = []
            mock_ctx.files_modified = []
            mock_ctx.initial_goal = ""
            mock_ctx.recent_activity = []
            MockAnalyzer.return_value.extract_handoff_context.return_value = mock_ctx

            with patch("gobby.workflows.context_actions.get_git_status", return_value=""):
                with patch(
                    "gobby.workflows.context_actions.get_recent_git_commits", return_value=[]
                ):
                    extract_handoff_context(
                        session_manager=mock_session_manager,
                        session_id="test-session-id",
                        worktree_manager=mock_wt_manager,
                    )

                    assert mock_ctx.active_worktree is not None
                    assert mock_ctx.active_worktree["id"] == "wt-123"
                    assert mock_ctx.active_worktree["branch_name"] == "feature/auth"

    def test_enriches_with_worktree_context_via_db(
        self, mock_session_manager, mock_session, tmp_path
    ):
        """Should create worktree manager from db when provided."""
        transcript_path = tmp_path / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write('{"type": "user", "message": {"content": "test"}}\n')

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        mock_db = MagicMock()

        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            mock_ctx = MagicMock()
            mock_ctx.git_status = ""
            mock_ctx.git_commits = []
            mock_ctx.active_gobby_task = None
            mock_ctx.active_worktree = None
            mock_ctx.todo_state = []
            mock_ctx.files_modified = []
            mock_ctx.initial_goal = ""
            mock_ctx.recent_activity = []
            MockAnalyzer.return_value.extract_handoff_context.return_value = mock_ctx

            with patch("gobby.workflows.context_actions.get_git_status", return_value=""):
                with patch(
                    "gobby.workflows.context_actions.get_recent_git_commits", return_value=[]
                ):
                    with patch("gobby.storage.worktrees.LocalWorktreeManager") as MockWtManager:
                        mock_wt_instance = MagicMock()
                        mock_wt_instance.list.return_value = []
                        MockWtManager.return_value = mock_wt_instance

                        extract_handoff_context(
                            session_manager=mock_session_manager,
                            session_id="test-session-id",
                            db=mock_db,
                        )

                        MockWtManager.assert_called_once_with(mock_db)

    def test_handles_worktree_exception_gracefully(
        self, mock_session_manager, mock_session, tmp_path
    ):
        """Should handle worktree lookup exceptions gracefully."""
        transcript_path = tmp_path / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write('{"type": "user", "message": {"content": "test"}}\n')

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        mock_wt_manager = MagicMock()
        mock_wt_manager.list.side_effect = Exception("DB error")

        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            mock_ctx = MagicMock()
            mock_ctx.git_status = ""
            mock_ctx.git_commits = []
            mock_ctx.active_gobby_task = None
            mock_ctx.active_worktree = None
            mock_ctx.todo_state = []
            mock_ctx.files_modified = []
            mock_ctx.initial_goal = ""
            mock_ctx.recent_activity = []
            MockAnalyzer.return_value.extract_handoff_context.return_value = mock_ctx

            with patch("gobby.workflows.context_actions.get_git_status", return_value=""):
                with patch(
                    "gobby.workflows.context_actions.get_recent_git_commits", return_value=[]
                ):
                    # Should not raise, should continue gracefully
                    result = extract_handoff_context(
                        session_manager=mock_session_manager,
                        session_id="test-session-id",
                        worktree_manager=mock_wt_manager,
                    )

                    assert result.get("handoff_context_extracted") is True

    def test_handles_extraction_exception(self, mock_session_manager, mock_session, tmp_path):
        """Should return error dict when extraction raises exception."""
        transcript_path = tmp_path / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write('{"type": "user", "message": {"content": "test"}}\n')

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            MockAnalyzer.return_value.extract_handoff_context.side_effect = Exception("Parse error")

            result = extract_handoff_context(
                session_manager=mock_session_manager,
                session_id="test-session-id",
            )

            assert "error" in result
            assert "Parse error" in result["error"]

    def test_config_without_compact_handoff_attribute(
        self, mock_session_manager, mock_session, tmp_path
    ):
        """Should proceed when config doesn't have compact_handoff attribute."""
        transcript_path = tmp_path / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write('{"type": "user", "message": {"content": "test"}}\n')

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        config = MagicMock(spec=[])  # No compact_handoff attribute

        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            mock_ctx = MagicMock()
            mock_ctx.git_status = ""
            mock_ctx.git_commits = []
            mock_ctx.active_gobby_task = None
            mock_ctx.active_worktree = None
            mock_ctx.todo_state = []
            mock_ctx.files_modified = []
            mock_ctx.initial_goal = ""
            mock_ctx.recent_activity = []
            MockAnalyzer.return_value.extract_handoff_context.return_value = mock_ctx

            with patch("gobby.workflows.context_actions.get_git_status", return_value=""):
                with patch(
                    "gobby.workflows.context_actions.get_recent_git_commits", return_value=[]
                ):
                    result = extract_handoff_context(
                        session_manager=mock_session_manager,
                        session_id="test-session-id",
                        config=config,
                    )

                    assert result.get("handoff_context_extracted") is True

    def test_skips_empty_lines_in_transcript(self, mock_session_manager, mock_session, tmp_path):
        """Should skip empty lines when reading transcript file."""
        transcript_path = tmp_path / "transcript.jsonl"
        # Create transcript with empty lines
        with open(transcript_path, "w") as f:
            f.write('{"type": "user", "message": {"content": "test"}}\n')
            f.write("\n")  # Empty line
            f.write("   \n")  # Whitespace-only line
            f.write('{"type": "assistant", "message": {"content": "response"}}\n')

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            mock_ctx = MagicMock()
            mock_ctx.git_status = ""
            mock_ctx.git_commits = []
            mock_ctx.active_gobby_task = None
            mock_ctx.active_worktree = None
            mock_ctx.todo_state = []
            mock_ctx.files_modified = []
            mock_ctx.initial_goal = "test"
            mock_ctx.recent_activity = []
            MockAnalyzer.return_value.extract_handoff_context.return_value = mock_ctx

            with patch("gobby.workflows.context_actions.get_git_status", return_value=""):
                with patch(
                    "gobby.workflows.context_actions.get_recent_git_commits", return_value=[]
                ):
                    result = extract_handoff_context(
                        session_manager=mock_session_manager,
                        session_id="test-session-id",
                    )

                    assert result.get("handoff_context_extracted") is True
                    # Verify the analyzer was called with only non-empty lines
                    call_args = MockAnalyzer.return_value.extract_handoff_context.call_args
                    turns = call_args[0][0]
                    assert len(turns) == 2  # Only the two valid JSON lines


# --- Tests for extract_handoff_context with compressor ---


class TestExtractHandoffContextWithCompressor:
    """Tests for extract_handoff_context() compressor integration."""

    @pytest.fixture
    def mock_compressor(self):
        """Create a mock compressor."""
        compressor = MagicMock()
        compressor.compress.return_value = "Compressed markdown content"
        return compressor

    def test_compressor_none_uses_default_max_turns(
        self, mock_session_manager, mock_session, tmp_path
    ):
        """Should use default max_turns of 100 when compressor=None."""
        transcript_path = tmp_path / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write('{"type": "user", "message": {"content": "test"}}\n')

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            mock_ctx = MagicMock()
            mock_ctx.git_status = ""
            mock_ctx.git_commits = []
            mock_ctx.active_gobby_task = None
            mock_ctx.active_worktree = None
            mock_ctx.todo_state = []
            mock_ctx.files_modified = []
            mock_ctx.initial_goal = ""
            mock_ctx.recent_activity = []
            MockAnalyzer.return_value.extract_handoff_context.return_value = mock_ctx

            with patch("gobby.workflows.context_actions.get_git_status", return_value=""):
                with patch(
                    "gobby.workflows.context_actions.get_recent_git_commits", return_value=[]
                ):
                    extract_handoff_context(
                        session_manager=mock_session_manager,
                        session_id="test-session-id",
                        compressor=None,
                    )

                    # Verify max_turns=100 was passed
                    call_args = MockAnalyzer.return_value.extract_handoff_context.call_args
                    assert call_args.kwargs.get("max_turns") == 100

    def test_compressor_provided_increases_max_turns(
        self, mock_session_manager, mock_session, mock_compressor, tmp_path
    ):
        """Should increase max_turns to 200 when compressor provided."""
        transcript_path = tmp_path / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write('{"type": "user", "message": {"content": "test"}}\n')

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            mock_ctx = MagicMock()
            mock_ctx.git_status = ""
            mock_ctx.git_commits = []
            mock_ctx.active_gobby_task = None
            mock_ctx.active_worktree = None
            mock_ctx.todo_state = []
            mock_ctx.files_modified = []
            mock_ctx.initial_goal = ""
            mock_ctx.recent_activity = []
            MockAnalyzer.return_value.extract_handoff_context.return_value = mock_ctx

            with patch("gobby.workflows.context_actions.get_git_status", return_value=""):
                with patch(
                    "gobby.workflows.context_actions.get_recent_git_commits", return_value=[]
                ):
                    extract_handoff_context(
                        session_manager=mock_session_manager,
                        session_id="test-session-id",
                        compressor=mock_compressor,
                    )

                    # Verify max_turns=200 was passed
                    call_args = MockAnalyzer.return_value.extract_handoff_context.call_args
                    assert call_args.kwargs.get("max_turns") == 200

    def test_compressor_called_with_correct_arguments(
        self, mock_session_manager, mock_session, mock_compressor, tmp_path
    ):
        """Should call compressor.compress() with markdown and handoff context type."""
        transcript_path = tmp_path / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write('{"type": "user", "message": {"content": "test"}}\n')

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            mock_ctx = MagicMock()
            mock_ctx.git_status = ""
            mock_ctx.git_commits = []
            mock_ctx.active_gobby_task = None
            mock_ctx.active_worktree = None
            mock_ctx.todo_state = []
            mock_ctx.files_modified = []
            mock_ctx.initial_goal = "Test goal"
            mock_ctx.recent_activity = []
            MockAnalyzer.return_value.extract_handoff_context.return_value = mock_ctx

            with patch("gobby.workflows.context_actions.get_git_status", return_value=""):
                with patch(
                    "gobby.workflows.context_actions.get_recent_git_commits", return_value=[]
                ):
                    extract_handoff_context(
                        session_manager=mock_session_manager,
                        session_id="test-session-id",
                        compressor=mock_compressor,
                    )

                    # Verify compressor was called
                    mock_compressor.compress.assert_called_once()
                    call_args = mock_compressor.compress.call_args

                    # Check that markdown content was passed (contains the initial goal)
                    assert "Test goal" in call_args[0][0]
                    # Check context_type is "handoff"
                    assert call_args.kwargs.get("context_type") == "handoff"

    def test_compressed_markdown_saved_to_session(
        self, mock_session_manager, mock_session, mock_compressor, tmp_path
    ):
        """Should save compressed markdown to session."""
        transcript_path = tmp_path / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write('{"type": "user", "message": {"content": "test"}}\n')

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            mock_ctx = MagicMock()
            mock_ctx.git_status = ""
            mock_ctx.git_commits = []
            mock_ctx.active_gobby_task = None
            mock_ctx.active_worktree = None
            mock_ctx.todo_state = []
            mock_ctx.files_modified = []
            mock_ctx.initial_goal = "Goal"
            mock_ctx.recent_activity = []
            MockAnalyzer.return_value.extract_handoff_context.return_value = mock_ctx

            with patch("gobby.workflows.context_actions.get_git_status", return_value=""):
                with patch(
                    "gobby.workflows.context_actions.get_recent_git_commits", return_value=[]
                ):
                    extract_handoff_context(
                        session_manager=mock_session_manager,
                        session_id="test-session-id",
                        compressor=mock_compressor,
                    )

                    # Verify compressed content was saved
                    mock_session_manager.update_compact_markdown.assert_called_once_with(
                        "test-session-id", "Compressed markdown content"
                    )

    def test_no_compressor_saves_uncompressed_markdown(
        self, mock_session_manager, mock_session, tmp_path
    ):
        """Should save uncompressed markdown when no compressor provided."""
        transcript_path = tmp_path / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write('{"type": "user", "message": {"content": "test"}}\n')

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            mock_ctx = MagicMock()
            mock_ctx.git_status = ""
            mock_ctx.git_commits = []
            mock_ctx.active_gobby_task = None
            mock_ctx.active_worktree = None
            mock_ctx.todo_state = []
            mock_ctx.files_modified = []
            mock_ctx.initial_goal = "Original goal"
            mock_ctx.recent_activity = []
            MockAnalyzer.return_value.extract_handoff_context.return_value = mock_ctx

            with patch("gobby.workflows.context_actions.get_git_status", return_value=""):
                with patch(
                    "gobby.workflows.context_actions.get_recent_git_commits", return_value=[]
                ):
                    extract_handoff_context(
                        session_manager=mock_session_manager,
                        session_id="test-session-id",
                        compressor=None,
                    )

                    # Verify original markdown was saved (contains "Original goal")
                    call_args = mock_session_manager.update_compact_markdown.call_args
                    assert "Original goal" in call_args[0][1]

    def test_compressor_with_success_result(
        self, mock_session_manager, mock_session, mock_compressor, tmp_path
    ):
        """Should return success with markdown_length from compressed content."""
        transcript_path = tmp_path / "transcript.jsonl"
        with open(transcript_path, "w") as f:
            f.write('{"type": "user", "message": {"content": "test"}}\n')

        mock_session.jsonl_path = str(transcript_path)
        mock_session_manager.get.return_value = mock_session

        with patch("gobby.sessions.analyzer.TranscriptAnalyzer") as MockAnalyzer:
            mock_ctx = MagicMock()
            mock_ctx.git_status = ""
            mock_ctx.git_commits = []
            mock_ctx.active_gobby_task = None
            mock_ctx.active_worktree = None
            mock_ctx.todo_state = []
            mock_ctx.files_modified = []
            mock_ctx.initial_goal = ""
            mock_ctx.recent_activity = []
            MockAnalyzer.return_value.extract_handoff_context.return_value = mock_ctx

            with patch("gobby.workflows.context_actions.get_git_status", return_value=""):
                with patch(
                    "gobby.workflows.context_actions.get_recent_git_commits", return_value=[]
                ):
                    result = extract_handoff_context(
                        session_manager=mock_session_manager,
                        session_id="test-session-id",
                        compressor=mock_compressor,
                    )

                    assert result["handoff_context_extracted"] is True
                    # markdown_length should reflect compressed content length
                    assert result["markdown_length"] == len("Compressed markdown content")


# --- Tests for format_handoff_as_markdown ---


class TestFormatHandoffAsMarkdown:
    """Tests for the format_handoff_as_markdown function."""

    @dataclass
    class MockHandoffContext:
        """Mock HandoffContext for testing."""

        active_gobby_task: dict | None = None
        active_worktree: dict | None = None
        todo_state: list = field(default_factory=list)
        git_commits: list = field(default_factory=list)
        git_status: str = ""
        files_modified: list = field(default_factory=list)
        initial_goal: str = ""
        recent_activity: list = field(default_factory=list)

    def test_empty_context_returns_empty_string(self):
        """Should return empty string when all context fields are empty."""
        ctx = self.MockHandoffContext()
        result = format_handoff_as_markdown(ctx)
        assert result == ""

    def test_formats_active_task(self):
        """Should format active task section."""
        ctx = self.MockHandoffContext(
            active_gobby_task={"id": "gt-123", "title": "Fix auth bug", "status": "in_progress"}
        )
        result = format_handoff_as_markdown(ctx)

        assert "### Active Task" in result
        assert "**Fix auth bug** (gt-123)" in result
        assert "Status: in_progress" in result

    def test_formats_active_task_with_missing_fields(self):
        """Should handle missing fields in active task with defaults."""
        ctx = self.MockHandoffContext(
            active_gobby_task={"some_field": "value"}  # Non-empty dict with no title/id/status
        )
        result = format_handoff_as_markdown(ctx)

        assert "### Active Task" in result
        assert "**Untitled** (unknown)" in result
        assert "Status: unknown" in result

    def test_formats_worktree_context(self):
        """Should format worktree context section."""
        ctx = self.MockHandoffContext(
            active_worktree={
                "branch_name": "feature/auth",
                "worktree_path": "/path/to/worktree",
                "base_branch": "main",
                "task_id": "gt-123",
            }
        )
        result = format_handoff_as_markdown(ctx)

        assert "### Worktree Context" in result
        assert "**Branch**: `feature/auth`" in result
        assert "**Path**: `/path/to/worktree`" in result
        assert "**Base**: `main`" in result
        assert "**Task**: gt-123" in result

    def test_formats_worktree_without_task_id(self):
        """Should format worktree without task_id."""
        ctx = self.MockHandoffContext(
            active_worktree={
                "branch_name": "feature/auth",
                "worktree_path": "/path",
                "base_branch": "main",
            }
        )
        result = format_handoff_as_markdown(ctx)

        assert "### Worktree Context" in result
        assert "**Task**" not in result

    def test_formats_todo_state(self):
        """Should format todo state with correct markers."""
        ctx = self.MockHandoffContext(
            todo_state=[
                {"content": "First task", "status": "completed"},
                {"content": "Second task", "status": "in_progress"},
                {"content": "Third task", "status": "pending"},
            ]
        )
        result = format_handoff_as_markdown(ctx)

        assert "### In-Progress Work" in result
        assert "- [x] First task" in result
        assert "- [>] Second task" in result
        assert "- [ ] Third task" in result

    def test_formats_git_commits(self):
        """Should format git commits section."""
        ctx = self.MockHandoffContext(
            git_commits=[
                {"hash": "abc123def456", "message": "feat: add feature"},
                {"hash": "789xyz", "message": "fix: bug fix"},
            ]
        )
        result = format_handoff_as_markdown(ctx)

        assert "### Commits This Session" in result
        assert "- `abc123d` feat: add feature" in result
        assert "- `789xyz` fix: bug fix" in result

    def test_formats_git_status(self):
        """Should format git status section."""
        ctx = self.MockHandoffContext(git_status="M src/file.py\nA new_file.py")
        result = format_handoff_as_markdown(ctx)

        assert "### Uncommitted Changes" in result
        assert "```\nM src/file.py\nA new_file.py\n```" in result

    def test_formats_files_modified(self):
        """Should format files modified section."""
        ctx = self.MockHandoffContext(files_modified=["src/auth.py", "tests/test_auth.py"])
        result = format_handoff_as_markdown(ctx)

        assert "### Files Being Modified" in result
        assert "- src/auth.py" in result
        assert "- tests/test_auth.py" in result

    def test_formats_initial_goal(self):
        """Should format initial goal section."""
        ctx = self.MockHandoffContext(initial_goal="Implement user authentication")
        result = format_handoff_as_markdown(ctx)

        assert "### Original Goal" in result
        assert "Implement user authentication" in result

    def test_formats_recent_activity(self):
        """Should format recent activity section with max 5 items."""
        ctx = self.MockHandoffContext(
            recent_activity=[
                "Activity 1",
                "Activity 2",
                "Activity 3",
                "Activity 4",
                "Activity 5",
                "Activity 6",
                "Activity 7",
            ]
        )
        result = format_handoff_as_markdown(ctx)

        assert "### Recent Activity" in result
        # Should only include last 5
        assert "- Activity 3" in result
        assert "- Activity 4" in result
        assert "- Activity 5" in result
        assert "- Activity 6" in result
        assert "- Activity 7" in result
        assert "- Activity 1" not in result
        assert "- Activity 2" not in result

    def test_formats_multiple_sections(self):
        """Should format multiple sections separated by double newlines."""
        ctx = self.MockHandoffContext(
            initial_goal="Fix the bug",
            git_status="M file.py",
        )
        result = format_handoff_as_markdown(ctx)

        assert "\n\n" in result
        sections = result.split("\n\n")
        assert len(sections) == 2

    def test_prompt_template_parameter_is_ignored(self):
        """Should ignore prompt_template parameter (reserved for future)."""
        ctx = self.MockHandoffContext(initial_goal="Goal")
        result = format_handoff_as_markdown(ctx, prompt_template="custom template")

        assert "### Original Goal" in result
        assert "Goal" in result

    def test_handles_empty_strings_in_context(self):
        """Should not include sections with empty strings."""
        ctx = self.MockHandoffContext(
            initial_goal="",
            git_status="",
        )
        result = format_handoff_as_markdown(ctx)

        assert "### Original Goal" not in result
        assert "### Uncommitted Changes" not in result

    def test_handles_commit_with_empty_hash(self):
        """Should handle commits with empty hash gracefully."""
        ctx = self.MockHandoffContext(git_commits=[{"hash": "", "message": "test commit"}])
        result = format_handoff_as_markdown(ctx)

        assert "### Commits This Session" in result
        assert "- `` test commit" in result
