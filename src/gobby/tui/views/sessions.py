"""Sessions view with DataTable."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.reactive import reactive
from textual.widgets import DataTable

if TYPE_CHECKING:
    from gobby.tui.client import DaemonClient

# Provider color mapping
PROVIDER_COLORS: dict[str, str] = {
    "claude_code": "#D97706",  # Anthropic orange
    "claude-code": "#D97706",
    "gemini": "#4285F4",  # Google blue
    "gemini_cli": "#4285F4",
    "codex": "#00A67E",  # OpenAI green
    "codex_cli": "#00A67E",
    "unknown": "#666666",
}

# Status color mapping
STATUS_COLORS: dict[str, str] = {
    "active": "#6CBF47",
    "running": "#3498DB",
    "waiting": "#F5A623",
    "idle": "#666666",
    "expired": "#666666",
}


class SessionsView(DataTable):
    """Sessions list view with DataTable."""

    DEFAULT_CSS = """
    SessionsView {
        height: 1fr;
        border: solid #333333;
    }

    SessionsView > .datatable--header {
        background: #161616;
        text-style: bold;
    }

    SessionsView > .datatable--cursor {
        background: #6CBF47 30%;
    }

    SessionsView > .datatable--hover {
        background: #252525;
    }
    """

    # Reactive filter state
    filter_status: reactive[str] = reactive("active")

    def __init__(
        self,
        client: DaemonClient | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize sessions view.

        Args:
            client: DaemonClient instance for fetching data
            **kwargs: Additional arguments for DataTable
        """
        super().__init__(
            cursor_type="row",
            zebra_stripes=True,
            **kwargs,
        )
        self.client = client
        self._sessions: list[dict[str, Any]] = []

    def on_mount(self) -> None:
        """Initialize columns when mounted."""
        self.add_column("ID", width=12, key="id")
        self.add_column("STATUS", width=12, key="status")
        self.add_column("CONTEXT / LAST ACTION", key="context")

    async def refresh_data(self) -> None:
        """Fetch sessions from daemon and populate table."""
        if not self.client:
            return

        # Map filter to API status
        status = None if self.filter_status == "all" else self.filter_status
        if status == "active":
            status = None  # API returns active by default

        self._sessions = await self.client.list_sessions(status=status)
        self._update_table()

    def _update_table(self) -> None:
        """Update the table with current session data."""
        self.clear()

        for session in self._sessions:
            self.add_row(
                self._format_id(session),
                self._format_status(session),
                self._format_context(session),
                key=session.get("id", ""),
            )

    def _format_id(self, session: dict[str, Any]) -> str:
        """Format session ID for display.

        Args:
            session: Session data dict

        Returns:
            Formatted session ID string
        """
        # Use ref if available, otherwise short ID
        ref = session.get("ref")
        if ref:
            return ref
        session_id = session.get("id", "")
        return f"sess_{session_id[:6]}" if session_id else "sess_???"

    def _format_status(self, session: dict[str, Any]) -> str:
        """Format status with provider badge.

        Args:
            session: Session data dict

        Returns:
            Formatted status string with Rich markup
        """
        # Determine status
        status = session.get("status", "unknown")
        if status == "active":
            # Check if there's recent activity
            status_text = "RUNNING"
            status_color = STATUS_COLORS.get("running", "#666666")
        elif status == "expired":
            status_text = "EXPIRED"
            status_color = STATUS_COLORS.get("expired", "#666666")
        else:
            status_text = status.upper()
            status_color = STATUS_COLORS.get(status, "#666666")

        return f"[{status_color}]{status_text}[/]"

    def _format_context(self, session: dict[str, Any]) -> str:
        """Format context/last action column.

        Args:
            session: Session data dict

        Returns:
            Formatted context string
        """
        parts: list[str] = []

        # Title or summary
        title = session.get("title") or session.get("summary_title")
        if title:
            parts.append(title[:40])
        else:
            parts.append("[dim](no title)[/]")

        # Provider badge
        source = session.get("source", "unknown")
        provider_color = PROVIDER_COLORS.get(source.lower(), PROVIDER_COLORS["unknown"])
        provider_display = source.replace("_", " ").replace("-", " ").title()
        parts.append(f"[{provider_color}][{provider_display}][/]")

        # Timestamp
        updated = session.get("updated_at", "")
        if updated:
            # Format as relative time or just show time portion
            time_part = updated[11:16] if len(updated) > 16 else updated
            parts.append(f"[dim]{time_part}[/]")

        return " ".join(parts)

    def watch_filter_status(self, new_filter: str) -> None:
        """React to filter changes.

        Args:
            new_filter: The new filter value
        """
        # Trigger data refresh when filter changes
        self.call_later(self.refresh_data)

    def get_selected_session(self) -> dict[str, Any] | None:
        """Get the currently selected session.

        Returns:
            Selected session dict or None
        """
        if not self._sessions:
            return None

        row_key = self.cursor_row
        if row_key is not None and 0 <= row_key < len(self._sessions):
            return self._sessions[row_key]
        return None
