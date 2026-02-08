"""
Tests for skill_manager integration in ActionContext and ActionExecutor.

This module tests the skill_manager field added to support workflow-based
skill injection (part of consolidate-skill-injection epic #6640).
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.templates import TemplateEngine

pytestmark = pytest.mark.unit


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_skill_manager():
    """Create a mock skill manager."""
    manager = MagicMock()
    manager.discover_skills.return_value = [
        {"name": "commit", "description": "Create git commits"},
        {"name": "review-pr", "description": "Review pull requests"},
    ]
    manager.get_skill.return_value = {
        "name": "commit",
        "content": "# Commit Skill\nInstructions...",
    }
    return manager


@pytest.fixture
def mock_services():
    """Create mock service dependencies."""
    return {
        "template_engine": MagicMock(spec=TemplateEngine),
        "llm_service": MagicMock(),
        "transcript_processor": MagicMock(),
        "config": MagicMock(),
        "tool_proxy_getter": MagicMock(),
        "memory_manager": MagicMock(),
        "task_manager": MagicMock(),
        "session_task_manager": MagicMock(),
        "stop_registry": MagicMock(),
        "progress_tracker": MagicMock(),
        "stuck_detector": MagicMock(),
        "websocket_server": MagicMock(),
    }


@pytest.fixture
def workflow_state():
    """Create a workflow state for testing."""
    return WorkflowState(
        session_id="test-session-id",
        workflow_name="test-workflow",
        step="test-step",
        step_entered_at=datetime.now(UTC),
        variables={},
    )


# =============================================================================
# ActionContext Tests
# =============================================================================


class TestActionContextSkillManager:
    """Tests for skill_manager field in ActionContext."""

    def test_action_context_accepts_skill_manager(
        self, temp_db, session_manager, workflow_state, mock_services, mock_skill_manager
    ):
        """Test that ActionContext accepts skill_manager parameter."""
        context = ActionContext(
            session_id=workflow_state.session_id,
            state=workflow_state,
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
            skill_manager=mock_skill_manager,
        )

        assert context.skill_manager is mock_skill_manager

    def test_action_context_skill_manager_defaults_to_none(
        self, temp_db, session_manager, workflow_state, mock_services
    ):
        """Test that skill_manager defaults to None when not provided."""
        context = ActionContext(
            session_id=workflow_state.session_id,
            state=workflow_state,
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
        )

        assert context.skill_manager is None

    def test_action_context_skill_manager_can_be_used(
        self, temp_db, session_manager, workflow_state, mock_services, mock_skill_manager
    ):
        """Test that skill_manager can be accessed and used from context."""
        context = ActionContext(
            session_id=workflow_state.session_id,
            state=workflow_state,
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
            skill_manager=mock_skill_manager,
        )

        # Verify we can call methods on the skill_manager
        skills = context.skill_manager.discover_skills()
        assert len(skills) == 2
        assert skills[0]["name"] == "commit"


# =============================================================================
# ActionExecutor Tests
# =============================================================================


class TestActionExecutorSkillManager:
    """Tests for skill_manager field in ActionExecutor."""

    def test_action_executor_accepts_skill_manager(
        self, temp_db, session_manager, mock_services, mock_skill_manager
    ):
        """Test that ActionExecutor accepts skill_manager parameter."""
        executor = ActionExecutor(
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
            skill_manager=mock_skill_manager,
        )

        assert executor.skill_manager is mock_skill_manager

    def test_action_executor_skill_manager_defaults_to_none(
        self, temp_db, session_manager, mock_services
    ):
        """Test that skill_manager defaults to None when not provided."""
        executor = ActionExecutor(
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
        )

        assert executor.skill_manager is None

    def test_action_executor_with_all_parameters_including_skill_manager(
        self, temp_db, session_manager, mock_services, mock_skill_manager
    ):
        """Test ActionExecutor with all parameters including skill_manager."""
        executor = ActionExecutor(
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
            llm_service=mock_services["llm_service"],
            transcript_processor=mock_services["transcript_processor"],
            config=mock_services["config"],
            tool_proxy_getter=mock_services["tool_proxy_getter"],
            memory_manager=mock_services["memory_manager"],
            task_manager=mock_services["task_manager"],
            session_task_manager=mock_services["session_task_manager"],
            stop_registry=mock_services["stop_registry"],
            progress_tracker=mock_services["progress_tracker"],
            stuck_detector=mock_services["stuck_detector"],
            websocket_server=mock_services["websocket_server"],
            skill_manager=mock_skill_manager,
        )

        assert executor.skill_manager is mock_skill_manager
        # Verify other fields still work
        assert executor.db is temp_db
        assert executor.llm_service is mock_services["llm_service"]

    def test_action_executor_skill_manager_accessible_for_actions(
        self, temp_db, session_manager, mock_services, mock_skill_manager
    ):
        """Test that skill_manager is accessible for action handlers."""
        executor = ActionExecutor(
            db=temp_db,
            session_manager=session_manager,
            template_engine=mock_services["template_engine"],
            skill_manager=mock_skill_manager,
        )

        # Verify we can access skill_manager from the executor
        skill = executor.skill_manager.get_skill("commit")
        assert skill["name"] == "commit"
        assert "content" in skill
