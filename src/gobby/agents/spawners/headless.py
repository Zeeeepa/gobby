"""Headless spawner for agent execution with output capture."""

from __future__ import annotations

import asyncio
import os
import subprocess  # nosec B404 - subprocess needed for headless agent spawning
from pathlib import Path
from typing import TYPE_CHECKING

from gobby.agents.constants import get_terminal_env_vars
from gobby.agents.sandbox import SandboxConfig, compute_sandbox_paths, get_sandbox_resolver
from gobby.agents.spawners.base import HeadlessResult

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["HeadlessSpawner"]


# Import these from spawn.py to avoid duplication
def _get_spawn_utils() -> tuple[
    Callable[..., list[str]],
    Callable[[str, str], str],
    int,
]:
    """Lazy import to avoid circular dependencies."""
    from gobby.agents.spawn import (
        MAX_ENV_PROMPT_LENGTH,
        build_cli_command,
        create_prompt_file,
    )

    return build_cli_command, create_prompt_file, MAX_ENV_PROMPT_LENGTH


class HeadlessSpawner:
    """
    Spawner for headless mode with output capture.

    Runs the process without a visible terminal, capturing all output
    to a buffer that can be stored in the session transcript.
    """

    def spawn(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
    ) -> HeadlessResult:
        """
        Spawn a headless process with output capture.

        Args:
            command: Command to run
            cwd: Working directory
            env: Environment variables to set

        Returns:
            HeadlessResult with process handle for output capture
        """
        try:
            # Merge environment
            spawn_env = os.environ.copy()
            if env:
                spawn_env.update(env)

            # Spawn process with captured output
            # Use DEVNULL for stdin since headless mode uses -p flag (print mode)
            # which reads prompt from CLI args, not stdin. A pipe stdin would hang.
            process = subprocess.Popen(  # nosec B603 - command built from config
                command,
                cwd=cwd,
                env=spawn_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,  # Line buffered
            )

            return HeadlessResult(
                success=True,
                message=f"Spawned headless process with PID {process.pid}",
                pid=process.pid,
                process=process,
            )

        except Exception as e:
            return HeadlessResult(
                success=False,
                message=f"Failed to spawn headless process: {e}",
                error=str(e),
            )

    async def spawn_and_capture(
        self,
        command: list[str],
        cwd: str | Path,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> HeadlessResult:
        """
        Spawn a headless process and capture output asynchronously.

        Args:
            command: Command to run
            cwd: Working directory
            env: Environment variables to set
            timeout: Optional timeout in seconds
            on_output: Optional callback for each line of output

        Returns:
            HeadlessResult with captured output
        """
        result = self.spawn(command, cwd, env)
        if not result.success or result.process is None:
            return result

        try:
            # Read output asynchronously
            async def read_output() -> None:
                if result.process and result.process.stdout:
                    loop = asyncio.get_running_loop()
                    while True:
                        line = await loop.run_in_executor(None, result.process.stdout.readline)
                        if not line:
                            break
                        line = line.rstrip("\n")
                        result.output_buffer.append(line)
                        if on_output:
                            on_output(line)

            if timeout:
                await asyncio.wait_for(read_output(), timeout=timeout)
            else:
                await read_output()

            # Wait for process to complete without blocking the event loop
            if result.process:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, result.process.wait)

        except TimeoutError:
            if result.process:
                result.process.terminate()
                # Also wait for termination to complete (non-blocking)
                try:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, result.process.wait)
                except Exception:
                    pass  # nosec B110 - Best-effort process cleanup
            result.error = "Process timed out"

        except Exception as e:
            result.error = str(e)

        return result

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
    ) -> HeadlessResult:
        """
        Spawn a CLI agent in headless mode.

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
            HeadlessResult with process handle
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
            mode="headless",  # Non-interactive headless mode
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
