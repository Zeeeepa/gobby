"""Tests for the SMS communications adapter."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import pytest

from gobby.communications.adapters.sms import SMSAdapter
from gobby.communications.models import ChannelConfig, CommsMessage


@pytest.fixture
def channel_config() -> ChannelConfig:
    return ChannelConfig(
        id="test_channel",
        channel_type="sms",
        name="Test SMS",
        enabled=True,
        config_json={
            "account_sid": "test-account-sid",
            "from_number": "+1234567890",
        },
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )


@pytest.fixture
def secret_resolver() -> Any:
    def resolver(key: str) -> str | None:
        if key == "$secret:TWILIO_AUTH_TOKEN":
            return "test-auth-token"
        return None

    return resolver


@pytest.fixture
def adapter() -> SMSAdapter:
    return SMSAdapter()


@pytest.mark.asyncio
async def test_initialize_success(
    adapter: SMSAdapter, channel_config: ChannelConfig, secret_resolver: Any
) -> None:
    """Test successful initialization."""
    await adapter.initialize(channel_config, secret_resolver)

    assert adapter._account_sid == "test-account-sid"
    assert adapter._auth_token == "test-auth-token"
    assert adapter._from_number == "+1234567890"
    assert adapter._client is not None
    assert (
        str(adapter._client.base_url)
        == "https://api.twilio.com/2010-04-01/Accounts/test-account-sid/"
    )


@pytest.mark.asyncio
async def test_initialize_missing_secrets(
    adapter: SMSAdapter, channel_config: ChannelConfig
) -> None:
    """Test initialization with missing secrets."""

    def empty_resolver(key: str) -> str | None:
        return None

    with pytest.raises(ValueError, match="TWILIO_AUTH_TOKEN secret is required"):
        await adapter.initialize(channel_config, empty_resolver)


@pytest.mark.asyncio
async def test_initialize_missing_config(adapter: SMSAdapter, secret_resolver: Any) -> None:
    """Test initialization with missing config params."""
    config = ChannelConfig(
        id="test_channel",
        channel_type="sms",
        name="Test SMS",
        enabled=True,
        config_json={},
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )
    with pytest.raises(ValueError, match="account_sid is required in config_json"):
        await adapter.initialize(config, secret_resolver)


@pytest.mark.asyncio
async def test_send_message_success(
    adapter: SMSAdapter, channel_config: ChannelConfig, secret_resolver: Any
) -> None:
    """Test sending a text message."""
    await adapter.initialize(channel_config, secret_resolver)

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {"sid": "SM12345"}
        mock_post.return_value = mock_response

        message = CommsMessage(
            id="1",
            channel_id="+0987654321",
            direction="outbound",
            content="Hello world",
            created_at="2024-01-01T00:00:00Z",
        )

        msg_id = await adapter.send_message(message)

        assert msg_id == "SM12345"
        mock_post.assert_called_with(
            "Messages.json",
            data={
                "To": "+0987654321",
                "From": "+1234567890",
                "Body": "Hello world",
            },
        )


def test_parse_webhook(adapter: SMSAdapter) -> None:
    """Test parsing a Twilio webhook."""
    payload = {
        "From": "+0987654321",
        "To": "+1234567890",
        "Body": "Hello from Twilio!",
        "MessageSid": "SM12345",
    }

    messages = adapter.parse_webhook(payload, {})

    assert len(messages) == 1
    msg = messages[0]
    assert msg.channel_id == "+0987654321"
    assert msg.direction == "inbound"
    assert msg.content == "Hello from Twilio!"
    assert msg.platform_message_id == "SM12345"
    assert msg.identity_id == "+0987654321"


def test_verify_webhook(adapter: SMSAdapter) -> None:
    """Test verify Twilio webhook signature."""
    import base64
    import hashlib
    import hmac

    secret = "my-secret"
    url = "https://example.com/webhook"

    payload_dict = {
        "From": "+0987654321",
        "Body": "Hello!",
    }
    payload_str = urlencode(payload_dict)

    # Calculate valid signature
    data = url
    for key in sorted(payload_dict.keys()):
        data += f"{key}{payload_dict[key]}"

    mac = hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha1)
    computed = base64.b64encode(mac.digest()).decode("utf-8")

    headers = {
        "x-twilio-signature": computed,
        "x-original-url": url,
    }

    assert adapter.verify_webhook(payload_str.encode("utf-8"), headers, secret) is True

    # Test invalid signature
    headers["x-twilio-signature"] = "invalid"
    assert adapter.verify_webhook(payload_str.encode("utf-8"), headers, secret) is False
