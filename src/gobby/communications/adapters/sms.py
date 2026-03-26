"""SMS channel adapter using Twilio REST API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl

import httpx

from gobby.communications.adapters import register_adapter
from gobby.communications.adapters.base import BaseChannelAdapter
from gobby.communications.models import ChannelCapabilities, ChannelConfig, CommsMessage

logger = logging.getLogger(__name__)


class SMSAdapter(BaseChannelAdapter):
    """Adapter for SMS via Twilio."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._account_sid: str | None = None
        self._auth_token: str | None = None
        self._from_number: str | None = None

    @property
    def channel_type(self) -> str:
        """The unique type identifier for this channel."""
        return "sms"

    @property
    def max_message_length(self) -> int:
        """Maximum message length supported by the platform."""
        return 1600

    @property
    def supports_webhooks(self) -> bool:
        """Whether this adapter supports inbound webhooks."""
        return True

    @property
    def supports_polling(self) -> bool:
        """Whether this adapter supports message polling."""
        return False

    async def initialize(
        self, config: ChannelConfig, secret_resolver: Callable[[str], str | None]
    ) -> None:
        """Set up API clients, validate credentials."""
        self._auth_token = secret_resolver("$secret:TWILIO_AUTH_TOKEN")
        self._account_sid = config.config_json.get("account_sid")
        self._from_number = config.config_json.get("from_number")

        if not self._auth_token:
            raise ValueError("TWILIO_AUTH_TOKEN secret is required")
        if not self._account_sid:
            raise ValueError("account_sid is required in config_json")
        if not self._from_number:
            raise ValueError("from_number is required in config_json")

        self._client = httpx.AsyncClient(
            base_url=f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/",
            auth=(self._account_sid, self._auth_token),
            timeout=30.0,
        )

        # In a real scenario we could make a request to test the auth, e.g. GET Messages.json
        # but that can be expensive/slow on Twilio. We just assume it's good.

    async def send_message(self, message: CommsMessage) -> str | None:
        """Send message and return platform message ID."""
        if not self._client or not self._from_number:
            raise RuntimeError("SMS adapter not initialized")

        # SMS is essentially flat, so we don't handle threading or rich formatting
        chunks = self.chunk_message(message.content, self.max_message_length)
        last_sid = None

        for chunk in chunks:
            payload = {
                "To": message.channel_id,  # channel_id is the recipient phone number
                "From": self._from_number,
                "Body": chunk,
            }

            response = await self._client.post("Messages.json", data=payload)
            response.raise_for_status()
            data = response.json()

            if "sid" not in data:
                raise ValueError(f"Failed to send SMS message, unknown error: {data}")

            last_sid = data["sid"]

        return last_sid

    async def shutdown(self) -> None:
        """Cleanly close connections."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def capabilities(self) -> ChannelCapabilities:
        """Return channel capabilities."""
        return ChannelCapabilities(
            threading=False,
            reactions=False,
            files=False,
            markdown=False,
            max_message_length=self.max_message_length,
        )

    def parse_webhook(
        self, payload: dict[str, Any] | bytes, headers: dict[str, str]
    ) -> list[CommsMessage]:
        """Normalize inbound webhook payload."""
        if isinstance(payload, bytes):
            # Twilio sends application/x-www-form-urlencoded
            payload_str = payload.decode("utf-8")
            params = dict(parse_qsl(payload_str))
        else:
            params = payload

        # For SMS, From is the sender number, To is our number, Body is the text
        from_number = params.get("From")
        body = params.get("Body")
        message_sid = params.get("MessageSid")

        if not from_number or not body:
            # Not a standard message webhook
            return []

        return [
            CommsMessage(
                id=message_sid or f"sms_{time.time()}",
                channel_id=from_number,  # In SMS, the channel is the conversation with the user
                direction="inbound",
                content=body,
                created_at=datetime.now().isoformat(),
                identity_id=from_number,  # Identity is also the phone number
                platform_message_id=message_sid,
                content_type="text",
                metadata_json=params,
            )
        ]

    def verify_webhook(self, payload: bytes, headers: dict[str, str], secret: str) -> bool:
        """Verify webhook signature."""
        # Normalize headers to lowercase for reliable lookup
        lower_headers = {k.lower(): v for k, v in headers.items()}
        twilio_signature = lower_headers.get("x-twilio-signature")

        if not twilio_signature:
            return False

        # Twilio needs the exact URL. If the proxy/router passes it in a custom header, use it.
        # Otherwise, we might not be able to verify properly. We look for common headers or fallback to empty.
        url = lower_headers.get("x-original-url") or lower_headers.get("x-gobby-webhook-url")

        # We'll parse the payload to sort the params
        payload_str = payload.decode("utf-8")
        params = dict(parse_qsl(payload_str))

        # Sort params and append to URL
        data = url if url else ""
        if data:
            for key in sorted(params.keys()):
                data += f"{key}{params[key]}"
        else:
            # If we don't have a URL, we cannot definitively verify the Twilio signature.
            # Return False since it's unverified.
            return False

        mac = hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha1)
        computed = base64.b64encode(mac.digest()).decode("utf-8")

        return hmac.compare_digest(computed, twilio_signature)


# Register the adapter
register_adapter("sms", SMSAdapter)
