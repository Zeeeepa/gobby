"""
Sandbox Configuration Models.

This module defines configuration models for sandbox/isolation settings
when spawning agents. The actual sandboxing is handled by each CLI's
built-in sandbox implementation - Gobby just passes the right flags.
"""

from abc import ABC, abstractmethod
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


class SandboxResolver(ABC):
    """
    Abstract base class for CLI-specific sandbox configuration resolution.

    Each CLI (Claude Code, Codex, Gemini) has different mechanisms for
    enabling sandboxing. Subclasses implement the resolve() method to
    convert a SandboxConfig and ResolvedSandboxPaths into CLI-specific
    arguments and environment variables.
    """

    @property
    @abstractmethod
    def cli_name(self) -> str:
        """Return the name of the CLI this resolver handles."""
        ...

    @abstractmethod
    def resolve(
        self, config: SandboxConfig, paths: ResolvedSandboxPaths
    ) -> tuple[list[str], dict[str, str]]:
        """
        Resolve sandbox configuration to CLI-specific args and env vars.

        Args:
            config: The sandbox configuration from the agent definition.
            paths: The resolved paths for the sandbox environment.

        Returns:
            A tuple of (cli_args, env_vars) where:
            - cli_args: List of command-line arguments to pass to the CLI
            - env_vars: Dict of environment variables to set
        """
        ...


class ClaudeSandboxResolver(SandboxResolver):
    """
    Sandbox resolver for Claude Code CLI.

    Claude Code uses --settings with a JSON object containing sandbox config.
    See: https://code.claude.com/docs/en/sandboxing
    """

    @property
    def cli_name(self) -> str:
        return "claude"

    def resolve(
        self, config: SandboxConfig, paths: ResolvedSandboxPaths
    ) -> tuple[list[str], dict[str, str]]:
        if not config.enabled:
            return ([], {})

        import json

        # Build settings JSON for Claude Code
        settings = {
            "sandbox": {
                "enabled": True,
                "autoAllowBashIfSandboxed": True,
                # Network config - allow localhost for Gobby daemon
                "network": {
                    "allowLocalBinding": True,
                },
            }
        }

        return (["--settings", json.dumps(settings)], {})


class CodexSandboxResolver(SandboxResolver):
    """
    Sandbox resolver for OpenAI Codex CLI.

    Codex uses --sandbox flag with mode (read-only, workspace-write, danger-full-access)
    and --add-dir for additional writable paths.
    See: https://developers.openai.com/codex/cli/reference/
    """

    @property
    def cli_name(self) -> str:
        return "codex"

    def resolve(
        self, config: SandboxConfig, paths: ResolvedSandboxPaths
    ) -> tuple[list[str], dict[str, str]]:
        if not config.enabled:
            return ([], {})

        args: list[str] = []

        # Sandbox mode
        if config.mode == "restrictive":
            args.extend(["--sandbox", "read-only"])
        else:
            args.extend(["--sandbox", "workspace-write"])

        # Add extra write paths (workspace is implicit in workspace-write mode)
        for path in paths.write_paths:
            if path != paths.workspace_path:
                args.extend(["--add-dir", path])

        return (args, {})


class GeminiSandboxResolver(SandboxResolver):
    """
    Sandbox resolver for Google Gemini CLI.

    Gemini uses -s/--sandbox flag and SEATBELT_PROFILE env var for macOS.
    See: https://geminicli.com/docs/cli/sandbox/
    """

    @property
    def cli_name(self) -> str:
        return "gemini"

    def resolve(
        self, config: SandboxConfig, paths: ResolvedSandboxPaths
    ) -> tuple[list[str], dict[str, str]]:
        if not config.enabled:
            return ([], {})

        args = ["-s"]
        env: dict[str, str] = {}

        # Set SEATBELT_PROFILE based on mode (macOS)
        if config.mode == "restrictive":
            env["SEATBELT_PROFILE"] = "restrictive-closed"
        else:
            env["SEATBELT_PROFILE"] = "permissive-open"

        return (args, env)


def get_sandbox_resolver(cli: str) -> SandboxResolver:
    """
    Factory function to get the appropriate sandbox resolver for a CLI.

    Args:
        cli: The CLI name ("claude", "codex", or "gemini")

    Returns:
        The appropriate SandboxResolver subclass instance.

    Raises:
        ValueError: If the CLI is not recognized.
    """
    resolvers: dict[str, type[SandboxResolver]] = {
        "claude": ClaudeSandboxResolver,
        "codex": CodexSandboxResolver,
        "gemini": GeminiSandboxResolver,
    }

    if cli not in resolvers:
        raise ValueError(f"Unknown CLI: {cli}. Must be one of: {list(resolvers.keys())}")

    return resolvers[cli]()


def compute_sandbox_paths(
    config: SandboxConfig,
    workspace_path: str,
    gobby_daemon_port: int = 60887,
) -> ResolvedSandboxPaths:
    """
    Compute resolved sandbox paths from a SandboxConfig.

    This helper function combines the workspace path with extra paths
    from the config to produce the final ResolvedSandboxPaths.

    Args:
        config: The sandbox configuration.
        workspace_path: The primary workspace/worktree path.
        gobby_daemon_port: Port where Gobby daemon is running.

    Returns:
        ResolvedSandboxPaths with all paths computed.
    """
    # Start with workspace in write paths
    write_paths = [workspace_path]

    # Add extra write paths
    for path in config.extra_write_paths:
        if path not in write_paths:
            write_paths.append(path)

    # Collect read paths
    read_paths = list(config.extra_read_paths)

    return ResolvedSandboxPaths(
        workspace_path=workspace_path,
        gobby_daemon_port=gobby_daemon_port,
        read_paths=read_paths,
        write_paths=write_paths,
        allow_external_network=config.allow_network,
    )
