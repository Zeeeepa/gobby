from unittest.mock import AsyncMock, patch

import pytest

from gobby.communications.adapters.email import EmailAdapter
from gobby.communications.models import ChannelConfig, CommsMessage


@pytest.fixture
def adapter():
    return EmailAdapter()

@pytest.fixture
def mock_secret_resolver():
    def _resolve(secret_ref: str) -> str | None:
        if secret_ref == "$secret:EMAIL_PASSWORD":
            return "pass123"
        return None
    return _resolve

@pytest.mark.asyncio
async def test_initialize(adapter, mock_secret_resolver):
    config = ChannelConfig(
        id="test",
        channel_type="email",
        name="test",
        enabled=True,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        config_json={
            "smtp_host": "smtp.example.com",
            "imap_host": "imap.example.com",
            "from_address": "bot@example.com"
        }
    )

    with patch('aiosmtplib.SMTP') as MockSMTP, \
         patch('aioimaplib.IMAP4_SSL') as MockIMAP:

        mock_smtp_inst = AsyncMock()
        MockSMTP.return_value = mock_smtp_inst

        mock_imap_inst = AsyncMock()
        MockIMAP.return_value = mock_imap_inst

        await adapter.initialize(config, mock_secret_resolver)

        assert adapter._password == "pass123"
        assert adapter._smtp_client is mock_smtp_inst
        assert adapter._imap_client is mock_imap_inst

        mock_smtp_inst.connect.assert_called_once()
        mock_smtp_inst.login.assert_called_once_with("bot@example.com", "pass123")

        mock_imap_inst.wait_hello_from_server.assert_called_once()
        mock_imap_inst.login.assert_called_once_with("bot@example.com", "pass123")

@pytest.mark.asyncio
async def test_send_message(adapter, mock_secret_resolver):
    config = ChannelConfig(
        id="test",
        channel_type="email",
        name="test",
        enabled=True,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        config_json={"from_address": "bot@example.com", "smtp_host": "smtp.example.com"}
    )

    with patch('aiosmtplib.SMTP') as MockSMTP, \
         patch('aioimaplib.IMAP4_SSL'):
        mock_smtp_inst = AsyncMock()
        MockSMTP.return_value = mock_smtp_inst
        await adapter.initialize(config, mock_secret_resolver)

    msg = CommsMessage(
        id="test_id",
        channel_id="user@example.com",
        direction="outbound",
        content="Hello via email",
        metadata_json={"subject": "Test Subject"},
        created_at="2024-01-01T00:00:00Z"
    )

    msg_id = await adapter.send_message(msg)

    assert msg_id is not None
    mock_smtp_inst.send_message.assert_called_once()

    sent_msg = mock_smtp_inst.send_message.call_args[0][0]
    assert sent_msg["Subject"] == "Test Subject"
    assert sent_msg["To"] == "user@example.com"
    assert sent_msg["From"] == "bot@example.com"

@pytest.mark.asyncio
async def test_poll(adapter, mock_secret_resolver):
    config = ChannelConfig(
        id="test",
        channel_type="email",
        name="test",
        enabled=True,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        config_json={"from_address": "bot@example.com", "imap_host": "imap.example.com"}
    )

    with patch('aiosmtplib.SMTP'), patch('aioimaplib.IMAP4_SSL') as MockIMAP:
        mock_imap_inst = AsyncMock()
        MockIMAP.return_value = mock_imap_inst
        await adapter.initialize(config, mock_secret_resolver)

        # Mock IMAP responses
        mock_imap_inst.search.return_value = ("OK", [b"1 2"])

        # Create a mock email payload
        email_content = b"From: user@example.com\r\nSubject: Test Reply\r\nMessage-ID: <msg123>\r\n\r\nHello back!"

        mock_imap_inst.fetch.side_effect = [
            ("OK", [(b"1 (RFC822 {100})", email_content), b")"]),
            ("OK", [(b"2 (RFC822 {100})", email_content), b")"])
        ]

        messages = await adapter.poll()

        assert len(messages) == 2
        assert messages[0].channel_id == "user@example.com"
        assert messages[0].content.strip() == "Hello back!"
        assert messages[0].platform_message_id == "<msg123>"
        assert messages[0].metadata_json["subject"] == "Test Reply"

def test_parse_webhook(adapter):
    with pytest.raises(NotImplementedError):
        adapter.parse_webhook({}, {})

def test_verify_webhook(adapter):
    assert not adapter.verify_webhook(b"", {}, "")
