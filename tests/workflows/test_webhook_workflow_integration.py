"""
Integration tests for webhook workflow scenarios.

These tests verify end-to-end webhook execution within workflows,
covering event triggers, response chaining, failure handling,
and combination with plugin actions.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.hooks.plugins import HookPlugin, PluginRegistry
from gobby.workflows.actions import ActionContext, ActionExecutor
from gobby.workflows.definitions import WorkflowState
from gobby.workflows.engine import WorkflowEngine
from gobby.workflows.evaluator import ConditionEvaluator
from gobby.workflows.loader import WorkflowLoader
from gobby.workflows.state_manager import WorkflowStateManager

# =============================================================================
# Mock HTTP Response Helpers
# =============================================================================


def create_mock_response(status=200, body="{}", headers=None):
    """Create a mock aiohttp response."""
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.text = AsyncMock(return_value=body)
    mock_response.headers = headers or {}
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    return mock_response


def create_mock_session(responses):
    """Create a mock aiohttp session returning given responses in order."""
    if not isinstance(responses, list):
        responses = [responses]

    call_index = [0]
    call_args_list = []

    def get_response(*args, **kwargs):
        call_args_list.append((args, kwargs))
        idx = min(call_index[0], len(responses) - 1)
        call_index[0] += 1
        resp = responses[idx]
        if isinstance(resp, Exception):
            raise resp
        return resp

    mock_session = MagicMock()
    mock_session.request = MagicMock(side_effect=get_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session._call_args_list = call_args_list
    return mock_session


# =============================================================================
# Test Plugin for Integration Tests
# =============================================================================


class WebhookTestPlugin(HookPlugin):
    """Plugin for testing webhook + plugin action combinations."""

    name = "webhook-test"
    version = "1.0.0"

    def __init__(self):
        super().__init__()
        self.action_calls = []

    def on_load(self, config: dict) -> None:
        self.register_action("log_webhook_result", self._log_webhook_result)
        self.register_action("process_data", self._process_data)
        self.register_action("fallback_handler", self._fallback_handler)

    async def _log_webhook_result(self, context: ActionContext, **kwargs) -> dict:
        """Log webhook result from previous action."""
        self.action_calls.append(
            {
                "action": "log_webhook_result",
                "kwargs": kwargs,
                "variables": dict(context.state.variables) if context.state else {},
            }
        )
        return {"logged": True}

    async def _process_data(self, context: ActionContext, **kwargs) -> dict:
        """Process data from previous actions."""
        self.action_calls.append(
            {
                "action": "process_data",
                "kwargs": kwargs,
                "variables": dict(context.state.variables) if context.state else {},
            }
        )
        return {"processed": True, "input": kwargs.get("data")}

    async def _fallback_handler(self, context: ActionContext, **kwargs) -> dict:
        """Fallback handler for webhook failures."""
        self.action_calls.append(
            {
                "action": "fallback_handler",
                "kwargs": kwargs,
                "error": kwargs.get("error"),
            }
        )
        return {"fallback_executed": True}


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Create mock database."""
    return MagicMock()


@pytest.fixture
def mock_session_manager():
    """Create mock session manager."""
    manager = MagicMock()
    manager.get.return_value = MagicMock(project_id="test-project")
    return manager


@pytest.fixture
def mock_template_engine():
    """Create mock template engine with variable interpolation."""
    engine = MagicMock()

    def render(template, context):
        if isinstance(template, str):
            result = template
            for key, value in context.items():
                if isinstance(value, (str, int, float)):
                    result = result.replace(f"${{{key}}}", str(value))
            return result
        return template

    engine.render.side_effect = render
    return engine


@pytest.fixture
def webhook_test_plugin():
    """Create and load test plugin."""
    plugin = WebhookTestPlugin()
    plugin.on_load({})
    return plugin


