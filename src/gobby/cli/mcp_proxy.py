"""
MCP proxy CLI commands.

Provides CLI access to MCP proxy functionality:
- list-servers: List configured MCP servers
- list-tools: List tools from MCP servers
- get-schema: Get full schema for a specific tool
- call-tool: Execute a tool on an MCP server
- add-server: Add a new MCP server configuration
- remove-server: Remove an MCP server configuration
- recommend-tools: Get AI-powered tool recommendations
"""

import json
import sys
from typing import Any

import click

from gobby.config.app import DaemonConfig
from gobby.utils.daemon_client import DaemonClient


def get_daemon_client(ctx: click.Context) -> DaemonClient:
    """Get daemon client from context config."""
    config: DaemonConfig = ctx.obj["config"]
    return DaemonClient(host="localhost", port=config.daemon_port)


def check_daemon_running(client: DaemonClient) -> bool:
    """Check if daemon is running and print error if not."""
    is_healthy, error = client.check_health()
    if not is_healthy:
        if error is None:
            click.echo("Error: Gobby daemon is not running. Start it with: gobby start", err=True)
        else:
            click.echo(f"Error: Cannot connect to daemon: {error}", err=True)
        return False
    return True


def call_mcp_api(
    client: DaemonClient,
    endpoint: str,
    method: str = "POST",
    json_data: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Call MCP API endpoint and handle errors."""
    try:
        response = client.call_http_api(endpoint, method=method, json_data=json_data)
        if response.status_code == 200:
            return response.json()
        else:
            error_msg = response.text or f"HTTP {response.status_code}"
            click.echo(f"Error: {error_msg}", err=True)
            return None
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return None


@click.group("mcp-proxy")
def mcp_proxy() -> None:
    """Manage MCP proxy servers and tools."""
    pass


@mcp_proxy.command("list-servers")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def list_servers(ctx: click.Context, json_format: bool) -> None:
    """List all configured MCP servers."""
    client = get_daemon_client(ctx)
    if not check_daemon_running(client):
        sys.exit(1)

    result = call_mcp_api(client, "/mcp/servers", method="GET")
    if result is None:
        sys.exit(1)

    servers = result.get("servers", [])

    if json_format:
        click.echo(json.dumps(result, indent=2))
        return

    if not servers:
        click.echo("No MCP servers configured.")
        return

    connected = result.get('connected_count', 0)
    total = result.get('total_count', 0)
    click.echo(f"MCP Servers ({connected}/{total} connected):")
    for server in servers:
        status_icon = "●" if server.get("connected") else "○"
        state = server.get("state", "unknown")
        click.echo(f"  {status_icon} {server['name']} ({state})")


@mcp_proxy.command("list-tools")
@click.option("--server", "-s", help="Filter by server name")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def list_tools(ctx: click.Context, server: str | None, json_format: bool) -> None:
    """List tools from MCP servers."""
    client = get_daemon_client(ctx)
    if not check_daemon_running(client):
        sys.exit(1)

    endpoint = "/mcp/tools"
    if server:
        endpoint = f"/mcp/tools?server={server}"

    result = call_mcp_api(client, endpoint, method="GET")
    if result is None:
        sys.exit(1)

    if json_format:
        click.echo(json.dumps(result, indent=2))
        return

    tools_by_server = result.get("tools", {})
    if not tools_by_server:
        click.echo("No tools available.")
        return

    for server_name, tools in tools_by_server.items():
        click.echo(f"\n{server_name}:")
        if not tools:
            click.echo("  (no tools)")
            continue
        for tool in tools:
            name = tool.get("name", "unknown")
            brief = tool.get("brief", tool.get("description", ""))[:60]
            click.echo(f"  • {name}")
            if brief:
                click.echo(f"    {brief}")


@mcp_proxy.command("get-schema")
@click.argument("server_name")
@click.argument("tool_name")
@click.pass_context
def get_schema(ctx: click.Context, server_name: str, tool_name: str) -> None:
    """Get full schema for a specific tool.

    Examples:
        gobby mcp-proxy get-schema context7 get-library-docs
        gobby mcp-proxy get-schema supabase list_tables
    """
    client = get_daemon_client(ctx)
    if not check_daemon_running(client):
        sys.exit(1)

    result = call_mcp_api(
        client,
        "/mcp/tools/schema",
        method="POST",
        json_data={"server_name": server_name, "tool_name": tool_name},
    )
    if result is None:
        sys.exit(1)

    # Always output as JSON for schema (it's complex)
    click.echo(json.dumps(result, indent=2))


@mcp_proxy.command("call-tool")
@click.argument("server_name")
@click.argument("tool_name")
@click.option("--arg", "-a", "args", multiple=True, help="Tool argument in key=value format")
@click.option("--json-args", "-j", "json_args", help="Tool arguments as JSON string")
@click.option("--raw", is_flag=True, help="Output raw result without formatting")
@click.pass_context
def call_tool(
    ctx: click.Context,
    server_name: str,
    tool_name: str,
    args: tuple[str, ...],
    json_args: str | None,
    raw: bool,
) -> None:
    """Execute a tool on an MCP server.

    Examples:
        gobby mcp-proxy call-tool supabase list_tables
        gobby mcp-proxy call-tool context7 get-library-docs -a topic=react -a tokens=5000
        gobby mcp-proxy call-tool myserver mytool -j '{"key": "value"}'
    """
    client = get_daemon_client(ctx)
    if not check_daemon_running(client):
        sys.exit(1)

    # Parse arguments
    arguments: dict[str, Any] = {}

    if json_args:
        try:
            arguments = json.loads(json_args)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid JSON arguments: {e}", err=True)
            sys.exit(1)

    # Add key=value args (override JSON args)
    for arg in args:
        if "=" not in arg:
            click.echo(f"Error: Invalid argument format '{arg}'. Use key=value", err=True)
            sys.exit(1)
        key, value = arg.split("=", 1)
        # Try to parse value as JSON for proper typing
        try:
            arguments[key] = json.loads(value)
        except json.JSONDecodeError:
            arguments[key] = value

    result = call_mcp_api(
        client,
        "/mcp/tools/call",
        method="POST",
        json_data={
            "server_name": server_name,
            "tool_name": tool_name,
            "arguments": arguments,
        },
    )
    if result is None:
        sys.exit(1)

    if raw:
        click.echo(json.dumps(result, indent=2))
    else:
        # Format result nicely
        if result.get("success"):
            content = result.get("result", result)
            if isinstance(content, dict):
                click.echo(json.dumps(content, indent=2))
            else:
                click.echo(content)
        else:
            click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
            sys.exit(1)


@mcp_proxy.command("add-server")
@click.argument("name")
@click.option("--transport", "-t", required=True, type=click.Choice(["http", "stdio", "websocket"]))
@click.option("--url", "-u", help="Server URL (for http/websocket)")
@click.option("--command", "-c", help="Command to run (for stdio)")
@click.option("--args", "cmd_args", help="Command arguments as JSON array (for stdio)")
@click.option("--env", help="Environment variables as JSON object")
@click.option("--headers", help="HTTP headers as JSON object")
@click.option("--disabled", is_flag=True, help="Add server as disabled")
@click.pass_context
def add_server(
    ctx: click.Context,
    name: str,
    transport: str,
    url: str | None,
    command: str | None,
    cmd_args: str | None,
    env: str | None,
    headers: str | None,
    disabled: bool,
) -> None:
    """Add a new MCP server configuration.

    Examples:
        gobby mcp-proxy add-server my-http -t http -u https://api.example.com/mcp
        gobby mcp-proxy add-server my-stdio -t stdio -c npx --args '["mcp-server"]'
    """
    client = get_daemon_client(ctx)
    if not check_daemon_running(client):
        sys.exit(1)

    # Validate transport requirements
    if transport in ("http", "websocket") and not url:
        click.echo(f"Error: --url is required for {transport} transport", err=True)
        sys.exit(1)
    if transport == "stdio" and not command:
        click.echo("Error: --command is required for stdio transport", err=True)
        sys.exit(1)

    # Parse JSON options
    parsed_args = None
    parsed_env = None
    parsed_headers = None

    if cmd_args:
        try:
            parsed_args = json.loads(cmd_args)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid JSON for --args: {e}", err=True)
            sys.exit(1)

    if env:
        try:
            parsed_env = json.loads(env)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid JSON for --env: {e}", err=True)
            sys.exit(1)

    if headers:
        try:
            parsed_headers = json.loads(headers)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid JSON for --headers: {e}", err=True)
            sys.exit(1)

    result = call_mcp_api(
        client,
        "/mcp/servers",
        method="POST",
        json_data={
            "name": name,
            "transport": transport,
            "url": url,
            "command": command,
            "args": parsed_args,
            "env": parsed_env,
            "headers": parsed_headers,
            "enabled": not disabled,
        },
    )
    if result is None:
        sys.exit(1)

    if result.get("success"):
        click.echo(f"Added MCP server: {name}")
    else:
        click.echo(f"Error: {result.get('error', 'Failed to add server')}", err=True)
        sys.exit(1)


@mcp_proxy.command("remove-server")
@click.argument("name")
@click.confirmation_option(prompt="Are you sure you want to remove this server?")
@click.pass_context
def remove_server(ctx: click.Context, name: str) -> None:
    """Remove an MCP server configuration."""
    client = get_daemon_client(ctx)
    if not check_daemon_running(client):
        sys.exit(1)

    result = call_mcp_api(
        client,
        f"/mcp/servers/{name}",
        method="DELETE",
    )
    if result is None:
        sys.exit(1)

    if result.get("success"):
        click.echo(f"Removed MCP server: {name}")
    else:
        click.echo(f"Error: {result.get('error', 'Failed to remove server')}", err=True)
        sys.exit(1)


@mcp_proxy.command("recommend-tools")
@click.argument("task_description")
@click.option("--agent", "-a", "agent_id", help="Agent ID for filtered recommendations")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def recommend_tools(
    ctx: click.Context,
    task_description: str,
    agent_id: str | None,
    json_format: bool,
) -> None:
    """Get AI-powered tool recommendations for a task.

    Examples:
        gobby mcp-proxy recommend-tools "I need to query a database"
        gobby mcp-proxy recommend-tools "Search for documentation" --agent my-agent
    """
    client = get_daemon_client(ctx)
    if not check_daemon_running(client):
        sys.exit(1)

    result = call_mcp_api(
        client,
        "/mcp/tools/recommend",
        method="POST",
        json_data={
            "task_description": task_description,
            "agent_id": agent_id,
        },
    )
    if result is None:
        sys.exit(1)

    if json_format:
        click.echo(json.dumps(result, indent=2))
        return

    recommendations = result.get("recommendations", [])
    if not recommendations:
        click.echo("No tool recommendations found.")
        return

    click.echo("Recommended tools:")
    for rec in recommendations:
        server = rec.get("server", "unknown")
        tool = rec.get("tool", "unknown")
        reason = rec.get("reason", "")
        click.echo(f"  • {server}/{tool}")
        if reason:
            click.echo(f"    {reason}")


@mcp_proxy.command("status")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
@click.pass_context
def proxy_status(ctx: click.Context, json_format: bool) -> None:
    """Show MCP proxy status and health."""
    client = get_daemon_client(ctx)
    if not check_daemon_running(client):
        sys.exit(1)

    result = call_mcp_api(client, "/mcp/status", method="GET")
    if result is None:
        sys.exit(1)

    if json_format:
        click.echo(json.dumps(result, indent=2))
        return

    click.echo("MCP Proxy Status:")
    click.echo(f"  Servers: {result.get('total_servers', 0)}")
    click.echo(f"  Connected: {result.get('connected_servers', 0)}")
    click.echo(f"  Tools cached: {result.get('cached_tools', 0)}")

    health = result.get("server_health", {})
    if health:
        click.echo("\nServer Health:")
        for name, info in health.items():
            state = info.get("state", "unknown")
            health_status = info.get("health", "unknown")
            failures = info.get("failures", 0)
            icon = "●" if state == "connected" else "○"
            click.echo(f"  {icon} {name}: {state} ({health_status})", nl=False)
            if failures > 0:
                click.echo(f" - {failures} failures", nl=False)
            click.echo()
