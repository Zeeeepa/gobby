"""Bootstrap configuration for pre-database settings.

These 5 settings are needed before the database is available:
database_path, daemon_port, bind_host, websocket_port, ui_port.

All other configuration is managed via the DB (config_store) + Pydantic defaults.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Default bootstrap file location
DEFAULT_BOOTSTRAP_PATH = "~/.gobby/bootstrap.yaml"


@dataclass(frozen=True)
class BootstrapConfig:
    """Minimal settings needed before the database is available."""

    database_path: str = "~/.gobby/gobby-hub.db"
    daemon_port: int = 60887
    bind_host: str = "localhost"
    websocket_port: int = 60888
    ui_port: int = 60889

    def to_config_dict(self) -> dict[str, Any]:
        """Convert to a dict suitable for DaemonConfig construction.

        Maps bootstrap fields into the nested structure DaemonConfig expects.
        """
        return {
            "database_path": self.database_path,
            "daemon_port": self.daemon_port,
            "bind_host": self.bind_host,
            "websocket": {"port": self.websocket_port},
            "ui": {"port": self.ui_port},
        }


def load_bootstrap(path: str | None = None) -> BootstrapConfig:
    """Load bootstrap config from YAML, falling back to defaults if missing.

    Args:
        path: Path to bootstrap.yaml. Defaults to ~/.gobby/bootstrap.yaml.
              Also accepts a path to the legacy config.yaml (ignored — defaults used).

    Returns:
        BootstrapConfig with values from file or defaults.
    """
    if path is None:
        path = DEFAULT_BOOTSTRAP_PATH

    bootstrap_path = Path(path).expanduser()

    # If caller passed a non-bootstrap path (e.g. legacy config.yaml path),
    # try bootstrap.yaml in the same directory first.
    if bootstrap_path.name != "bootstrap.yaml":
        candidate = bootstrap_path.parent / "bootstrap.yaml"
        if candidate.exists():
            bootstrap_path = candidate
        elif not bootstrap_path.exists():
            # Neither file exists — use defaults
            return BootstrapConfig()

    if not bootstrap_path.exists():
        return BootstrapConfig()

    try:
        with open(bootstrap_path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            return BootstrapConfig()

        return BootstrapConfig(
            database_path=str(data.get("database_path", BootstrapConfig.database_path)),
            daemon_port=int(data.get("daemon_port", BootstrapConfig.daemon_port)),
            bind_host=str(data.get("bind_host", BootstrapConfig.bind_host)),
            websocket_port=int(data.get("websocket_port", BootstrapConfig.websocket_port)),
            ui_port=int(data.get("ui_port", BootstrapConfig.ui_port)),
        )
    except Exception as e:
        logger.warning(f"Failed to load bootstrap config from {bootstrap_path}: {e}")
        return BootstrapConfig()
