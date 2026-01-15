"""Daemon client for TUI communication.

Provides HTTP REST API and WebSocket clients for communicating with
the Gobby daemon.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx


class DaemonClient:
    """Client for communicating with Gobby daemon."""

    def __init__(
        self,
        http_base: str = "http://localhost:8765",
        ws_base: str = "ws://localhost:8766",
    ) -> None:
        """Initialize the daemon client.

        Args:
            http_base: Base URL for HTTP REST API
            ws_base: Base URL for WebSocket connection
        """
        self.http_base = http_base
        self.ws_base = ws_base
        self._http_client: httpx.AsyncClient | None = None
        self._event_handlers: dict[str, list[Callable[..., Any]]] = {}
        self._connected = False

    async def connect(self) -> bool:
        """Connect to the daemon.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self._http_client = httpx.AsyncClient(
                base_url=self.http_base,
                timeout=10.0,
            )
            # Test connection
            status = await self.get_daemon_status()
            # API returns "healthy" when daemon is running
            self._connected = status.get("status") in ("healthy", "running")
            return self._connected
        except Exception:
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from the daemon."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._connected = False

    @property
    def connected(self) -> bool:
        """Check if connected to daemon."""
        return self._connected

    async def get_daemon_status(self) -> dict[str, Any]:
        """Get daemon status.

        Returns:
            Daemon status dict with keys like 'status', 'uptime', etc.
        """
        if not self._http_client:
            return {"status": "disconnected"}

        try:
            response = await self._http_client.get("/admin/status")
            response.raise_for_status()
            return response.json()
        except Exception:
            return {"status": "error"}

    async def list_sessions(
        self,
        status: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List sessions with optional filters.

        Args:
            status: Filter by session status ('active', 'expired')
            project_id: Filter by project ID
            limit: Maximum number of sessions to return

        Returns:
            List of session dictionaries
        """
        if not self._http_client:
            return []

        try:
            params: dict[str, Any] = {"limit": limit}
            if status:
                params["status"] = status
            if project_id:
                params["project_id"] = project_id

            response = await self._http_client.get("/sessions", params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("sessions", [])
        except Exception:
            return []

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get a single session by ID.

        Args:
            session_id: The session ID to fetch

        Returns:
            Session dict or None if not found
        """
        if not self._http_client:
            return None

        try:
            response = await self._http_client.get(f"/sessions/{session_id}")
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    async def get_session_messages(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get messages for a session.

        Args:
            session_id: The session ID
            limit: Maximum number of messages to return

        Returns:
            List of message dictionaries
        """
        if not self._http_client:
            return []

        try:
            response = await self._http_client.get(
                f"/sessions/{session_id}/messages",
                params={"limit": limit},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("messages", [])
        except Exception:
            return []

    def on_event(self, event_type: str, handler: Callable[..., Any]) -> None:
        """Register an event handler for WebSocket events.

        Args:
            event_type: The event type to listen for
            handler: Callback function to invoke
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    async def _dispatch_event(self, event: dict[str, Any]) -> None:
        """Dispatch an event to registered handlers.

        Args:
            event: The event dict with 'type' key
        """
        event_type = event.get("type", "unknown")
        # Create a copy to avoid mutating the internal handler lists
        handlers = list(self._event_handlers.get(event_type, []))
        handlers.extend(self._event_handlers.get("*", []))  # Wildcard handlers

        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass  # Log errors in production
