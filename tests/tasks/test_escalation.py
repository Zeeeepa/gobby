"""Tests for task escalation system."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.tasks.enhanced_validator import EscalationReason
from gobby.tasks.escalation import (
    EscalationManager,
    EscalationSummary,
)


@pytest.fixture
def mock_task_manager():
    """Create a mock task manager."""
    manager = MagicMock()
    return manager


@pytest.fixture
def mock_history_manager():
    """Create a mock validation history manager."""
    manager = MagicMock()
    manager.get_recurring_issue_summary.return_value = {
        "recurring_issues": [],
        "total_iterations": 3,
    }
    return manager


@pytest.fixture
def mock_webhook_client():
    """Create a mock webhook client."""
    client = AsyncMock()
    client.send_escalation.return_value = True
    return client


@pytest.fixture
def escalation_manager(mock_task_manager, mock_history_manager):
    """Create an EscalationManager instance."""
    return EscalationManager(
        task_manager=mock_task_manager,
        history_manager=mock_history_manager,
    )


class TestEscalationManager:
    """Tests for EscalationManager."""

    def test_escalate_sets_task_status(self, escalation_manager, mock_task_manager):
        """Test that escalate() sets task status to 'escalated'."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task.status = "in_progress"
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.update_task.return_value = mock_task

        escalation_manager.escalate(
            task_id="gt-test123",
            reason=EscalationReason.MAX_ITERATIONS,
        )

        # Verify update_task was called with status='escalated'
        mock_task_manager.update_task.assert_called_once()
        call_kwargs = mock_task_manager.update_task.call_args.kwargs
        assert call_kwargs["status"] == "escalated"

    def test_escalate_sets_timestamp(self, escalation_manager, mock_task_manager):
        """Test that escalate() sets escalated_at timestamp."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.update_task.return_value = mock_task

        before = datetime.now(UTC)
        escalation_manager.escalate(
            task_id="gt-test123",
            reason=EscalationReason.MAX_ITERATIONS,
        )
        after = datetime.now(UTC)

        call_kwargs = mock_task_manager.update_task.call_args.kwargs
        assert "escalated_at" in call_kwargs
        escalated_at = datetime.fromisoformat(call_kwargs["escalated_at"])
        assert before <= escalated_at <= after

    def test_escalate_sets_reason(self, escalation_manager, mock_task_manager):
        """Test that escalate() sets escalation_reason."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.update_task.return_value = mock_task

        escalation_manager.escalate(
            task_id="gt-test123",
            reason=EscalationReason.RECURRING_ISSUES,
        )

        call_kwargs = mock_task_manager.update_task.call_args.kwargs
        assert call_kwargs["escalation_reason"] == "recurring_issues"

    def test_escalate_with_feedback(self, escalation_manager, mock_task_manager):
        """Test escalation with additional feedback."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.update_task.return_value = mock_task

        result = escalation_manager.escalate(
            task_id="gt-test123",
            reason=EscalationReason.CONSECUTIVE_ERRORS,
            feedback="LLM validation failed repeatedly",
        )

        assert result.feedback == "LLM validation failed repeatedly"

    def test_de_escalate_returns_to_open(self, escalation_manager, mock_task_manager):
        """Test that de_escalate_task() returns task to open status."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task.status = "escalated"
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.update_task.return_value = mock_task

        escalation_manager.de_escalate(task_id="gt-test123")

        call_kwargs = mock_task_manager.update_task.call_args.kwargs
        assert call_kwargs["status"] == "open"
        assert call_kwargs["escalated_at"] is None
        assert call_kwargs["escalation_reason"] is None

    def test_de_escalate_clears_escalation_fields(self, escalation_manager, mock_task_manager):
        """Test that de_escalate clears escalation metadata."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task.status = "escalated"
        mock_task.escalated_at = "2026-01-01T00:00:00+00:00"
        mock_task.escalation_reason = "max_iterations"
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.update_task.return_value = mock_task

        escalation_manager.de_escalate(task_id="gt-test123")

        call_kwargs = mock_task_manager.update_task.call_args.kwargs
        assert call_kwargs["escalated_at"] is None
        assert call_kwargs["escalation_reason"] is None

    def test_de_escalate_raises_if_not_escalated(self, escalation_manager, mock_task_manager):
        """Test that de_escalate raises if task is not escalated."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task.status = "open"
        mock_task_manager.get_task.return_value = mock_task

        with pytest.raises(ValueError, match="not escalated"):
            escalation_manager.de_escalate(task_id="gt-test123")


