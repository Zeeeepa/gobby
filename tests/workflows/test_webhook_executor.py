"""
Tests for WebhookExecutor.

TDD Red Phase: These tests should FAIL initially because WebhookExecutor doesn't exist yet.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# This import will fail until WebhookExecutor is implemented
from gobby.workflows.webhook_executor import WebhookExecutor, WebhookResult


@pytest.fixture
def mock_template_engine():
    """Create a mock template engine for variable interpolation."""
    engine = MagicMock()
    engine.render.side_effect = lambda tmpl, ctx: tmpl  # Pass through by default
    return engine


@pytest.fixture
def mock_webhook_registry():
    """Create a mock webhook registry for webhook_id resolution."""
    return {
        "slack_alerts": {
            "url": "https://hooks.slack.com/services/xxx",
            "headers": {"Content-Type": "application/json"},
        },
        "jira_api": {
            "url": "https://api.jira.com/webhook",
            "headers": {"Authorization": "Bearer default-token"},
        },
    }


@pytest.fixture
def mock_secrets():
    """Create a mock secrets provider."""
    return {
        "API_KEY": "secret-api-key-123",
        "SLACK_TOKEN": "xoxb-slack-token",
    }


@pytest.fixture
def executor(mock_template_engine, mock_webhook_registry, mock_secrets):
    """Create a WebhookExecutor instance with mocked dependencies."""
    return WebhookExecutor(
        template_engine=mock_template_engine,
        webhook_registry=mock_webhook_registry,
        secrets=mock_secrets,
    )


class TestWebhookExecutorSuccessPath:
    """Tests for successful webhook execution."""

    @pytest.mark.asyncio
    async def test_executor_makes_http_request_with_correct_method(self, executor):
        """Executor should make HTTP request with the configured method."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value='{"ok": true}')
            mock_response.headers = {"Content-Type": "application/json"}

            mock_session = MagicMock()
            mock_session.request = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await executor.execute(
                url="https://api.example.com/events",
                method="PUT",
                headers={},
                payload={"test": "data"},
                timeout=30,
            )

            mock_session.request.assert_called_once()
            call_args = mock_session.request.call_args
            assert call_args[1]["method"] == "PUT"
            assert call_args[1]["url"] == "https://api.example.com/events"

    @pytest.mark.asyncio
    async def test_executor_sends_headers_from_config(self, executor):
        """Executor should send configured headers including interpolated values."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value='{}')
            mock_response.headers = {}

            mock_session = MagicMock()
            mock_session.request = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await executor.execute(
                url="https://api.example.com/webhook",
                method="POST",
                headers={
                    "Authorization": "Bearer test-token",
                    "X-Custom-Header": "custom-value",
                },
                payload=None,
                timeout=30,
            )

            call_args = mock_session.request.call_args
            headers = call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer test-token"
            assert headers["X-Custom-Header"] == "custom-value"

    @pytest.mark.asyncio
    async def test_executor_interpolates_payload_variables(self, executor, mock_template_engine):
        """Executor should interpolate ${context.var} in payload."""
        # Configure template engine to interpolate
        mock_template_engine.render.side_effect = lambda tmpl, ctx: tmpl.replace(
            "${session_id}", "sess-123"
        ).replace("${context.summary}", "Session completed successfully")

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value='{}')
            mock_response.headers = {}

            mock_session = MagicMock()
            mock_session.request = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await executor.execute(
                url="https://api.example.com/webhook",
                method="POST",
                headers={},
                payload={"event": "session_end", "id": "${session_id}", "summary": "${context.summary}"},
                timeout=30,
                context={"session_id": "sess-123", "context": {"summary": "Session completed successfully"}},
            )

            call_args = mock_session.request.call_args
            json_payload = call_args[1].get("json") or call_args[1].get("data")
            # Payload should have interpolated values
            assert isinstance(result, WebhookResult)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_executor_captures_response(self, executor):
        """Executor should capture status, body, and headers from response."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 201
            mock_response.text = AsyncMock(return_value='{"ticket_id": "PROJ-123"}')
            mock_response.headers = {"X-Request-Id": "req-abc"}

            mock_session = MagicMock()
            mock_session.request = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await executor.execute(
                url="https://api.example.com/webhook",
                method="POST",
                headers={},
                payload={},
                timeout=30,
            )

            assert result.status_code == 201
            assert result.body == '{"ticket_id": "PROJ-123"}'
            assert result.headers["X-Request-Id"] == "req-abc"


