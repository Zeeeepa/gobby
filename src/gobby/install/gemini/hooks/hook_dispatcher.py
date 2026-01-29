#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx",
#     "pyyaml",
# ]
# ///
"""Hook Dispatcher - Routes Gemini CLI hooks to HookManager.

This is a thin wrapper script that receives hook calls from Gemini CLI
and routes them to the appropriate handler via HookManager.

Gemini CLI invokes hooks with JSON input on stdin and expects JSON output
on stdout. Exit codes: 0 = allow, 2 = deny.

Usage:
    hook_dispatcher.py --type SessionStart < input.json > output.json
    hook_dispatcher.py --type BeforeTool --debug < input.json > output.json

Exit Codes:
    0 - Success / Allow
    1 - General error (logged, continues)
    2 - Deny / Block
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Default daemon configuration
DEFAULT_DAEMON_PORT = 60887
DEFAULT_CONFIG_PATH = "~/.gobby/config.yaml"


def get_daemon_url() -> str:
    """Get the daemon HTTP URL from config file.

    Reads daemon_port from ~/.gobby/config.yaml if it exists,
    otherwise uses the default port 60887.

    Returns:
        Full daemon URL like http://localhost:60887
    """
    config_path = Path(DEFAULT_CONFIG_PATH).expanduser()

    if config_path.exists():
        try:
            import yaml

            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
            port = config.get("daemon_port", DEFAULT_DAEMON_PORT)
        except Exception:
            # If config read fails, use default
            port = DEFAULT_DAEMON_PORT
    else:
        port = DEFAULT_DAEMON_PORT

    return f"http://localhost:{port}"


def get_terminal_context() -> dict[str, str | int | bool | None]:
    """Capture terminal/process context for session correlation.

    Returns:
        Dict with terminal identifiers (values may be None if unavailable)
    """
    context: dict[str, str | int | bool | None] = {}

    # Parent process ID (shell or Gemini process)
    try:
        context["parent_pid"] = os.getppid()
    except Exception:
        context["parent_pid"] = None

    # TTY device name
    try:
        context["tty"] = os.ttyname(0)
    except Exception:
        context["tty"] = None

    # macOS Terminal.app session ID
    context["term_session_id"] = os.environ.get("TERM_SESSION_ID")

    # iTerm2 session ID
    context["iterm_session_id"] = os.environ.get("ITERM_SESSION_ID")

    # VS Code integrated terminal detection
    # VSCODE_IPC_HOOK_CLI is set when running in VS Code's integrated terminal
    # TERM_PROGRAM == "vscode" is also a reliable indicator
    vscode_ipc_hook = os.environ.get("VSCODE_IPC_HOOK_CLI")
    term_program = os.environ.get("TERM_PROGRAM")
    context["vscode_ipc_hook_cli"] = vscode_ipc_hook
    context["vscode_terminal_detected"] = bool(vscode_ipc_hook) or term_program == "vscode"

    # Tmux pane (if running in tmux)
    context["tmux_pane"] = os.environ.get("TMUX_PANE")

    # Kitty terminal window ID
    context["kitty_window_id"] = os.environ.get("KITTY_WINDOW_ID")

    # Alacritty IPC socket path (unique per instance)
    context["alacritty_socket"] = os.environ.get("ALACRITTY_SOCKET")

    # Generic terminal program identifier (set by many terminals)
    context["term_program"] = os.environ.get("TERM_PROGRAM")

    return context


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments with type and debug flags
    """
    parser = argparse.ArgumentParser(description="Gemini CLI Hook Dispatcher")
    parser.add_argument(
        "--type",
        required=True,
        help="Hook type (e.g., SessionStart, BeforeTool)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def check_daemon_running(timeout: float = 0.5) -> bool:
    """Check if gobby daemon is active and responding.

    Performs a quick health check to verify the HTTP server is running
    before processing hooks. This prevents hook execution when the daemon
    is stopped, avoiding long timeouts and confusing error messages.

    Args:
        timeout: Maximum time to wait for response in seconds (default: 0.5)

    Returns:
        True if daemon is running and responding, False otherwise
    """
    try:
        import httpx

        daemon_url = get_daemon_url()
        response = httpx.get(
            f"{daemon_url}/admin/status",
            timeout=timeout,
            follow_redirects=False,
        )
        return response.status_code == 200
    except Exception:
        # Any error (connection refused, timeout, etc.) means client is not running
        return False


def main() -> int:
    """Main dispatcher execution.

    Returns:
        Exit code (0=allow, 1=error, 2=deny)
    """
    try:
        # Parse arguments
        args = parse_arguments()
    except (argparse.ArgumentError, SystemExit):
        # Argument parsing failed - return empty dict and exit 1
        print(json.dumps({}))
        return 1

    hook_type = args.type  # PascalCase: SessionStart, BeforeTool, etc.
    debug_mode = args.debug

    # Check if gobby daemon is running before processing hooks
    if not check_daemon_running():
        # Critical hooks that manage session state MUST have daemon running
        # Per Gemini CLI docs: SessionEnd, Notification, PreCompress are async/non-blocking
        # Only SessionStart is critical for session initialization
        critical_hooks = {"SessionStart"}
        if hook_type in critical_hooks:
            # Block the hook - forces user to start daemon before critical lifecycle events
            print(
                f"Gobby daemon is not running. Start with 'gobby start' before continuing. "
                f"({hook_type} requires daemon for session state management)",
                file=sys.stderr,
            )
            return 2  # Exit 2 = block operation
        else:
            # Non-critical hooks can proceed without daemon
            print(
                json.dumps(
                    {"status": "daemon_not_running", "message": "gobby daemon is not running"}
                )
            )
            return 0  # Exit 0 (allow) - allow operation to continue

    # Setup logger for dispatcher (not HookManager)
    import logging

    logger = logging.getLogger("gobby.hooks.gemini.dispatcher")
    if debug_mode:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    try:
        # Read JSON input from stdin
        input_data = json.load(sys.stdin)

        # Inject terminal context for SessionStart hooks
        # This captures the terminal/process info for session correlation
        if hook_type == "SessionStart":
            input_data["terminal_context"] = get_terminal_context()
            # Note: gobby_context (parent_session_id, workflow, etc.) is no longer
            # injected from env vars. For spawned agents, the session is pre-created
            # with all linkage via preflight+resume pattern, so the daemon already
            # has the context when SessionStart fires.

        # Log what Gemini CLI sends us (for debugging hook data issues)
        # Extract common context fields for structured logging
        session_id = input_data.get("session_id")
        task_id = input_data.get("task_id")
        project_id = input_data.get("project_id")
        base_context = {
            "hook_type": hook_type,
            "session_id": session_id,
            "task_id": task_id,
            "project_id": project_id,
        }

        logger.info(
            "[%s] Received input keys: %s",
            hook_type,
            list(input_data.keys()),
            extra=base_context,
        )

        # Log hook-specific critical fields
        if hook_type == "SessionStart":
            logger.info(
                "[SessionStart] session_id=%s",
                session_id,
                extra=base_context,
            )
        elif hook_type == "SessionEnd":
            reason = input_data.get("reason")
            logger.info(
                "[SessionEnd] session_id=%s, reason=%s",
                session_id,
                reason,
                extra={**base_context, "reason": reason},
            )
        elif hook_type == "BeforeAgent":
            prompt = input_data.get("prompt", "")
            prompt_preview = prompt[:100] + "..." if len(prompt) > 100 else prompt
            logger.info(
                "[BeforeAgent] session_id=%s, prompt=%s",
                session_id,
                prompt_preview,
                extra={**base_context, "prompt_preview": prompt_preview},
            )
        elif hook_type == "BeforeTool":
            tool_name = input_data.get("tool_name") or input_data.get("function_name", "unknown")
            logger.info(
                "[BeforeTool] tool_name=%s, session_id=%s",
                tool_name,
                session_id,
                extra={**base_context, "tool_name": tool_name},
            )
        elif hook_type == "AfterTool":
            tool_name = input_data.get("tool_name") or input_data.get("function_name", "unknown")
            error = input_data.get("error")
            logger.info(
                "[AfterTool] tool_name=%s, session_id=%s",
                tool_name,
                session_id,
                extra={**base_context, "tool_name": tool_name, "error": error},
            )
        elif hook_type == "BeforeToolSelection":
            logger.info(
                "[BeforeToolSelection] session_id=%s",
                session_id,
                extra=base_context,
            )
        elif hook_type == "BeforeModel":
            model = input_data.get("model", "unknown")
            logger.info(
                "[BeforeModel] session_id=%s, model=%s",
                session_id,
                model,
                extra={**base_context, "model": model},
            )
        elif hook_type == "AfterModel":
            logger.info(
                "[AfterModel] session_id=%s",
                session_id,
                extra=base_context,
            )
        elif hook_type == "PreCompress":
            logger.info(
                "[PreCompress] session_id=%s",
                session_id,
                extra=base_context,
            )
        elif hook_type == "Notification":
            message = input_data.get("message")
            logger.info(
                "[Notification] session_id=%s, message=%s",
                session_id,
                message,
                extra={**base_context, "notification_message": message},
            )
        elif hook_type == "AfterAgent":
            logger.info(
                "[AfterAgent] session_id=%s",
                session_id,
                extra=base_context,
            )

        if debug_mode:
            logger.debug(f"Input data: {input_data}")

    except json.JSONDecodeError as e:
        # Invalid JSON input - return empty dict and exit 1
        if debug_mode:
            logger.error(f"JSON decode error: {e}")
        print(json.dumps({}))
        return 1

    # Call daemon HTTP endpoint
    import httpx

    daemon_url = get_daemon_url()
    try:
        response = httpx.post(
            f"{daemon_url}/hooks/execute",
            json={
                "hook_type": hook_type,  # PascalCase for Gemini
                "input_data": input_data,
                "source": "gemini",  # Required: identifies CLI source
            },
            timeout=30.0,  # Generous timeout for hook processing
        )

        if response.status_code == 200:
            # Success - daemon returns result directly
            result = response.json()

            if debug_mode:
                logger.debug(f"Output data: {result}")

            # Determine exit code based on decision
            decision = result.get("decision", "allow")

            # Check for block/deny decision - return exit code 2 to signal blocking
            # For blocking, output goes to STDERR (Gemini reads stderr on exit 2)
            if result.get("continue") is False or decision in ("deny", "block"):
                # Output just the reason, not the full JSON
                reason = result.get("stopReason") or result.get("reason") or "Blocked by hook"
                print(reason, file=sys.stderr)
                return 2

            # Only print output if there's something meaningful to show
            if result and result != {}:
                print(json.dumps(result))

            return 0
        else:
            # HTTP error from daemon
            error_detail = response.text
            logger.error(
                f"Daemon returned error: status={response.status_code}, detail={error_detail}"
            )
            print(json.dumps({"status": "error", "message": f"Daemon error: {error_detail}"}))
            return 1

    except httpx.ConnectError:
        # Daemon not reachable
        logger.error("Failed to connect to daemon (unreachable)")
        print(json.dumps({"status": "error", "message": "Daemon unreachable"}))
        return 1

    except httpx.TimeoutException:
        # Hook processing took too long
        logger.error(f"Hook execution timeout: {hook_type}")
        print(json.dumps({"status": "error", "message": "Hook execution timeout"}))
        return 1

    except Exception as e:
        # General error - log and return 1
        logger.error(f"Hook execution failed: {e}", exc_info=True)
        print(json.dumps({"status": "error", "message": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
