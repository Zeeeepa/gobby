"""Slack channel adapter."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from gobby.communications.adapters import register_adapter
from gobby.communications.adapters.base import BaseChannelAdapter
from gobby.communications.models import (
    ChannelCapabilities,
    ChannelConfig,
    CommsAttachment,
    CommsMessage,
)

logger = logging.getLogger(__name__)


class SlackVerificationChallenge(Exception):
    """Exception raised to return a URL verification challenge."""

    def __init__(self, challenge: str):
        self.challenge = challenge
        super().__init__(challenge)


class SlackAdapter(BaseChannelAdapter):
    """Adapter for Slack Web API and Events API."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._bot_token: str | None = None
        self._signing_secret: str | None = None
        self._bot_user_id: str | None = None

    @property
    def channel_type(self) -> str:
        """The unique type identifier for this channel."""
        return "slack"

    @property
    def max_message_length(self) -> int:
        """Maximum message length supported by the platform."""
        return 3000

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
        self._bot_token = secret_resolver("$secret:SLACK_BOT_TOKEN")
        self._signing_secret = secret_resolver("$secret:SLACK_SIGNING_SECRET")

        if not self._bot_token:
            raise ValueError("SLACK_BOT_TOKEN secret is required")

        # signing secret is optional if not using webhooks, but usually required
        if not self._signing_secret:
            logger.warning("SLACK_SIGNING_SECRET secret is not set, webhook verification will fail")

        self._client = httpx.AsyncClient(
            base_url="https://slack.com/api/",
            headers={"Authorization": f"Bearer {self._bot_token}"},
            timeout=30.0,
        )

        # Verify token via auth.test
        response = await self._client.post("auth.test")
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise ValueError(f"Slack auth.test failed: {data.get('error')}")

        self._bot_user_id = data.get("user_id")

    async def send_message(self, message: CommsMessage) -> str | None:
        """Send message and return platform message ID."""
        if not self._client:
            raise RuntimeError("Slack adapter not initialized")

        chunks = self.chunk_message(message.content, self.max_message_length)
        last_ts = None

        for chunk in chunks:
            payload: dict[str, Any] = {
                "channel": message.channel_id,
                "text": chunk,
            }
            if message.platform_thread_id:
                payload["thread_ts"] = message.platform_thread_id

            response = await self._client.post("chat.postMessage", json=payload)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                error_msg = data.get("error", "Unknown error")
                raise ValueError(f"Failed to send Slack message: {error_msg}")

            last_ts = data.get("ts")

        return last_ts

    async def send_attachment(
        self, message: CommsMessage, attachment: CommsAttachment, file_path: Path
    ) -> str | None:
        """Send a file via Slack files.upload API."""
        if not self._client:
            raise RuntimeError("Slack adapter not initialized")

        with open(file_path, "rb") as f:
            data: dict[str, Any] = {
                "channels": message.channel_id,
                "filename": attachment.filename,
                "title": attachment.filename,
            }
            if message.content:
                data["initial_comment"] = message.content
            if message.platform_thread_id:
                data["thread_ts"] = message.platform_thread_id

            response = await self._client.post(
                "files.upload",
                data=data,
                files={"file": (attachment.filename, f, attachment.content_type)},
            )
            response.raise_for_status()
            result = response.json()
            if not result.get("ok"):
                raise ValueError(f"Failed to upload Slack file: {result.get('error')}")

            file_info = result.get("file", {})
            shares = file_info.get("shares", {})
            for channel_shares in shares.values():
                for share_list in channel_shares.values():
                    if share_list:
                        return str(share_list[0].get("ts"))
        return None

    async def shutdown(self) -> None:
        """Cleanly close connections."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def capabilities(self) -> ChannelCapabilities:
        """Return channel capabilities."""
        return ChannelCapabilities(
            threading=True,
            reactions=True,
            files=True,
            markdown=True,
            max_message_length=self.max_message_length,
        )

    def parse_webhook(
        self, payload: dict[str, Any] | bytes, headers: dict[str, str]
    ) -> list[CommsMessage]:
        """Normalize inbound webhook payload."""
        if isinstance(payload, bytes):
            try:
                payload_dict = json.loads(payload)
            except json.JSONDecodeError as e:
                raise ValueError("Invalid JSON payload") from e
        else:
            payload_dict = payload

        # Handle url_verification
        if payload_dict.get("type") == "url_verification":
            challenge = payload_dict.get("challenge", "")
            # We raise a custom exception that the router can catch to return the challenge
            raise SlackVerificationChallenge(challenge)

        messages: list[CommsMessage] = []

        if payload_dict.get("type") == "event_callback":
            event = payload_dict.get("event", {})
            event_type = event.get("type")

            # Only process message events, ignore bot messages and edits for now
            if event_type == "message" and not event.get("bot_id") and not event.get("subtype"):
                text = event.get("text", "")
                user = event.get("user")
                channel = event.get("channel")
                ts = event.get("ts")
                thread_ts = event.get("thread_ts")

                if channel and text:
                    messages.append(
                        CommsMessage(
                            id=ts or f"slack_msg_{time.time()}",
                            channel_id=channel,
                            direction="inbound",
                            content=text,
                            created_at=datetime.now().isoformat(),
                            identity_id=user,
                            platform_message_id=ts,
                            platform_thread_id=thread_ts,
                            content_type="text",
                            metadata_json=event,
                        )
                    )
            elif event_type == "reaction_added":
                user = event.get("user")
                reaction = event.get("reaction")
                item = event.get("item", {})

                if item.get("type") == "message":
                    channel = item.get("channel")
                    ts = item.get("ts")

                    if channel and reaction and ts:
                        messages.append(
                            CommsMessage(
                                id=f"slack_rxn_{ts}_{time.time()}",
                                channel_id=channel,
                                direction="inbound",
                                content=reaction,
                                created_at=datetime.now().isoformat(),
                                identity_id=user,
                                platform_message_id=ts,  # ID of message being reacted to
                                content_type="reaction",
                                metadata_json=event,
                            )
                        )

        return messages

    def verify_webhook(self, payload: bytes, headers: dict[str, str], secret: str) -> bool:
        """Verify webhook signature."""
        timestamp = headers.get("x-slack-request-timestamp")
        slack_signature = headers.get("x-slack-signature")

        if not timestamp or not slack_signature:
            # Try lowercase variations if necessary, though ASGI/WSGI usually normalizes to lower
            timestamp = headers.get("X-Slack-Request-Timestamp") or timestamp
            slack_signature = headers.get("X-Slack-Signature") or slack_signature

        if not timestamp or not slack_signature:
            return False

        # Prevent replay attacks
        try:
            if abs(time.time() - float(timestamp)) > 60 * 5:
                return False
        except ValueError:
            return False

        sig_basestring = f"v0:{timestamp}:{payload.decode('utf-8')}"
        my_signature = (
            "v0="
            + hmac.new(
                secret.encode("utf-8"), sig_basestring.encode("utf-8"), hashlib.sha256
            ).hexdigest()
        )

        return hmac.compare_digest(my_signature, slack_signature)


# Register the adapter
register_adapter("slack", SlackAdapter)