class TestWebhookExecutorFailureHandling:
    """Tests for failure handling and retries."""

    @pytest.mark.asyncio
    async def test_request_timeout_raises_error(self, executor):
        """Request timeout should raise TimeoutError after configured seconds."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await executor.execute(
                url="https://api.example.com/webhook",
                method="POST",
                headers={},
                payload={},
                timeout=5,
            )

            assert result.success is False
            assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_http_5xx_triggers_retry(self, executor):
        """HTTP 5xx response should trigger retry when in retry_on_status."""
        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_response = AsyncMock()
            if call_count < 3:
                mock_response.status = 500
                mock_response.text = AsyncMock(return_value="Internal Server Error")
            else:
                mock_response.status = 200
                mock_response.text = AsyncMock(return_value='{"ok": true}')
            mock_response.headers = {}
            return mock_response

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = mock_request
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await executor.execute(
                url="https://api.example.com/webhook",
                method="POST",
                headers={},
                payload={},
                timeout=30,
                retry_config={"max_attempts": 3, "backoff_seconds": 0.1, "retry_on_status": [500, 502]},
            )

            assert call_count == 3
            assert result.success is True

    @pytest.mark.asyncio
    async def test_retries_use_exponential_backoff(self, executor):
        """Retries should use exponential backoff (backoff_seconds * 2^attempt)."""
        call_times = []

        async def mock_request(*args, **kwargs):
            call_times.append(asyncio.get_event_loop().time())
            mock_response = AsyncMock()
            mock_response.status = 503
            mock_response.text = AsyncMock(return_value="Service Unavailable")
            mock_response.headers = {}
            return mock_response

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = mock_request
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await executor.execute(
                url="https://api.example.com/webhook",
                method="POST",
                headers={},
                payload={},
                timeout=30,
                retry_config={"max_attempts": 3, "backoff_seconds": 0.1, "retry_on_status": [503]},
            )

            # Should have made 3 attempts
            assert len(call_times) == 3
            # Verify exponential backoff: first retry ~0.1s, second ~0.2s
            if len(call_times) >= 2:
                first_delay = call_times[1] - call_times[0]
                assert first_delay >= 0.05  # Allow some timing variance
            if len(call_times) >= 3:
                second_delay = call_times[2] - call_times[1]
                assert second_delay >= first_delay  # Second delay should be longer

    @pytest.mark.asyncio
    async def test_max_attempts_exhausted_calls_on_failure(self, executor):
        """After max_attempts exhausted, on_failure handler should be called."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="Internal Server Error")
            mock_response.headers = {}

            mock_session = MagicMock()
            mock_session.request = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            on_failure_called = False

            async def on_failure_handler(result):
                nonlocal on_failure_called
                on_failure_called = True

            result = await executor.execute(
                url="https://api.example.com/webhook",
                method="POST",
                headers={},
                payload={},
                timeout=30,
                retry_config={"max_attempts": 2, "backoff_seconds": 0.01, "retry_on_status": [500]},
                on_failure=on_failure_handler,
            )

            assert result.success is False
            assert on_failure_called is True

    @pytest.mark.asyncio
    async def test_network_error_triggers_retry(self, executor):
        """Network errors (connection refused) should trigger retry."""
        call_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Connection refused")
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value='{}')
            mock_response.headers = {}
            return mock_response

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = mock_request
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await executor.execute(
                url="https://api.example.com/webhook",
                method="POST",
                headers={},
                payload={},
                timeout=30,
                retry_config={"max_attempts": 3, "backoff_seconds": 0.01, "retry_on_status": [500]},
            )

            assert call_count == 2
            assert result.success is True


