"""
Service lifecycle utilities for Qdrant and Neo4j.

Provides status checks for Docker-based services
without starting or stopping anything.
"""

import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Qdrant
# ---------------------------------------------------------------------------


def is_qdrant_installed(*, gobby_home: Path | None = None) -> bool:
    """Check if Qdrant service is installed.

    Checks for the unified Docker Compose file and qdrant storage directory.
    """
    home = gobby_home or Path("~/.gobby").expanduser()
    compose = home / "services" / "docker-compose.yml"
    qdrant_dir = home / "services" / "qdrant"
    return compose.exists() and qdrant_dir.exists()


async def is_qdrant_healthy(url: str | None) -> bool:
    """Check if a Qdrant instance is reachable and healthy.

    Sends a GET request to /healthz with a short timeout.
    Returns False if URL is None or unreachable.
    """
    if not url:
        return False
    healthz_url = f"{url.rstrip('/')}/healthz"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(healthz_url, timeout=5)
            if resp.status_code == 200:
                return True
            logger.warning(f"Qdrant health check failed: {healthz_url} returned {resp.status_code}")
            return False
    except httpx.HTTPError as e:
        logger.warning(f"Qdrant health check failed: {healthz_url} unreachable: {e}")
        return False


async def get_qdrant_status(
    *,
    gobby_home: Path | None = None,
    qdrant_url: str | None = None,
) -> dict[str, Any]:
    """Get comprehensive Qdrant status.

    Returns dict with:
        installed: bool - service files exist
        healthy: bool - API is reachable
        url: str | None - configured URL
    """
    installed = is_qdrant_installed(gobby_home=gobby_home)
    healthy = await is_qdrant_healthy(qdrant_url) if installed else False

    return {
        "installed": installed,
        "healthy": healthy,
        "url": qdrant_url,
    }


# ---------------------------------------------------------------------------
# Neo4j
# ---------------------------------------------------------------------------


def is_neo4j_installed(*, gobby_home: Path | None = None) -> bool:
    """Check if Neo4j services are installed locally.

    Checks for the presence of ~/.gobby/services/neo4j/ directory.
    """
    home = gobby_home or Path("~/.gobby").expanduser()
    return (home / "services" / "neo4j").exists()


async def is_neo4j_healthy(url: str | None) -> bool:
    """Check if a Neo4j instance is reachable and healthy.

    Sends a GET request to the Neo4j HTTP endpoint with a short timeout.
    Returns False if URL is None, unreachable, or returns 5xx.
    """
    if not url:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5)
            if resp.status_code >= 500:
                logger.warning(f"Neo4j health check failed: {url} returned {resp.status_code}")
                return False
            return True
    except httpx.HTTPError as e:
        logger.warning(f"Neo4j health check failed: {url} unreachable: {e}")
        return False


async def get_neo4j_status(
    *,
    gobby_home: Path | None = None,
    neo4j_url: str | None = None,
) -> dict[str, Any]:
    """Get comprehensive Neo4j status.

    Returns dict with:
        installed: bool - service directory exists
        healthy: bool - API is reachable
        url: str | None - configured URL
    """
    installed = is_neo4j_installed(gobby_home=gobby_home)
    healthy = await is_neo4j_healthy(neo4j_url) if installed else False

    return {
        "installed": installed,
        "healthy": healthy,
        "url": neo4j_url,
    }
