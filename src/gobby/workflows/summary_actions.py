"""Summary generation workflow actions.

Extracted from actions.py as part of strangler fig decomposition.
These functions handle session summary generation, title synthesis, and handoff creation.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import aiofiles

from gobby.sessions.analyzer import HandoffContext, TranscriptAnalyzer
from gobby.workflows.git_utils import (
    get_file_changes,
    get_git_diff_summary,
    get_git_status,
    get_recent_git_commits,
)

if TYPE_CHECKING:
    from gobby.workflows.actions import ActionContext
    from gobby.workflows.templates import TemplateRenderer

logger = logging.getLogger(__name__)


def _get_result_truncation_limit(content_str: str) -> int:
    """Return truncation limit based on content type.

    Errors/test output get 1000 chars for visibility. Default: 200 chars.
    """
    error_indicators = [
        "Error",
        "error",
        "ERROR",
        "Failed",
        "failed",
        "Traceback",
        "Exception",
        "FAIL",
        "AssertionError",
    ]
    if any(ind in content_str[:500] for ind in error_indicators):
        return 1000
    test_indicators = ["pytest", "PASSED", "FAILED", "test_", "npm test"]
    if any(ind in content_str[:500] for ind in test_indicators):
        return 1000
    return 200


def format_turns_for_llm(turns: list[dict[str, Any]]) -> str:
    """Format transcript turns for LLM analysis.

    Handles both Claude Code format (nested message.role/content) and
    Gemini CLI format (flat type/role/content).

    Args:
        turns: List of transcript turn dicts

    Returns:
        Formatted string with turn summaries
    """
    formatted: list[str] = []
    for i, turn in enumerate(turns):
        # Detect format: Gemini CLI uses "type" field, Claude uses nested "message"
        event_type = turn.get("type")

        if event_type:
            # Gemini CLI format: flat structure with type field
            role, content = _format_gemini_turn(turn, event_type)
            if role is None:
                continue  # Skip non-displayable events
        else:
            # Claude Code format: nested message structure
            role, content = _format_claude_turn(turn)

        formatted.append(f"[Turn {i + 1} - {role}]: {content}")

    return "\n\n".join(formatted)


def _format_gemini_turn(turn: dict[str, Any], event_type: str) -> tuple[str | None, str]:
    """Format a Gemini CLI turn.

    Returns:
        Tuple of (role, formatted_content) or (None, "") if should skip
    """
    if event_type == "message":
        role = turn.get("role", "unknown")
        if role == "model":
            role = "assistant"
        content = turn.get("content", "")
        if isinstance(content, list):
            content = " ".join(str(part) for part in content)
        return role, str(content)

    elif event_type == "tool_use":
        tool_name = turn.get("tool_name") or turn.get("function_name", "unknown")
        params = turn.get("parameters") or turn.get("args", {})
        param_preview = str(params)[:100] if params else ""
        return "assistant", f"[Tool: {tool_name}] {param_preview}"

    elif event_type == "tool_result":
        tool_name = turn.get("tool_name", "")
        output = turn.get("output") or turn.get("result", "")
        output_str = str(output)
        limit = _get_result_truncation_limit(output_str)
        preview = output_str[:limit]
        suffix = "..." if len(output_str) > limit else ""
        return "tool", f"[Result{' from ' + tool_name if tool_name else ''}]: {preview}{suffix}"

    elif event_type in ("init", "result"):
        # Skip initialization and final result events
        return None, ""

    else:
        # Unknown type, try to extract something
        content = turn.get("content", turn.get("message", ""))
        return "unknown", str(content)[:200]


def _format_claude_turn(turn: dict[str, Any]) -> tuple[str, str]:
    """Format a Claude Code turn with nested message structure."""
    message = turn.get("message", {})
    role = message.get("role", "unknown")
    content = message.get("content", "")

    # Assistant messages have content as array of blocks
    if isinstance(content, list):
        text_parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "thinking":
                    text_parts.append(f"[Thinking: {block.get('thinking', '')}]")
                elif block.get("type") == "tool_use":
                    text_parts.append(f"[Tool: {block.get('name', 'unknown')}]")
                elif block.get("type") == "tool_result":
                    result_content = block.get("content", "")
                    # Extract text from list of content blocks if needed
                    if isinstance(result_content, list):
                        extracted = []
                        for item in result_content:
                            if isinstance(item, dict):
                                extracted.append(item.get("text", "") or item.get("content", ""))
                            else:
                                extracted.append(str(item))
                        result_content = " ".join(extracted)
                    content_str = str(result_content)
                    limit = _get_result_truncation_limit(content_str)
                    preview = content_str[:limit]
                    suffix = "..." if len(content_str) > limit else ""
                    text_parts.append(f"[Result: {preview}{suffix}]")
        content = " ".join(text_parts)

    return role, str(content)


def _format_structured_context(ctx: HandoffContext) -> str:
    """Format HandoffContext fields as concise text for LLM consumption.

    Args:
        ctx: Structured context extracted from transcript analysis

    Returns:
        Formatted text block with anchoring data (files, commits, decisions)
    """
    sections: list[str] = []

    if ctx.active_gobby_task:
        task = ctx.active_gobby_task
        sections.append(
            f"Active Task: {task.get('title', 'Untitled')} "
            f"(#{task.get('id', '?')}, status: {task.get('status', 'unknown')})"
        )

    if ctx.task_progress:
        progress_lines = [
            f"  - {p['action']}: {p['title']} ({p['id']})" for p in ctx.task_progress[-15:]
        ]
        sections.append("Task Progress:\n" + "\n".join(progress_lines))

    if ctx.initial_goal:
        sections.append(f"Original Goal: {ctx.initial_goal[:500]}")

    if ctx.files_modified:
        sections.append("Files Modified:\n" + "\n".join(f"  - {f}" for f in ctx.files_modified))

    if ctx.git_commits:
        commit_lines = [
            f"  - {c.get('hash', '')[:7]} {c.get('message', '')}" for c in ctx.git_commits[:10]
        ]
        sections.append("Recent Commits:\n" + "\n".join(commit_lines))

    if ctx.recent_activity:
        sections.append(
            "Recent Activity:\n" + "\n".join(f"  - {a}" for a in ctx.recent_activity[-10:])
        )

    if ctx.key_decisions:
        sections.append("Key Decisions:\n" + "\n".join(f"  - {d}" for d in ctx.key_decisions))

    return "\n\n".join(sections) if sections else ""


async def _write_summary_file(
    session_id: str,
    content: str,
    output_path: str | None = None,
    session_manager: Any = None,
) -> str | None:
    """Write summary to file in session_summaries directory.

    Args:
        session_id: Internal session ID
        content: Summary markdown content
        output_path: Override directory for summary files
        session_manager: Session manager to look up external_id

    Returns:
        Path to written file, or None on failure
    """
    external_id: str | None = None
    summary_dir: Path | None = None
    try:
        summary_dir = Path(output_path or "~/.gobby/session_summaries").expanduser()
        summary_dir.mkdir(parents=True, exist_ok=True)

        # Use external_id in filename for failback reader compatibility
        if session_manager:
            session = session_manager.get(session_id)
            if session:
                external_id = getattr(session, "external_id", None)

        file_id = external_id or session_id
        timestamp = int(time.time())
        summary_file = summary_dir / f"session_{timestamp}_{file_id}.md"

        async with aiofiles.open(summary_file, "w", encoding="utf-8") as f:
            await f.write(content)

        logger.info(
            "Session summary written",
            extra={
                "session_id": session_id,
                "external_id": external_id,
                "summary_file": str(summary_file),
                "output_dir": str(summary_dir),
            },
        )
        return str(summary_file)
    except Exception as e:
        logger.error(
            f"Failed to write summary file: {e}",
            exc_info=True,
            extra={
                "session_id": session_id,
                "external_id": external_id,
                "output_dir": str(summary_dir) if summary_dir is not None else None,
            },
        )
        return None


async def _rename_tmux_window(session: Any, title: str) -> None:
    """Rename the tmux window for a session after title synthesis.

    For user sessions (agent_depth 0), renames on the default tmux server.
    For spawned agents, renames on Gobby's isolated ``-L gobby`` socket.
    Failures are logged but never propagated.
    """
    import asyncio

    tc = getattr(session, "terminal_context", None)
    if not tc:
        return
    pane = tc.get("tmux_pane")
    if not pane:
        return

    agent_depth = getattr(session, "agent_depth", 0) or 0

    try:
        if agent_depth > 0:
            # Spawned agent — rename on Gobby's isolated socket
            from gobby.agents.tmux import get_tmux_session_manager

            mgr = get_tmux_session_manager()
            await mgr.rename_window(pane, title)
        else:
            # User session — rename on the default tmux server.
            # Chain: enable set-titles (propagates to terminal emulator),
            # rename the window, then disable automatic-rename so tmux
            # doesn't overwrite our title on the next command.
            proc = await asyncio.create_subprocess_exec(
                "tmux",
                "set-option",
                "-g",
                "set-titles",
                "on",
                ";",
                "rename-window",
                "-t",
                pane,
                title,
                ";",
                "set-option",
                "-w",
                "-t",
                pane,
                "automatic-rename",
                "off",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode != 0:
                logger.debug(
                    "tmux rename-window failed for pane %s: %s",
                    pane,
                    (stderr or b"").decode().strip(),
                )
    except Exception as e:
        logger.debug(f"_rename_tmux_window: {e}")


async def synthesize_title(
    session_manager: Any,
    session_id: str,
    llm_service: Any,
    transcript_processor: Any,
    template_engine: TemplateRenderer,
    template: str | None = None,
    prompt: str | None = None,
) -> dict[str, Any] | None:
    """Synthesize and set a session title.

    Args:
        session_manager: The session manager instance
        session_id: Current session ID
        llm_service: LLM service instance
        transcript_processor: Transcript processor instance
        template_engine: Template engine for rendering
        template: Optional prompt template
        prompt: Optional user prompt to generate title from (preferred over transcript)

    Returns:
        Dict with title_synthesized or error
    """
    if not llm_service:
        return {"error": "Missing LLM service"}

    current_session = session_manager.get(session_id)
    if not current_session:
        return {"error": "Session not found"}

    try:
        # If prompt provided directly, use it (preferred path)
        if prompt:
            llm_prompt = (
                "Create a short title (3-5 words) for this coding session based on "
                "the user's first message. Output ONLY the title, no quotes or explanation.\n\n"
                f"User message: {prompt}"
            )
        else:
            # Fall back to reading transcript
            transcript_path = getattr(current_session, "jsonl_path", None)
            if not transcript_path:
                return {"error": "No transcript path and no prompt provided"}

            turns = []
            path = Path(transcript_path)
            if path.exists():
                async with aiofiles.open(path, encoding="utf-8") as f:
                    i = 0
                    async for line in f:
                        if i >= 20:
                            break
                        if line.strip():
                            turns.append(json.loads(line))
                            i += 1

            if not turns:
                return {"error": "Empty transcript"}

            formatted_turns = format_turns_for_llm(turns)

            if not template:
                template = (
                    "Create a short, concise title (3-5 words) for this coding session "
                    "based on the transcript.\n\nTranscript:\n{{ transcript }}"
                )

            llm_prompt = template_engine.render(template, {"transcript": formatted_turns})

        provider = llm_service.get_default_provider()
        title = await provider.generate_text(llm_prompt)

        # Clean title (remove quotes, etc)
        title = title.strip().strip('"').strip("'")

        session_manager.update_title(session_id, title)

        # Rename tmux window to match synthesized title
        await _rename_tmux_window(current_session, title)

        return {"title_synthesized": title}

    except Exception as e:
        logger.error(f"synthesize_title: Failed: {e}")
        return {"error": str(e)}


async def generate_summary(
    session_manager: Any,
    session_id: str,
    llm_service: Any,
    transcript_processor: Any,
    template: str | None = None,
    previous_summary: str | None = None,
    mode: Literal["clear", "compact"] = "clear",
    write_file: bool = False,
    output_path: str | None = None,
) -> dict[str, Any] | None:
    """Generate a session summary using LLM and store it in the session record.

    Args:
        session_manager: The session manager instance
        session_id: Current session ID
        llm_service: LLM service instance
        transcript_processor: Transcript processor instance
        template: Optional prompt template
        previous_summary: Previous summary_markdown for cumulative compression (compact mode)
        mode: "clear" or "compact" - passed to LLM context to control summarization density

    Returns:
        Dict with summary_generated and summary_length, or error

    Raises:
        ValueError: If mode is not "clear" or "compact"
    """
    # Validate mode parameter
    valid_modes = {"clear", "compact"}
    if mode not in valid_modes:
        raise ValueError(f"Invalid mode '{mode}'. Must be one of: {', '.join(sorted(valid_modes))}")

    if not llm_service or not transcript_processor:
        logger.warning("generate_summary: Missing LLM service or transcript processor")
        return {"error": "Missing services"}

    current_session = session_manager.get(session_id)
    if not current_session:
        return {"error": "Session not found"}

    transcript_path = getattr(current_session, "jsonl_path", None)
    if not transcript_path:
        logger.warning(f"generate_summary: No transcript path for session {session_id}")
        return {"error": "No transcript path"}

    if not template:
        template = (
            "Summarize this session, focusing on what was accomplished, "
            "key decisions, and what is left to do.\n\n"
            "Transcript:\n{transcript_summary}"
        )

    # 1. Process Transcript
    try:
        transcript_file = Path(transcript_path)
        if not transcript_file.exists():
            logger.warning(f"Transcript file not found: {transcript_path}")
            return {"error": "Transcript not found"}

        turns = []
        async with aiofiles.open(transcript_file, encoding="utf-8") as f:
            async for line in f:
                if line.strip():
                    turns.append(json.loads(line))

        # Turn extraction is deliberately mode-agnostic: we always extract the most
        # recent turns since the last /clear and let the prompt control summarization
        # density. The mode parameter is passed to the LLM context where the template
        # can adjust output format (e.g., compact mode may instruct denser summaries).
        recent_turns = transcript_processor.extract_turns_since_clear(turns, max_turns=100)

        # Format turns for LLM
        transcript_summary = format_turns_for_llm(recent_turns)
    except Exception as e:
        logger.error(f"Failed to process transcript: {e}")
        return {"error": str(e)}

    # 2. Gather context variables for template
    last_messages = transcript_processor.extract_last_messages(recent_turns, num_pairs=2)
    last_messages_str = format_turns_for_llm(last_messages) if last_messages else ""

    # Get git status and file changes
    git_status = get_git_status()
    file_changes = get_file_changes()
    git_diff_summary = get_git_diff_summary()

    # Extract structured context from transcript analysis
    analyzer = TranscriptAnalyzer()
    handoff_ctx = analyzer.extract_handoff_context(turns, max_turns=150)
    real_commits = get_recent_git_commits()
    if real_commits:
        handoff_ctx.git_commits = real_commits
    if not handoff_ctx.git_status:
        handoff_ctx.git_status = git_status
    structured_context = _format_structured_context(handoff_ctx)

    # 3. Call LLM
    try:
        llm_context = {
            "turns": recent_turns,
            "transcript_summary": transcript_summary,
            "session": current_session,
            "last_messages": last_messages_str,
            "git_status": git_status,
            "file_changes": file_changes,
            "git_diff_summary": git_diff_summary,
            "structured_context": structured_context,
            "todo_list": "",
            "previous_summary": previous_summary or "",
            "mode": mode,
        }
        provider = llm_service.get_default_provider()
        summary_content = await provider.generate_summary(
            context=llm_context,
            prompt_template=template,
        )
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        return {"error": f"LLM error: {e}"}

    # 4. Save to session
    session_manager.update_summary(session_id, summary_markdown=summary_content)

    # 5. Write to file if requested
    summary_file_path = None
    if write_file:
        summary_file_path = await _write_summary_file(
            session_id=session_id,
            content=summary_content,
            output_path=output_path,
            session_manager=session_manager,
        )

    logger.info(f"Generated summary for session {session_id} (mode={mode})")
    result: dict[str, Any] = {"summary_generated": True, "summary_length": len(summary_content)}
    if summary_file_path:
        result["summary_file"] = summary_file_path
    return result


async def generate_handoff(
    session_manager: Any,
    session_id: str,
    llm_service: Any,
    transcript_processor: Any,
    template: str | None = None,
    previous_summary: str | None = None,
    mode: Literal["clear", "compact"] = "clear",
    write_file: bool = False,
    output_path: str | None = None,
) -> dict[str, Any] | None:
    """Generate a handoff record by summarizing the session.

    This is a convenience action that combines generate_summary + mark status.

    Args:
        session_manager: The session manager instance
        session_id: Current session ID
        llm_service: LLM service instance
        transcript_processor: Transcript processor instance
        template: Optional prompt template
        previous_summary: Previous summary for cumulative compression (compact mode)
        mode: "clear" or "compact"

    Returns:
        Dict with handoff_created and summary_length, or error

    Raises:
        ValueError: If mode is not "clear" or "compact" (via generate_summary)
    """
    # Reuse generate_summary logic
    summary_result = await generate_summary(
        session_manager=session_manager,
        session_id=session_id,
        llm_service=llm_service,
        transcript_processor=transcript_processor,
        template=template,
        previous_summary=previous_summary,
        mode=mode,
        write_file=write_file,
        output_path=output_path,
    )

    if summary_result and "error" in summary_result:
        return summary_result

    # Mark Session Status
    session_manager.update_status(session_id, "handoff_ready")

    if not summary_result:
        return {"error": "Failed to generate summary"}

    return {"handoff_created": True, "summary_length": summary_result.get("summary_length", 0)}


# --- ActionHandler-compatible wrappers ---
# These match the ActionHandler protocol: (context: ActionContext, **kwargs) -> dict | None


async def handle_synthesize_title(context: ActionContext, **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for synthesize_title."""
    # Extract prompt from event data (UserPromptSubmit hook)
    prompt = None
    if context.event_data:
        prompt = context.event_data.get("prompt")

    return await synthesize_title(
        session_manager=context.session_manager,
        session_id=context.session_id,
        llm_service=context.llm_service,
        transcript_processor=context.transcript_processor,
        template_engine=context.template_engine,
        template=kwargs.get("template"),
        prompt=prompt,
    )


