"""
Communications router for webhook receiving and channel management.
"""

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


class ChannelCreate(BaseModel):
    """Model for creating a new channel."""

    channel_type: str = Field(alias="type")
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] | None = None


class ChannelUpdate(BaseModel):
    """Model for updating a channel's config."""

    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] | None = None
    enabled: bool | None = None


def create_communications_router(server: "HTTPServer") -> APIRouter:
    """
    Create communications router for channels, webhooks, and messages.

    Args:
        server: HTTPServer instance

    Returns:
        APIRouter instance
    """
    router = APIRouter(prefix="/api/comms", tags=["communications"])

    def _get_manager() -> Any:
        manager = server.services.communications_manager
        if not manager:
            raise HTTPException(status_code=503, detail="Communications manager not available")
        return manager

    @router.post("/webhooks/{channel_name}")
    async def receive_webhook(
        channel_name: str,
        request: Request,
    ) -> Response:
        """Receive inbound webhooks from communication platforms."""
        manager = _get_manager()

        # Some platforms like Slack may send JSON or URL-encoded form data.
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                payload = await request.json()
            except Exception:
                payload = await request.body()
        else:
            payload = await request.body()

        headers = dict(request.headers)

        # Handle Slack's url_verification challenge at the routing layer as a convenience
        if (
            isinstance(payload, dict)
            and payload.get("type") == "url_verification"
            and "challenge" in payload
        ):
            return Response(content=payload["challenge"], media_type="text/plain")

        try:
            await manager.handle_inbound(channel_name, payload, headers)
            return Response(status_code=200)
        except ValueError as e:
            logger.warning(f"Webhook error for {channel_name}: {e}")
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.error(
                f"Internal error processing webhook for {channel_name}: {e}", exc_info=True
            )
            raise HTTPException(
                status_code=500, detail="Internal server error processing webhook"
            ) from e

    @router.get("/webhooks/{channel_name}")
    async def verify_webhook(
        channel_name: str,
        request: Request,
    ) -> Response:
        """Handle verification challenges (GET requests) for platforms that use them."""
        # Typically looking for a query param named "challenge", "validationToken", etc.
        challenge = request.query_params.get("challenge") or request.query_params.get(
            "validationToken"
        )
        if challenge:
            return Response(content=challenge, media_type="text/plain")

        return Response(status_code=200)

    @router.get("/channels")
    async def list_channels() -> Any:
        """List all channels."""
        manager = _get_manager()
        return manager.list_channels()

    @router.post("/channels")
    async def create_channel(channel: ChannelCreate) -> Any:
        """Create a new channel."""
        manager = _get_manager()
        try:
            return await manager.add_channel(
                channel_type=channel.channel_type,
                name=channel.name,
                config=channel.config,
                secrets=channel.secrets,
            )
        except Exception as e:
            logger.error(f"Failed to create channel: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.put("/channels/{channel_id}")
    async def update_channel(channel_id: str, channel_update: ChannelUpdate) -> Any:
        """Update an existing channel."""
        manager = _get_manager()
        store = manager._store

        channel = store.get_channel(channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail=f"Channel with ID {channel_id} not found")

        # Update fields
        if channel_update.config is not None:
            channel.config_json.update(channel_update.config)
        if channel_update.enabled is not None:
            channel.enabled = channel_update.enabled

        # Update secret if provided
        if channel_update.secrets and "webhook_secret" in channel_update.secrets:
            channel.webhook_secret = channel_update.secrets["webhook_secret"]

        try:
            # Save to DB
            channel = store.update_channel(channel)

            # If the manager is active, we should recreate the adapter to pick up changes
            # Note: _adapters is keyed by channel name
            if channel.name in manager._adapters:
                await manager.remove_channel(channel.name)

            if channel.enabled:
                await manager.add_channel(
                    channel_type=channel.channel_type,
                    name=channel.name,
                    config=channel.config_json,
                    secrets={"webhook_secret": channel.webhook_secret}
                    if channel.webhook_secret
                    else None,
                )

            return channel
        except Exception as e:
            logger.error(f"Failed to update channel {channel_id}: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.delete("/channels/{channel_id}")
    async def remove_channel(channel_id: str) -> Any:
        """Delete a channel."""
        manager = _get_manager()
        store = manager._store

        channel = store.get_channel(channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail=f"Channel with ID {channel_id} not found")

        try:
            await manager.remove_channel(channel.name)
            return {"success": True}
        except Exception as e:
            logger.error(f"Failed to remove channel {channel_id}: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.get("/channels/{channel_id}/status")
    async def get_channel_status(channel_id: str) -> Any:
        """Get the health/status of a channel."""
        manager = _get_manager()
        store = manager._store

        channel = store.get_channel(channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail=f"Channel with ID {channel_id} not found")

        return manager.get_channel_status(channel.name)

    @router.get("/messages")
    async def list_messages(
        channel_id: str | None = None,
        session_id: str | None = None,
        direction: str | None = None,
        limit: int = Query(default=50, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> Any:
        """List messages with optional filters."""
        manager = _get_manager()
        store = manager._store

        try:
            return store.list_messages(
                channel_id=channel_id,
                session_id=session_id,
                direction=direction,
                limit=limit,
                offset=offset,
            )
        except Exception as e:
            logger.error(f"Failed to list messages: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail=str(e)) from e

    return router
