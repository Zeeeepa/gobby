"""
Example Notify Plugin - Demonstrates Custom Workflow Actions with Schema Validation

This plugin demonstrates the full pattern for creating custom workflow actions:
1. Schema definition using JSON Schema
2. Executor function implementation
3. Registration via register_workflow_action()
4. Usage in workflow YAML files

This is a reference implementation showing best practices for plugin development.

Installation:
    1. Copy this file to ~/.gobby/plugins/example_notify.py
    2. Enable in ~/.gobby/config.yaml:
       hook_extensions:
         plugins:
           enabled: true
           plugins:
             example-notify:
               enabled: true
               config:
                 default_channel: "#general"
                 log_file: "~/.gobby/logs/metrics.log"
    3. Restart gobby daemon: gobby stop && gobby start

Usage in Workflows:
    # HTTP notification example
    - action: plugin:example-notify:http_notify
      url: "https://hooks.slack.com/services/xxx"
      method: "POST"
      payload:
        text: "Build completed: {result}"

    # Metric logging example
    - action: plugin:example-notify:log_metric
      metric_name: "build_duration"
      value: 42.5
      tags:
        project: "my-app"
        environment: "production"
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gobby.hooks.plugins import HookPlugin

if TYPE_CHECKING:
    from gobby.workflows.actions import ActionContext


class ExampleNotifyPlugin(HookPlugin):
    """
    Example plugin demonstrating custom workflow actions with schema validation.

    This plugin provides two actions:
    - http_notify: Send HTTP notifications (mock implementation for example)
    - log_metric: Log metrics to a file

    Both actions use register_workflow_action() for schema validation.
    """

    name = "example-notify"
    version = "1.0.0"
    description = "Example plugin demonstrating workflow actions with schema validation"

    def __init__(self) -> None:
        super().__init__()
        # Configuration defaults
        self.default_channel: str = "#general"
        self.log_file: Path = Path("~/.gobby/logs/metrics.log").expanduser()
        self._metrics_logged: int = 0
        self._notifications_sent: int = 0

    def on_load(self, config: dict[str, Any]) -> None:
        """Initialize plugin with configuration and register actions."""
        # Load configuration
        self.default_channel = config.get("default_channel", self.default_channel)
        log_file = config.get("log_file", str(self.log_file))
        self.log_file = Path(log_file).expanduser()

        self.logger.info(
            f"Example Notify plugin loaded: channel={self.default_channel}, "
            f"log_file={self.log_file}"
        )

        # =====================================================================
        # PATTERN: Register actions with schema validation
        # =====================================================================
        #
        # Use register_workflow_action() when you want input validation.
        # The schema follows JSON Schema format with 'properties' and 'required'.
        #
        # Actions are available in workflows as: plugin:<plugin-name>:<action-type>
        # Example: plugin:example-notify:http_notify

        # Register http_notify action with full schema
        self.register_workflow_action(
            action_type="http_notify",
            schema=HTTP_NOTIFY_SCHEMA,
            executor_fn=self._execute_http_notify,
        )

        # Register log_metric action with full schema
        self.register_workflow_action(
            action_type="log_metric",
            schema=LOG_METRIC_SCHEMA,
            executor_fn=self._execute_log_metric,
        )

        # =====================================================================
        # ALTERNATIVE: Simple registration without schema
        # =====================================================================
        #
        # Use register_action() for actions that don't need input validation:
        #
        #     self.register_action("simple_action", self._execute_simple)
        #
        # This is equivalent to register_workflow_action with an empty schema.

    def on_unload(self) -> None:
        """Cleanup and log statistics on plugin unload."""
        self.logger.info(
            f"Example Notify stats: notifications_sent={self._notifications_sent}, "
            f"metrics_logged={self._metrics_logged}"
        )

    # =========================================================================
    # Action Executors
    # =========================================================================
    #
    # Executor functions must be async and follow this signature:
    #
    #     async def executor(
    #         context: ActionContext,
    #         **kwargs: Any
    #     ) -> dict[str, Any] | None
    #
    # - context: ActionContext with session info, variables, workflow state
    # - kwargs: Input parameters from the workflow YAML (validated against schema)
    # - Returns: Dict with results (stored in workflow variables if capture_output set)

    async def _execute_http_notify(
        self,
        context: ActionContext,
        url: str,
        method: str = "POST",
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        channel: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute HTTP notification action.

        In a real implementation, this would make an actual HTTP request.
        For this example, we simulate the notification and log it.

        Args:
            context: Workflow action context
            url: Target URL for the notification
            method: HTTP method (GET, POST, PUT, DELETE)
            payload: Request body (JSON-serializable)
            headers: Additional HTTP headers
            channel: Optional channel override

        Returns:
            Dict with notification result
        """
        effective_channel = channel or self.default_channel
        timestamp = datetime.now(UTC).isoformat()

        # In a real implementation, you would use aiohttp here:
        #
        #     async with aiohttp.ClientSession() as session:
        #         async with session.request(method, url, json=payload) as resp:
        #             return {"status_code": resp.status, "body": await resp.text()}
        #
        # For this example, we simulate success:

        self.logger.info(
            f"[SIMULATED] HTTP {method} to {url} | channel={effective_channel} | payload={payload}"
        )

        self._notifications_sent += 1

        return {
            "success": True,
            "simulated": True,
            "method": method,
            "url": url,
            "channel": effective_channel,
            "timestamp": timestamp,
            "notification_count": self._notifications_sent,
        }

    async def _execute_log_metric(
        self,
        context: ActionContext,
        metric_name: str,
        value: int | float,
        tags: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute metric logging action.

        Writes metrics to a log file in JSON Lines format.

        Args:
            context: Workflow action context
            metric_name: Name of the metric (e.g., "build_duration")
            value: Numeric value of the metric
            tags: Optional key-value tags for the metric

        Returns:
            Dict with logging result
        """
        timestamp = datetime.now(UTC).isoformat()

        metric_entry = {
            "timestamp": timestamp,
            "metric": metric_name,
            "value": value,
            "tags": tags or {},
            "session_id": context.session_id if context else None,
        }

        # Ensure log directory exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Append to log file in JSON Lines format
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(metric_entry) + "\n")

            self._metrics_logged += 1

            self.logger.debug(f"Logged metric: {metric_name}={value}")

            return {
                "success": True,
                "metric_name": metric_name,
                "value": value,
                "timestamp": timestamp,
                "log_file": str(self.log_file),
                "metrics_logged": self._metrics_logged,
            }

        except OSError as e:
            self.logger.error(f"Failed to write metric: {e}")
            return {
                "success": False,
                "error": str(e),
                "metric_name": metric_name,
                "value": value,
            }


# =============================================================================
# JSON Schema Definitions
# =============================================================================
#
# Schemas define the expected input parameters for workflow actions.
# They enable validation before execution and serve as documentation.
#
# Schema format follows JSON Schema draft-07 with these commonly used fields:
# - properties: Object mapping parameter names to their schemas
# - required: Array of required parameter names
# - type: "string", "number", "integer", "boolean", "array", "object", "null"
# - description: Human-readable description of the parameter
# - default: Default value if not provided
# - enum: Array of allowed values

HTTP_NOTIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": "Send an HTTP notification to a webhook URL",
    "properties": {
        "url": {
            "type": "string",
            "description": "Target URL for the HTTP request (e.g., Slack webhook URL)",
        },
        "method": {
            "type": "string",
            "description": "HTTP method to use",
            "enum": ["GET", "POST", "PUT", "DELETE"],
            "default": "POST",
        },
        "payload": {
            "type": "object",
            "description": "Request body as JSON object",
        },
        "headers": {
            "type": "object",
            "description": "Additional HTTP headers as key-value pairs",
        },
        "channel": {
            "type": "string",
            "description": "Override the default notification channel",
        },
    },
    "required": ["url"],
}

LOG_METRIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": "Log a metric value with optional tags",
    "properties": {
        "metric_name": {
            "type": "string",
            "description": "Name of the metric (e.g., 'build_duration', 'test_count')",
        },
        "value": {
            "type": "number",
            "description": "Numeric value of the metric",
        },
        "tags": {
            "type": "object",
            "description": "Key-value tags for metric categorization",
        },
    },
    "required": ["metric_name", "value"],
}


# For dynamic discovery, the class must be importable
__all__ = ["ExampleNotifyPlugin"]
