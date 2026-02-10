"""
Mem0 service installation and uninstallation.

Handles local Docker-based install and remote URL configuration.
"""

import logging
import shutil
import subprocess  # nosec B404 - subprocess needed for docker compose management
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Bundled compose file location (inside package)
_COMPOSE_SRC = Path(__file__).resolve().parents[2] / "data" / "docker-compose.mem0.yml"

DEFAULT_MEM0_URL = "http://localhost:8888"


def install_mem0(
    *,
    gobby_home: Path | None = None,
    remote_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Install mem0 services.

    Args:
        gobby_home: Gobby home directory (default: ~/.gobby)
        remote_url: If set, skip Docker and use remote mem0 instance
        api_key: Optional API key for mem0

    Returns:
        Dict with 'success' and details
    """
    home = gobby_home or Path("~/.gobby").expanduser()

    if remote_url:
        return _install_remote(home, remote_url, api_key)
    return _install_local(home, api_key)


def _install_local(home: Path, api_key: str | None) -> dict[str, Any]:
    """Install mem0 via local Docker Compose."""
    # Check Docker is available
    if not shutil.which("docker"):
        return {"success": False, "error": "Docker not found. Install Docker to use local mem0."}

    # Copy compose file
    svc_dir = home / "services" / "mem0"
    svc_dir.mkdir(parents=True, exist_ok=True)
    dest = svc_dir / "docker-compose.yml"
    shutil.copy2(_COMPOSE_SRC, dest)

    # Run docker compose up -d
    try:
        result = subprocess.run(  # nosec B603 B607 - hardcoded docker command
            ["docker", "compose", "-f", str(dest), "up", "-d"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return {
                "success": False,
                "error": f"Docker compose up failed: {result.stderr or result.stdout}",
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Docker compose up timed out after 120s"}

    # Wait for health check
    if not _wait_for_health(DEFAULT_MEM0_URL):
        return {
            "success": False,
            "error": "Health check failed: mem0 did not become healthy in time",
        }

    # Update daemon config
    _update_config(mem0_url=DEFAULT_MEM0_URL, mem0_api_key=api_key)

    return {
        "success": True,
        "mem0_url": DEFAULT_MEM0_URL,
        "compose_file": str(dest),
        "mode": "local",
    }


def _install_remote(home: Path, remote_url: str, api_key: str | None) -> dict[str, Any]:
    """Configure remote mem0 instance (no Docker)."""
    if not _check_remote_health(remote_url):
        return {
            "success": False,
            "error": f"Remote mem0 unreachable at {remote_url}",
        }

    _update_config(mem0_url=remote_url, mem0_api_key=api_key)

    return {
        "success": True,
        "mem0_url": remote_url,
        "mode": "remote",
    }


def uninstall_mem0(
    *,
    gobby_home: Path | None = None,
    remove_volumes: bool = False,
) -> dict[str, Any]:
    """Uninstall mem0 services.

    Args:
        gobby_home: Gobby home directory (default: ~/.gobby)
        remove_volumes: Also remove Docker volumes (data loss!)

    Returns:
        Dict with 'success' and details
    """
    home = gobby_home or Path("~/.gobby").expanduser()
    svc_dir = home / "services" / "mem0"
    compose_file = svc_dir / "docker-compose.yml"

    if not svc_dir.exists():
        _update_config(mem0_url=None, mem0_api_key=None)
        return {"success": True, "already_uninstalled": True, "message": "Mem0 not installed"}

    # Run docker compose down
    if compose_file.exists():
        cmd = ["docker", "compose", "-f", str(compose_file), "down"]
        if remove_volumes:
            cmd.append("-v")

        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=60)  # nosec B603 - hardcoded docker command
        except subprocess.TimeoutExpired:
            logger.warning("Docker compose down timed out")

    # Remove service directory
    shutil.rmtree(svc_dir, ignore_errors=True)

    # Reset config
    _update_config(mem0_url=None, mem0_api_key=None)

    return {"success": True, "removed": str(svc_dir), "volumes_removed": remove_volumes}


def _wait_for_health(url: str, retries: int = 30, interval: float = 2.0) -> bool:
    """Wait for mem0 to become healthy via HTTP check."""
    import time

    for _ in range(retries):
        try:
            resp = httpx.get(f"{url}/docs", timeout=5)
            if resp.status_code < 500:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(interval)
    return False


def _check_remote_health(url: str) -> bool:
    """Check if a remote mem0 URL is reachable."""
    try:
        resp = httpx.get(f"{url}/docs", timeout=10)
        return resp.status_code < 500
    except httpx.HTTPError:
        return False


def _update_config(
    mem0_url: str | None = None,
    mem0_api_key: str | None = None,
) -> None:
    """Update daemon config with mem0 settings."""
    try:
        from gobby.config.app import load_config, save_config

        config = load_config()
        config.memory.mem0_url = mem0_url
        config.memory.mem0_api_key = mem0_api_key
        save_config(config)
    except Exception as e:
        logger.warning(f"Failed to update config: {e}")
