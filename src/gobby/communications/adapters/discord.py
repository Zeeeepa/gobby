"""Discord channel adapter."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
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

HAS_WEBSOCKETS = False
try:
    import websockets
    import websockets.client

    HAS_WEBSOCKETS = True
except ImportError:
    pass

HAS_CRYPTOGRAPHY = False
try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    HAS_CRYPTOGRAPHY = True
except ImportError:
    pass


class DiscordAdapter(BaseChannelAdapter):
    """Adapter for Discord using Gateway for receiving and REST for sending."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._gateway_task: asyncio.Task[Any] | None = None
        self._bot_token: str = ""

    @property
    def channel_type(self) -> str:
        """The unique type identifier for this channel."""
        return "discord"

    @property
    def max_message_length(self) -> int:
        """Maximum message length supported by the platform."""
        return 2000

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
        token_ref = config.config_json.get("bot_token", "$secret:DISCORD_BOT_TOKEN")
        token = secret_resolver(token_ref) if token_ref.startswith("$secret:") else token_ref

        if not token:
            raise ValueError(f"Could not resolve Discord bot token: {token_ref}")

        self._bot_token = token

        # Set up REST API client
        self._client = httpx.AsyncClient(
            base_url="https://discord.com/api/v10",
            headers={"Authorization": f"Bot {self._bot_token}"},
            timeout=30.0,
        )

        if HAS_WEBSOCKETS and config.config_json.get("enable_gateway", True):
            self._gateway_task = asyncio.create_task(self._run_gateway())

    async def _run_gateway(self) -> None:
        """Background task to connect to Discord Gateway and handle events."""
        if not HAS_WEBSOCKETS:
            return

        try:
            while True:
                try:
                    async with websockets.client.connect(  # type: ignore[attr-defined]
                        "wss://gateway.discord.gg/?v=10&encoding=json"
                    ) as ws:
                        # Send IDENTIFY
                        identify_payload = {
                            "op": 2,
                            "d": {
                                "token": self._bot_token,
                                "intents": 37376,  # 1 << 9 (GUILD_MESSAGES) | 1 << 12 (DIRECT_MESSAGES) | 1 << 15 (MESSAGE_CONTENT)
                                "properties": {
                                    "os": "linux",
                                    "browser": "gobby",
                                    "device": "gobby",
                                },
                            },
                        }
                        await ws.send(json.dumps(identify_payload))

                        async for message in ws:
                            if isinstance(message, (str, bytes)):
                                data = json.loads(message)

                                # In a full implementation we would handle heartbeat and other opcodes
                                # Here we specifically look for MESSAGE_CREATE as requested
                                if data.get("t") == "MESSAGE_CREATE":
                                    msg_data = data.get("d", {})
                                    logger.debug(
                                        f"Discord gateway received MESSAGE_CREATE: {msg_data.get('id')}"
                                    )
                                    # Since supports_polling=False, we don't have a way to inject this
                                    # into the polling loop. Real implementations might push this to
                                    # an event bus or call a callback.
                except Exception as e:
                    logger.warning(f"Discord gateway connection error: {e}")
                    await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass

    async def send_message(self, message: CommsMessage) -> str | None:
        """Send message and return platform message ID."""
        if not self._client:
            raise RuntimeError("Discord adapter not initialized")

        chunks = self.chunk_message(message.content, self.max_message_length)
        last_id = None

        # Use platform_thread_id or the internal channel_id for routing
        channel_id = message.platform_thread_id or message.channel_id

        for chunk in chunks:
            payload: dict[str, Any] = {
                "content": chunk,
            }

            response = await self._client.post(f"/channels/{channel_id}/messages", json=payload)
            response.raise_for_status()
            data = response.json()
            last_id = data.get("id")

        return last_id

    async def send_attachment(
        self, message: CommsMessage, attachment: CommsAttachment, file_path: Path
    ) -> str | None:
        """Send a file via Discord multipart form data."""
        if not self._client:
            raise RuntimeError("Discord adapter not initialized")

        channel_id = message.platform_thread_id or message.channel_id
        with open(file_path, "rb") as f:
            data: dict[str, Any] = {}
            if message.content:
                data["content"] = message.content
            payload_json = json.dumps(data) if data else json.dumps({})
            files: dict[str, Any] = {
                "files[0]": (attachment.filename, f, attachment.content_type),
            }
            response = await self._client.post(
                f"/channels/{channel_id}/messages",
                data={"payload_json": payload_json},
                files=files,
            )
            response.raise_for_status()
            result = response.json()
            msg_id: str | None = result.get("id")
            return msg_id

    async def shutdown(self) -> None:
        """Cleanly close connections."""
        if self._gateway_task:
            self._gateway_task.cancel()
            try:
                await self._gateway_task
            except asyncio.CancelledError:
                pass
            self._gateway_task = None

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

        # Discord Interactions structure
        messages: list[CommsMessage] = []

        # Interaction type 1 is PING
        if payload_dict.get("type") == 1:
            # The router should return {"type": 1} to acknowledge the ping
            # But the adapter API doesn't have a way to respond with data,
            # so we'd normally just return empty and let router handle ping
            return messages

        # Handle MESSAGE_REACTION_ADD events
        event_type = payload_dict.get("t")
        if event_type == "MESSAGE_REACTION_ADD":
            d = payload_dict.get("d", {})
            user_id = d.get("user_id")
            channel_id = d.get("channel_id")
            msg_id = d.get("message_id")
            emoji = d.get("emoji", {})
            reaction = emoji.get("name", "")

            if channel_id and reaction and msg_id:
                messages.append(
                    CommsMessage(
                        id=f"discord_rxn_{msg_id}_{time.time()}",
                        channel_id=channel_id,
                        direction="inbound",
                        content=reaction,
                        created_at=datetime.now(UTC).isoformat(),
                        identity_id=user_id,
                        platform_message_id=msg_id,
                        content_type="reaction",
                        metadata_json=d,
                    )
                )
            return messages

        # Interaction type or MESSAGE_CREATE structure
        data = payload_dict.get("data", {})

        # Fallback to direct MESSAGE_CREATE payload (gateway-like but via webhook if applicable)
        msg_data = payload_dict if "content" in payload_dict else data

        content = msg_data.get("content", "")
        author = payload_dict.get("member", {}).get("user", {}) or payload_dict.get("author", {})
        user_id = author.get("id")
        channel_id = payload_dict.get("channel_id")
        msg_id = payload_dict.get("id") or msg_data.get("id")
        # Extract thread ID from message reference or thread metadata
        thread_id = None
        message_reference = payload_dict.get("message_reference")
        if message_reference:
            thread_id = message_reference.get("channel_id")
        thread_meta = payload_dict.get("thread")
        if thread_meta:
            thread_id = thread_meta.get("id")

        if channel_id and content:
            messages.append(
                CommsMessage(
                    id=msg_id or f"discord_msg_{time.time()}",
                    channel_id=channel_id,
                    direction="inbound",
                    content=content,
                    created_at=datetime.now(UTC).isoformat(),
                    identity_id=user_id,
                    platform_message_id=msg_id,
                    platform_thread_id=thread_id,
                    content_type="text",
                    metadata_json=payload_dict,
                )
            )

        return messages

    def verify_webhook(self, payload: bytes, headers: dict[str, str], secret: str) -> bool:
        """Verify webhook signature."""
        if not HAS_CRYPTOGRAPHY:
            logger.warning("cryptography package missing, cannot verify Discord webhook signature")
            return False

        signature = headers.get("X-Signature-Ed25519") or headers.get("x-signature-ed25519")
        timestamp = headers.get("X-Signature-Timestamp") or headers.get("x-signature-timestamp")

        if not signature or not timestamp or not secret:
            return False

        try:
            public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(secret))
            public_key.verify(bytes.fromhex(signature), timestamp.encode() + payload)
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False


# Register the adapter
register_adapter("discord", DiscordAdapter)
