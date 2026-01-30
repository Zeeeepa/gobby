"""Context injection and handoff workflow actions.

Extracted from actions.py as part of strangler fig decomposition.
These functions handle context injection, message injection, and handoff extraction.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.workflows.actions import ActionContext

from gobby.workflows.git_utils import get_git_status, get_recent_git_commits

logger = logging.getLogger(__name__)


def inject_context(
    session_manager: Any,
    session_id: str,
    state: Any,
    template_engine: Any,
    source: str | None = None,
    template: str | None = None,
    require: bool = False,
) -> dict[str, Any] | None:
    """Inject context from a source.

    Args:
        session_manager: The session manager instance
        session_id: Current session ID
        state: WorkflowState instance
        template_engine: Template engine for rendering
        source: Source type (previous_session_summary, handoff, artifacts, etc.)
        template: Optional template for rendering
        require: If True, block session when no content found (default: False)

    Returns:
        Dict with inject_context key, blocking decision, or None
    """
    # Validate required parameters
    if session_manager is None:
        logger.warning(f"inject_context: session_manager is None (session_id={session_id})")
        return None

    if state is None:
        logger.warning(f"inject_context: state is None (session_id={session_id})")
        return None

    if template_engine is None:
        logger.warning(f"inject_context: template_engine is None (session_id={session_id})")
        return None

    if not session_id:
        logger.warning("inject_context: session_id is empty or None")
        return None

    # Debug logging for troubleshooting
    logger.debug(
        f"inject_context called: source={source!r}, "
        f"template_present={template is not None}, "
        f"template_len={len(template) if template else 0}, "
        f"session_id={session_id}"
    )

    # Support template-only injection (no source lookup needed)
    condition_result = (not source) and bool(template)
    logger.debug(
        f"inject_context: not source={not source}, bool(template)={bool(template)}, "
        f"condition_result={condition_result}"
    )
    if not source and template:
        # Render static template directly
        logger.debug("inject_context: entering template-only path")
        render_context: dict[str, Any] = {
            "session": session_manager.get(session_id),
            "state": state,
            "artifacts": state.artifacts if state else {},
            "observations": state.observations if state else {},
        }
        rendered = template_engine.render(template, render_context)
        logger.debug(f"inject_context: rendered template, len={len(rendered) if rendered else 0}")
        if state:
            state.context_injected = True
        return {"inject_context": rendered}

    if not source:
        return None

    content = ""

    if source in ["previous_session_summary", "handoff"]:
        current_session = session_manager.get(session_id)
        if not current_session:
            logger.warning(f"Session {session_id} not found")
            return None

        if current_session.parent_session_id:
            parent = session_manager.get(current_session.parent_session_id)
            if parent:
                content = parent.summary_markdown
                # Failback: try reading from file if database summary is empty
                # This handles cases where daemon was unavailable during /clear
                if not content and hasattr(parent, "external_id") and parent.external_id:
                    summary_dir = Path.home() / ".gobby" / "session_summaries"
                    if summary_dir.exists():
                        for summary_file in summary_dir.glob(f"session_*_{parent.external_id}.md"):
                            try:
                                content = summary_file.read_text()
                                logger.info(
                                    f"Recovered summary from failback file for {parent.external_id}"
                                )
                                break
                            except Exception as e:
                                logger.warning(f"Failed to read failback file {summary_file}: {e}")

    elif source == "artifacts":
        if state.artifacts:
            lines = ["## Captured Artifacts"]
            for name, path in state.artifacts.items():
                lines.append(f"- {name}: {path}")
            content = "\n".join(lines)

    elif source == "observations":
        if state.observations:
            content = "## Observations\n" + json.dumps(state.observations, indent=2)

    elif source == "workflow_state":
        try:
            state_dict = state.model_dump(exclude={"observations", "artifacts"})
        except AttributeError:
            state_dict = state.dict(exclude={"observations", "artifacts"})
        content = "## Workflow State\n" + json.dumps(state_dict, indent=2, default=str)

    elif source == "compact_handoff":
        # Look at CURRENT session's compact_markdown (not parent)
        # On compact, the same session continues - compact_markdown was saved to this session
        # during pre_compact, so we read it from the current session itself.
        current_session = session_manager.get(session_id)
        logger.debug(
            f"compact_handoff lookup: session_id={session_id}, "
            f"compact_markdown exists: {bool(getattr(current_session, 'compact_markdown', None)) if current_session else False}"
        )
        if current_session and current_session.compact_markdown:
            content = current_session.compact_markdown
            logger.debug(
                f"Loaded compact_markdown ({len(content)} chars) from current session {session_id}"
            )

    if content:
        if template:
            render_context = {
                "session": session_manager.get(session_id),
                "state": state,
                "artifacts": state.artifacts,
                "observations": state.observations,
            }

            if source in ["previous_session_summary", "handoff"]:
                render_context["summary"] = content
                render_context["handoff"] = {"notes": content}
            elif source == "artifacts":
                render_context["artifacts_list"] = content
            elif source == "observations":
                render_context["observations_text"] = content
            elif source == "workflow_state":
                render_context["workflow_state_text"] = content
            elif source == "compact_handoff":
                # Pass content to template (like /clear does with summary)
                render_context["handoff"] = content

            content = template_engine.render(template, render_context)

        state.context_injected = True
        return {"inject_context": content}

    # No content found - block if required
    if require:
        reason = f"Required handoff context not found (source={source})"
        logger.warning(f"inject_context: {reason}")
        return {"decision": "block", "reason": reason}

    return None


def inject_message(
    session_manager: Any,
    session_id: str,
    state: Any,
    template_engine: Any,
    content: str | None = None,
    **extra_kwargs: Any,
) -> dict[str, Any] | None:
    """Inject a message to the user/assistant, rendering it as a template.

    Args:
        session_manager: The session manager instance
        session_id: Current session ID
        state: WorkflowState instance
        template_engine: Template engine for rendering
        content: Template content to render
        **extra_kwargs: Additional context for rendering

    Returns:
        Dict with inject_message key, or None
    """
    if not content:
        return None

    render_context: dict[str, Any] = {
        "session": session_manager.get(session_id),
        "state": state,
        "artifacts": state.artifacts,
        "step_action_count": state.step_action_count,
        "variables": state.variables or {},
    }
    render_context.update(extra_kwargs)

    rendered_content = template_engine.render(content, render_context)
    return {"inject_message": rendered_content}


def extract_handoff_context(
    session_manager: Any,
    session_id: str,
    config: Any | None = None,
    db: Any | None = None,
    worktree_manager: Any | None = None,
) -> dict[str, Any] | None:
    """Extract handoff context from transcript and save to session.compact_markdown.

    Args:
        session_manager: The session manager instance
        session_id: Current session ID
        config: Optional config with compact_handoff settings
        db: Optional LocalDatabase instance for dependency injection
        worktree_manager: Optional LocalWorktreeManager instance for dependency injection

    Returns:
        Dict with extraction result or error
    """
    if config:
        compact_config = getattr(config, "compact_handoff", None)
        if compact_config and not compact_config.enabled:
            return {"skipped": True, "reason": "compact_handoff disabled"}

    current_session = session_manager.get(session_id)
    if not current_session:
        return {"error": "Session not found"}

    transcript_path = getattr(current_session, "jsonl_path", None)
    if not transcript_path:
        return {"error": "No transcript path"}

    try:
        from gobby.sessions.analyzer import TranscriptAnalyzer

        path = Path(transcript_path)
        if not path.exists():
            return {"error": "Transcript file not found"}

        turns = []
        with open(path) as f:
            for line in f:
                if line.strip():
                    turns.append(json.loads(line))

        analyzer = TranscriptAnalyzer()
        handoff_ctx = analyzer.extract_handoff_context(turns, max_turns=100)

        # Enrich with real-time git status
        if not handoff_ctx.git_status:
            handoff_ctx.git_status = get_git_status()

        # Enrich with real git commits
        real_commits = get_recent_git_commits()
        if real_commits:
            handoff_ctx.git_commits = real_commits

        # Enrich with worktree context if session is in a worktree
        try:
            # Use injected worktree_manager, or create one from injected db
            wt_manager = worktree_manager
            if wt_manager is None and db is not None:
                from gobby.storage.worktrees import LocalWorktreeManager

                wt_manager = LocalWorktreeManager(db)

            if wt_manager is not None:
                worktrees = wt_manager.list(agent_session_id=session_id, limit=1)
                if worktrees:
                    wt = worktrees[0]
                    handoff_ctx.active_worktree = {
                        "id": wt.id,
                        "branch_name": wt.branch_name,
                        "worktree_path": wt.worktree_path,
                        "base_branch": wt.base_branch,
                        "task_id": wt.task_id,
                        "status": wt.status,
                    }
            else:
                logger.debug("Skipping worktree enrichment: no worktree_manager or db provided")
        except Exception as wt_err:
            logger.debug(f"Failed to get worktree context: {wt_err}")

        # Note: active_skills population removed - redundant with _build_skill_injection_context()
        # which already handles skill restoration on session start

        # Format as markdown (like /clear stores formatted summary)
        markdown = format_handoff_as_markdown(handoff_ctx)

        # Save to session.compact_markdown
        session_manager.update_compact_markdown(session_id, markdown)

        logger.debug(
            f"Saved compact handoff markdown ({len(markdown)} chars) to session {session_id}"
        )
        return {"handoff_context_extracted": True, "markdown_length": len(markdown)}

    except Exception as e:
        logger.error(f"extract_handoff_context: Failed: {e}")
        return {"error": str(e)}


def recommend_skills_for_task(task: dict[str, Any] | None) -> list[str]:
    """Recommend relevant skills based on task category.

    Uses HookSkillManager to get skill recommendations based on the task's
    category field. Returns always-apply skills if no category is set.

    Args:
        task: Task dict with optional 'category' field, or None.

    Returns:
        List of recommended skill names for this task.
    """
    if task is None:
        return []

    try:
        from gobby.hooks.skill_manager import HookSkillManager

        manager = HookSkillManager()
        category = task.get("category")
        return manager.recommend_skills(category=category)
    except Exception as e:
        logger.debug(f"Failed to recommend skills: {e}")
        return []


def format_handoff_as_markdown(ctx: Any, prompt_template: str | None = None) -> str:
    """Format HandoffContext as markdown for storage.

    Args:
        ctx: HandoffContext with extracted session data
        prompt_template: Optional custom template (unused, reserved for future)

    Returns:
        Formatted markdown string with all sections
    """
    _ = prompt_template  # Reserved for future template support
    sections: list[str] = []

    # Active task section
    if ctx.active_gobby_task:
        task = ctx.active_gobby_task
        sections.append(
            f"### Active Task\n"
            f"**{task.get('title', 'Untitled')}** ({task.get('id', 'unknown')})\n"
            f"Status: {task.get('status', 'unknown')}"
        )

    # Worktree context section
    if ctx.active_worktree:
        wt = ctx.active_worktree
        lines = ["### Worktree Context"]
        lines.append(f"- **Branch**: `{wt.get('branch_name', 'unknown')}`")
        lines.append(f"- **Path**: `{wt.get('worktree_path', 'unknown')}`")
        lines.append(f"- **Base**: `{wt.get('base_branch', 'main')}`")
        if wt.get("task_id"):
            lines.append(f"- **Task**: {wt.get('task_id')}")
        sections.append("\n".join(lines))

    # Todo state section
    if ctx.todo_state:
        lines = ["### In-Progress Work"]
        for todo in ctx.todo_state:
            status = todo.get("status", "pending")
            marker = "x" if status == "completed" else ">" if status == "in_progress" else " "
            lines.append(f"- [{marker}] {todo.get('content', '')}")
        sections.append("\n".join(lines))

    # Git commits section
    if ctx.git_commits:
        lines = ["### Commits This Session"]
        for commit in ctx.git_commits:
            lines.append(f"- `{commit.get('hash', '')[:7]}` {commit.get('message', '')}")
        sections.append("\n".join(lines))

    # Git status section
    if ctx.git_status:
        sections.append(f"### Uncommitted Changes\n```\n{ctx.git_status}\n```")

    # Files modified section - only show files still dirty (not yet committed)
    if ctx.files_modified and ctx.git_status:
        # Filter to files that appear in git status (still uncommitted)
        dirty_files = [f for f in ctx.files_modified if f in ctx.git_status]
        if dirty_files:
            lines = ["### Files Being Modified"]
            for f in dirty_files:
                lines.append(f"- {f}")
            sections.append("\n".join(lines))

    # Initial goal section - only if task is still active (not closed/completed)
    if ctx.initial_goal:
        task_status = None
        if ctx.active_gobby_task:
            task_status = ctx.active_gobby_task.get("status")
        # Only include if no task or task is still open/in_progress
        if task_status in (None, "open", "in_progress"):
            sections.append(f"### Original Goal\n{ctx.initial_goal}")

    # Recent activity section
    if ctx.recent_activity:
        lines = ["### Recent Activity"]
        for activity in ctx.recent_activity[-5:]:
            lines.append(f"- {activity}")
        sections.append("\n".join(lines))

    # Note: Active Skills section removed - redundant with _build_skill_injection_context()
    # which already handles skill restoration on session start

    return "\n\n".join(sections)


# --- ActionHandler-compatible wrappers ---
# These match the ActionHandler protocol: (context: ActionContext, **kwargs) -> dict | None


async def handle_inject_context(context: ActionContext, **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for inject_context."""
    return await asyncio.to_thread(
        inject_context,
        session_manager=context.session_manager,
        session_id=context.session_id,
        state=context.state,
        template_engine=context.template_engine,
        source=kwargs.get("source"),
        template=kwargs.get("template"),
        require=kwargs.get("require", False),
    )


async def handle_inject_message(context: ActionContext, **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for inject_message."""
    return await asyncio.to_thread(
        inject_message,
        session_manager=context.session_manager,
        session_id=context.session_id,
        state=context.state,
        template_engine=context.template_engine,
        content=kwargs.get("content"),
        **{k: v for k, v in kwargs.items() if k != "content"},
    )


async def handle_extract_handoff_context(
    context: ActionContext, **kwargs: Any
) -> dict[str, Any] | None:
    """ActionHandler wrapper for extract_handoff_context."""
    return await asyncio.to_thread(
        extract_handoff_context,
        session_manager=context.session_manager,
        session_id=context.session_id,
        config=context.config,
        db=context.db,
        worktree_manager=kwargs.get("worktree_manager"),
    )
