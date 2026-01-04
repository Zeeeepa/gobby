"""Tests for EnhancedTaskValidator core loop."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.tasks.enhanced_validator import (
    EnhancedTaskValidator,
    ValidationResult,
    EscalationReason,
)
from gobby.tasks.validation_models import Issue, IssueType, IssueSeverity


@pytest.fixture
def mock_task_manager():
    """Create a mock task manager."""
    manager = MagicMock()
    task = MagicMock()
    task.id = "gt-test123"
    task.title = "Test Task"
    task.description = "Test description"
    task.validation_criteria = "Must pass all tests"
    manager.get_task.return_value = task
    return manager


@pytest.fixture
def mock_history_manager():
    """Create a mock validation history manager."""
    manager = MagicMock()
    manager.get_iteration_history.return_value = []
    manager.has_recurring_issues.return_value = False
    return manager


@pytest.fixture
def mock_llm_validator():
    """Create a mock LLM validator."""
    validator = AsyncMock()
    validator.validate.return_value = {
        "valid": True,
        "feedback": "All checks passed",
        "issues": [],
    }
    return validator


@pytest.fixture
def validator(mock_task_manager, mock_history_manager, mock_llm_validator):
    """Create an EnhancedTaskValidator instance."""
    return EnhancedTaskValidator(
        task_manager=mock_task_manager,
        history_manager=mock_history_manager,
        llm_validator=mock_llm_validator,
        max_iterations=3,
        error_threshold=2,
    )


class TestEnhancedTaskValidator:
    """Tests for EnhancedTaskValidator core loop."""

    @pytest.mark.asyncio
    async def test_returns_valid_immediately_on_first_pass(
        self, validator, mock_llm_validator
    ):
        """Test that validation returns valid immediately on first pass."""
        mock_llm_validator.validate.return_value = {
            "valid": True,
            "feedback": "All checks passed",
            "issues": [],
        }

        result = await validator.validate_with_retry("gt-test123")

        assert result.valid is True
        assert result.iterations == 1
        assert result.escalated is False
        mock_llm_validator.validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_on_invalid(self, validator, mock_llm_validator):
        """Test that validation retries on invalid result."""
        # First two calls invalid, third valid
        mock_llm_validator.validate.side_effect = [
            {"valid": False, "feedback": "Test failed", "issues": []},
            {"valid": False, "feedback": "Still failing", "issues": []},
            {"valid": True, "feedback": "Fixed", "issues": []},
        ]

        result = await validator.validate_with_retry("gt-test123")

        assert result.valid is True
        assert result.iterations == 3
        assert mock_llm_validator.validate.call_count == 3

    @pytest.mark.asyncio
    async def test_escalates_after_max_iterations(
        self, validator, mock_llm_validator
    ):
        """Test that validation escalates after max_iterations exceeded."""
        # All calls return invalid
        mock_llm_validator.validate.return_value = {
            "valid": False,
            "feedback": "Test failed",
            "issues": [],
        }

        result = await validator.validate_with_retry("gt-test123")

        assert result.valid is False
        assert result.escalated is True
        assert result.escalation_reason == EscalationReason.MAX_ITERATIONS
        assert result.iterations == 3  # max_iterations

    @pytest.mark.asyncio
    async def test_escalates_on_consecutive_errors(
        self, validator, mock_llm_validator
    ):
        """Test that validation escalates on consecutive errors threshold."""
        # Raise errors on validation
        mock_llm_validator.validate.side_effect = Exception("LLM error")

        result = await validator.validate_with_retry("gt-test123")

        assert result.valid is False
        assert result.escalated is True
        assert result.escalation_reason == EscalationReason.CONSECUTIVE_ERRORS

    @pytest.mark.asyncio
    async def test_escalates_on_recurring_issues(
        self, validator, mock_llm_validator, mock_history_manager
    ):
        """Test that validation escalates when recurring issues detected."""
        # Return invalid with same issue
        issue = Issue(IssueType.TEST_FAILURE, IssueSeverity.MAJOR, "Same error")
        mock_llm_validator.validate.return_value = {
            "valid": False,
            "feedback": "Test failed",
            "issues": [issue.to_dict()],
        }
        # After 2nd iteration, recurring issues detected
        mock_history_manager.has_recurring_issues.side_effect = [False, True, True]

        result = await validator.validate_with_retry("gt-test123")

        assert result.valid is False
        assert result.escalated is True
        assert result.escalation_reason == EscalationReason.RECURRING_ISSUES

    @pytest.mark.asyncio
    async def test_records_each_iteration_in_history(
        self, validator, mock_llm_validator, mock_history_manager
    ):
        """Test that each iteration is recorded in history."""
        mock_llm_validator.validate.side_effect = [
            {"valid": False, "feedback": "Attempt 1", "issues": []},
            {"valid": True, "feedback": "Attempt 2", "issues": []},
        ]

        await validator.validate_with_retry("gt-test123")

        # Should record 2 iterations
        assert mock_history_manager.record_iteration.call_count == 2

        # Check first iteration was recorded
        first_call = mock_history_manager.record_iteration.call_args_list[0]
        assert first_call.kwargs["task_id"] == "gt-test123"
        assert first_call.kwargs["iteration"] == 1
        assert first_call.kwargs["status"] == "invalid"

        # Check second iteration was recorded
        second_call = mock_history_manager.record_iteration.call_args_list[1]
        assert second_call.kwargs["iteration"] == 2
        assert second_call.kwargs["status"] == "valid"

    @pytest.mark.asyncio
    async def test_validation_result_includes_feedback(
        self, validator, mock_llm_validator
    ):
        """Test that validation result includes feedback from validator."""
        mock_llm_validator.validate.return_value = {
            "valid": True,
            "feedback": "All tests passing, code looks good",
            "issues": [],
        }

        result = await validator.validate_with_retry("gt-test123")

        assert result.feedback == "All tests passing, code looks good"

    @pytest.mark.asyncio
    async def test_validation_result_includes_issues(
        self, validator, mock_llm_validator
    ):
        """Test that validation result includes issues from validator."""
        issues = [
            {"type": "test_failure", "severity": "major", "title": "Test failed"},
        ]
        mock_llm_validator.validate.return_value = {
            "valid": False,
            "feedback": "Issues found",
            "issues": issues,
        }

        result = await validator.validate_with_retry("gt-test123")

        assert len(result.issues) == 1
        assert result.issues[0].title == "Test failed"

    @pytest.mark.asyncio
    async def test_continues_on_single_error(self, validator, mock_llm_validator):
        """Test that validation continues after a single error."""
        # First call raises error, second succeeds
        mock_llm_validator.validate.side_effect = [
            Exception("Temporary error"),
            {"valid": True, "feedback": "Success", "issues": []},
        ]

        result = await validator.validate_with_retry("gt-test123")

        assert result.valid is True
        assert result.iterations == 2

    @pytest.mark.asyncio
    async def test_validation_with_context(
        self, validator, mock_llm_validator
    ):
        """Test validation with additional context provided."""
        mock_llm_validator.validate.return_value = {
            "valid": True,
            "feedback": "Good",
            "issues": [],
        }

        result = await validator.validate_with_retry(
            "gt-test123",
            context={"diff": "file changes here"},
        )

        # Context should be passed to validator
        call_kwargs = mock_llm_validator.validate.call_args.kwargs
        assert "context" in call_kwargs
        assert call_kwargs["context"]["diff"] == "file changes here"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_valid(self):
        """Test creating a valid ValidationResult."""
        result = ValidationResult(
            valid=True,
            iterations=1,
            feedback="All good",
        )

        assert result.valid is True
        assert result.escalated is False
        assert result.escalation_reason is None

    def test_validation_result_escalated(self):
        """Test creating an escalated ValidationResult."""
        result = ValidationResult(
            valid=False,
            iterations=3,
            feedback="Failed",
            escalated=True,
            escalation_reason=EscalationReason.MAX_ITERATIONS,
        )

        assert result.valid is False
        assert result.escalated is True
        assert result.escalation_reason == EscalationReason.MAX_ITERATIONS

    def test_validation_result_with_issues(self):
        """Test ValidationResult with issues list."""
        issues = [
            Issue(IssueType.TEST_FAILURE, IssueSeverity.MAJOR, "Test failed"),
        ]
        result = ValidationResult(
            valid=False,
            iterations=1,
            feedback="Issues found",
            issues=issues,
        )

        assert len(result.issues) == 1
        assert result.issues[0].title == "Test failed"
