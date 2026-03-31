"""Tests for gobby.communications.adapters.email."""

from email.message import EmailMessage
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

try:
    from gobby.communications.adapters.email import EmailAdapter
except ImportError:
    EmailAdapter = None


@pytest.fixture
def adapter() -> "EmailAdapter":
    if not EmailAdapter:
        pytest.skip("EmailAdapter not available")
    adapter = EmailAdapter()
    return adapter


@pytest.fixture
def config() -> MagicMock:
    mock_config = MagicMock()
    mock_config.config_json = {
        "smtp_host": "smtp.test.com",
        "smtp_port": 587,
        "imap_host": "imap.test.com",
        "imap_port": 993,
        "from_address": "bot@test.com",
        "to_address": "user@test.com",
        "password": "fake-password",
    }
    return mock_config


class TestEmailAdapter:
    @pytest.mark.asyncio
    @patch("gobby.communications.adapters.email.aiosmtplib", create=True)
    @patch("gobby.communications.adapters.email.aioimaplib", create=True)
    async def test_initialize_success(self, mock_imap, mock_smtp, adapter, config) -> None:
        # Setup mocks
        mock_smtp_client = AsyncMock()
        mock_smtp.SMTP.return_value = mock_smtp_client

        mock_imap_client = AsyncMock()
        mock_imap.IMAP4_SSL.return_value = mock_imap_client

        # Mock secret resolver
        def resolver(ref: str) -> str:
            return "secret-pass"

        # Apply settings
        config.config_json["password"] = "$secret:EMAIL_PASSWORD"

        await adapter.initialize(config, resolver)

        assert adapter._smtp_host == "smtp.test.com"
        assert adapter._imap_host == "imap.test.com"
        assert adapter._from_address == "bot@test.com"
        assert adapter._password == "secret-pass"

        mock_smtp.SMTP.assert_called_with(
            hostname="smtp.test.com", port=587, use_tls=False, start_tls=True
        )
        mock_smtp_client.connect.assert_called_once()
        mock_smtp_client.login.assert_called_once_with("bot@test.com", "secret-pass")

        mock_imap.IMAP4_SSL.assert_called_with(host="imap.test.com", port=993)
        mock_imap_client.wait_hello_from_server.assert_called_once()
        mock_imap_client.login.assert_called_once_with("bot@test.com", "secret-pass")

    @pytest.mark.asyncio
    async def test_initialize_missing_password(self, adapter, config) -> None:
        config.config_json["password"] = "$secret:MISSING"

        def resolver(ref):
            return None

        with pytest.raises(ValueError, match="Could not resolve Email password"):
            await adapter.initialize(config, resolver)

    @pytest.mark.asyncio
    @patch("gobby.communications.adapters.email.aiosmtplib", create=True)
    async def test_ensure_smtp_connected_already_connected(self, mock_smtp, adapter) -> None:
        adapter._smtp_client = AsyncMock()
        adapter._smtp_client.is_connected = True

        await adapter._ensure_smtp_connected()
        adapter._smtp_client.noop.assert_called_once()

    @pytest.mark.asyncio
    @patch("gobby.communications.adapters.email.aiosmtplib", create=True)
    async def test_ensure_smtp_connected_reconnects(self, mock_smtp, adapter) -> None:
        old_client = AsyncMock()
        old_client.is_connected = False
        adapter._smtp_client = old_client
        adapter._smtp_host = "test"
        adapter._smtp_port = 587
        adapter._from_address = "bot"
        adapter._password = "pass"

        new_client = AsyncMock()
        mock_smtp.SMTP.return_value = new_client

        await adapter._ensure_smtp_connected()

        old_client.close.assert_called_once()
        mock_smtp.SMTP.assert_called_once()
        new_client.connect.assert_called_once()
        new_client.login.assert_called_with("bot", "pass")

    @pytest.mark.asyncio
    async def test_send_message_uninitialized(self, adapter) -> None:
        adapter._smtp_client = None
        msg = MagicMock()
        with pytest.raises(RuntimeError):
            await adapter.send_message(msg)

    @pytest.mark.asyncio
    @patch("gobby.communications.adapters.email.aiosmtplib", create=True)
    async def test_send_message_success(self, mock_smtp, adapter) -> None:
        adapter._smtp_client = AsyncMock()
        adapter._smtp_client.is_connected = True
        adapter._from_address = "bot@test.com"
        adapter._default_destination = "user@test.com"

        msg = MagicMock()
        msg.content = "hello world"
        msg.metadata_json = {"subject": "Test Subj"}
        msg.platform_thread_id = None
        msg.content_type = "text"

        msg_id = await adapter.send_message(msg)

        assert msg_id is not None
        assert "@test.com" in msg_id
        adapter._smtp_client.send_message.assert_called_once()

        # Check email message was constructed correctly
        sent_email = adapter._smtp_client.send_message.call_args[0][0]
        assert isinstance(sent_email, EmailMessage)
        assert sent_email["Subject"] == "Test Subj"
        assert sent_email["To"] == "user@test.com"
        assert sent_email.get_content().strip() == "hello world"

    @pytest.mark.asyncio
    @patch("gobby.communications.adapters.email.aiosmtplib", create=True)
    async def test_send_message_with_html_and_reply(self, mock_smtp, adapter) -> None:
        adapter._smtp_client = AsyncMock()
        adapter._smtp_client.is_connected = True
        adapter._from_address = "bot@test.com"
        adapter._default_destination = "user@test.com"

        msg = MagicMock()
        msg.content = "<b>html</b>"
        msg.metadata_json = {}
        msg.platform_thread_id = "thread-123"
        msg.content_type = "html"

        await adapter.send_message(msg)

        sent_email = adapter._smtp_client.send_message.call_args[0][0]
        assert sent_email["In-Reply-To"] == "thread-123"
        assert sent_email["References"] == "thread-123"

    @pytest.mark.asyncio
    @patch("gobby.communications.adapters.email.aiosmtplib", create=True)
    async def test_send_attachment(self, mock_smtp, adapter, tmp_path) -> None:
        adapter._smtp_client = AsyncMock()
        adapter._smtp_client.is_connected = True
        adapter._from_address = "bot@test.com"
        adapter._default_destination = "user@test.com"

        file_path = tmp_path / "test.txt"
        file_path.write_bytes(b"attachment content")

        msg = MagicMock()
        msg.content = "see attached"
        msg.metadata_json = {}
        msg.platform_thread_id = None

        attachment = MagicMock()
        attachment.filename = "test.txt"
        attachment.content_type = "text/plain"

        msg_id = await adapter.send_attachment(msg, attachment, file_path)
        assert msg_id is not None

        adapter._smtp_client.send_message.assert_called_once()
        sent_email = adapter._smtp_client.send_message.call_args[0][0]

        # Verify multipart
        assert sent_email.is_multipart()
        parts = list(sent_email.iter_parts())
        assert len(parts) == 2  # Text body + attachment
        assert parts[1].get_filename() == "test.txt"
        assert parts[1].get_payload(decode=True) == b"attachment content"

    @pytest.mark.asyncio
    @patch("gobby.communications.adapters.email.aioimaplib", create=True)
    async def test_poll_no_messages(self, mock_imap, adapter) -> None:
        adapter._imap_client = AsyncMock()
        # Mock search to return empty response
        adapter._imap_client.search.return_value = ("OK", [b""])

        messages = await adapter.poll()
        assert messages == []
        adapter._imap_client.search.assert_called_with("UNSEEN")

    @pytest.mark.asyncio
    @patch("gobby.communications.adapters.email.aioimaplib", create=True)
    async def test_poll_with_messages(self, mock_imap, adapter) -> None:
        adapter._imap_client = AsyncMock()

        # poll() now calls imap.select("INBOX") before search
        adapter._imap_client.select.return_value = ("OK", [])
        # Mock search to return msg numbers
        adapter._imap_client.search.return_value = ("OK", [b"1 2"])

        # Craft two raw RFC822 emails
        msg1 = EmailMessage()
        msg1["Message-ID"] = "msg1@test"
        msg1["From"] = "user@test.com"
        msg1["Subject"] = "Test 1"
        msg1.set_content("plain text content")

        msg2 = EmailMessage()
        msg2["Message-ID"] = "msg2@test"
        msg2["From"] = "other@test.com"
        msg2.add_alternative("<b>HTML</b>", subtype="html")

        # poll() now uses string num_str (decoded from bytes) for fetch/store
        def fetch_side_effect(num, query):
            if num == "1":
                return ("OK", [("1 (RFC822)", bytes(msg1))])
            if num == "2":
                return ("OK", [("2 (RFC822)", bytes(msg2))])
            return ("BAD", [])

        adapter._imap_client.fetch = AsyncMock(side_effect=fetch_side_effect)
        adapter._imap_client.store = AsyncMock(return_value=("OK", []))

        messages = await adapter.poll()
        assert len(messages) == 2

        assert messages[0].platform_message_id == "msg1@test"
        assert messages[0].content.strip() == "plain text content"
        assert messages[0].content_type == "text"
        assert messages[0].identity_id == "user@test.com"
        assert messages[0].metadata_json["subject"] == "Test 1"

        assert messages[1].platform_message_id == "msg2@test"
        assert "HTML" in messages[1].content

        assert adapter._imap_client.store.call_count == 2
        adapter._imap_client.store.assert_any_call("1", "+FLAGS", "(\\Seen)")

    @pytest.mark.asyncio
    async def test_shutdown(self, adapter) -> None:
        smtp_mock = AsyncMock()
        imap_mock = AsyncMock()
        adapter._smtp_client = smtp_mock
        adapter._imap_client = imap_mock

        await adapter.shutdown()

        smtp_mock.quit.assert_called_once()
        imap_mock.close.assert_called_once()
        imap_mock.logout.assert_called_once()

        assert adapter._smtp_client is None
        assert adapter._imap_client is None

    def test_capabilities(self, adapter) -> None:
        caps = adapter.capabilities()
        assert caps.threading is True
        assert caps.reactions is False
        assert caps.files is True
        assert caps.max_message_length == 100000

    def test_parse_webhook_raises(self, adapter) -> None:
        with pytest.raises(NotImplementedError):
            adapter.parse_webhook(b"", {})

    def test_verify_webhook(self, adapter) -> None:
        assert adapter.verify_webhook(b"", {}, "") is False
