"""CLI command building for agent spawning.

Provides functions to construct CLI commands for Claude, Gemini, and Codex
with proper flags for prompts, permissions, and session management.
"""

from __future__ import annotations


def build_cli_command(
    cli: str,
    prompt: str | None = None,
    session_id: str | None = None,
    auto_approve: bool = False,
    working_directory: str | None = None,
    mode: str = "terminal",
    sandbox_args: list[str] | None = None,
) -> list[str]:
    """
    Build the CLI command with proper prompt passing and permission flags.

    Each CLI has different syntax for passing prompts and handling permissions:

    Claude Code:
    - claude --session-id <uuid> --dangerously-skip-permissions [prompt]
    - Use --dangerously-skip-permissions for autonomous subagent operation

    Gemini CLI:
    - gemini -i "prompt" (interactive mode with initial prompt)
    - gemini --approval-mode yolo -i "prompt" (YOLO + interactive)
    - gemini "prompt" (one-shot non-interactive for headless)

    Codex CLI:
    - codex --full-auto -C <dir> [PROMPT]
    - Or: codex -c 'sandbox_permissions=["disk-full-read-access"]' -a never [PROMPT]

    Args:
        cli: CLI name (claude, gemini, codex)
        prompt: Optional prompt to pass
        session_id: Optional session ID (used by Claude CLI)
        auto_approve: If True, add flags to auto-approve actions/permissions
        working_directory: Optional working directory (used by Codex -C flag)
        mode: Execution mode - "terminal" (interactive) or "headless" (non-interactive)
        sandbox_args: Optional list of CLI args for sandbox configuration

    Returns:
        Command list for subprocess execution
    """
    command = [cli]

    if cli == "claude":
        # Claude CLI flags
        if session_id:
            command.extend(["--session-id", session_id])
        if auto_approve:
            # Skip all permission prompts for autonomous subagent operation
            command.append("--dangerously-skip-permissions")
        # For headless mode, use -p (print mode) for single-turn execution
        # For terminal mode, don't use -p to allow multi-turn interaction
        if prompt and mode != "terminal":
            command.append("-p")

    elif cli == "gemini":
        # Gemini CLI flags
        if auto_approve:
            command.extend(["--approval-mode", "yolo"])
        # For terminal mode, use -i (prompt-interactive) to execute prompt and stay interactive
        # For headless mode, use positional prompt for one-shot execution
        if prompt:
            if mode == "terminal":
                command.extend(["-i", prompt])
                # Add sandbox args before returning (prompt already added via -i flag)
                if sandbox_args:
                    command.extend(sandbox_args)
                return command  # Don't add prompt again as positional
            # else: fall through to add as positional for headless

    elif cli == "codex":
        # Codex CLI flags
        if auto_approve:
            # --full-auto: low-friction sandboxed automatic execution
            command.append("--full-auto")
        if working_directory:
            command.extend(["-C", working_directory])

    # Add sandbox args before prompt (prompt must be last)
    if sandbox_args:
        command.extend(sandbox_args)

    # All three CLIs accept prompt as positional argument (must come last)
    # For Gemini terminal mode, this is skipped (handled above with -i flag)
    if prompt:
        command.append(prompt)

    return command


def build_gemini_command_with_resume(
    gemini_external_id: str,
    prompt: str | None = None,
    auto_approve: bool = False,
    gobby_session_id: str | None = None,
) -> list[str]:
    """
    Build Gemini CLI command with session resume.

    Uses -r flag to resume a preflight-captured session, with session context
    injected into the initial prompt.

    Args:
        gemini_external_id: Gemini's session_id from preflight capture
        prompt: Optional user prompt
        auto_approve: If True, add --approval-mode yolo
        gobby_session_id: Gobby session ID to inject into context

    Returns:
        Command list for subprocess execution
    """
    command = ["gemini"]

    # Resume the preflight session
    command.extend(["-r", gemini_external_id])

    if auto_approve:
        command.extend(["--approval-mode", "yolo"])

    # Build prompt with session context
    if gobby_session_id:
        context_prefix = (
            f"Your Gobby session_id is: {gobby_session_id}\n"
            f"Use this when calling Gobby MCP tools.\n\n"
        )
        full_prompt = context_prefix + (prompt or "")
    else:
        full_prompt = prompt or ""

    # Use -i for interactive mode with initial prompt
    if full_prompt:
        command.extend(["-i", full_prompt])

    return command


def build_codex_command_with_resume(
    codex_external_id: str,
    prompt: str | None = None,
    auto_approve: bool = False,
    gobby_session_id: str | None = None,
    working_directory: str | None = None,
) -> list[str]:
    """
    Build Codex CLI command with session resume.

    Uses `codex resume {session_id}` to resume a preflight-captured session,
    with session context injected into the prompt.

    Args:
        codex_external_id: Codex's session_id from preflight capture
        prompt: Optional user prompt
        auto_approve: If True, add --full-auto flag
        gobby_session_id: Gobby session ID to inject into context
        working_directory: Optional working directory override

    Returns:
        Command list for subprocess execution
    """
    command = ["codex", "resume", codex_external_id]

    if auto_approve:
        command.append("--full-auto")

    if working_directory:
        command.extend(["-C", working_directory])

    # Build prompt with session context
    if gobby_session_id:
        context_prefix = (
            f"Your Gobby session_id is: {gobby_session_id}\n"
            f"Use this when calling Gobby MCP tools.\n\n"
        )
        full_prompt = context_prefix + (prompt or "")
    else:
        full_prompt = prompt or ""

    # Prompt is a positional argument after session_id
    if full_prompt:
        command.append(full_prompt)

    return command
