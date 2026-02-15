"""
Neo4j service installation and uninstallation.

Handles local Docker-based Neo4j setup for knowledge graph features.
"""

import asyncio
import logging
import shutil
import subprocess  # nosec B404 - subprocess needed for docker compose management
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Bundled file locations (inside package)
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_COMPOSE_SRC = _DATA_DIR / "docker-compose.neo4j.yml"

DEFAULT_NEO4J_HTTP_URL = "http://localhost:8474"
DEFAULT_NEO4J_BOLT_URL = "bolt://localhost:8687"
DEFAULT_NEO4J_AUTH = "neo4j:gobbyneo4j"


def install_neo4j(
    *,
    gobby_home: Path | None = None,
) -> dict[str, Any]:
    """Install Neo4j via local Docker Compose.

    Args:
        gobby_home: Gobby home directory (default: ~/.gobby)

    Returns:
        Dict with 'success' and details
    """
    home = gobby_home or Path("~/.gobby").expanduser()

    # Check Docker is available
    if not shutil.which("docker"):
        return {"success": False, "error": "Docker not found. Install Docker to use Neo4j."}

    # Copy compose file
    svc_dir = home / "services" / "neo4j"
    svc_dir.mkdir(parents=True, exist_ok=True)
    dest = svc_dir / "docker-compose.yml"
    shutil.copy2(_COMPOSE_SRC, dest)

    # Run docker compose up -d
    try:
        result = subprocess.run(  # nosec B603 B607 - hardcoded docker command
            ["docker", "compose", "-f", str(dest), "up", "-d", "--remove-orphans"],
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
    except (OSError, subprocess.SubprocessError) as e:
        return {"success": False, "error": f"Docker compose execution failed: {e}"}

    # Wait for health check
    if not _wait_for_health(DEFAULT_NEO4J_HTTP_URL):
        return {
            "success": False,
            "error": "Health check failed: Neo4j did not become healthy in time",
        }

    # Update daemon config
    _update_config(neo4j_url=DEFAULT_NEO4J_HTTP_URL, neo4j_auth=DEFAULT_NEO4J_AUTH)

    return {
        "success": True,
        "neo4j_url": DEFAULT_NEO4J_HTTP_URL,
        "bolt_url": DEFAULT_NEO4J_BOLT_URL,
        "compose_file": str(dest),
        "mode": "local",
    }


def uninstall_neo4j(
    *,
    gobby_home: Path | None = None,
    remove_volumes: bool = False,
) -> dict[str, Any]:
    """Uninstall Neo4j services.

    Args:
        gobby_home: Gobby home directory (default: ~/.gobby)
        remove_volumes: Also remove Docker volumes (data loss!)

    Returns:
        Dict with 'success' and details
    """
    home = gobby_home or Path("~/.gobby").expanduser()
    svc_dir = home / "services" / "neo4j"
    compose_file = svc_dir / "docker-compose.yml"

    if not svc_dir.exists():
        _update_config(neo4j_url=None, neo4j_auth=None)
        return {"success": True, "already_uninstalled": True, "message": "Neo4j not installed"}

    # Run docker compose down
    if compose_file.exists():
        cmd = ["docker", "compose", "-f", str(compose_file), "down"]
        if remove_volumes:
            cmd.append("-v")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)  # nosec B603 - hardcoded docker command
            if result.returncode != 0:
                logger.warning(f"Docker compose down failed: {result.stderr or result.stdout}")
        except subprocess.TimeoutExpired:
            logger.warning("Docker compose down timed out")

    # Remove service directory
    shutil.rmtree(svc_dir, ignore_errors=True)

    # Reset config
    _update_config(neo4j_url=None, neo4j_auth=None)

    return {"success": True, "removed": str(svc_dir), "volumes_removed": remove_volumes}


def _wait_for_health(url: str, retries: int = 30, interval: float = 2.0) -> bool:
    """Synchronous wrapper for health check."""
    return asyncio.run(_wait_for_health_async(url, retries, interval))


async def _wait_for_health_async(url: str, retries: int = 30, interval: float = 2.0) -> bool:
    """Wait for Neo4j to become healthy via async HTTP check."""

    async with httpx.AsyncClient() as client:
        for _ in range(retries):
            try:
                resp = await client.get(url, timeout=5)
                if 200 <= resp.status_code < 300:
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(interval)
    return False


def _update_config(
    neo4j_url: str | None = None,
    neo4j_auth: str | None = None,
) -> None:
    """Update daemon config with Neo4j settings."""
    try:
        from gobby.config.app import load_config, save_config

        config = load_config()
        config.memory.neo4j_url = neo4j_url
        config.memory.neo4j_auth = neo4j_auth
        save_config(config)
    except (ImportError, OSError, ValueError) as e:
        logger.warning(f"Failed to update config: {e}")
