"""Alert dispatcher for conductor notifications.

Provides alert dispatching with:
- Multiple priority levels (info, normal, urgent, critical)
- Logging for all alerts
- Optional callme integration for critical alerts
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol


class CallmeClient(Protocol):
    """Protocol for callme client interface."""

    def initiate_call(self, message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Initiate a phone call alert."""
        ...


@dataclass
class AlertDispatcher:
    """Dispatcher for system alerts.

    Handles alerts at different priority levels:
    - info: Informational messages, logged at INFO level
    - normal: Normal alerts, logged at INFO level
    - urgent: Urgent alerts, logged at WARNING level
    - critical: Critical alerts, logged at ERROR level, triggers callme if configured
    """

    callme_client: CallmeClient | None = None
    """Optional callme client for critical alerts."""

    _history: list[dict[str, Any]] = field(default_factory=list)
    """Internal history of dispatched alerts."""

    _logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    """Logger instance."""

    def dispatch(
        self,
        priority: str,
        message: str,
        context: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """
        Dispatch an alert.

        Args:
            priority: Alert priority (info, normal, urgent, critical)
            message: Alert message
            context: Optional context dict with additional data
            source: Optional source identifier (e.g., "TaskMonitor")

        Returns:
            Dict with success status and alert details
        """
        now = datetime.now(UTC)

        # Build alert record
        alert_record = {
            "priority": priority,
            "message": message,
            "context": context,
            "source": source,
            "timestamp": now.isoformat(),
        }

        # Log based on priority
        log_message = f"[{priority.upper()}] {message}"
        if source:
            log_message = f"[{source}] {log_message}"
        if context:
            log_message += f" context={context}"

        if priority == "critical":
            self._logger.error(log_message)
        elif priority == "urgent":
            self._logger.warning(log_message)
        else:  # info, normal
            self._logger.info(log_message)

        # Store in history
        self._history.append(alert_record)

        # Build result
        result: dict[str, Any] = {
            "success": True,
            "priority": priority,
            "timestamp": now.isoformat(),
        }

        if context:
            result["context"] = context
        if source:
            result["source"] = source

        # Handle critical alerts with callme
        if priority == "critical":
            result["callme_triggered"] = False
            if self.callme_client is not None:
                try:
                    call_result = self.callme_client.initiate_call(
                        message=message,
                        context=context,
                    )
                    result["callme_triggered"] = True
                    result["callme_result"] = call_result
                except Exception as e:
                    self._logger.error(f"Callme failed: {e}")
                    result["callme_error"] = str(e)

        return result

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Get alert history.

        Args:
            limit: Maximum number of alerts to return

        Returns:
            List of alert records (oldest first)
        """
        return self._history[:limit]

    def clear_history(self) -> None:
        """Clear alert history."""
        self._history.clear()
