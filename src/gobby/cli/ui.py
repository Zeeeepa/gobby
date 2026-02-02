"""
CLI commands for Gobby web UI development.
"""

import subprocess
import sys
from pathlib import Path

import click

# Path to web UI directory
WEB_UI_DIR = Path(__file__).parent.parent / "ui" / "web"


@click.group()
def ui() -> None:
    """Web UI development commands."""
    pass


@ui.command()
@click.option("--port", "-p", default=5173, help="Dev server port")
@click.option("--host", "-h", default="localhost", help="Dev server host")
def dev(port: int, host: str) -> None:
    """Start the web UI development server with hot-reload."""
    if not WEB_UI_DIR.exists():
        click.echo(f"Error: Web UI directory not found at {WEB_UI_DIR}", err=True)
        sys.exit(1)

    package_json = WEB_UI_DIR / "package.json"
    if not package_json.exists():
        click.echo(f"Error: package.json not found at {package_json}", err=True)
        sys.exit(1)

    node_modules = WEB_UI_DIR / "node_modules"
    if not node_modules.exists():
        click.echo("Installing dependencies...")
        result = subprocess.run(
            ["npm", "install"],
            cwd=WEB_UI_DIR,
            capture_output=False,
        )
        if result.returncode != 0:
            click.echo("Failed to install dependencies", err=True)
            sys.exit(1)

    click.echo(f"Starting dev server at http://{host}:{port}")
    click.echo("Press Ctrl+C to stop")
    click.echo()

    try:
        subprocess.run(
            ["npm", "run", "dev", "--", "--host", host, "--port", str(port)],
            cwd=WEB_UI_DIR,
            check=True,
        )
    except KeyboardInterrupt:
        click.echo("\nDev server stopped")
    except subprocess.CalledProcessError as e:
        click.echo(f"Dev server failed with code {e.returncode}", err=True)
        sys.exit(e.returncode)


@ui.command()
def build() -> None:
    """Build the web UI for production."""
    if not WEB_UI_DIR.exists():
        click.echo(f"Error: Web UI directory not found at {WEB_UI_DIR}", err=True)
        sys.exit(1)

    node_modules = WEB_UI_DIR / "node_modules"
    if not node_modules.exists():
        click.echo("Installing dependencies...")
        result = subprocess.run(
            ["npm", "install"],
            cwd=WEB_UI_DIR,
            capture_output=False,
        )
        if result.returncode != 0:
            click.echo("Failed to install dependencies", err=True)
            sys.exit(1)

    click.echo("Building web UI...")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=WEB_UI_DIR,
        capture_output=False,
    )

    if result.returncode == 0:
        dist_dir = WEB_UI_DIR / "dist"
        click.echo(f"Build complete: {dist_dir}")
    else:
        click.echo("Build failed", err=True)
        sys.exit(result.returncode)


@ui.command()
def install_deps() -> None:
    """Install web UI dependencies."""
    if not WEB_UI_DIR.exists():
        click.echo(f"Error: Web UI directory not found at {WEB_UI_DIR}", err=True)
        sys.exit(1)

    click.echo("Installing dependencies...")
    result = subprocess.run(
        ["npm", "install"],
        cwd=WEB_UI_DIR,
        capture_output=False,
    )

    if result.returncode == 0:
        click.echo("Dependencies installed")
    else:
        click.echo("Failed to install dependencies", err=True)
        sys.exit(result.returncode)