@pytest.fixture
def plugin_registry(webhook_test_plugin):
    """Create registry with test plugin."""
    registry = PluginRegistry()
    registry.register_plugin(webhook_test_plugin)
    return registry


@pytest.fixture
def action_executor(mock_db, mock_session_manager, mock_template_engine, plugin_registry):
    """Create ActionExecutor with plugin actions registered."""
    executor = ActionExecutor(
        db=mock_db,
        session_manager=mock_session_manager,
        template_engine=mock_template_engine,
    )
    executor.register_plugin_actions(plugin_registry)
    return executor


@pytest.fixture
def workflow_state():
    """Create a workflow state for testing."""
    return WorkflowState(
        session_id="test-session-123",
        workflow_name="test-workflow",
        step="execute",
        variables={},
    )


@pytest.fixture
def action_context(workflow_state, mock_db, mock_session_manager, mock_template_engine):
    """Create ActionContext for testing."""
    return ActionContext(
        session_id=workflow_state.session_id,
        state=workflow_state,
        db=mock_db,
        session_manager=mock_session_manager,
        template_engine=mock_template_engine,
    )


@pytest.fixture
def mock_loader():
    """Create mock workflow loader."""
    return MagicMock(spec=WorkflowLoader)


@pytest.fixture
def mock_state_manager():
    """Create mock state manager."""
    return MagicMock(spec=WorkflowStateManager)


@pytest.fixture
def workflow_engine(mock_loader, mock_state_manager, action_executor):
    """Create WorkflowEngine for testing."""
    return WorkflowEngine(
        loader=mock_loader,
        state_manager=mock_state_manager,
        action_executor=action_executor,
        evaluator=ConditionEvaluator(),
    )


# =============================================================================
# Test: Workflow Triggered by Event Fires Webhook
# =============================================================================


class TestWorkflowEventTriggersWebhook:
    """Tests for workflows that fire webhooks on events."""

    @pytest.mark.asyncio
    async def test_session_end_event_triggers_webhook(self, action_executor, workflow_state):
        """Webhook is fired when workflow action executes on event."""
        mock_response = create_mock_response(
            status=200,
            body='{"received": true}',
        )
        mock_session = create_mock_session(mock_response)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            # Execute webhook action as if triggered by event
            result = await action_executor.execute(
                "webhook",
                context,
                url="https://api.example.com/session-end",
                method="POST",
                payload={"session_id": "test-session", "event": "session_end"},
            )

            # Verify webhook was called
            assert mock_session.request.call_count == 1
            call_kwargs = mock_session.request.call_args[1]
            assert call_kwargs["url"] == "https://api.example.com/session-end"
            assert call_kwargs["method"] == "POST"

            # Verify result
            assert result is not None
            assert result.get("success") is True

    @pytest.mark.asyncio
    async def test_webhook_payload_includes_event_context(self, action_executor, workflow_state):
        """Webhook payload can include interpolated event context."""
        mock_response = create_mock_response(status=200, body='{"ok": true}')
        mock_session = create_mock_session(mock_response)

        # Set up state variables that would come from event
        workflow_state.variables["user_id"] = "user-456"
        workflow_state.variables["action_count"] = 42

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            result = await action_executor.execute(
                "webhook",
                context,
                url="https://api.example.com/events",
                method="POST",
                payload={
                    "user": "${user_id}",
                    "actions": "${action_count}",
                },
            )

            assert result.get("success") is True


# =============================================================================
# Test: Webhook Response Data Used in Subsequent Action
# =============================================================================


