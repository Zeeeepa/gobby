"""
Watchdog configuration module.

Contains configuration for the daemon watchdog process that monitors
daemon health and restarts it if unresponsive.
"""

from pydantic import BaseModel, Field

__all__ = ["WatchdogConfig"]


class WatchdogConfig(BaseModel):
    """Configuration for the daemon watchdog process."""

    enabled: bool = Field(
        default=True,
        description="Enable watchdog by default when starting daemon",
    )
    health_check_interval: float = Field(
        default=10.0,
        ge=1.0,
        le=300.0,
        description="Seconds between health checks",
    )
    failure_threshold: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Consecutive failures before triggering restart",
    )
    restart_cooldown: float = Field(
        default=30.0,
        ge=5.0,
        le=300.0,
        description="Minimum seconds between restart attempts",
    )
    max_restarts_per_hour: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Circuit breaker: max restarts allowed per hour",
    )
