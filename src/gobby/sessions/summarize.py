"""Shared session summary generation.

Single entry point for producing compact_markdown and summary_markdown
at session boundaries. Used by:
- MCP set_handoff_context (automated fallback path)
- hook_manager._dispatch_session_summaries (graceful exit via /clear, /exit, /compact)
- SessionLifecycleManager (expired sessions safety net)
"""

from __future__ import annotations

import json
import logging
import subprocess  # nosec B404 - subprocess needed for git commands
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


async def generate_session_summaries(
    session_id: str,
    session_manager: Any,
    llm_service: Any | None = None,
    db: Any | None = None,
    write_file: bool = False,
    output_path: str = "~/.gobby/session_summaries",
    set_handoff_ready: bool = True,
    compact_only: bool = False,
    full_only: bool = False,
) -> dict[str, Any]:
    """Generate compact_markdown and summary_markdown for a session.

    Reads the transcript, runs TranscriptAnalyzer for compact context,
    uses LLM for full archival summary, persists to DB, and optionally
    writes files to session_summaries directory.

    Args:
        session_id: Platform session ID (UUID).
        session_manager: LocalSessionManager instance.
        llm_service: LLM service for generating full summaries.
        db: Database for prompt template loading.
        write_file: Write summary files to disk.
        output_path: Directory for summary files.
        set_handoff_ready: Update session status to handoff_ready.
        compact_only: Generate compact summary only (TranscriptAnalyzer).
        full_only: Generate full LLM summary only.

    Returns:
        Dict with success status, markdown lengths, and context summary.
    """
    if not session_manager:
        return {"success": False, "error": "Session manager not available"}

    session = session_manager.get(session_id)
    if not session:
        return {"success": False, "error": "No session found", "session_id": session_id}

    # Get transcript path
    transcript_path = session.jsonl_path
    if not transcript_path:
        return {
            "success": False,
            "error": "No transcript path for session",
            "session_id": session_id,
        }

    path = Path(transcript_path)
    if not path.exists():
        return {
            "success": False,
            "error": "Transcript file not found",
            "path": transcript_path,
        }

    # Read and parse transcript
    turns = _read_transcript(path)

    # Analyze transcript
    from gobby.sessions.analyzer import TranscriptAnalyzer

    analyzer = TranscriptAnalyzer()
    handoff_ctx = analyzer.extract_handoff_context(turns)

    # Enrich with real-time git status
    _enrich_git_context(handoff_ctx, path.parent)

    # Determine what to generate (neither flag = both)
    generate_compact = compact_only or not full_only
    generate_full = full_only or not compact_only

    compact_markdown: str | None = None
    full_markdown: str | None = None
    full_error: str | None = None

    if generate_compact:
        from gobby.sessions.formatting import format_handoff_as_markdown

        compact_markdown = format_handoff_as_markdown(handoff_ctx)

    if generate_full:
        full_markdown, full_error = await _generate_full_summary(
            session=session,
            turns=turns,
            handoff_ctx=handoff_ctx,
            llm_service=llm_service,
            db=db,
            session_manager=session_manager,
        )
        if full_error and full_only and not compact_only:
            return {
                "success": False,
                "error": f"Failed to generate full summary: {full_error}",
                "session_id": session_id,
            }

    # Persist to database
    if compact_markdown:
        session_manager.update_compact_markdown(session_id, compact_markdown)
    if full_markdown:
        session_manager.update_summary(session_id, summary_markdown=full_markdown)

    # Set handoff_ready status
    if set_handoff_ready:
        session_manager.update_status(session_id, "handoff_ready")

    # Write files if requested
    files_written = await _write_files(
        session_id=session_id,
        full_markdown=full_markdown,
        compact_markdown=compact_markdown,
        write_file=write_file,
        output_path=output_path,
        session_manager=session_manager,
    )

    logger.info(
        "Session summaries generated for %s (compact=%d, full=%d chars)",
        session_id,
        len(compact_markdown) if compact_markdown else 0,
        len(full_markdown) if full_markdown else 0,
    )

    return {
        "success": True,
        "session_id": session_id,
        "compact_length": len(compact_markdown) if compact_markdown else 0,
        "full_length": len(full_markdown) if full_markdown else 0,
        "full_error": full_error,
        "files_written": files_written,
        "context_summary": {
            "has_active_task": bool(handoff_ctx.active_gobby_task),
            "files_modified_count": len(handoff_ctx.files_modified),
            "git_commits_count": len(handoff_ctx.git_commits),
            "has_initial_goal": bool(handoff_ctx.initial_goal),
        },
    }