async def handle_generate_summary(context: ActionContext, **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for generate_summary."""
    return await generate_summary(
        session_manager=context.session_manager,
        session_id=context.session_id,
        llm_service=context.llm_service,
        transcript_processor=context.transcript_processor,
        template=kwargs.get("template"),
        mode=kwargs.get("mode", "clear"),
        previous_summary=kwargs.get("previous_summary"),
        write_file=kwargs.get("write_file", False),
        output_path=kwargs.get("output_path"),
    )


async def handle_generate_handoff(context: ActionContext, **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for generate_handoff.

    Handles mode detection from event_data and previous summary fetching for compact mode.
    Also supports loading templates from prompts collection via 'prompt' parameter.
    """
    # Detect mode from kwargs or event data
    mode = kwargs.get("mode", "clear")

    # Check if this is a compact event based on event_data
    COMPACT_EVENT_TYPES = {"pre_compact", "compact"}
    if context.event_data:
        raw_event_type = context.event_data.get("event_type") or ""
        normalized_event_type = str(raw_event_type).strip().lower()
        if normalized_event_type in COMPACT_EVENT_TYPES:
            mode = "compact"

    # For compact mode, fetch previous summary for cumulative compression
    previous_summary = None
    if mode == "compact":
        current_session = context.session_manager.get(context.session_id)
        if current_session:
            previous_summary = getattr(current_session, "summary_markdown", None)
            if previous_summary:
                logger.debug(
                    f"Compact mode: using previous summary ({len(previous_summary)} chars) "
                    f"for cumulative compression"
                )

    # Load template from prompts collection if 'prompt' parameter provided
    template = kwargs.get("template")
    prompt_path = kwargs.get("prompt")
    if prompt_path and not template:
        try:
            from gobby.prompts.loader import PromptLoader

            loader = PromptLoader()
            prompt_template = loader.load(prompt_path)
            template = prompt_template.content
            logger.debug(f"Loaded prompt template from: {prompt_path}")
        except Exception as e:
            logger.warning(f"Failed to load prompt from {prompt_path}: {e}")
            # Fall back to inline template or default

    return await generate_handoff(
        session_manager=context.session_manager,
        session_id=context.session_id,
        llm_service=context.llm_service,
        transcript_processor=context.transcript_processor,
        template=template,
        previous_summary=previous_summary,
        mode=mode,
        write_file=kwargs.get("write_file", False),
        output_path=kwargs.get("output_path"),
    )
