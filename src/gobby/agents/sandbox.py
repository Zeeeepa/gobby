"""
Sandbox Configuration Models.

This module defines configuration models for sandbox/isolation settings
when spawning agents. The actual sandboxing is handled by each CLI's
built-in sandbox implementation - Gobby just passes the right flags.
"""

from typing import Literal

from pydantic import BaseModel, Field


class SandboxConfig(BaseModel):
    """
    Configuration for sandbox/isolation when spawning agents.

    This is opt-in - by default sandboxing is disabled to preserve
    existing behavior. When enabled, the appropriate CLI flags are
    passed to enable the CLI's built-in sandbox.

    Attributes:
        enabled: Whether to enable sandboxing. Default False.
        mode: Sandbox strictness level.
            - "permissive": Allow more operations (easier debugging)
            - "restrictive": Stricter isolation (more secure)
        allow_network: Whether to allow network access (except localhost:60887
            which is always allowed for Gobby daemon communication).
        extra_read_paths: Additional paths to allow read access.
        extra_write_paths: Additional paths to allow write access
            (worktree paths are always allowed).
    """

    enabled: bool = False
    mode: Literal["permissive", "restrictive"] = "permissive"
    allow_network: bool = True
    extra_read_paths: list[str] = Field(default_factory=list)
    extra_write_paths: list[str] = Field(default_factory=list)


class ResolvedSandboxPaths(BaseModel):
    """
    Resolved paths and settings for sandbox execution.

    This is the computed result after resolving a SandboxConfig against
    the actual workspace and daemon configuration. It contains the concrete
    paths and settings that will be passed to CLI sandbox flags.

    Attributes:
        workspace_path: The primary workspace/worktree path for the agent.
        gobby_daemon_port: Port where Gobby daemon is running (for network allowlist).
        read_paths: All paths the sandbox should allow read access to.
        write_paths: All paths the sandbox should allow write access to.
        allow_external_network: Whether to allow network access beyond localhost.
    """

    workspace_path: str
    gobby_daemon_port: int = 60887
    read_paths: list[str]
    write_paths: list[str]
    allow_external_network: bool