def _read_transcript(path: Path) -> list[dict[str, Any]]:
    """Read and parse JSONL transcript file."""
    turns: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                turns.append(json.loads(line))
    return turns


def _enrich_git_context(handoff_ctx: Any, cwd: Path) -> None:
    """Enrich HandoffContext with real-time git status and commits."""
    if not handoff_ctx.git_status:
        try:
            result = subprocess.run(  # nosec B603 B607 - hardcoded git command
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=cwd,
            )
            handoff_ctx.git_status = result.stdout.strip() if result.returncode == 0 else ""
        except Exception:
            pass

    try:
        result = subprocess.run(  # nosec B603 B607 - hardcoded git command
            ["git", "log", "--oneline", "-10", "--format=%H|%s"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd,
        )
        if result.returncode == 0:
            commits = []
            for line in result.stdout.strip().split("\n"):
                if "|" in line:
                    hash_val, message = line.split("|", 1)
                    commits.append({"hash": hash_val, "message": message})
            if commits:
                handoff_ctx.git_commits = commits
    except Exception:
        pass


async def _generate_full_summary(
    session: Any,
    turns: list[dict[str, Any]],
    handoff_ctx: Any,
    llm_service: Any | None,
    db: Any | None,
    session_manager: Any,
) -> tuple[str | None, str | None]:
    """Generate the full LLM-based archival summary.

    Returns:
        Tuple of (full_markdown, error_message). One will be None.
    """
    try:
        # Resolve LLM provider
        provider = None
        if llm_service:
            provider = llm_service.get_default_provider()
        if not provider:
            from gobby.config.app import load_config
            from gobby.llm.claude import ClaudeLLMProvider

            config = load_config()
            provider = ClaudeLLMProvider(config)

        # Get transcript parser
        from gobby.sessions.transcripts.claude import ClaudeTranscriptParser

        parser = ClaudeTranscriptParser()

        # Load prompt template
        prompt_template = None
        try:
            from gobby.prompts.loader import PromptLoader

            loader = PromptLoader(db=db or getattr(session_manager, "db", None))
            prompt_obj = loader.load("handoff/session_end")
            prompt_template = prompt_obj.content
        except FileNotFoundError:
            pass

        if not prompt_template:
            raise ValueError("No prompt template found for handoff/session_end")

        # Prepare context for LLM
        from gobby.workflows.git_utils import get_file_changes, get_git_diff_summary
        from gobby.workflows.summary_actions import (
            _format_structured_context,
            format_turns_for_llm,
        )

        last_turns = parser.extract_turns_since_clear(turns, max_turns=50)
        last_messages = parser.extract_last_messages(turns, num_pairs=2)
        last_messages_str = format_turns_for_llm(last_messages) if last_messages else ""

        file_changes = get_file_changes()
        git_diff_summary = get_git_diff_summary()
        structured_context = _format_structured_context(handoff_ctx)

        context = {
            "transcript_summary": format_turns_for_llm(last_turns),
            "last_messages": last_messages_str,
            "git_status": handoff_ctx.git_status or "",
            "file_changes": file_changes,
            "git_diff_summary": git_diff_summary,
            "structured_context": structured_context,
            "external_id": session.id[:12],
            "session_id": session.id,
            "session_source": session.source,
        }

        full_markdown = await provider.generate_summary(context, prompt_template=prompt_template)
        return full_markdown, None

    except Exception as e:
        logger.error(
            "Failed to generate full summary for session %s: %s",
            session.id,
            e,
            exc_info=True,
        )
        return None, str(e)


async def _write_files(
    session_id: str,
    full_markdown: str | None,
    compact_markdown: str | None,
    write_file: bool,
    output_path: str,
    session_manager: Any,
) -> list[str]:
    """Write summary files to disk if requested."""
    files_written: list[str] = []
    if not write_file:
        return files_written

    from gobby.workflows.summary_actions import _write_summary_file

    if full_markdown:
        full_path: str | None = await _write_summary_file(
            session_id, full_markdown, output_path, session_manager, mode="full"
        )
        if full_path:
            files_written.append(full_path)

    if compact_markdown:
        compact_path: str | None = await _write_summary_file(
            session_id, compact_markdown, output_path, session_manager, mode="compact"
        )
        if compact_path:
            files_written.append(compact_path)

    return files_written