class TestGenerateEscalationSummary:
    """Tests for escalation summary generation."""

    def test_generates_summary_with_reason(
        self, escalation_manager, mock_task_manager, mock_history_manager
    ):
        """Test that summary includes escalation reason."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task.title = "Fix authentication bug"
        mock_task.escalation_reason = "max_iterations"
        mock_task_manager.get_task.return_value = mock_task

        summary = escalation_manager.generate_escalation_summary("gt-test123")

        assert isinstance(summary, EscalationSummary)
        assert "max_iterations" in summary.reason
        assert "Fix authentication bug" in summary.title

    def test_summary_includes_iteration_count(
        self, escalation_manager, mock_task_manager, mock_history_manager
    ):
        """Test that summary includes iteration count."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task.title = "Test task"
        mock_task.escalation_reason = "max_iterations"
        mock_task_manager.get_task.return_value = mock_task
        mock_history_manager.get_recurring_issue_summary.return_value = {
            "recurring_issues": [],
            "total_iterations": 5,
        }

        summary = escalation_manager.generate_escalation_summary("gt-test123")

        assert summary.total_iterations == 5

    def test_summary_includes_recurring_issues(
        self, escalation_manager, mock_task_manager, mock_history_manager
    ):
        """Test that summary includes recurring issues when present."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task.title = "Test task"
        mock_task.escalation_reason = "recurring_issues"
        mock_task_manager.get_task.return_value = mock_task
        mock_history_manager.get_recurring_issue_summary.return_value = {
            "recurring_issues": [
                {"title": "Test failure", "count": 3, "type": "test_failure"},
            ],
            "total_iterations": 3,
        }

        summary = escalation_manager.generate_escalation_summary("gt-test123")

        assert len(summary.recurring_issues) == 1
        assert summary.recurring_issues[0]["title"] == "Test failure"

    def test_summary_as_markdown(self, escalation_manager, mock_task_manager, mock_history_manager):
        """Test that summary can be rendered as markdown."""
        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task.title = "Fix bug"
        mock_task.escalation_reason = "max_iterations"
        mock_task_manager.get_task.return_value = mock_task

        summary = escalation_manager.generate_escalation_summary("gt-test123")
        markdown = summary.to_markdown()

        assert "# Escalation Summary" in markdown
        assert "Fix bug" in markdown
        assert "max_iterations" in markdown


class TestWebhookNotification:
    """Tests for webhook notification on escalation."""

    @pytest.mark.asyncio
    async def test_sends_webhook_when_configured(
        self, mock_task_manager, mock_history_manager, mock_webhook_client
    ):
        """Test that webhook is sent when client is configured."""
        manager = EscalationManager(
            task_manager=mock_task_manager,
            history_manager=mock_history_manager,
            webhook_client=mock_webhook_client,
        )

        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task.title = "Test task"
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.update_task.return_value = mock_task

        await manager.escalate_async(
            task_id="gt-test123",
            reason=EscalationReason.MAX_ITERATIONS,
        )

        mock_webhook_client.send_escalation.assert_called_once()
        call_args = mock_webhook_client.send_escalation.call_args
        assert call_args.kwargs["task_id"] == "gt-test123"

    @pytest.mark.asyncio
    async def test_no_webhook_when_not_configured(self, mock_task_manager, mock_history_manager):
        """Test that no error when webhook client not configured."""
        manager = EscalationManager(
            task_manager=mock_task_manager,
            history_manager=mock_history_manager,
            webhook_client=None,
        )

        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.update_task.return_value = mock_task

        # Should not raise
        await manager.escalate_async(
            task_id="gt-test123",
            reason=EscalationReason.MAX_ITERATIONS,
        )

    @pytest.mark.asyncio
    async def test_escalation_continues_on_webhook_failure(
        self, mock_task_manager, mock_history_manager, mock_webhook_client
    ):
        """Test that escalation completes even if webhook fails."""
        mock_webhook_client.send_escalation.side_effect = Exception("Network error")

        manager = EscalationManager(
            task_manager=mock_task_manager,
            history_manager=mock_history_manager,
            webhook_client=mock_webhook_client,
        )

        mock_task = MagicMock()
        mock_task.id = "gt-test123"
        mock_task_manager.get_task.return_value = mock_task
        mock_task_manager.update_task.return_value = mock_task

        # Should not raise, escalation should still complete
        await manager.escalate_async(
            task_id="gt-test123",
            reason=EscalationReason.MAX_ITERATIONS,
        )

        # Task should still be escalated
        mock_task_manager.update_task.assert_called_once()
