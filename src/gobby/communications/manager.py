"""Central CommunicationsManager for the Gobby communications framework."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.communications.adapters import get_adapter_class
from gobby.communications.models import ChannelConfig, CommsMessage
from gobby.communications.rate_limiter import TokenBucketRateLimiter
from gobby.communications.router import MessageRouter

if TYPE_CHECKING:
    from gobby.communications.adapters.base import BaseChannelAdapter
    from gobby.config.communications import CommunicationsConfig
    from gobby.storage.communications import LocalCommunicationsStore
    from gobby.storage.secrets import SecretStore

logger = logging.getLogger(__name__)


class CommunicationsManager:
    """Central manager for communication channel adapters.

    Owns the adapter lifecycle, message routing, and inbound/outbound coordination.
    Same pattern as pipeline_executor, memory_manager, etc. on ServiceContainer.
    """

    def __init__(
        self,
        config: CommunicationsConfig,
        store: LocalCommunicationsStore,
        secret_store: SecretStore,
    ) -> None:
        """Initialize the communications manager.

        Args:
            config: Communications configuration.
            store: Local communications storage manager.
            secret_store: Secret store for resolving $secret: references.
        """
        self._config = config
        self._store = store
        self._secret_store = secret_store
        self._adapters: dict[str, BaseChannelAdapter] = {}
        self._channel_by_name: dict[str, ChannelConfig] = {}
        self._rate_limiter = TokenBucketRateLimiter.from_defaults(config.channel_defaults)
        self._router = MessageRouter(store)
        self.event_callback: Callable[..., Any] | None = None

    async def start(self) -> None:
        """Load enabled channels from DB, initialize adapters, configure rate limiter."""
        channels = self._store.list_channels(enabled_only=True)
        for channel in channels:
            try:
                adapter = await self._init_adapter(channel)
                self._adapters[channel.name] = adapter
                self._channel_by_name[channel.name] = channel
                # Configure rate limiter with per-channel overrides
                rate = channel.config_json.get(
                    "rate_limit_per_minute",
                    self._config.channel_defaults.rate_limit_per_minute,
                )
                burst = channel.config_json.get(
                    "burst",
                    self._config.channel_defaults.burst,
                )
                self._rate_limiter.configure_channel(channel.id, int(rate), int(burst))
                logger.info(
                    f"Communications: initialized channel {channel.name!r} ({channel.channel_type})",
                )
            except Exception as e:
                logger.error(f"Failed to initialize channel {channel.name!r}: {e}")
        logger.info(f"CommunicationsManager started ({len(self._adapters)} channels active)")

    async def stop(self) -> None:
        """Shutdown all adapters and clear state."""
        for name, adapter in list(self._adapters.items()):
            try:
                await adapter.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down channel {name!r}: {e}")
        self._adapters.clear()
        self._channel_by_name.clear()
        logger.info("CommunicationsManager stopped")

    async def _init_adapter(self, channel: ChannelConfig) -> BaseChannelAdapter:
        """Lookup adapter class from registry, instantiate, and initialize.

        Args:
            channel: Channel configuration.

        Returns:
            Initialized adapter instance.

        Raises:
            ValueError: If no adapter is registered for the channel type.
        """
        adapter_cls = get_adapter_class(channel.channel_type)
        if adapter_cls is None:
            raise ValueError(f"No adapter registered for channel type {channel.channel_type!r}")
        adapter = adapter_cls()
        await adapter.initialize(channel, self._secret_store.get)
        return adapter

    async def send_message(
        self,
        channel_name: str,
        content: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CommsMessage:
        """Send a message to a named channel.

        Args:
            channel_name: Name of the channel to send to.
            content: Message content.
            session_id: Optional session ID to associate with the message.
            metadata: Optional metadata dict.

        Returns:
            The CommsMessage that was sent (or failed).

        Raises:
            ValueError: If the channel is not found or not active.
        """
        adapter = self._adapters.get(channel_name)
        if adapter is None:
            raise ValueError(f"Channel {channel_name!r} not found or not active")

        channel = self._channel_by_name[channel_name]

        # Rate limit check — waits until a token is available
        await self._rate_limiter.wait_if_needed(channel.id)

        # Build CommsMessage
        message = CommsMessage(
            id=str(uuid.uuid4()),
            channel_id=channel.id,
            direction="outbound",
            content=content,
            session_id=session_id,
            status="pending",
            metadata_json=metadata or {},
            created_at=datetime.now(UTC).isoformat(),
        )

        # Send via adapter
        try:
            platform_message_id = await adapter.send_message(message)
            message.platform_message_id = platform_message_id
            message.status = "sent"
        except Exception as e:
            message.status = "failed"
            message.error = str(e)
            logger.error(f"Failed to send message to {channel_name!r}: {e}")

        # Store in DB
        try:
            self._store.save_message(message)
        except Exception as e:
            logger.error(f"Failed to store outbound message: {e}")

        # Fire event callback
        if self.event_callback is not None:
            try:
                await self.event_callback("comms.message_sent", message=message)
            except Exception as e:
                logger.debug(f"Event callback error on send_message: {e}")

        return message

    async def send_event(
        self,
        event_type: str,
        content: str,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> list[CommsMessage]:
        """Route event to matching channels and send to each.

        Args:
            event_type: Event type string (e.g., "task.created").
            content: Message content to send.
            project_id: Optional project ID for routing rule matching.
            session_id: Optional session ID for routing rule matching.

        Returns:
            List of CommsMessages sent.
        """
        channel_ids = await self._router.match_channels(
            event_type, project_id=project_id, session_id=session_id
        )

        # Build reverse map: channel_id -> channel_name for active adapters
        id_to_name: dict[str, str] = {c.id: n for n, c in self._channel_by_name.items()}

        messages: list[CommsMessage] = []
        for channel_id in channel_ids:
            channel_name = id_to_name.get(channel_id)
            if channel_name is None:
                continue
            try:
                msg = await self.send_message(channel_name, content, session_id=session_id)
                messages.append(msg)
            except Exception as e:
                logger.error(f"send_event: failed to send to {channel_name!r}: {e}")

        return messages

    async def handle_inbound(
        self,
        channel_name: str,
        payload: dict[str, Any] | bytes,
        headers: dict[str, str],
    ) -> list[CommsMessage]:
        """Handle an inbound webhook payload.

        Args:
            channel_name: Name of the channel receiving the webhook.
            payload: Raw webhook payload (dict or bytes).
            headers: HTTP headers from the webhook request.

        Returns:
            List of stored CommsMessages parsed from the payload.

        Raises:
            ValueError: If channel is not found or webhook verification fails.
        """
        adapter = self._adapters.get(channel_name)
        if adapter is None:
            raise ValueError(f"Channel {channel_name!r} not found or not active")

        channel = self._channel_by_name[channel_name]

        # Verify webhook signature if a secret is configured
        if channel.webhook_secret:
            raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            if not adapter.verify_webhook(raw, headers, channel.webhook_secret):
                raise ValueError(
                    f"Webhook signature verification failed for channel {channel_name!r}"
                )

        # Parse messages from payload
        payload_for_parse: dict[str, Any] | bytes = payload
        parsed: list[CommsMessage] = adapter.parse_webhook(payload_for_parse, headers)

        stored: list[CommsMessage] = []
        for message in parsed:
            # Ensure channel_id is set
            if not message.channel_id:
                message.channel_id = channel.id

            # Resolve identity: if identity_id looks like an external_user_id, resolve it
            if message.identity_id:
                identity = self._store.get_identity(channel.id, message.identity_id)
                if identity:
                    message.session_id = identity.session_id
                    message.identity_id = identity.id

            # Store message
            try:
                self._store.save_message(message)
                stored.append(message)
            except Exception as e:
                logger.error(f"Failed to store inbound message: {e}")

        # Fire event callback for each stored message
        if self.event_callback is not None:
            for msg in stored:
                try:
                    await self.event_callback("comms.message_received", message=msg)
                except Exception as e:
                    logger.debug(f"Event callback error on handle_inbound: {e}")

        return stored

    async def add_channel(
        self,
        channel_type: str,
        name: str,
        config: dict[str, Any],
        secrets: dict[str, Any] | None = None,
    ) -> ChannelConfig:
        """Create a new channel in DB and initialize its adapter.

        Args:
            channel_type: The type identifier (e.g., "slack", "telegram").
            name: Unique channel name.
            config: Channel configuration dict.
            secrets: Optional secrets dict (may include webhook_secret).

        Returns:
            The created ChannelConfig.
        """
        now = datetime.now(UTC).isoformat()
        channel_config = ChannelConfig(
            id=str(uuid.uuid4()),
            channel_type=channel_type,
            name=name,
            enabled=True,
            config_json=config,
            created_at=now,
            updated_at=now,
            webhook_secret=secrets.get("webhook_secret") if secrets else None,
        )

        # Save to DB
        self._store.save_channel(channel_config)

        # Initialize adapter
        try:
            adapter = await self._init_adapter(channel_config)
            self._adapters[name] = adapter
            self._channel_by_name[name] = channel_config
            # Configure rate limiter
            rate = config.get(
                "rate_limit_per_minute",
                self._config.channel_defaults.rate_limit_per_minute,
            )
            burst = config.get(
                "burst",
                self._config.channel_defaults.burst,
            )
            self._rate_limiter.configure_channel(channel_config.id, int(rate), int(burst))
            logger.info(f"Added channel {name!r} ({channel_type})")
        except Exception as e:
            logger.error(f"Failed to initialize adapter for new channel {name!r}: {e}")

        return channel_config

    async def remove_channel(self, name: str) -> None:
        """Shutdown adapter and delete channel from DB.

        Args:
            name: Channel name to remove.
        """
        adapter = self._adapters.pop(name, None)
        channel = self._channel_by_name.pop(name, None)

        if adapter is not None:
            try:
                await adapter.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down channel {name!r}: {e}")

        if channel is not None:
            self._rate_limiter.remove_channel(channel.id)
            try:
                self._store.delete_channel(channel.id)
                logger.info(f"Removed channel {name!r}")
            except Exception as e:
                logger.error(f"Failed to delete channel {name!r} from DB: {e}")

    def list_channels(self) -> list[ChannelConfig]:
        """List all channels (enabled and disabled) from DB.

        Returns:
            List of ChannelConfig objects.
        """
        return self._store.list_channels(enabled_only=False)

    def get_channel_status(self, name: str) -> dict[str, Any]:
        """Get adapter health/connected status for a channel.

        Args:
            name: Channel name.

        Returns:
            Dict with status information.
        """
        channel = self._channel_by_name.get(name)
        adapter = self._adapters.get(name)

        if channel is not None and adapter is not None:
            return {
                "name": name,
                "channel_type": channel.channel_type,
                "status": "active",
                "active": True,
                "enabled": channel.enabled,
                "supports_webhooks": adapter.supports_webhooks,
                "supports_polling": adapter.supports_polling,
            }

        # Channel not active — check DB
        channels = self._store.list_channels(enabled_only=False)
        db_channel = next((c for c in channels if c.name == name), None)
        if db_channel is None:
            return {"name": name, "status": "not_found", "active": False}

        return {
            "name": name,
            "channel_type": db_channel.channel_type,
            "status": "inactive",
            "active": False,
            "enabled": db_channel.enabled,
        }
