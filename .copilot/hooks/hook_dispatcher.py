#!/usr/bin/env python3
"""Hook Dispatcher - Routes GitHub Copilot CLI hooks to HookManager.

This is a thin wrapper script that receives hook calls from Copilot CLI
and routes them to the appropriate handler via HookManager.

Usage:
    hook_dispatcher.py --type sessionStart < input.json > output.json
    hook_dispatcher.py --type preToolUse --debug < input.json > output.json

Exit Codes:
    0 - Success
    1 - General error (logged, continues)
    2 - Block action (Copilot interprets as deny)
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
    """Get the daemon HTTP URL from config file."""
    config_path = Path(DEFAULT_CONFIG_PATH).expanduser()

    if config_path.exists():
        try:
            import yaml

            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
            port = config.get("daemon_port", DEFAULT_DAEMON_PORT)
        except Exception:
            port = DEFAULT_DAEMON_PORT
    else:
        port = DEFAULT_DAEMON_PORT

    return f"http://localhost:{port}"


def get_terminal_context() -> dict[str, str | int | None]:
    """Capture terminal/process context for session correlation."""
    context: dict[str, str | int | None] = {}

    try:
        context["parent_pid"] = os.getppid()
    except Exception:
        context["parent_pid"] = None

    try:
        context["tty"] = os.ttyname(0)
    except Exception:
        context["tty"] = None

    context["term_session_id"] = os.environ.get("TERM_SESSION_ID")
    context["iterm_session_id"] = os.environ.get("ITERM_SESSION_ID")
    context["vscode_terminal_id"] = os.environ.get("VSCODE_GIT_ASKPASS_NODE")
    context["tmux_pane"] = os.environ.get("TMUX_PANE")
    context["kitty_window_id"] = os.environ.get("KITTY_WINDOW_ID")
    context["alacritty_socket"] = os.environ.get("ALACRITTY_SOCKET")
    context["term_program"] = os.environ.get("TERM_PROGRAM")

    return context


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Copilot CLI Hook Dispatcher")
    parser.add_argument(
        "--type",
        required=True,
        help="Hook type (e.g., sessionStart, preToolUse)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def check_daemon_running(timeout: float = 0.5) -> bool:
    """Check if gobby daemon is active and responding."""
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
        return False


def main() -> int:
    """Main dispatcher execution."""
    try:
        args = parse_arguments()
    except (argparse.ArgumentError, SystemExit):
        print(json.dumps({}))
        return 2

    hook_type = args.type
    debug_mode = args.debug

    # Check if daemon is running
    if not check_daemon_running():
        critical_hooks = {"sessionStart", "sessionEnd"}
        if hook_type in critical_hooks:
            print(
                f"Gobby daemon is not running. Start with 'gobby start' before continuing. "
                f"({hook_type} requires daemon for session state management)",
                file=sys.stderr,
            )
            return 2
        else:
            print(
                json.dumps(
                    {"status": "daemon_not_running", "message": "gobby daemon is not running"}
                )
            )
            return 0

    import logging

    logger = logging.getLogger("gobby.hooks.dispatcher.copilot")
    if debug_mode:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING, handlers=[])

    try:
        input_data = json.load(sys.stdin)

        if hook_type == "sessionStart":
            input_data["terminal_context"] = get_terminal_context()

        logger.info(f"[{hook_type}] Received input keys: {list(input_data.keys())}")

        if debug_mode:
            logger.debug(f"Input data: {input_data}")

    except json.JSONDecodeError as e:
        if debug_mode:
            logger.error(f"JSON decode error: {e}")
        print(json.dumps({}))
        return 2

    import httpx

    daemon_url = get_daemon_url()
    try:
        response = httpx.post(
            f"{daemon_url}/hooks/execute",
            json={
                "hook_type": hook_type,
                "input_data": input_data,
                "source": "copilot",
            },
            timeout=90.0,
        )

        if response.status_code == 200:
            result = response.json()

            if debug_mode:
                logger.debug(f"Output data: {result}")

            # Check for block decision
            if result.get("continue") is False or result.get("permissionDecision") == "deny":
                reason = result.get("reason") or "Blocked by hook"
                print(reason, file=sys.stderr)
                return 2

            if result and result != {}:
                print(json.dumps(result))

            return 0
        else:
            error_detail = response.text
            logger.error(
                f"Daemon returned error: status={response.status_code}, detail={error_detail}"
            )
            print(json.dumps({"status": "error", "message": f"Daemon error: {error_detail}"}))
            return 1

    except Exception as e:
        logger.error(f"Hook execution failed: {e}", exc_info=True)
        print(json.dumps({"status": "error", "message": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
