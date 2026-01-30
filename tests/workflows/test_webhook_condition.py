"""Tests for webhook condition type in workflow evaluator."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.workflows.definitions import WorkflowState
from gobby.workflows.evaluator import ConditionEvaluator
from gobby.workflows.webhook_executor import WebhookExecutor, WebhookResult

pytestmark = pytest.mark.unit

@pytest.fixture
def evaluator() -> ConditionEvaluator:
    """Create a ConditionEvaluator instance."""
    return ConditionEvaluator()


@pytest.fixture
def state() -> WorkflowState:
    """Create a WorkflowState instance."""
    return WorkflowState(
        session_id="test-session",
        workflow_name="test-workflow",
        step="step1",
    )


@pytest.fixture
def mock_webhook_executor() -> WebhookExecutor:
    """Create a mock WebhookExecutor."""
    executor = MagicMock(spec=WebhookExecutor)
    return executor


class TestWebhookConditionEvaluation:
    """Tests for webhook condition pre-evaluation."""

    @pytest.mark.asyncio
    async def test_evaluate_webhook_conditions_success(
        self, evaluator: ConditionEvaluator, state: WorkflowState
    ) -> None:
        """Test evaluating a successful webhook condition."""
        # Create mock webhook result
        mock_result = WebhookResult(
            success=True,
            status_code=200,
            body='{"approved": true}',
            headers={"Content-Type": "application/json"},
        )

        # Create mock executor
        mock_executor = MagicMock(spec=WebhookExecutor)
        mock_executor.execute = AsyncMock(return_value=mock_result)
        evaluator.register_webhook_executor(mock_executor)

        conditions = [
            {
                "type": "webhook",
                "id": "approval_check",
                "url": "https://api.example.com/check",
                "method": "POST",
            }
        ]

        result = await evaluator.evaluate_webhook_conditions(conditions, state)

        assert result["evaluated"] == 1
        assert "approval_check" in result["results"]
        assert result["results"]["approval_check"]["success"] is True
        assert result["results"]["approval_check"]["status_code"] == 200
        assert "_webhook_approval_check_result" in state.variables
        assert state.variables["_webhook_approval_check_result"]["success"] is True

    @pytest.mark.asyncio
    async def test_evaluate_webhook_conditions_with_store_as(
        self, evaluator: ConditionEvaluator, state: WorkflowState
    ) -> None:
        """Test evaluating webhook and storing result in named variable."""
        mock_result = WebhookResult(
            success=True,
            status_code=200,
            body='{"data": {"status": "approved"}}',
        )

        mock_executor = MagicMock(spec=WebhookExecutor)
        mock_executor.execute = AsyncMock(return_value=mock_result)
        evaluator.register_webhook_executor(mock_executor)

        conditions = [
            {
                "type": "webhook",
                "id": "check",
                "url": "https://api.example.com/check",
                "store_as": "api_response",
            }
        ]

        await evaluator.evaluate_webhook_conditions(conditions, state)

        # Should be stored in both default and named variable
        assert "_webhook_check_result" in state.variables
        assert "api_response" in state.variables
        assert state.variables["api_response"]["success"] is True

    @pytest.mark.asyncio
    async def test_evaluate_webhook_conditions_failure(
        self, evaluator: ConditionEvaluator, state: WorkflowState
    ) -> None:
        """Test evaluating a failed webhook condition."""
        mock_result = WebhookResult(
            success=False,
            status_code=500,
            body="Internal Server Error",
            error="HTTP 500",
        )

        mock_executor = MagicMock(spec=WebhookExecutor)
        mock_executor.execute = AsyncMock(return_value=mock_result)
        evaluator.register_webhook_executor(mock_executor)

        conditions = [
            {
                "type": "webhook",
                "id": "failing_check",
                "url": "https://api.example.com/check",
            }
        ]

        result = await evaluator.evaluate_webhook_conditions(conditions, state)

        assert result["evaluated"] == 1
        assert state.variables["_webhook_failing_check_result"]["success"] is False
        assert state.variables["_webhook_failing_check_result"]["status_code"] == 500

    @pytest.mark.asyncio
    async def test_evaluate_webhook_conditions_exception(
        self, evaluator: ConditionEvaluator, state: WorkflowState
    ) -> None:
        """Test webhook evaluation when exception occurs."""
        mock_executor = MagicMock(spec=WebhookExecutor)
        mock_executor.execute = AsyncMock(side_effect=Exception("Connection failed"))
        evaluator.register_webhook_executor(mock_executor)

        conditions = [
            {
                "type": "webhook",
                "id": "error_check",
                "url": "https://api.example.com/check",
            }
        ]

        result = await evaluator.evaluate_webhook_conditions(conditions, state)

        assert result["evaluated"] == 0  # Exception means not successfully evaluated
        assert len(result["errors"]) == 1
        assert "Connection failed" in result["errors"][0]
        # Error result should still be stored
        assert state.variables["_webhook_error_check_result"]["success"] is False

    @pytest.mark.asyncio
    async def test_evaluate_webhook_conditions_no_executor(
        self, evaluator: ConditionEvaluator, state: WorkflowState
    ) -> None:
        """Test webhook evaluation when no executor is registered."""
        conditions = [
            {
                "type": "webhook",
                "id": "check",
                "url": "https://api.example.com/check",
            }
        ]

        result = await evaluator.evaluate_webhook_conditions(conditions, state)

        assert result["evaluated"] == 0
        assert any("No webhook executor" in e for e in result["errors"])


class TestWebhookConditionChecking:
    """Tests for checking pre-evaluated webhook conditions."""

    def test_check_webhook_condition_success(
        self, evaluator: ConditionEvaluator, state: WorkflowState
    ) -> None:
        """Test checking a successful webhook condition."""
        # Pre-populate the webhook result in state
        state.variables["_webhook_check_result"] = {
            "success": True,
            "status_code": 200,
            "body": "OK",
            "json_body": None,
        }

        conditions = [
            {
                "type": "webhook",
                "id": "check",
                "expect_success": True,
            }
        ]

        result = evaluator.check_exit_conditions(conditions, state)
        assert result is True

    def test_check_webhook_condition_expect_failure(
        self, evaluator: ConditionEvaluator, state: WorkflowState
    ) -> None:
        """Test checking a webhook condition that expects failure."""
        state.variables["_webhook_check_result"] = {
            "success": False,
            "status_code": 404,
            "body": "Not Found",
            "json_body": None,
        }

        conditions = [
            {
                "type": "webhook",
                "id": "check",
                "expect_success": False,  # We expect it to fail
            }
        ]

        result = evaluator.check_exit_conditions(conditions, state)
        assert result is True

    def test_check_webhook_condition_status_code(
        self, evaluator: ConditionEvaluator, state: WorkflowState
    ) -> None:
        """Test checking webhook condition with specific status code."""
        state.variables["_webhook_check_result"] = {
            "success": True,
            "status_code": 201,
            "body": "Created",
            "json_body": None,
        }

        # Check for specific status code
        conditions = [
            {
                "type": "webhook",
                "id": "check",
                "status_code": 201,
            }
        ]

        result = evaluator.check_exit_conditions(conditions, state)
        assert result is True

        # Check for wrong status code
        conditions = [
            {
                "type": "webhook",
                "id": "check",
                "status_code": 200,
            }
        ]

        result = evaluator.check_exit_conditions(conditions, state)
        assert result is False

    def test_check_webhook_condition_status_code_list(
        self, evaluator: ConditionEvaluator, state: WorkflowState
    ) -> None:
        """Test checking webhook condition with list of status codes."""
        state.variables["_webhook_check_result"] = {
            "success": True,
            "status_code": 201,
            "body": "",
            "json_body": None,
        }

        conditions = [
            {
                "type": "webhook",
                "id": "check",
                "status_code": [200, 201, 202],
            }
        ]

        result = evaluator.check_exit_conditions(conditions, state)
        assert result is True

    def test_check_webhook_condition_body_contains(
        self, evaluator: ConditionEvaluator, state: WorkflowState
    ) -> None:
        """Test checking webhook condition with body_contains."""
        state.variables["_webhook_check_result"] = {
            "success": True,
            "status_code": 200,
            "body": "Status: APPROVED - proceeding with operation",
            "json_body": None,
        }

        # Should pass - body contains "APPROVED"
        conditions = [
            {
                "type": "webhook",
                "id": "check",
                "body_contains": "APPROVED",
            }
        ]

        result = evaluator.check_exit_conditions(conditions, state)
        assert result is True

        # Should fail - body doesn't contain "REJECTED"
        conditions = [
            {
                "type": "webhook",
                "id": "check",
                "body_contains": "REJECTED",
            }
        ]

        result = evaluator.check_exit_conditions(conditions, state)
        assert result is False

    def test_check_webhook_condition_json_field(
        self, evaluator: ConditionEvaluator, state: WorkflowState
    ) -> None:
        """Test checking webhook condition with JSON field check."""
        state.variables["_webhook_check_result"] = {
            "success": True,
            "status_code": 200,
            "body": '{"data": {"approved": true, "user": {"name": "test"}}}',
            "json_body": {"data": {"approved": True, "user": {"name": "test"}}},
        }

        # Check simple field value
        conditions = [
            {
                "type": "webhook",
                "id": "check",
                "json_field": "data.approved",
                "json_value": True,
            }
        ]

        result = evaluator.check_exit_conditions(conditions, state)
        assert result is True

        # Check nested field value
        conditions = [
            {
                "type": "webhook",
                "id": "check",
                "json_field": "data.user.name",
                "json_value": "test",
            }
        ]

        result = evaluator.check_exit_conditions(conditions, state)
        assert result is True

        # Check field exists (truthy check)
        conditions = [
            {
                "type": "webhook",
                "id": "check",
                "json_field": "data.approved",
            }
        ]

        result = evaluator.check_exit_conditions(conditions, state)
        assert result is True

    def test_check_webhook_condition_json_field_missing(
        self, evaluator: ConditionEvaluator, state: WorkflowState
    ) -> None:
        """Test checking webhook condition with missing JSON field."""
        state.variables["_webhook_check_result"] = {
            "success": True,
            "status_code": 200,
            "body": '{"status": "ok"}',
            "json_body": {"status": "ok"},
        }

        conditions = [
            {
                "type": "webhook",
                "id": "check",
                "json_field": "data.approved",
            }
        ]

        result = evaluator.check_exit_conditions(conditions, state)
        assert result is False

    def test_check_webhook_condition_not_evaluated(
        self, evaluator: ConditionEvaluator, state: WorkflowState
    ) -> None:
        """Test checking webhook condition that wasn't pre-evaluated."""
        # No webhook result in state.variables
        conditions = [
            {
                "type": "webhook",
                "id": "unevaluated",
                "expect_success": True,
            }
        ]

        result = evaluator.check_exit_conditions(conditions, state)
        assert result is False  # Should fail since not evaluated

    def test_check_mixed_conditions(
        self, evaluator: ConditionEvaluator, state: WorkflowState
    ) -> None:
        """Test checking multiple condition types including webhook."""
        state.variables["my_var"] = "set"
        state.variables["_webhook_api_check_result"] = {
            "success": True,
            "status_code": 200,
            "body": "OK",
            "json_body": None,
        }

        conditions = [
            {
                "type": "variable_set",
                "variable": "my_var",
            },
            {
                "type": "webhook",
                "id": "api_check",
                "expect_success": True,
            },
        ]

        result = evaluator.check_exit_conditions(conditions, state)
        assert result is True

        # Remove the variable - should fail
        del state.variables["my_var"]
        result = evaluator.check_exit_conditions(conditions, state)
        assert result is False


class TestGetNestedValue:
    """Tests for the _get_nested_value helper."""

    def test_get_simple_value(self, evaluator: ConditionEvaluator) -> None:
        """Test getting a simple value."""
        obj = {"name": "test"}
        assert evaluator._get_nested_value(obj, "name") == "test"

    def test_get_nested_value(self, evaluator: ConditionEvaluator) -> None:
        """Test getting a nested value."""
        obj = {"data": {"user": {"id": 123}}}
        assert evaluator._get_nested_value(obj, "data.user.id") == 123

    def test_get_missing_value(self, evaluator: ConditionEvaluator) -> None:
        """Test getting a missing value."""
        obj = {"data": {"user": {}}}
        assert evaluator._get_nested_value(obj, "data.user.id") is None
        assert evaluator._get_nested_value(obj, "missing.path") is None

    def test_get_value_from_non_dict(self, evaluator: ConditionEvaluator) -> None:
        """Test getting value when path traverses non-dict."""
        obj = {"data": "string"}
        assert evaluator._get_nested_value(obj, "data.nested") is None
