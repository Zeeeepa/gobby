"""
Neo4j service lifecycle utilities.

Provides status checks for the optional Neo4j Docker services
without starting or stopping anything.
"""

import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


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
    healthy = await is_neo4j_healthy(neo4j_url)

    return {
        "installed": installed,
        "healthy": healthy,
        "url": neo4j_url,
    }
