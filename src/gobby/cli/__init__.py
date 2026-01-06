"""
Gobby CLI entry point.
"""

import click

from gobby.config.app import load_config

from .agents import agents
from .daemon import restart, start, status, stop
from .extensions import hooks, plugins, webhooks
from .init import init
from .install import install, uninstall
from .mcp import mcp_server
from .mcp_proxy import mcp_proxy
from .memory import memory
from .sessions import sessions
from .skills import skills
from .tasks import tasks
from .workflows import workflow


@click.group()
@click.option(
    "--config",
    type=click.Path(exists=True),
    help="Path to custom configuration file",
)
@click.pass_context
def cli(ctx: click.Context, config: str | None) -> None:
    """Gobby - Local-first daemon for AI coding assistants."""
    # Store config in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config)


# Register commands
cli.add_command(start)
cli.add_command(stop)
cli.add_command(restart)
cli.add_command(status)
cli.add_command(mcp_server)
cli.add_command(init)
cli.add_command(install)
cli.add_command(uninstall)
cli.add_command(tasks)
cli.add_command(memory)
cli.add_command(skills)
cli.add_command(sessions)
cli.add_command(agents)
cli.add_command(mcp_proxy)
cli.add_command(workflow)
cli.add_command(hooks)
cli.add_command(plugins)
cli.add_command(webhooks)