class TestWebhookResponseChaining:
    """Tests for using webhook response data in subsequent actions."""

    @pytest.mark.asyncio
    async def test_webhook_response_captured_to_state_variables(
        self, action_executor, workflow_state
    ):
        """Webhook response is captured and available for subsequent actions."""
        mock_response = create_mock_response(
            status=201,
            body='{"ticket_id": "JIRA-123", "url": "https://jira.example.com/JIRA-123"}',
            headers={"X-Request-Id": "req-abc-123"},
        )
        mock_session = create_mock_session(mock_response)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            result = await action_executor.execute(
                "webhook",
                context,
                url="https://api.jira.com/create-ticket",
                method="POST",
                payload={"summary": "Test ticket"},
                capture_response={
                    "status_var": "jira_status",
                    "body_var": "jira_response",
                },
            )

            # Response should be captured
            assert result.get("success") is True
            assert result.get("status_code") == 201
            assert "ticket_id" in result.get("body", "")

    @pytest.mark.asyncio
    async def test_chained_actions_can_access_webhook_response(
        self,
        action_executor,
        workflow_state,
        webhook_test_plugin,
    ):
        """Subsequent plugin action can access webhook response via state."""
        mock_response = create_mock_response(
            status=200,
            body='{"data": "webhook_result_data"}',
        )
        mock_session = create_mock_session(mock_response)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            # First: Execute webhook
            webhook_result = await action_executor.execute(
                "webhook",
                context,
                url="https://api.example.com/fetch-data",
                method="GET",
            )

            # Store result in state (simulating what engine does)
            workflow_state.variables["webhook_body"] = webhook_result.get("body")

            # Second: Plugin action accesses the result
            plugin_result = await action_executor.execute(
                "plugin:webhook-test:process_data",
                context,
                data=workflow_state.variables.get("webhook_body"),
            )

            # Verify plugin received the webhook data
            assert plugin_result.get("processed") is True
            assert len(webhook_test_plugin.action_calls) == 1
            assert (
                webhook_test_plugin.action_calls[0]["kwargs"]["data"]
                == '{"data": "webhook_result_data"}'
            )


# =============================================================================
# Test: Webhook Failure Triggers Fallback Action
# =============================================================================