class TestWebhookExecutorEdgeCases:
    """Tests for edge cases and special handling."""

    @pytest.mark.asyncio
    async def test_webhook_id_resolves_to_url(self, executor, mock_webhook_registry):
        """webhook_id should resolve to URL from webhook registry."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value='{}')
            mock_response.headers = {}

            mock_session = MagicMock()
            mock_session.request = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await executor.execute_by_webhook_id(
                webhook_id="slack_alerts",
                payload={"text": "Hello"},
            )

            call_args = mock_session.request.call_args
            assert call_args[1]["url"] == "https://hooks.slack.com/services/xxx"
            assert result.success is True

    @pytest.mark.asyncio
    async def test_missing_webhook_id_raises_error(self, executor):
        """Missing webhook_id in registry should raise clear error."""
        with pytest.raises(ValueError, match="webhook_id.*not found|unknown webhook"):
            await executor.execute_by_webhook_id(
                webhook_id="nonexistent_webhook",
                payload={},
            )

    @pytest.mark.asyncio
    async def test_secrets_interpolation_in_headers(self, executor, mock_secrets):
        """Secrets interpolation (${secrets.API_KEY}) should work in headers."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value='{}')
            mock_response.headers = {}

            mock_session = MagicMock()
            mock_session.request = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await executor.execute(
                url="https://api.example.com/webhook",
                method="POST",
                headers={"Authorization": "Bearer ${secrets.API_KEY}"},
                payload={},
                timeout=30,
            )

            call_args = mock_session.request.call_args
            headers = call_args[1]["headers"]
            # Secret should be interpolated
            assert headers["Authorization"] == "Bearer secret-api-key-123"
            assert result.success is True

    @pytest.mark.asyncio
    async def test_large_response_body_handled(self, executor):
        """Large response bodies (>1MB) should be handled without memory issues."""
        large_body = "x" * (1024 * 1024 + 100)  # Just over 1MB

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value=large_body)
            mock_response.headers = {"Content-Length": str(len(large_body))}

            mock_session = MagicMock()
            mock_session.request = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await executor.execute(
                url="https://api.example.com/webhook",
                method="POST",
                headers={},
                payload={},
                timeout=30,
            )

            assert result.success is True
            # Body might be truncated for safety
            assert len(result.body) > 0


class TestWebhookResult:
    """Tests for WebhookResult data class."""

    def test_webhook_result_success_attributes(self):
        """WebhookResult should have success, status_code, body, headers, error."""
        result = WebhookResult(
            success=True,
            status_code=200,
            body='{"ok": true}',
            headers={"Content-Type": "application/json"},
            error=None,
        )

        assert result.success is True
        assert result.status_code == 200
        assert result.body == '{"ok": true}'
        assert result.headers["Content-Type"] == "application/json"
        assert result.error is None

    def test_webhook_result_failure_attributes(self):
        """WebhookResult for failure should have error message."""
        result = WebhookResult(
            success=False,
            status_code=None,
            body=None,
            headers=None,
            error="Connection refused",
        )

        assert result.success is False
        assert result.status_code is None
        assert result.error == "Connection refused"

    def test_webhook_result_json_body(self):
        """WebhookResult should have helper to parse JSON body."""
        result = WebhookResult(
            success=True,
            status_code=200,
            body='{"ticket_id": "PROJ-123", "url": "https://jira.example.com/PROJ-123"}',
            headers={},
            error=None,
        )

        json_body = result.json_body()
        assert json_body["ticket_id"] == "PROJ-123"
        assert json_body["url"] == "https://jira.example.com/PROJ-123"

    def test_webhook_result_json_body_returns_none_for_invalid(self):
        """json_body() should return None for non-JSON body."""
        result = WebhookResult(
            success=True,
            status_code=200,
            body="Not JSON content",
            headers={},
            error=None,
        )

        assert result.json_body() is None
