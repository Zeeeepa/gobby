"""
Logging configuration module.

Contains logging-related Pydantic config models:
- LoggingSettings: Log levels, formats, file paths, rotation settings

Extracted from app.py using Strangler Fig pattern for code decomposition.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

__all__ = ["LoggingSettings"]


class LoggingSettings(BaseModel):
    """Logging configuration."""

    level: Literal["debug", "info", "warning", "error"] = Field(
        default="info",
        description="Log level",
    )
    format: Literal["text", "json"] = Field(
        default="text",
        description="Log format (text or json)",
    )

    # Log file paths
    client: str = Field(
        default="~/.gobby/logs/gobby.log",
        description="Daemon main log file path",
    )
    client_error: str = Field(
        default="~/.gobby/logs/gobby-error.log",
        description="Daemon error log file path",
    )
    hook_manager: str = Field(
        default="~/.gobby/logs/hook-manager.log",
        description="Claude Code hook manager log file path",
    )
    mcp_server: str = Field(
        default="~/.gobby/logs/mcp-server.log",
        description="MCP server log file path",
    )
    mcp_client: str = Field(
        default="~/.gobby/logs/mcp-client.log",
        description="MCP client connection log file path",
    )

    max_size_mb: int = Field(
        default=10,
        description="Maximum log file size in MB",
    )
    backup_count: int = Field(
        default=5,
        description="Number of backup log files to keep",
    )

    @field_validator("max_size_mb", "backup_count")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        """Validate value is positive."""
        if v <= 0:
            raise ValueError("Value must be positive")
        return v
