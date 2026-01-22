"""
Conductor management CLI commands.

Commands for managing the conductor loop:
- start: Start the conductor loop
- stop: Stop the conductor loop
- restart: Restart the conductor loop
- status: Show conductor status
- chat: Send a message to the conductor
"""

import json

import click
import httpx


def get_daemon_url() -> str:
    """Get daemon URL from config."""
    from gobby.config.app import load_config

    config = load_config()
    return f"http://localhost:{config.daemon_port}"


@click.group()
def conductor() -> None:
    """Manage the conductor orchestration loop."""
    pass


@conductor.command("start")
@click.option("--interval", "-i", type=int, default=30, help="Check interval in seconds")
@click.option("--autonomous", "-a", is_flag=True, help="Enable autonomous agent spawning")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def start_conductor(interval: int, autonomous: bool, json_format: bool) -> None:
    """Start the conductor loop.

    Examples:

        gobby conductor start

        gobby conductor start --interval 60

        gobby conductor start --autonomous
    """
    daemon_url = get_daemon_url()

    try:
        response = httpx.post(
            f"{daemon_url}/conductor/start",
            json={"interval": interval, "autonomous": autonomous},
            timeout=10.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        click.echo("Error: Cannot connect to Gobby daemon. Is it running?", err=True)
        return
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: HTTP {e.response.status_code}: {e.response.text}", err=True)
        return
    except ValueError as e:
        click.echo(f"Error: Invalid JSON response: {e}", err=True)
        return
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return

    if json_format:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    if result.get("success"):
        click.echo("Conductor started")
        click.echo(f"  Interval: {interval}s")
        if autonomous:
            click.echo("  Autonomous mode: enabled")
    else:
        click.echo(f"Failed to start conductor: {result.get('error')}", err=True)


@conductor.command("stop")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def stop_conductor(json_format: bool) -> None:
    """Stop the conductor loop.

    Examples:

        gobby conductor stop
    """
    daemon_url = get_daemon_url()

    try:
        response = httpx.post(
            f"{daemon_url}/conductor/stop",
            json={},
            timeout=10.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        click.echo("Error: Cannot connect to Gobby daemon. Is it running?", err=True)
        return
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: HTTP {e.response.status_code}: {e.response.text}", err=True)
        return
    except ValueError as e:
        click.echo(f"Error: Invalid JSON response: {e}", err=True)
        return
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return

    if json_format:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    if result.get("success"):
        click.echo("Conductor stopped")
    else:
        click.echo(f"Failed to stop conductor: {result.get('error')}", err=True)


@conductor.command("restart")
@click.option("--interval", "-i", type=int, default=30, help="Check interval in seconds")
@click.option("--autonomous", "-a", is_flag=True, help="Enable autonomous agent spawning")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def restart_conductor(interval: int, autonomous: bool, json_format: bool) -> None:
    """Restart the conductor loop.

    Examples:

        gobby conductor restart

        gobby conductor restart --interval 60
    """
    daemon_url = get_daemon_url()

    try:
        response = httpx.post(
            f"{daemon_url}/conductor/restart",
            json={"interval": interval, "autonomous": autonomous},
            timeout=10.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        click.echo("Error: Cannot connect to Gobby daemon. Is it running?", err=True)
        return
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: HTTP {e.response.status_code}: {e.response.text}", err=True)
        return
    except ValueError as e:
        click.echo(f"Error: Invalid JSON response: {e}", err=True)
        return
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return

    if json_format:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    if result.get("success"):
        click.echo("Conductor restarted")
    else:
        click.echo(f"Failed to restart conductor: {result.get('error')}", err=True)


@conductor.command("status")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def status_conductor(json_format: bool) -> None:
    """Show conductor status.

    Examples:

        gobby conductor status

        gobby conductor status --json
    """
    daemon_url = get_daemon_url()

    try:
        response = httpx.get(
            f"{daemon_url}/conductor/status",
            timeout=10.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        click.echo("Error: Cannot connect to Gobby daemon. Is it running?", err=True)
        return
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: HTTP {e.response.status_code}: {e.response.text}", err=True)
        return
    except ValueError as e:
        click.echo(f"Error: Invalid JSON response: {e}", err=True)
        return
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return

    if json_format:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    running = result.get("running", False)
    if running:
        click.echo("Conductor: running")
        click.echo(f"  Interval: {result.get('interval', 'unknown')}s")
        click.echo(f"  Autonomous: {result.get('autonomous', False)}")
        if result.get("last_tick"):
            click.echo(f"  Last tick: {result['last_tick']}")
    else:
        click.echo("Conductor: not running")


@conductor.command("chat")
@click.argument("message")
@click.option("--json", "json_format", is_flag=True, help="Output as JSON")
def chat_conductor(message: str, json_format: bool) -> None:
    """Send a message to the conductor.

    The conductor can process commands like status checks, task queries,
    or trigger manual actions.

    Examples:

        gobby conductor chat "Check all tasks"

        gobby conductor chat "spawn agent for task-123"

        gobby conductor chat --json "status check"
    """
    daemon_url = get_daemon_url()

    try:
        response = httpx.post(
            f"{daemon_url}/conductor/chat",
            json={"message": message},
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        click.echo("Error: Cannot connect to Gobby daemon. Is it running?", err=True)
        return
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: HTTP {e.response.status_code}: {e.response.text}", err=True)
        return
    except ValueError as e:
        click.echo(f"Error: Invalid JSON response: {e}", err=True)
        return
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return

    if json_format:
        click.echo(json.dumps(result, indent=2, default=str))
        return

    if result.get("success"):
        click.echo(result.get("response", "OK"))
    else:
        click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
