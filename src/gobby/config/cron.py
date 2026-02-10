"""Configuration for the Gobby cron scheduler."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class CronConfig(BaseModel):
    """Configuration for the cron scheduler system."""

    enabled: bool = Field(
        default=True,
        description="Enable the cron scheduler",
    )
    check_interval_seconds: int = Field(
        default=30,
        description="How often to check for due jobs (seconds)",
    )
    max_concurrent_jobs: int = Field(
        default=5,
        description="Maximum number of concurrently running cron jobs",
    )
    cleanup_after_days: int = Field(
        default=30,
        description="Delete cron run history older than this many days",
    )
    backoff_delays: list[int] = Field(
        default=[30, 60, 300, 900, 3600],
        description="Exponential backoff delays in seconds for consecutive failures",
    )

    @field_validator("check_interval_seconds")
    @classmethod
    def validate_check_interval(cls, v: int) -> int:
        if v < 10:
            raise ValueError("check_interval_seconds must be at least 10")
        return v

    @field_validator("max_concurrent_jobs")
    @classmethod
    def validate_max_concurrent(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_concurrent_jobs must be at least 1")
        return v
