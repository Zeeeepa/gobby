"""
Mem0 service lifecycle utilities.

Provides status checks for the optional mem0 Docker services
without starting or stopping anything.
"""

import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def is_mem0_installed(*, gobby_home: Path | None = None) -> bool:
    """Check if mem0 services are installed locally.

    Checks for the presence of ~/.gobby/services/mem0/ directory.
    """
    home = gobby_home or Path("~/.gobby").expanduser()
    return (home / "services" / "mem0").exists()


async def is_mem0_healthy(url: str | None) -> bool:
    """Check if a mem0 instance is reachable and healthy.

    Sends a GET request to the /docs endpoint with a short timeout.
    Returns False if URL is None, unreachable, or returns 5xx.
    """
    if not url:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{url}/docs", timeout=5)
            if resp.status_code >= 500:
                logger.warning(f"mem0 health check failed: {url} returned {resp.status_code}")
                return False
            return True
    except httpx.HTTPError as e:
        logger.warning(f"mem0 health check failed: {url} unreachable: {e}")
        return False


async def get_mem0_status(
    *,
    gobby_home: Path | None = None,
    mem0_url: str | None = None,
) -> dict[str, Any]:
    """Get comprehensive mem0 status.

    Returns dict with:
        installed: bool - service directory exists
        healthy: bool - API is reachable
        url: str | None - configured URL
    """
    installed = is_mem0_installed(gobby_home=gobby_home)
    healthy = await is_mem0_healthy(mem0_url)

    return {
        "installed": installed,
        "healthy": healthy,
        "url": mem0_url,
    }
