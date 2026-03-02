"""Tests for workflows/webhook_actions.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_template_engine() -> MagicMock:
    engine = MagicMock()
    engine.render.side_effect = lambda v, _ctx: v
    return engine


@pytest.fixture
def mock_state() -> MagicMock:
    state = MagicMock()
    state.variables = {"api_key": "test123"}
    return state


# --- execute_webhook ---


@pytest.mark.asyncio
async def test_execute_webhook_success(
    mock_template_engine: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.webhook_actions import execute_webhook

    mock_result = MagicMock()
    mock_result.success = True
    mock_result.status_code = 200
    mock_result.error = None
    mock_result.body = '{"ok": true}'

    with (
        patch("gobby.workflows.webhook.WebhookAction") as MockAction,
        patch("gobby.workflows.webhook_executor.WebhookExecutor") as MockExecutor,
    ):
        action_instance = MagicMock()
        action_instance.url = "https://example.com/hook"
        action_instance.method = "POST"
        action_instance.headers = {}
        action_instance.payload = {}
        action_instance.timeout = 30
        action_instance.retry = None
        action_instance.capture_response = None
        action_instance.webhook_id = None
        MockAction.from_dict.return_value = action_instance

        MockExecutor.return_value.execute = AsyncMock(return_value=mock_result)

        result = await execute_webhook(
            mock_template_engine,
            mock_state,
            None,
            url="https://example.com/hook",
        )

    assert result["success"] is True
    assert result["status_code"] == 200


@pytest.mark.asyncio
async def test_execute_webhook_invalid_config(
    mock_template_engine: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.webhook_actions import execute_webhook

    with patch("gobby.workflows.webhook.WebhookAction") as MockAction:
        MockAction.from_dict.side_effect = ValueError("bad config")

        result = await execute_webhook(mock_template_engine, mock_state, None)

    assert result["success"] is False
    assert "bad config" in result["error"]


@pytest.mark.asyncio
async def test_execute_webhook_no_url_no_id(
    mock_template_engine: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.webhook_actions import execute_webhook

    with patch("gobby.workflows.webhook.WebhookAction") as MockAction:
        action_instance = MagicMock()
        action_instance.url = None
        action_instance.webhook_id = None
        MockAction.from_dict.return_value = action_instance

        result = await execute_webhook(mock_template_engine, mock_state, None)

    assert result["success"] is False
    assert "url or webhook_id" in result["error"]


@pytest.mark.asyncio
async def test_execute_webhook_webhook_id_unsupported(
    mock_template_engine: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.webhook_actions import execute_webhook

    with patch("gobby.workflows.webhook.WebhookAction") as MockAction:
        action_instance = MagicMock()
        action_instance.url = None
        action_instance.webhook_id = "wh-123"
        MockAction.from_dict.return_value = action_instance

        result = await execute_webhook(mock_template_engine, mock_state, None)

    assert result["success"] is False
    assert "webhook_id" in result["error"]


@pytest.mark.asyncio
async def test_execute_webhook_failure(
    mock_template_engine: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.webhook_actions import execute_webhook

    mock_result = MagicMock()
    mock_result.success = False
    mock_result.status_code = 500
    mock_result.error = "server error"
    mock_result.body = None

    with (
        patch("gobby.workflows.webhook.WebhookAction") as MockAction,
        patch("gobby.workflows.webhook_executor.WebhookExecutor") as MockExecutor,
    ):
        action_instance = MagicMock()
        action_instance.url = "https://example.com"
        action_instance.method = "POST"
        action_instance.headers = {}
        action_instance.payload = None
        action_instance.timeout = 30
        action_instance.retry = None
        action_instance.capture_response = None
        action_instance.webhook_id = None
        MockAction.from_dict.return_value = action_instance

        MockExecutor.return_value.execute = AsyncMock(return_value=mock_result)

        result = await execute_webhook(mock_template_engine, mock_state, None, url="https://example.com")

    assert result["success"] is False
    assert result["body"] is None


@pytest.mark.asyncio
async def test_execute_webhook_with_capture(
    mock_template_engine: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.webhook_actions import execute_webhook

    mock_result = MagicMock()
    mock_result.success = True
    mock_result.status_code = 200
    mock_result.error = None
    mock_result.body = '{"key": "val"}'
    mock_result.headers = {"content-type": "application/json"}
    mock_result.json_body.return_value = {"key": "val"}

    capture = MagicMock()
    capture.status_var = "resp_status"
    capture.body_var = "resp_body"
    capture.headers_var = "resp_headers"

    with (
        patch("gobby.workflows.webhook.WebhookAction") as MockAction,
        patch("gobby.workflows.webhook_executor.WebhookExecutor") as MockExecutor,
    ):
        action_instance = MagicMock()
        action_instance.url = "https://example.com"
        action_instance.method = "GET"
        action_instance.headers = {}
        action_instance.payload = None
        action_instance.timeout = 30
        action_instance.retry = None
        action_instance.capture_response = capture
        action_instance.webhook_id = None
        MockAction.from_dict.return_value = action_instance

        MockExecutor.return_value.execute = AsyncMock(return_value=mock_result)

        result = await execute_webhook(
            mock_template_engine,
            mock_state,
            None,
            url="https://example.com",
            capture_response={"status_var": "resp_status"},
        )

    assert result["success"] is True
    assert mock_state.variables["resp_status"] == 200
    assert mock_state.variables["resp_body"] == {"key": "val"}


@pytest.mark.asyncio
async def test_execute_webhook_with_config_secrets(
    mock_template_engine: MagicMock,
    mock_state: MagicMock,
) -> None:
    from gobby.workflows.webhook_actions import execute_webhook

    mock_result = MagicMock()
    mock_result.success = True
    mock_result.status_code = 200
    mock_result.error = None
    mock_result.body = "ok"

    config = MagicMock()
    config.webhook_secrets = {"API_KEY": "secret"}

    with (
        patch("gobby.workflows.webhook.WebhookAction") as MockAction,
        patch("gobby.workflows.webhook_executor.WebhookExecutor") as MockExecutor,
    ):
        action_instance = MagicMock()
        action_instance.url = "https://example.com"
        action_instance.method = "POST"
        action_instance.headers = {}
        action_instance.payload = None
        action_instance.timeout = 30
        action_instance.retry = None
        action_instance.capture_response = None
        action_instance.webhook_id = None
        MockAction.from_dict.return_value = action_instance

        MockExecutor.return_value.execute = AsyncMock(return_value=mock_result)

        result = await execute_webhook(
            mock_template_engine, mock_state, config, url="https://example.com"
        )

    assert result["success"] is True
