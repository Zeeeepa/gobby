"""Email channel adapter."""

from __future__ import annotations

import email
import logging
from collections.abc import Callable
from datetime import datetime
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Any

from gobby.communications.adapters import register_adapter
from gobby.communications.adapters.base import BaseChannelAdapter
from gobby.communications.models import (
    ChannelCapabilities,
    ChannelConfig,
    CommsAttachment,
    CommsMessage,
)

logger = logging.getLogger(__name__)

HAS_SMTP = False
try:
    import aiosmtplib

    HAS_SMTP = True
except ImportError:
    pass

HAS_IMAP = False
try:
    import aioimaplib

    HAS_IMAP = True
except ImportError:
    pass


class EmailAdapter(BaseChannelAdapter):
    """Adapter for Email using SMTP for sending and IMAP for receiving."""

    def __init__(self) -> None:
        self._smtp_client: aiosmtplib.SMTP | None = None
        self._imap_client: aioimaplib.IMAP4_SSL | None = None
        self._smtp_host: str = ""
        self._smtp_port: int = 587
        self._imap_host: str = ""
        self._imap_port: int = 993
        self._from_address: str = ""
        self._password: str = ""

    @property
    def channel_type(self) -> str:
        """The unique type identifier for this channel."""
        return "email"

    @property
    def max_message_length(self) -> int:
        """Maximum message length supported by the platform."""
        return 100000

    @property
    def supports_webhooks(self) -> bool:
        """Whether this adapter supports inbound webhooks."""
        return False

    @property
    def supports_polling(self) -> bool:
        """Whether this adapter supports message polling."""
        return True

    async def initialize(
        self, config: ChannelConfig, secret_resolver: Callable[[str], str | None]
    ) -> None:
        """Set up API clients, validate credentials."""
        self._smtp_host = config.config_json.get("smtp_host", "")
        self._smtp_port = config.config_json.get("smtp_port", 587)
        self._imap_host = config.config_json.get("imap_host", "")
        self._imap_port = config.config_json.get("imap_port", 993)
        self._from_address = config.config_json.get("from_address", "")

        password_ref = config.config_json.get("password", "$secret:EMAIL_PASSWORD")
        password = (
            secret_resolver(password_ref) if password_ref.startswith("$secret:") else password_ref
        )

        if not password:
            raise ValueError(f"Could not resolve Email password: {password_ref}")

        self._password = password

        if HAS_SMTP and self._smtp_host:
            self._smtp_client = aiosmtplib.SMTP(
                hostname=self._smtp_host,
                port=self._smtp_port,
                use_tls=self._smtp_port == 465,
                start_tls=self._smtp_port == 587,
            )
            await self._smtp_client.connect()
            await self._smtp_client.login(self._from_address, self._password)

        if HAS_IMAP and self._imap_host:
            self._imap_client = aioimaplib.IMAP4_SSL(host=self._imap_host, port=self._imap_port)
            await self._imap_client.wait_hello_from_server()
            await self._imap_client.login(self._from_address, self._password)

    async def send_message(self, message: CommsMessage) -> str | None:
        """Send message and return platform message ID."""
        if not HAS_SMTP or not self._smtp_client:
            raise RuntimeError("Email SMTP client not initialized or aiosmtplib missing")

        msg = EmailMessage()
        msg["Subject"] = message.metadata_json.get("subject", "Message from Gobby")
        msg["From"] = self._from_address
        msg["To"] = message.channel_id

        domain = self._from_address.split("@")[-1] if "@" in self._from_address else "gobby.local"
        msg_id = make_msgid(domain=domain)
        msg["Message-ID"] = msg_id

        if message.platform_thread_id:
            msg["In-Reply-To"] = message.platform_thread_id
            msg["References"] = message.platform_thread_id

        if message.content_type == "html":
            msg.set_content(message.content, subtype="html")
        else:
            msg.set_content(message.content)

        await self._smtp_client.send_message(msg)
        return msg_id

    async def send_attachment(
        self, message: CommsMessage, attachment: CommsAttachment, file_path: Path
    ) -> str | None:
        """Send an email with a MIME attachment."""
        if not HAS_SMTP or not self._smtp_client:
            raise RuntimeError("Email SMTP client not initialized or aiosmtplib missing")

        msg = EmailMessage()
        msg["Subject"] = message.metadata_json.get("subject", "Message from Gobby")
        msg["From"] = self._from_address
        msg["To"] = message.channel_id

        domain = self._from_address.split("@")[-1] if "@" in self._from_address else "gobby.local"
        msg_id = make_msgid(domain=domain)
        msg["Message-ID"] = msg_id

        if message.platform_thread_id:
            msg["In-Reply-To"] = message.platform_thread_id
            msg["References"] = message.platform_thread_id

        msg.set_content(message.content or "")

        maintype, subtype = (attachment.content_type or "application/octet-stream").split("/", 1)
        file_data = file_path.read_bytes()
        msg.add_attachment(
            file_data, maintype=maintype, subtype=subtype, filename=attachment.filename
        )

        await self._smtp_client.send_message(msg)
        return msg_id

    async def poll(self) -> list[CommsMessage]:
        """Poll for new messages."""
        if not HAS_IMAP or not self._imap_client:
            return []

        await self._imap_client.select("INBOX")
        status, response = await self._imap_client.search("UNSEEN")
        if status != "OK" or not response[0]:
            return []

        messages: list[CommsMessage] = []
        msg_nums = response[0].split()

        for num in msg_nums:
            status, fetch_data = await self._imap_client.fetch(num.decode(), "(RFC822)")
            if status != "OK":
                continue

            for part in fetch_data:
                if isinstance(part, tuple):
                    msg_bytes = part[1]
                    email_msg = email.message_from_bytes(msg_bytes)

                    msg_id = email_msg.get("Message-ID", "")
                    thread_id = email_msg.get("In-Reply-To", "")
                    sender = email_msg.get("From", "")
                    subject = email_msg.get("Subject", "")

                    content = ""
                    content_type = "text"
                    if email_msg.is_multipart():
                        for payload_part in email_msg.walk():
                            if payload_part.get_content_type() == "text/plain":
                                payload = payload_part.get_payload(decode=True)
                                if isinstance(payload, bytes):
                                    content = payload.decode(errors="replace")
                                break
                            elif payload_part.get_content_type() == "text/html" and not content:
                                payload = payload_part.get_payload(decode=True)
                                if isinstance(payload, bytes):
                                    content = payload.decode(errors="replace")
                                content_type = "html"
                    else:
                        payload = email_msg.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            content = payload.decode(errors="replace")
                        elif isinstance(payload, str):
                            content = payload
                        if email_msg.get_content_type() == "text/html":
                            content_type = "html"

                    messages.append(
                        CommsMessage(
                            id=msg_id or str(datetime.now().timestamp()),
                            channel_id=sender,
                            direction="inbound",
                            content=content,
                            created_at=datetime.now().isoformat(),
                            identity_id=sender,
                            platform_message_id=msg_id,
                            platform_thread_id=thread_id,
                            content_type=content_type,
                            metadata_json={"subject": subject},
                        )
                    )

        return messages

    async def shutdown(self) -> None:
        """Cleanly close connections."""
        if self._smtp_client:
            try:
                await self._smtp_client.quit()
            except Exception as e:
                logger.warning(f"Error during SMTP shutdown: {e}")
            self._smtp_client = None

        if self._imap_client:
            try:
                await self._imap_client.close()
                await self._imap_client.logout()
            except Exception as e:
                logger.warning(f"Error during IMAP shutdown: {e}")
            self._imap_client = None

    def capabilities(self) -> ChannelCapabilities:
        """Return channel capabilities."""
        return ChannelCapabilities(
            threading=True,
            reactions=False,
            files=True,
            markdown=False,
            max_message_length=self.max_message_length,
        )

    def parse_webhook(
        self, payload: dict[str, Any] | bytes, headers: dict[str, str]
    ) -> list[CommsMessage]:
        """Normalize inbound webhook payload."""
        raise NotImplementedError("Email adapter does not support webhooks")

    def verify_webhook(self, payload: bytes, headers: dict[str, str], secret: str) -> bool:
        """Verify webhook signature."""
        return False


# Register the adapter
register_adapter("email", EmailAdapter)