class TestWebhookFailureFallback:
    """Tests for fallback actions when webhooks fail."""

    @pytest.mark.asyncio
    async def test_webhook_timeout_returns_error(self, action_executor, workflow_state):
        """Webhook timeout is captured as error in result."""
        mock_session = MagicMock()
        mock_session.request = MagicMock(side_effect=TimeoutError("Connection timed out"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            result = await action_executor.execute(
                "webhook",
                context,
                url="https://slow.example.com/webhook",
                method="POST",
                payload={},
                timeout=5,
            )

            assert result.get("success") is False
            assert "error" in result
            assert "timeout" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_webhook_5xx_error_captured(self, action_executor, workflow_state):
        """HTTP 5xx errors are captured in result."""
        mock_response = create_mock_response(
            status=503,
            body='{"error": "Service Unavailable"}',
        )
        mock_session = create_mock_session(mock_response)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            result = await action_executor.execute(
                "webhook",
                context,
                url="https://api.example.com/webhook",
                method="POST",
                payload={},
            )

            # Non-2xx status means success=False
            assert result.get("success") is False
            assert result.get("status_code") == 503

    @pytest.mark.asyncio
    async def test_fallback_action_executes_after_webhook_failure(
        self,
        action_executor,
        workflow_state,
        webhook_test_plugin,
    ):
        """Fallback plugin action is executed after webhook failure."""
        mock_session = MagicMock()
        mock_session.request = MagicMock(side_effect=TimeoutError("Timeout"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            # Execute webhook (will fail)
            webhook_result = await action_executor.execute(
                "webhook",
                context,
                url="https://api.example.com/webhook",
                method="POST",
                payload={},
            )

            # Webhook failed
            assert webhook_result.get("success") is False

            # Execute fallback action (simulating what workflow engine would do)
            fallback_result = await action_executor.execute(
                "plugin:webhook-test:fallback_handler",
                context,
                error=webhook_result.get("error"),
                original_url="https://api.example.com/webhook",
            )

            # Verify fallback was executed
            assert fallback_result.get("fallback_executed") is True
            assert len(webhook_test_plugin.action_calls) == 1
            assert webhook_test_plugin.action_calls[0]["action"] == "fallback_handler"
            assert "timeout" in webhook_test_plugin.action_calls[0]["error"].lower()


# =============================================================================
# Test: Chained Webhooks in Sequence
# =============================================================================


class TestChainedWebhooks:
    """Tests for multiple webhooks executing in sequence."""

    @pytest.mark.asyncio
    async def test_multiple_webhooks_execute_in_order(self, action_executor, workflow_state):
        """Multiple webhooks execute in correct sequence."""
        responses = [
            create_mock_response(status=200, body='{"step": 1}'),
            create_mock_response(status=200, body='{"step": 2}'),
            create_mock_response(status=200, body='{"step": 3}'),
        ]
        mock_session = create_mock_session(responses)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            results = []

            # Execute three webhooks in sequence
            for i in range(3):
                result = await action_executor.execute(
                    "webhook",
                    context,
                    url=f"https://api.example.com/step-{i+1}",
                    method="POST",
                    payload={"step": i + 1},
                )
                results.append(result)

            # All should succeed
            assert all(r.get("success") for r in results)

            # Verify order
            assert mock_session.request.call_count == 3
            call_urls = [mock_session._call_args_list[i][1]["url"] for i in range(3)]
            assert call_urls == [
                "https://api.example.com/step-1",
                "https://api.example.com/step-2",
                "https://api.example.com/step-3",
            ]

    @pytest.mark.asyncio
    async def test_webhook_chain_passes_data_forward(self, action_executor, workflow_state):
        """Response from first webhook can be passed to second webhook."""
        responses = [
            create_mock_response(status=200, body='{"token": "abc123"}'),
            create_mock_response(status=200, body='{"authorized": true}'),
        ]
        mock_session = create_mock_session(responses)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            # First webhook: get auth token
            result1 = await action_executor.execute(
                "webhook",
                context,
                url="https://auth.example.com/token",
                method="POST",
                payload={"username": "test"},
            )

            # Parse token from response
            import json

            token = json.loads(result1.get("body", "{}")).get("token")
            workflow_state.variables["auth_token"] = token

            # Second webhook: use token
            result2 = await action_executor.execute(
                "webhook",
                context,
                url="https://api.example.com/protected",
                method="POST",
                headers={"Authorization": f"Bearer {token}"},
                payload={"action": "do_something"},
            )

            assert result1.get("success") is True
            assert result2.get("success") is True

            # Verify second call included the token
            second_call = mock_session._call_args_list[1]
            assert second_call[1]["headers"]["Authorization"] == "Bearer abc123"

    @pytest.mark.asyncio
    async def test_webhook_chain_stops_on_failure_when_required(
        self, action_executor, workflow_state
    ):
        """Chain can be designed to stop on failure."""
        responses = [
            create_mock_response(status=200, body='{"ok": true}'),
            create_mock_response(status=500, body='{"error": "Failed"}'),
            create_mock_response(status=200, body='{"should_not_run": true}'),
        ]
        mock_session = create_mock_session(responses)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            results = []

            for i in range(3):
                result = await action_executor.execute(
                    "webhook",
                    context,
                    url=f"https://api.example.com/step-{i+1}",
                    method="POST",
                    payload={},
                )
                results.append(result)

                # Stop on failure (simulating workflow logic)
                if not result.get("success"):
                    break

            # Only 2 webhooks should have been called
            assert len(results) == 2
            assert results[0].get("success") is True
            assert results[1].get("success") is False
            assert mock_session.request.call_count == 2


# =============================================================================
# Test: Webhook with Plugin Action Combination
# =============================================================================


class TestWebhookPluginCombination:
    """Tests for workflows combining webhooks with plugin actions."""

    @pytest.mark.asyncio
    async def test_plugin_action_before_webhook(
        self, action_executor, workflow_state, webhook_test_plugin
    ):
        """Plugin action can prepare data for webhook."""
        mock_response = create_mock_response(status=200, body='{"received": true}')
        mock_session = create_mock_session(mock_response)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            # Plugin action prepares data
            plugin_result = await action_executor.execute(
                "plugin:webhook-test:process_data",
                context,
                data="prepare_for_webhook",
            )
            workflow_state.variables["prepared_data"] = plugin_result

            # Webhook uses prepared data
            webhook_result = await action_executor.execute(
                "webhook",
                context,
                url="https://api.example.com/submit",
                method="POST",
                payload={"data": workflow_state.variables.get("prepared_data")},
            )

            assert plugin_result.get("processed") is True
            assert webhook_result.get("success") is True

    @pytest.mark.asyncio
    async def test_plugin_action_after_webhook(
        self, action_executor, workflow_state, webhook_test_plugin
    ):
        """Plugin action can process webhook response."""
        mock_response = create_mock_response(
            status=200,
            body='{"ticket_id": "PROJ-456", "status": "created"}',
        )
        mock_session = create_mock_session(mock_response)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            # Webhook creates ticket
            webhook_result = await action_executor.execute(
                "webhook",
                context,
                url="https://api.jira.com/create",
                method="POST",
                payload={"summary": "Test"},
            )

            # Store in state
            workflow_state.variables["webhook_response"] = webhook_result.get("body")

            # Plugin action logs/processes result
            plugin_result = await action_executor.execute(
                "plugin:webhook-test:log_webhook_result",
                context,
                ticket_body=webhook_result.get("body"),
            )

            assert webhook_result.get("success") is True
            assert plugin_result.get("logged") is True
            assert len(webhook_test_plugin.action_calls) == 1

    @pytest.mark.asyncio
    async def test_mixed_sequence_webhook_plugin_webhook(
        self, action_executor, workflow_state, webhook_test_plugin
    ):
        """Complex sequence: webhook -> plugin -> webhook works correctly."""
        responses = [
            create_mock_response(status=200, body='{"token": "xyz789"}'),
            create_mock_response(status=200, body='{"final": "success"}'),
        ]
        mock_session = create_mock_session(responses)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            # Step 1: Webhook to get token
            result1 = await action_executor.execute(
                "webhook",
                context,
                url="https://auth.example.com/login",
                method="POST",
                payload={"user": "test"},
            )
            workflow_state.variables["auth_response"] = result1.get("body")

            # Step 2: Plugin processes the response
            result2 = await action_executor.execute(
                "plugin:webhook-test:process_data",
                context,
                data=result1.get("body"),
            )
            workflow_state.variables["processed"] = result2

            # Step 3: Another webhook using processed data
            result3 = await action_executor.execute(
                "webhook",
                context,
                url="https://api.example.com/final",
                method="POST",
                payload={"auth": workflow_state.variables.get("auth_response")},
            )

            # All should succeed
            assert result1.get("success") is True
            assert result2.get("processed") is True
            assert result3.get("success") is True

            # Verify execution order
            assert mock_session.request.call_count == 2
            assert len(webhook_test_plugin.action_calls) == 1


# =============================================================================
# Test: Workflow Engine Integration
# =============================================================================


class TestWorkflowEngineWebhookIntegration:
    """Tests for webhook execution through WorkflowEngine."""

    @pytest.mark.asyncio
    async def test_engine_executes_webhook_action_in_workflow(
        self, workflow_engine, workflow_state
    ):
        """WorkflowEngine correctly executes webhook actions."""
        mock_response = create_mock_response(status=200, body='{"engine": "test"}')
        mock_session = create_mock_session(mock_response)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            # Simulate workflow action list
            actions = [
                {
                    "action": "webhook",
                    "url": "https://api.example.com/engine-test",
                    "method": "POST",
                    "payload": {"source": "workflow_engine"},
                },
            ]

            await workflow_engine._execute_actions(actions, workflow_state)

            # Verify webhook was called
            assert mock_session.request.call_count == 1

    @pytest.mark.asyncio
    async def test_engine_handles_webhook_error_gracefully(self, workflow_engine, workflow_state):
        """WorkflowEngine handles webhook errors without crashing."""
        mock_session = MagicMock()
        mock_session.request = MagicMock(side_effect=TimeoutError("Timeout"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            actions = [
                {
                    "action": "webhook",
                    "url": "https://slow.example.com/timeout",
                    "method": "POST",
                    "payload": {},
                },
            ]

            # Should not raise
            await workflow_engine._execute_actions(actions, workflow_state)

    @pytest.mark.asyncio
    async def test_engine_executes_mixed_actions(
        self,
        workflow_engine,
        workflow_state,
        webhook_test_plugin,
    ):
        """WorkflowEngine executes mixed webhook and plugin actions."""
        mock_response = create_mock_response(status=200, body='{"mixed": true}')
        mock_session = create_mock_session(mock_response)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            actions = [
                {
                    "action": "plugin:webhook-test:process_data",
                    "data": "before_webhook",
                },
                {
                    "action": "webhook",
                    "url": "https://api.example.com/mixed",
                    "method": "POST",
                    "payload": {},
                },
                {
                    "action": "plugin:webhook-test:log_webhook_result",
                    "after": "webhook",
                },
            ]

            await workflow_engine._execute_actions(actions, workflow_state)

            # All actions executed
            assert mock_session.request.call_count == 1
            assert len(webhook_test_plugin.action_calls) == 2


# =============================================================================
# Test: Error Handling and Edge Cases
# =============================================================================


class TestWebhookErrorHandling:
    """Tests for error handling in webhook workflows."""

    @pytest.mark.asyncio
    async def test_invalid_url_returns_error(self, action_executor, workflow_state):
        """Invalid URL configuration returns error."""
        context = ActionContext(
            session_id="test-session",
            state=workflow_state,
            db=MagicMock(),
            session_manager=MagicMock(),
            template_engine=MagicMock(),
        )

        result = await action_executor.execute(
            "webhook",
            context,
            # Missing url
            method="POST",
            payload={},
        )

        assert result is not None
        assert "error" in result

    @pytest.mark.asyncio
    async def test_4xx_error_not_retried_by_default(self, action_executor, workflow_state):
        """4xx client errors are not retried by default."""
        mock_response = create_mock_response(
            status=400,
            body='{"error": "Bad Request"}',
        )
        mock_session = create_mock_session(mock_response)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            result = await action_executor.execute(
                "webhook",
                context,
                url="https://api.example.com/webhook",
                method="POST",
                payload={"invalid": "data"},
                retry={
                    "max_attempts": 3,
                    "backoff_seconds": 0.01,
                    "retry_on_status": [500, 502, 503],
                },
            )

            # Should only be called once (no retry for 400)
            assert mock_session.request.call_count == 1
            assert result.get("success") is False
            assert result.get("status_code") == 400

    @pytest.mark.asyncio
    async def test_execution_time_within_threshold(self, action_executor, workflow_state):
        """Webhook execution completes within acceptable time."""
        import time

        mock_response = create_mock_response(status=200, body='{"fast": true}')
        mock_session = create_mock_session(mock_response)

        with patch(
            "gobby.workflows.webhook_executor.aiohttp.ClientSession", return_value=mock_session
        ):
            context = ActionContext(
                session_id="test-session",
                state=workflow_state,
                db=MagicMock(),
                session_manager=MagicMock(),
                template_engine=MagicMock(),
            )

            start = time.time()
            result = await action_executor.execute(
                "webhook",
                context,
                url="https://api.example.com/fast",
                method="GET",
            )
            elapsed = time.time() - start

            assert result.get("success") is True
            # Should complete in under 5 seconds (mocked, so should be near-instant)
            assert elapsed < 5.0
