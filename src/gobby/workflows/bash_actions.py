from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.workflows.actions import ActionContext

logger = logging.getLogger(__name__)


async def handle_bash_run(context: ActionContext, **kwargs: Any) -> dict[str, Any] | None:
    """Handle the 'bash' workflow action.

    Args:
        context: Action execution context
        **kwargs: Action parameters
            command: Bash command to execute (can contain Jinja2 templates)
            background: Whether to run in background (default: False)
            capture_output: Whether to capture stdout/stderr (default: True, ignored if background=True)
            cwd: Working directory for command (optional)

    Returns:
        Dict with execution results (stdout, stderr, exit_code, or pid)
    """
    command_template = kwargs.get("command")
    if not command_template:
        logger.warning("Missing 'command' parameter for bash action")
        return {"error": "Missing 'command' parameter for bash action"}

    background = kwargs.get("background", False)
    capture_output = kwargs.get("capture_output", True)
    cwd = kwargs.get("cwd")

    # Prepare template context
    variables = context.state.variables if context.state else {}
    render_context = {
        "variables": variables,
        "session_id": context.session_id,
    }

    # If event_data is present (e.g. from hook), include it
    if context.event_data:
        render_context["event"] = context.event_data

    try:
        command = context.template_engine.render(command_template, render_context)
    except Exception as e:
        logger.error(f"Error rendering bash command template: {e}")
        return {"error": f"Template rendering failed: {str(e)}"}

    logger.info(f"Executing bash command: {command}")

    try:
        if background:
            # Run in background (don't wait)
            # Use shell=True to support pipes, redirects, etc.
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                stdin=asyncio.subprocess.DEVNULL,
                cwd=cwd,
            )

            return {"status": "started", "pid": proc.pid}
        else:
            # Run and wait for completion
            subprocess_kwargs: dict[str, Any] = {
                "cwd": cwd,
            }

            if capture_output:
                subprocess_kwargs["stdout"] = asyncio.subprocess.PIPE
                subprocess_kwargs["stderr"] = asyncio.subprocess.PIPE
            else:
                subprocess_kwargs["stdout"] = asyncio.subprocess.DEVNULL
                subprocess_kwargs["stderr"] = asyncio.subprocess.DEVNULL

            # Use shell=True
            proc = await asyncio.create_subprocess_shell(command, **subprocess_kwargs)

            if capture_output:
                stdout_bytes, stderr_bytes = await proc.communicate()
                stdout = stdout_bytes.decode("utf-8", errors="replace")
                stderr = stderr_bytes.decode("utf-8", errors="replace")
            else:
                await proc.wait()
                stdout = ""
                stderr = ""

            return {
                "stdout": stdout.strip(),
                "stderr": stderr.strip(),
                "exit_code": proc.returncode if proc.returncode is not None else 0,
            }

    except Exception as e:
        logger.error(f"Bash command execution failed: {e}", exc_info=True)
        return {"error": str(e), "exit_code": 1}