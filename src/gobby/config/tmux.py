"""Configuration for the tmux agent spawning module."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TmuxConfig(BaseModel):
    """Configuration for tmux-based agent spawning.

    Controls how Gobby creates and manages tmux sessions for agents.
    All sessions use ``-L <socket_name>`` to isolate from the user's
    personal tmux server.
    """

    enabled: bool = Field(
        default=True,
        description="Enable tmux as first-class agent spawning backend.",
    )
    command: str = Field(
        default="tmux",
        description="Path or name of the tmux binary.",
    )
    socket_name: str = Field(
        default="gobby",
        description="Isolated tmux socket name (passed as -L <socket_name>).",
    )
    config_file: str | None = Field(
        default=None,
        description="Optional tmux config file (passed as -f <path>).",
    )
    session_prefix: str = Field(
        default="gobby",
        description="Prefix for auto-generated session names.",
    )
    history_limit: int = Field(
        default=10000,
        ge=100,
        description="Scrollback buffer size for spawned sessions.",
    )
