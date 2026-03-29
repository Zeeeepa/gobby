"""Tests for the Slack communications adapter."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.communications.adapters.slack import SlackAdapter, SlackVerificationChallenge
from gobby.communications.models import ChannelConfig, CommsMessage


@pytest.fixture
def channel_config() -> ChannelConfig:
    return ChannelConfig(
        id="test_channel",
        channel_type="slack",
        name="Test Slack",
        enabled=True,
        config_json={},
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )


@pytest.fixture
def secret_resolver() -> Any:
    def resolver(key: str) -> str | None:
        if key == "$secret:SLACK_BOT_TOKEN":
            return "xoxb-test-token"
        if key == "$secret:SLACK_SIGNING_SECRET":
            return "test-signing-secret"
        return None

    return resolver


@pytest.fixture
def adapter() -> SlackAdapter:
    return SlackAdapter()


@pytest.mark.asyncio
async def test_initialize_success(
    adapter: SlackAdapter, channel_config: ChannelConfig, secret_resolver: Any
) -> None:
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "user_id": "U12345"}
        mock_post.return_value = mock_response

        await adapter.initialize(channel_config, secret_resolver)

        assert adapter._bot_token == "xoxb-test-token"
        assert adapter._signing_secret == "test-signing-secret"
        assert adapter._bot_user_id == "U12345"
        mock_post.assert_called_once_with("auth.test")


@pytest.mark.asyncio
async def test_initialize_missing_token(
    adapter: SlackAdapter, channel_config: ChannelConfig
) -> None:
    with pytest.raises(ValueError, match="SLACK_BOT_TOKEN secret is required"):
        await adapter.initialize(channel_config, lambda x: None)


@pytest.mark.asyncio
async def test_initialize_auth_failure(
    adapter: SlackAdapter, channel_config: ChannelConfig, secret_resolver: Any
) -> None:
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": False, "error": "invalid_auth"}
        mock_post.return_value = mock_response

        with pytest.raises(ValueError, match="Slack auth.test failed: invalid_auth"):
            await adapter.initialize(channel_config, secret_resolver)


@pytest.mark.asyncio
async def test_send_message_success(
    adapter: SlackAdapter, channel_config: ChannelConfig, secret_resolver: Any
) -> None:
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_auth_response = MagicMock()
        mock_auth_response.json.return_value = {"ok": True, "user_id": "U12345"}
        mock_post.return_value = mock_auth_response
        await adapter.initialize(channel_config, secret_resolver)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "ts": "1234567890.123456"}
        mock_post.return_value = mock_response

        message = CommsMessage(
            id="msg_1",
            channel_id="C12345",
            direction="outbound",
            content="Hello World",
            created_at="2024-01-01T00:00:00Z",
            platform_thread_id="thread_123",
        )

        ts = await adapter.send_message(message)

        assert ts == "1234567890.123456"
        mock_post.assert_called_once_with(
            "chat.postMessage",
            json={
                "channel": "C12345",
                "text": "Hello World",
                "thread_ts": "thread_123",
            },
        )


def test_parse_webhook_url_verification(adapter: SlackAdapter) -> None:
    payload = {"type": "url_verification", "challenge": "test_challenge"}
    with pytest.raises(SlackVerificationChallenge) as exc_info:
        adapter.parse_webhook(payload, {})
    assert exc_info.value.challenge == "test_challenge"


def test_parse_webhook_event_callback(adapter: SlackAdapter) -> None:
    payload = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "text": "Hello bot",
            "user": "U123",
            "channel": "C123",
            "ts": "123.456",
            "thread_ts": "thread.789",
        },
    }

    messages = adapter.parse_webhook(payload, {})

    assert len(messages) == 1
    assert messages[0].content == "Hello bot"
    assert messages[0].identity_id == "U123"
    assert messages[0].channel_id == "C123"
    assert messages[0].platform_message_id == "123.456"
    assert messages[0].platform_thread_id == "thread.789"


def test_verify_webhook(adapter: SlackAdapter) -> None:
    secret = "test_secret"
    timestamp = str(int(time.time()))
    payload = b'{"test": "data"}'

    sig_basestring = f"v0:{timestamp}:{payload.decode('utf-8')}"
    signature = (
        "v0="
        + hmac.new(
            secret.encode("utf-8"), sig_basestring.encode("utf-8"), hashlib.sha256
        ).hexdigest()
    )

    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
    }

    assert adapter.verify_webhook(payload, headers, secret) is True


def test_verify_webhook_invalid_signature(adapter: SlackAdapter) -> None:
    secret = "test_secret"
    timestamp = str(int(time.time()))
    payload = b'{"test": "data"}'

    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": "v0=invalid_signature",
    }

    assert adapter.verify_webhook(payload, headers, secret) is False  # noqa: E501


def test_verify_webhook_replay_attack(adapter: SlackAdapter) -> None:
    secret = "test_secret"
    # Old timestamp (more than 5 minutes ago)
    timestamp = str(int(time.time()) - 400)
    payload = b'{"test": "data"}'

    sig_basestring = f"v0:{timestamp}:{payload.decode('utf-8')}"
    signature = (
        "v0="
        + hmac.new(
            secret.encode("utf-8"), sig_basestring.encode("utf-8"), hashlib.sha256
        ).hexdigest()
    )

    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
    }

    assert adapter.verify_webhook(payload, headers, secret) is False


@pytest.mark.asyncio
async def test_send_attachment_three_step_upload(
    adapter: SlackAdapter, channel_config: ChannelConfig, secret_resolver: Any
) -> None:
    """Test the files.getUploadURLExternal 3-step upload flow."""
    from pathlib import Path

    from gobby.communications.models import CommsAttachment

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_auth_response = MagicMock()
        mock_auth_response.json.return_value = {"ok": True, "user_id": "U12345"}
        mock_post.return_value = mock_auth_response
        await adapter.initialize(channel_config, secret_resolver)

    with (
        patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread,
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx.AsyncClient.put", new_callable=AsyncMock) as mock_put,
    ):
        mock_to_thread.return_value = b"file-content-bytes"

        # Step 1: getUploadURLExternal response
        mock_get_url_resp = MagicMock()
        mock_get_url_resp.status_code = 200
        mock_get_url_resp.json.return_value = {
            "ok": True,
            "upload_url": "https://files.slack.com/upload/v1/abc123",
            "file_id": "F123456",
        }

        # Step 3: completeUploadExternal response
        mock_complete_resp = MagicMock()
        mock_complete_resp.status_code = 200
        mock_complete_resp.json.return_value = {
            "ok": True,
            "files": [
                {
                    "id": "F123456",
                    "shares": {"public": {"C12345": [{"ts": "111.222"}]}},
                }
            ],
        }

        mock_post.side_effect = [mock_get_url_resp, mock_complete_resp]

        # Step 2: PUT to upload_url
        mock_upload_resp = MagicMock()
        mock_upload_resp.status_code = 200
        mock_upload_resp.raise_for_status = MagicMock()
        mock_put.return_value = mock_upload_resp

        message = CommsMessage(
            id="msg_1",
            channel_id="C12345",
            direction="outbound",
            content="Here's the file",
            created_at="2024-01-01T00:00:00Z",
            platform_thread_id="thread_1",
        )

        attachment = CommsAttachment(
            id="att_1",
            message_id="msg_1",
            filename="test.txt",
            content_type="text/plain",
            size_bytes=18,
        )

        ts = await adapter.send_attachment(message, attachment, Path("/fake/test.txt"))

        assert ts == "111.222"

        # Verify step 1: getUploadURLExternal
        step1_call = mock_post.call_args_list[0]
        assert step1_call[0][0] == "files.getUploadURLExternal"

        # Verify step 3: completeUploadExternal
        step3_call = mock_post.call_args_list[1]
        assert step3_call[0][0] == "files.completeUploadExternal"
        step3_data = step3_call[1]["data"]
        assert step3_data["channel_id"] == "C12345"
        assert step3_data["thread_ts"] == "thread_1"
        assert step3_data["initial_comment"] == "Here's the file"
