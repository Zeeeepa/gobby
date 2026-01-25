"""TUI command for launching the Gobby dashboard."""

import click


@click.command()
@click.option(
    "--port",
    "-p",
    default=60334,
    help="Daemon HTTP port",
    show_default=True,
)
@click.option(
    "--ws-port",
    "-w",
    default=60335,
    help="Daemon WebSocket port",
    show_default=True,
)
def ui(port: int, ws_port: int) -> None:
    """Launch the Gobby TUI dashboard.

    The TUI provides a terminal-based interface for monitoring and managing
    Gobby sessions, tasks, agents, and more.

    Requires the Gobby daemon to be running (gobby start).
    """
    from gobby.tui.app import run_tui

    daemon_url = f"http://localhost:{port}"
    ws_url = f"ws://localhost:{ws_port}"

    run_tui(daemon_url=daemon_url, ws_url=ws_url)
