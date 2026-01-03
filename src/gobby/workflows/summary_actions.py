"""Summary generation workflow actions.

Extracted from actions.py as part of strangler fig decomposition.
These functions handle session summary generation, title synthesis, and handoff creation.
"""

import json
import logging
from pathlib import Path
from typing import Any

from gobby.workflows.git_utils import get_file_changes, get_git_status

logger = logging.getLogger(__name__)


def format_turns_for_llm(turns: list[dict]) -> str:
    """Format transcript turns for LLM analysis.

    Args:
        turns: List of transcript turn dicts

    Returns:
        Formatted string with turn summaries
    """
    formatted: list[str] = []
    for i, turn in enumerate(turns):
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
            content = " ".join(text_parts)

        formatted.append(f"[Turn {i + 1} - {role}]: {content}")

    return "\n\n".join(formatted)


async def synthesize_title(
    session_manager: Any,
    session_id: str,
    llm_service: Any,
    transcript_processor: Any,
    template_engine: Any,
    template: str | None = None,
) -> dict[str, Any] | None:
    """Synthesize and set a session title.

    Args:
        session_manager: The session manager instance
        session_id: Current session ID
        llm_service: LLM service instance
        transcript_processor: Transcript processor instance
        template_engine: Template engine for rendering
        template: Optional prompt template

    Returns:
        Dict with title_synthesized or error
    """
    if not llm_service or not transcript_processor:
        return {"error": "Missing services"}

    current_session = session_manager.get(session_id)
    if not current_session:
        return {"error": "Session not found"}

    transcript_path = getattr(current_session, "jsonl_path", None)
    if not transcript_path:
        return {"error": "No transcript path"}

    try:
        # Read enough turns to get context
        turns = []
        path = Path(transcript_path)
        if path.exists():
            with open(path) as f:
                for i, line in enumerate(f):
                    if i > 20:
                        break
                    if line.strip():
                        turns.append(json.loads(line))

        if not turns:
            return {"error": "Empty transcript"}

        formatted_turns = format_turns_for_llm(turns)

        if not template:
            template = (
                "Create a short, concise title (3-6 words) for this coding session "
                "based on the transcript.\n\nTranscript:\n{{ transcript }}"
            )

        prompt = template_engine.render(template, {"transcript": formatted_turns})

        provider = llm_service.get_default_provider()
        title = await provider.generate_text(prompt)

        # clean title (remove quotes, etc)
        title = title.strip().strip('"').strip("'")

        session_manager.update_title(session_id, title)
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
    mode: str = "clear",
) -> dict[str, Any] | None:
    """Generate a session summary using LLM and store it in the session record.

    Args:
        session_manager: The session manager instance
        session_id: Current session ID
        llm_service: LLM service instance
        transcript_processor: Transcript processor instance
        template: Optional prompt template
        previous_summary: Previous summary_markdown for cumulative compression (compact mode)
        mode: "clear" or "compact" - affects how turns are extracted

    Returns:
        Dict with summary_generated and summary_length, or error
    """
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
        with open(transcript_file) as f:
            for line in f:
                if line.strip():
                    turns.append(json.loads(line))

        # Get turns since last /clear (up to 50 turns)
        # For compact mode, we still use this - the full JSONL is available
        # and the template will instruct the LLM to focus on what's new
        recent_turns = transcript_processor.extract_turns_since_clear(turns, max_turns=50)

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

    # 3. Call LLM
    try:
        llm_context = {
            "turns": recent_turns,
            "transcript_summary": transcript_summary,
            "session": current_session,
            "last_messages": last_messages_str,
            "git_status": git_status,
            "file_changes": file_changes,
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

    logger.info(f"Generated summary for session {session_id} (mode={mode})")
    return {"summary_generated": True, "summary_length": len(summary_content)}


async def generate_handoff(
    session_manager: Any,
    session_id: str,
    llm_service: Any,
    transcript_processor: Any,
    template: str | None = None,
    previous_summary: str | None = None,
    mode: str = "clear",
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
    )

    if summary_result and "error" in summary_result:
        return summary_result

    # Mark Session Status
    session_manager.update_status(session_id, "handoff_ready")

    if not summary_result:
        return {"error": "Failed to generate summary"}

    return {"handoff_created": True, "summary_length": summary_result.get("summary_length", 0)}
