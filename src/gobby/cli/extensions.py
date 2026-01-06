"""
CLI commands for hook extensions (hooks, plugins, webhooks).
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import click

from gobby.cli.mcp_proxy import call_mcp_api, check_daemon_running, get_daemon_client

if TYPE_CHECKING:
    from gobby.hooks.events import HookEventType

# =============================================================================
# Hooks Commands
# =============================================================================


@click.group()
def hooks() -> None:
    """Manage hook system configuration and testing."""


@hooks.command("list")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def hooks_list(ctx: click.Context, json_format: bool) -> None:
    """List supported hook event types."""
    from gobby.hooks.events import HookEventType

    hook_types = [{"name": e.value, "description": _get_hook_description(e)} for e in HookEventType]

    if json_format:
        click.echo(json.dumps(hook_types, indent=2))
        return

    click.echo("Supported Hook Event Types:")
    click.echo()
    for hook in hook_types:
        click.echo(f"  {hook['name']}")
        if hook["description"]:
            click.echo(f"    {hook['description']}")


def _get_hook_description(event_type: HookEventType) -> str:
    """Get description for a hook event type."""
    from gobby.hooks.events import HookEventType

    descriptions = {
        HookEventType.SESSION_START: "Fired when a new session starts",
        HookEventType.SESSION_END: "Fired when a session ends",
        HookEventType.BEFORE_AGENT: "Fired before agent turn starts",
        HookEventType.AFTER_AGENT: "Fired after agent turn completes",
        HookEventType.STOP: "Fired when agent attempts to stop (can block)",
        HookEventType.BEFORE_TOOL: "Fired before a tool is executed (can block)",
        HookEventType.AFTER_TOOL: "Fired after a tool completes",
        HookEventType.BEFORE_TOOL_SELECTION: "Fired before tool selection (Gemini)",
        HookEventType.BEFORE_MODEL: "Fired before model call (Gemini)",
        HookEventType.AFTER_MODEL: "Fired after model call (Gemini)",
        HookEventType.PRE_COMPACT: "Fired before session context is compacted",
        HookEventType.NOTIFICATION: "Notification event from CLI",
    }
    return descriptions.get(event_type, "")


@hooks.command("test")
@click.argument("hook_type")
@click.option(
    "--source",
    "-s",
    type=click.Choice(["claude", "gemini", "codex"]),
    default="claude",
    help="Source CLI to simulate",
)
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def hooks_test(ctx: click.Context, hook_type: str, source: str, json_format: bool) -> None:
    """Test a hook by sending a test event to the daemon.

    HOOK_TYPE is the event type to test (e.g., session-start, before-tool).
    """
    client = get_daemon_client(ctx)
    if not check_daemon_running(client):
        sys.exit(1)

    # Build test payload
    test_payload = {
        "hook_type": hook_type,
        "source": source,
        "input_data": {
            "session_id": "test-session-cli",
            "tool_name": "test_tool" if "tool" in hook_type.lower() else None,
        },
    }

    result = call_mcp_api(
        client,
        "/hooks/execute",
        method="POST",
        json_data=test_payload,
    )

    if result is None:
        click.echo("Failed to execute test hook", err=True)
        sys.exit(1)

    if json_format:
        click.echo(json.dumps(result, indent=2))
        return

    click.echo(f"Hook test: {hook_type}")
    click.echo(f"  Source: {source}")
    click.echo(f"  Continue: {result.get('continue', 'unknown')}")
    if result.get("reason"):
        click.echo(f"  Reason: {result.get('reason')}")
    inject_context = result.get("inject_context")
    if inject_context:
        click.echo(f"  Context: {str(inject_context)[:100]}...")


# =============================================================================
# Plugins Commands
# =============================================================================


@click.group()
def plugins() -> None:
    """Manage Python hook plugins."""


@plugins.command("list")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def plugins_list(ctx: click.Context, json_format: bool) -> None:
    """List loaded plugins."""
    client = get_daemon_client(ctx)
    if not check_daemon_running(client):
        sys.exit(1)

    result = call_mcp_api(client, "/plugins")

    if result is None:
        click.echo("Failed to list plugins", err=True)
        sys.exit(1)

    if json_format:
        click.echo(json.dumps(result, indent=2))
        return

    plugins_list = result.get("plugins", [])
    enabled = result.get("enabled", False)

    if not enabled:
        click.echo("Plugin system is disabled in configuration.")
        click.echo("Enable with: plugins.enabled: true in ~/.gobby/config.yaml")
        return

    if not plugins_list:
        click.echo("No plugins loaded.")
        click.echo()
        click.echo("Plugin directories:")
        for dir_path in result.get("plugin_dirs", []):
            click.echo(f"  {dir_path}")
        return

    click.echo(f"Loaded Plugins ({len(plugins_list)}):")
    click.echo()
    for plugin in plugins_list:
        click.echo(f"  {plugin['name']} v{plugin['version']}")
        if plugin.get("description"):
            click.echo(f"    {plugin['description']}")
        if plugin.get("handlers"):
            click.echo(f"    Handlers: {len(plugin['handlers'])}")
        if plugin.get("actions"):
            click.echo(f"    Actions: {', '.join(a['name'] for a in plugin['actions'])}")


@plugins.command("reload")
@click.argument("plugin_name")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def plugins_reload(ctx: click.Context, plugin_name: str, json_format: bool) -> None:
    """Reload a plugin by name.

    PLUGIN_NAME is the name of the plugin to reload.
    """
    client = get_daemon_client(ctx)
    if not check_daemon_running(client):
        sys.exit(1)

    result = call_mcp_api(
        client,
        "/plugins/reload",
        method="POST",
        json_data={"name": plugin_name},
    )

    if result is None:
        click.echo(f"Failed to reload plugin: {plugin_name}", err=True)
        sys.exit(1)

    if json_format:
        click.echo(json.dumps(result, indent=2))
        return

    if result.get("success"):
        click.echo(f"Plugin '{plugin_name}' reloaded successfully.")
        if result.get("version"):
            click.echo(f"  Version: {result.get('version')}")
    else:
        click.echo(f"Failed to reload plugin: {result.get('error', 'Unknown error')}", err=True)
        sys.exit(1)


# =============================================================================
# Webhooks Commands
# =============================================================================


@click.group()
def webhooks() -> None:
    """Manage webhook endpoints."""


@webhooks.command("list")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def webhooks_list(ctx: click.Context, json_format: bool) -> None:
    """List configured webhook endpoints."""
    client = get_daemon_client(ctx)
    if not check_daemon_running(client):
        sys.exit(1)

    result = call_mcp_api(client, "/webhooks")

    if result is None:
        click.echo("Failed to list webhooks", err=True)
        sys.exit(1)

    if json_format:
        click.echo(json.dumps(result, indent=2))
        return

    enabled = result.get("enabled", False)
    endpoints = result.get("endpoints", [])

    if not enabled:
        click.echo("Webhook system is disabled in configuration.")
        click.echo("Enable with: hook_extensions.webhooks.enabled: true")
        return

    if not endpoints:
        click.echo("No webhook endpoints configured.")
        click.echo()
        click.echo("Configure webhooks in ~/.gobby/config.yaml:")
        click.echo("  hook_extensions:")
        click.echo("    webhooks:")
        click.echo("      endpoints:")
        click.echo("        - name: my-webhook")
        click.echo("          url: https://example.com/hook")
        return

    click.echo(f"Webhook Endpoints ({len(endpoints)}):")
    click.echo()
    for endpoint in endpoints:
        status = "enabled" if endpoint.get("enabled", True) else "disabled"
        click.echo(f"  {endpoint['name']} [{status}]")
        click.echo(f"    URL: {endpoint.get('url', 'not configured')}")
        events = endpoint.get("events", [])
        if events:
            click.echo(f"    Events: {', '.join(events)}")
        else:
            click.echo("    Events: all")
        if endpoint.get("can_block"):
            click.echo("    Can block: yes")


@webhooks.command("test")
@click.argument("webhook_name")
@click.option(
    "--event",
    "-e",
    default="notification",
    help="Event type to send (default: notification)",
)
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def webhooks_test(ctx: click.Context, webhook_name: str, event: str, json_format: bool) -> None:
    """Test a webhook endpoint by sending a test event.

    WEBHOOK_NAME is the name of the webhook endpoint to test.
    """
    client = get_daemon_client(ctx)
    if not check_daemon_running(client):
        sys.exit(1)

    result = call_mcp_api(
        client,
        "/webhooks/test",
        method="POST",
        json_data={
            "name": webhook_name,
            "event_type": event,
        },
    )

    if result is None:
        click.echo(f"Failed to test webhook: {webhook_name}", err=True)
        sys.exit(1)

    if json_format:
        click.echo(json.dumps(result, indent=2))
        return

    if result.get("success"):
        click.echo(f"Webhook '{webhook_name}' test successful!")
        click.echo(f"  Status: {result.get('status_code', 'unknown')}")
        response_time = result.get("response_time_ms")
        if response_time:
            click.echo(f"  Response time: {response_time:.0f}ms")
    else:
        click.echo(f"Webhook test failed: {result.get('error', 'Unknown error')}", err=True)
        if result.get("status_code"):
            click.echo(f"  Status: {result.get('status_code')}")
        sys.exit(1)
