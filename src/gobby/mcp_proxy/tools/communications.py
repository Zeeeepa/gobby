"""Internal MCP tools for Communications."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gobby.mcp_proxy.tools.internal import InternalToolRegistry

if TYPE_CHECKING:
    from gobby.communications.manager import CommunicationsManager

__all__ = ["create_communications_registry"]


def create_communications_registry(
    comms_manager: CommunicationsManager,
) -> InternalToolRegistry:
    """Create a registry for communications identity tools."""
    registry = InternalToolRegistry(
        name="gobby-communications",
        description="Tools for managing communication channels and external user identities.",
    )

    @registry.tool(
        name="link_identity",
        description="Manually link an external user identity to a Gobby session. If the identity does not exist, it will be created.",
    )
    async def link_identity(
        channel: str,
        external_user_id: str,
        session_id: str,
        external_username: str | None = None,
    ) -> dict[str, Any]:
        """
        Manually link an external user on a channel to a Gobby session.

        Args:
            channel: Channel name or ID.
            external_user_id: The external user's unique ID on that channel.
            session_id: The Gobby session ID to link.
            external_username: Optional username to store with the identity.
        """
        try:
            # Check if channel exists (as name or ID)
            channel_config = comms_manager._channel_by_name.get(channel)
            if not channel_config:
                channels = comms_manager._store.list_channels(enabled_only=False)
                channel_config = next((c for c in channels if c.id == channel), None)

            if not channel_config:
                return {"success": False, "error": f"Channel {channel!r} not found"}

            # Resolve identity and update session
            identity = comms_manager._store.get_identity_by_external(
                channel_config.id, external_user_id
            )

            if identity:
                identity.session_id = session_id
                if external_username:
                    identity.external_username = external_username
                comms_manager._store.update_identity(identity)
            else:
                from gobby.communications.models import CommsIdentity

                identity = CommsIdentity(
                    id="",
                    channel_id=channel_config.id,
                    external_user_id=external_user_id,
                    external_username=external_username,
                    session_id=session_id,
                    created_at="",
                    updated_at="",
                )
                identity = comms_manager._store.create_identity(identity)

            return {"success": True, "identity_id": identity.id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="list_identities",
        description="List external user identities. Can filter by session or channel.",
    )
    async def list_identities(
        session_id: str | None = None,
        channel: str | None = None,
    ) -> dict[str, Any]:
        """
        List external user identities with optional filters.

        Args:
            session_id: Filter by linked session ID.
            channel: Filter by channel name or ID.
        """
        try:
            channel_id = None
            if channel:
                channel_config = comms_manager._channel_by_name.get(channel)
                if not channel_config:
                    channels = comms_manager._store.list_channels(enabled_only=False)
                    channel_config = next((c for c in channels if c.id == channel), None)
                if not channel_config:
                    return {"success": False, "error": f"Channel {channel!r} not found"}
                channel_id = channel_config.id

            identities = comms_manager._store.list_identities(channel_id=channel_id)

            if session_id:
                identities = [i for i in identities if i.session_id == session_id]

            results = []
            for i in identities:
                results.append(
                    {
                        "id": i.id,
                        "channel_id": i.channel_id,
                        "external_user_id": i.external_user_id,
                        "external_username": i.external_username,
                        "session_id": i.session_id,
                        "created_at": i.created_at,
                    }
                )

            return {"success": True, "identities": results, "count": len(results)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @registry.tool(
        name="unlink_identity",
        description="Remove the session link from an external identity.",
    )
    async def unlink_identity(
        identity_id: str,
    ) -> dict[str, Any]:
        """
        Unlink a session from an external user identity.

        Args:
            identity_id: The Gobby internal identity ID.
        """
        try:
            identity = comms_manager._store.get_identity(identity_id)
            if not identity:
                return {"success": False, "error": f"Identity {identity_id!r} not found"}

            if not identity.session_id:
                return {"success": True, "message": "Identity already has no linked session"}

            identity.session_id = None
            comms_manager._store.update_identity(identity)

            return {"success": True, "message": f"Session unlinked from identity {identity_id}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    return registry
