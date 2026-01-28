"""Embedded PTY spawner for agent execution with UI attachment."""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import TYPE_CHECKING

from gobby.agents.constants import get_terminal_env_vars
from gobby.agents.sandbox import SandboxConfig, compute_sandbox_paths, get_sandbox_resolver
from gobby.agents.spawners.base import EmbeddedPTYResult

# pty is only available on Unix-like systems
try:
    import pty
except ImportError:
    pty = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["EmbeddedSpawner"]

# Maximum prompt length to pass via environment variable
# Longer prompts will be written to a temp file
MAX_ENV_PROMPT_LENGTH = 4096


# Import these from spawn.py to avoid duplication
def _get_spawn_utils() -> tuple[
    Callable[..., list[str]],
    Callable[[str, str], str],
    int,
]:
    """Lazy import to avoid circular dependencies."""
    from gobby.agents.spawn import (
        MAX_ENV_PROMPT_LENGTH as _MAX_ENV_PROMPT_LENGTH,
    )
    from gobby.agents.spawn import (
        build_cli_command,
        create_prompt_file,
    )

    return build_cli_command, create_prompt_file, _MAX_ENV_PROMPT_LENGTH


class EmbeddedSpawner:
    """
    Spawner for embedded mode with PTY.

    Creates a pseudo-terminal that can be attached to a UI component.
    The master file descriptor can be used to read/write to the process.
    """

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
    ) -> EmbeddedPTYResult:
        """
        Spawn a process with a PTY for embedded mode.

        Args:
            command: Command to run
            cwd: Working directory
            env: Environment variables to set

        Returns:
            EmbeddedPTYResult with PTY file descriptors and process info
        """
        if not command or len(command) == 0:
            return EmbeddedPTYResult(
                success=False,
                message="Cannot spawn process with empty command",
                error="Empty command list provided",
            )

        if platform.system() == "Windows" or pty is None:
            return EmbeddedPTYResult(
                success=False,
                message="Embedded PTY mode not supported on Windows",
                error="Windows does not support Unix PTY",
            )

        master_fd: int | None = None
        slave_fd: int | None = None

        try:
            # Create pseudo-terminal
            master_fd, slave_fd = pty.openpty()

            # Merge environment
            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            # Fork and exec
            pid = os.fork()

            if pid == 0:
                # Child process
                try:
                    # Close master fd in child - not needed
                    os.close(master_fd)

                    # Create new session
                    os.setsid()

                    # Set slave as controlling terminal
                    os.dup2(slave_fd, 0)  # stdin
                    os.dup2(slave_fd, 1)  # stdout
                    os.dup2(slave_fd, 2)  # stderr

                    # Close original slave fd after duplication
                    os.close(slave_fd)

                    # Change to working directory
                    os.chdir(cwd)

                    # Execute command
                    os.execvpe(command[0], command, spawn_env)  # nosec B606 - config
                except Exception:
                    # Ensure we exit on any failure
                    os._exit(1)

                # Should never reach here, but just in case
                os._exit(1)
            else:
                # Parent process - close slave fd (child has its own copy)
                os.close(slave_fd)
                slave_fd = None  # Mark as closed

                return EmbeddedPTYResult(
                    success=True,
                    message=f"Spawned embedded PTY with PID {pid}",
                    master_fd=master_fd,
                    slave_fd=None,  # Closed in parent
                    pid=pid,
                )

        except Exception as e:
            # Clean up file descriptors on any error
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
            if slave_fd is not None:
                try:
                    os.close(slave_fd)
                except OSError:
                    pass
            return EmbeddedPTYResult(
                success=False,
                message=f"Failed to spawn embedded PTY: {e}",
                error=str(e),
            )

    def spawn_agent(
        self,
        cli: str,
        cwd: str | Path,
        session_id: str,
        parent_session_id: str,
        agent_run_id: str,
        project_id: str,
        workflow_name: str | None = None,
        agent_depth: int = 1,
        max_agent_depth: int = 3,
        prompt: str | None = None,
        sandbox_config: SandboxConfig | None = None,
    ) -> EmbeddedPTYResult:
        """
        Spawn a CLI agent with embedded PTY.

        Args:
            cli: CLI to run
            cwd: Working directory
            session_id: Pre-created child session ID
            parent_session_id: Parent session ID
            agent_run_id: Agent run record ID
            project_id: Project ID
            workflow_name: Optional workflow to activate
            agent_depth: Current nesting depth
            max_agent_depth: Maximum allowed depth
            prompt: Optional initial prompt
            sandbox_config: Optional sandbox configuration

        Returns:
            EmbeddedPTYResult with PTY info
        """
        build_cli_command, _create_prompt_file, max_env_prompt_length = _get_spawn_utils()

        # Resolve sandbox configuration if enabled
        sandbox_args: list[str] | None = None
        sandbox_env: dict[str, str] = {}

        if sandbox_config and sandbox_config.enabled:
            # Compute sandbox paths based on cwd (workspace)
            resolved_paths = compute_sandbox_paths(sandbox_config, str(cwd))
            # Get CLI-specific resolver and generate args/env
            resolver = get_sandbox_resolver(cli)
            sandbox_args, sandbox_env = resolver.resolve(sandbox_config, resolved_paths)

        # Build command with prompt as CLI argument and auto-approve for autonomous work
        command = build_cli_command(
            cli,
            prompt=prompt,
            session_id=session_id,
            auto_approve=True,  # Subagents need to work autonomously
            working_directory=str(cwd) if cli == "codex" else None,
            sandbox_args=sandbox_args,
        )

        # Handle prompt for environment variables (backup for hooks/context)
        prompt_env: str | None = None
        prompt_file: str | None = None

        if prompt:
            if len(prompt) <= max_env_prompt_length:
                prompt_env = prompt
            else:
                # Write to temp file with secure permissions
                prompt_file = _create_prompt_file(prompt, session_id)

        env = get_terminal_env_vars(
            session_id=session_id,
            parent_session_id=parent_session_id,
            agent_run_id=agent_run_id,
            project_id=project_id,
            workflow_name=workflow_name,
            agent_depth=agent_depth,
            max_agent_depth=max_agent_depth,
            prompt=prompt_env,
            prompt_file=prompt_file,
        )

        # Merge sandbox environment variables if present
        if sandbox_env:
            env.update(sandbox_env)

        return self.spawn(command, cwd, env)
