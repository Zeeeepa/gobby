"""Gobby Daemon Runner.

GobbyRunner is the main entry point for the daemon. Initialization and
lifecycle logic are extracted into runner_init.py and runner_lifecycle.py
to keep this module focused on the public API.

Related modules:
- runner_init.py — component wiring, dependency injection, service setup
- runner_lifecycle.py — event loop, startup sequence, shutdown sequence
- runner_broadcasting.py — WebSocket event broadcasting
- runner_maintenance.py — background maintenance loops, signal handling
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Strip Claude Code session marker so SDK subprocess calls don't fail with
# "cannot be launched inside another Claude Code session" when the daemon
# was started/restarted from within a Claude Code session.
os.environ.pop("CLAUDECODE", None)

# Suppress litellm's never-awaited coroutine warnings (upstream bug in LoggingWorker)
import warnings

warnings.filterwarnings("ignore", message="coroutine.*async_success_handler.*was never awaited")

logger = logging.getLogger(__name__)


class GobbyRunner:
    """Runner for Gobby daemon."""

    def __init__(self, config_path: Path | None = None, verbose: bool = False):
        from gobby.runner_init import (
            init_orchestration,
            init_servers,
            init_services,
            init_storage_and_config,
        )

        init_storage_and_config(self, config_path, verbose)
        init_services(self)
        init_orchestration(self)
        init_servers(self)

    async def run(self) -> None:
        from gobby.runner_lifecycle import run_daemon

        await run_daemon(self)


async def run_gobby(config_path: Path | None = None, verbose: bool = False) -> None:
    runner = GobbyRunner(config_path=config_path, verbose=verbose)
    await runner.run()


def _healthy_daemon_running(port: int, host: str = "localhost") -> bool:
    """Quick check whether a healthy Gobby daemon is already listening."""
    import urllib.parse
    import urllib.request

    # Normalize wildcard addresses to localhost for health check
    if host in ("0.0.0.0", "::", ""):
        host = "localhost"
    elif ":" in host and not host.startswith("["):
        host = f"[{host}]"

    try:
        url = f"http://{host}:{port}/api/admin/health"
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:  # nosec B310
            return bool(resp.status == 200)
    except Exception:
        return False


def main(config_path: Path | None = None, verbose: bool = False) -> None:
    # Fast guard: if a healthy daemon is already serving on our port, exit
    # cleanly so launchd (KeepAlive.SuccessfulExit=false) won't respawn us.
    from gobby.config.bootstrap import load_bootstrap

    bootstrap = load_bootstrap(str(config_path) if config_path else None)
    if _healthy_daemon_running(bootstrap.daemon_port, bootstrap.bind_host):
        print(
            f"Gobby daemon already healthy on port {bootstrap.daemon_port}, exiting.",
            file=sys.stderr,
        )
        sys.exit(0)

    try:
        asyncio.run(run_gobby(config_path=config_path, verbose=verbose))
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Gobby daemon")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--config", type=Path, help="Path to config file")

    args = parser.parse_args()
    main(config_path=args.config, verbose=args.verbose)
