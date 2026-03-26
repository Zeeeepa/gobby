"""Tests for the Discord communications adapter."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from gobby.communications.adapters.discord import DiscordAdapter
from gobby.communications.models import ChannelConfig, CommsMessage


@pytest.fixture
def channel_config() -> ChannelConfig:
    return ChannelConfig(
        id="test_discord_channel",
        channel_type="discord",
        name="Test Discord",
        enabled=True,
        config_json={},
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )


@pytest.fixture
def secret_resolver() -> MagicMock:
    def resolver(key: str) -> str | None:
        if key == "$secret:DISCORD_BOT_TOKEN":
            return "test-discord-token"
        return None

    return resolver


@pytest.fixture
def adapter() -> DiscordAdapter:
    return DiscordAdapter()


@pytest.mark.asyncio
async def test_initialize_success(
    adapter: DiscordAdapter, channel_config: ChannelConfig, secret_resolver: MagicMock
) -> None:
    # Disable gateway so it doesn't spin up tasks in unit test
    channel_config.config_json["enable_gateway"] = False

    await adapter.initialize(channel_config, secret_resolver)

    assert adapter._bot_token == "test-discord-token"
    assert adapter._client is not None
    assert str(adapter._client.base_url) == "https://discord.com/api/v10/"


@pytest.mark.asyncio
async def test_initialize_missing_token(
    adapter: DiscordAdapter, channel_config: ChannelConfig
) -> None:
    with pytest.raises(ValueError, match="Could not resolve Discord bot token: \\$secret:DISCORD_BOT_TOKEN"):
        await adapter.initialize(channel_config, lambda x: None)


@pytest.mark.asyncio
async def test_send_message_success(
    adapter: DiscordAdapter, channel_config: ChannelConfig, secret_resolver: MagicMock
) -> None:
    channel_config.config_json["enable_gateway"] = False
    await adapter.initialize(channel_config, secret_resolver)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "1234567890"}
        mock_post.return_value = mock_response

        message = CommsMessage(
            id="msg_1",
            channel_id="channel_123",
            direction="outbound",
            content="Hello Discord",
            created_at="2024-01-01T00:00:00Z",
        )

        msg_id = await adapter.send_message(message)

        assert msg_id == "1234567890"
        mock_post.assert_called_once_with(
            "/channels/channel_123/messages",
            json={"content": "Hello Discord"},
        )


def test_parse_webhook_ping(adapter: DiscordAdapter) -> None:
    payload = {"type": 1}
    messages = adapter.parse_webhook(payload, {})
    assert len(messages) == 0


def test_parse_webhook_message(adapter: DiscordAdapter) -> None:
    payload = {
        "type": 0,
        "channel_id": "channel_123",
        "id": "msg_456",
        "author": {"id": "user_789"},
        "content": "Hello bot",
    }

    messages = adapter.parse_webhook(payload, {})

    assert len(messages) == 1
    assert messages[0].content == "Hello bot"
    assert messages[0].identity_id == "user_789"
    assert messages[0].channel_id == "channel_123"
    assert messages[0].platform_message_id == "msg_456"


def test_verify_webhook(adapter: DiscordAdapter) -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    secret = public_key.public_bytes_raw().hex()

    timestamp = "1234567890"
    payload = b'{"type": 1}'
    message = timestamp.encode() + payload

    signature = private_key.sign(message)

    headers = {
        "X-Signature-Ed25519": signature.hex(),
        "X-Signature-Timestamp": timestamp,
    }

    assert adapter.verify_webhook(payload, headers, secret) is True


def test_verify_webhook_invalid_signature(adapter: DiscordAdapter) -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    secret = public_key.public_bytes_raw().hex()

    timestamp = "1234567890"
    payload = b'{"type": 1}'

    headers = {
        "X-Signature-Ed25519": "00" * 64,  # Invalid signature length is 64 bytes
        "X-Signature-Timestamp": timestamp,
    }

    assert adapter.verify_webhook(payload, headers, secret) is False
