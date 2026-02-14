"""Memory-related workflow actions.

Extracted from actions.py as part of strangler fig decomposition.
These functions handle memory injection, extraction, saving, and recall.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def memory_sync_import(memory_sync_manager: Any) -> dict[str, Any]:
    """Import memories from filesystem.

    Args:
        memory_sync_manager: The memory sync manager instance

    Returns:
        Dict with imported count or error
    """
    if not memory_sync_manager:
        return {"error": "Memory Sync Manager not available"}

    count = await memory_sync_manager.import_from_files()
    logger.info("Memory sync import: %s memories imported", count)
    return {"imported": {"memories": count}}


async def memory_sync_export(memory_sync_manager: Any) -> dict[str, Any]:
    """Export memories to filesystem.

    Args:
        memory_sync_manager: The memory sync manager instance

    Returns:
        Dict with exported count or error
    """
    if not memory_sync_manager:
        return {"error": "Memory Sync Manager not available"}

    count = await memory_sync_manager.export_to_files()
    logger.info("Memory sync export: %s memories exported", count)
    return {"exported": {"memories": count}}


async def memory_save(
    memory_manager: Any,
    session_manager: Any,
    session_id: str,
    content: str | None = None,
    memory_type: str = "fact",
    importance: float = 0.5,
    tags: list[str] | None = None,
    project_id: str | None = None,
) -> dict[str, Any] | None:
    """Save a memory directly from workflow context.

    Args:
        memory_manager: The memory manager instance
        session_manager: The session manager instance
        session_id: Current session ID (used for project resolution and logging)
        content: The memory content to save (required)
        memory_type: One of 'fact', 'preference', 'pattern', 'context'
        importance: Float 0.0-1.0
        tags: List of string tags
        project_id: Override project ID

    Returns:
        Dict with saved status and memory_id, or error
    """
    if not memory_manager:
        return {"error": "Memory Manager not available"}

    if not memory_manager.config.enabled:
        return None

    if not content:
        return {"error": "Missing required 'content' parameter"}

    # Resolve project_id
    if not project_id:
        session = session_manager.get(session_id)
        if session:
            project_id = session.project_id

    if not project_id:
        return {"error": "No project_id found"}

    logger.debug(
        "Saving memory type=%s session=%s project=%s importance=%.2f",
        memory_type,
        session_id,
        project_id,
        importance,
    )

    # Validate memory_type
    if memory_type not in ("fact", "preference", "pattern", "context"):
        memory_type = "fact"

    # Validate importance
    if not isinstance(importance, int | float):
        importance = 0.5
    importance = max(0.0, min(1.0, float(importance)))

    # Validate tags
    if tags is None:
        tags = []
    if not isinstance(tags, list):
        tags = []

    try:
        if memory_manager.content_exists(content, project_id):
            logger.debug("save_memory: Skipping duplicate: %s...", content[:50])
            return {"saved": False, "reason": "duplicate"}

        memory = await memory_manager.create_memory(
            content=content,
            memory_type=memory_type,
            importance=importance,
            project_id=project_id,
            source_type="workflow",
            source_session_id=session_id,
            tags=tags,
        )

        logger.info("save_memory: Created %s memory: %s...", memory_type, content[:50])
        return {
            "saved": True,
            "memory_id": memory.id,
            "memory_type": memory_type,
            "importance": importance,
        }

    except Exception as e:
        logger.error("save_memory: Failed for session %s: %s", session_id, e, exc_info=True)
        return {"error": str(e)}


async def memory_recall_relevant(
    memory_manager: Any,
    session_manager: Any,
    session_id: str,
    prompt_text: str | None = None,
    project_id: str | None = None,
    limit: int = 5,
    min_importance: float = 0.3,
    state: Any | None = None,
) -> dict[str, Any] | None:
    """Recall memories relevant to the current user prompt.

    Args:
        memory_manager: The memory manager instance
        session_manager: The session manager instance
        session_id: Current session ID
        prompt_text: The user's prompt text
        project_id: Override project ID
        limit: Max memories to retrieve
        min_importance: Minimum importance threshold
        state: WorkflowState for tracking injected memory IDs (for deduplication)

    Returns:
        Dict with inject_context and count, or None if disabled
    """
    if not memory_manager:
        return None

    if not memory_manager.config.enabled:
        return None

    if not prompt_text:
        logger.debug("memory_recall_relevant: No prompt_text provided")
        return None

    # Skip for very short prompts or commands
    if len(prompt_text.strip()) < 10 or prompt_text.strip().startswith("/"):
        logger.debug("memory_recall_relevant: Skipping short/command prompt")
        return None

    # Resolve project_id
    if not project_id:
        session = session_manager.get(session_id)
        if session:
            project_id = session.project_id

    # Get already-injected memory IDs from state for deduplication
    injected_ids: set[str] = set()
    if state is not None:
        # Access variables dict, defaulting to empty if not set
        variables = getattr(state, "variables", None) or {}
        injected_ids = set(variables.get("_injected_memory_ids", []))

    try:
        memories = memory_manager.search_memories(
            query=prompt_text,
            project_id=project_id,
            limit=limit,
            min_importance=min_importance,
            search_mode="auto",
        )

        if not memories:
            logger.debug("memory_recall_relevant: No relevant memories found")
            return {"injected": False, "count": 0}

        # Filter out memories that have already been injected in this session
        new_memories = [m for m in memories if m.id not in injected_ids]

        # Deduplicate by content to avoid showing same content with different IDs
        # (can happen when same content was stored with different project_ids)
        seen_content: set[str] = set()
        unique_memories = []
        for m in new_memories:
            normalized = m.content.strip()
            if normalized not in seen_content:
                seen_content.add(normalized)
                unique_memories.append(m)
        new_memories = unique_memories

        if not new_memories:
            logger.debug(
                "memory_recall_relevant: All %s memories already injected, skipping", len(memories)
            )
            return {"injected": False, "count": 0, "skipped": len(memories)}

        from gobby.memory.context import build_memory_context

        memory_context = build_memory_context(new_memories)

        # Track newly injected memory IDs in state
        if state is not None:
            new_ids = {m.id for m in new_memories}
            all_injected = injected_ids | new_ids
            # Ensure variables dict exists
            if not hasattr(state, "variables") or state.variables is None:
                state.variables = {}
            state.variables["_injected_memory_ids"] = list(all_injected)
            logger.debug(
                "memory_recall_relevant: Tracking %s new IDs, %s total injected",
                len(new_ids),
                len(all_injected),
            )

        logger.info("memory_recall_relevant: Injecting %s relevant memories", len(new_memories))

        return {
            "inject_context": memory_context,
            "injected": True,
            "count": len(new_memories),
        }

    except Exception as e:
        logger.error(
            "memory_recall_relevant: Failed for session %s: %s", session_id, e, exc_info=True
        )
        return {"error": str(e)}


def reset_memory_injection_tracking(state: Any | None = None) -> dict[str, Any]:
    """Reset the memory injection tracking, allowing previously injected memories to be recalled again.

    This should be called on pre_compact hook or /clear command so memories can be
    re-injected after context loss.

    Args:
        state: WorkflowState containing the injection tracking in variables

    Returns:
        Dict with cleared count and success status
    """
    if state is None:
        logger.debug("reset_memory_injection_tracking: No state provided")
        return {"success": False, "cleared": 0, "reason": "no_state"}

    variables = getattr(state, "variables", None)
    if variables is None:
        logger.debug("reset_memory_injection_tracking: No variables in state")
        return {"success": True, "cleared": 0}

    injected_ids = variables.get("_injected_memory_ids", [])
    cleared_count = len(injected_ids)

    if cleared_count > 0:
        variables["_injected_memory_ids"] = []
        logger.info(
            "reset_memory_injection_tracking: Cleared %s injected memory IDs", cleared_count
        )

    return {"success": True, "cleared": cleared_count}


# --- ActionHandler-compatible wrappers ---
# These match the ActionHandler protocol: (context: ActionContext, **kwargs) -> dict | None

if __name__ != "__main__":
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from gobby.workflows.actions import ActionContext


async def handle_memory_sync_import(
    context: "ActionContext", **kwargs: Any
) -> dict[str, Any] | None:
    """ActionHandler wrapper for memory_sync_import."""
    return await memory_sync_import(context.memory_sync_manager)


async def handle_memory_sync_export(
    context: "ActionContext", **kwargs: Any
) -> dict[str, Any] | None:
    """ActionHandler wrapper for memory_sync_export."""
    return await memory_sync_export(context.memory_sync_manager)


async def handle_memory_save(context: "ActionContext", **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for memory_save."""
    return await memory_save(
        memory_manager=context.memory_manager,
        session_manager=context.session_manager,
        session_id=context.session_id,
        content=kwargs.get("content"),
        memory_type=kwargs.get("memory_type", "fact"),
        importance=kwargs.get("importance", 0.5),
        tags=kwargs.get("tags"),
        project_id=kwargs.get("project_id"),
    )


async def handle_memory_recall_relevant(
    context: "ActionContext", **kwargs: Any
) -> dict[str, Any] | None:
    """ActionHandler wrapper for memory_recall_relevant."""
    prompt_text = None
    if context.event_data:
        # Check both "prompt" (from hook event) and "prompt_text" (legacy/alternative)
        prompt_text = context.event_data.get("prompt") or context.event_data.get("prompt_text")

    return await memory_recall_relevant(
        memory_manager=context.memory_manager,
        session_manager=context.session_manager,
        session_id=context.session_id,
        prompt_text=prompt_text,
        project_id=kwargs.get("project_id"),
        limit=kwargs.get("limit", 5),
        min_importance=kwargs.get("min_importance", 0.3),
        state=context.state,
    )


async def handle_reset_memory_injection_tracking(
    context: "ActionContext", **kwargs: Any
) -> dict[str, Any] | None:
    """ActionHandler wrapper for reset_memory_injection_tracking."""
    return reset_memory_injection_tracking(state=context.state)


async def handle_memory_extraction_gate(
    context: "ActionContext", **kwargs: Any
) -> dict[str, Any] | None:
    """Stop-gate that blocks agent from stopping until memory extraction is done.

    The agent has full context of its work — it uses create_memory/update_memory
    MCP tools directly. No need to pre-fetch memories; the agent can search itself.
    """
    return await memory_extraction_gate(
        memory_manager=context.memory_manager,
        session_id=context.session_id,
        session_manager=context.session_manager,
        state=context.state,
    )


async def handle_memory_review_gate(
    context: "ActionContext", **kwargs: Any
) -> dict[str, Any] | None:
    """Stop-gate that nudges the agent to review work and save memories.

    Conditional on pending_memory_review — only fires when significant
    work (Edit, Write, NotebookEdit, close_task) has occurred since last review.
    """
    return await memory_review_gate(
        memory_manager=context.memory_manager,
        session_id=context.session_id,
        session_manager=context.session_manager,
        state=context.state,
    )


async def handle_memory_extract_from_session(
    context: "ActionContext", **kwargs: Any
) -> dict[str, Any] | None:
    """Daemon-side memory extraction from session transcript.

    Safety net for capturing memories when the agent didn't save them.
    Uses SessionMemoryExtractor with LLM analysis.
    """
    return await memory_extract_from_session(
        memory_manager=context.memory_manager,
        session_manager=context.session_manager,
        llm_service=context.llm_service,
        transcript_processor=context.transcript_processor,
        session_id=context.session_id,
        max_memories=kwargs.get("max_memories", 5),
    )


async def handle_memory_inject_project_context(
    context: "ActionContext", **kwargs: Any
) -> dict[str, Any] | None:
    """Inject top project memories at session start.

    Provides baseline context for new/cleared sessions by injecting
    the most important project-level memories.
    """
    return await memory_inject_project_context(
        memory_manager=context.memory_manager,
        session_manager=context.session_manager,
        session_id=context.session_id,
        limit=kwargs.get("limit", 10),
        min_importance=kwargs.get("min_importance", 0.7),
        state=context.state,
    )


async def memory_extraction_gate(
    memory_manager: Any,
    session_id: str,
    session_manager: Any | None = None,
    state: Any | None = None,
) -> dict[str, Any] | None:
    """Memory extraction stop-gate logic.

    Blocks the agent from stopping until it has reviewed its work and either
    created new memories or confirmed there's nothing to save.

    Args:
        memory_manager: The memory manager instance
        session_id: Current session ID
        session_manager: Session manager for resolving #N refs
        state: WorkflowState for tracking extraction status

    Returns:
        Dict with block decision and reason, or None to allow stop
    """
    if not memory_manager:
        return None

    if not memory_manager.config.enabled:
        return None

    # Check if already extracted this turn
    variables = getattr(state, "variables", None) or {}
    if variables.get("memories_extracted"):
        return None

    # Resolve session ref: prefer #N format, fall back to UUID
    session_ref = session_id
    if session_manager:
        try:
            session = session_manager.get(session_id)
            if session and session.seq_num:
                session_ref = f"#{session.seq_num}"
        except Exception:
            logger.debug("Failed to resolve session ref", exc_info=True)

    reason = (
        "Before stopping, review your work this session and save any valuable memories.\n"
        "\n"
        "Use `create_memory` (via gobby-memory MCP) for NEW insights you discovered.\n"
        "Duplicates are handled automatically — just create freely.\n"
        "\n"
        "**What to save** (5-minute rule: would this save a future session >5 min?):\n"
        "- Debugging insights, root causes, misleading errors\n"
        "- Architecture decisions and trade-offs\n"
        "- API/library gotchas, undocumented quirks\n"
        "- Project conventions, environment quirks\n"
        "\n"
        "If you learned nothing new this session, that's fine.\n"
        "**When done**, call:\n"
        f'`set_variable(name="memories_extracted", value=true, session_id="{session_ref}")` on gobby-workflows'
    )

    logger.info("memory_extraction_gate: Blocking stop for session %s", session_id)

    return {"decision": "block", "reason": reason}


async def memory_review_gate(
    memory_manager: Any,
    session_id: str,
    session_manager: Any | None = None,
    state: Any | None = None,
) -> dict[str, Any] | None:
    """Memory review stop-gate logic.

    Blocks the agent from stopping when significant work has been done
    (pending_memory_review is true) and nudges it to save learnings.

    Args:
        memory_manager: The memory manager instance
        session_id: Current session ID
        session_manager: Session manager for resolving #N refs
        state: WorkflowState for checking pending_memory_review

    Returns:
        Dict with block decision and reason, or None to allow stop
    """
    if not memory_manager:
        return None

    if not memory_manager.config.enabled:
        return None

    # Check if there's pending work to review
    variables = getattr(state, "variables", None) or {}
    if not variables.get("pending_memory_review"):
        return None

    # Resolve session ref: prefer #N format, fall back to UUID
    session_ref = session_id
    if session_manager:
        try:
            session = session_manager.get(session_id)
            if session and session.seq_num:
                session_ref = f"#{session.seq_num}"
        except Exception:
            logger.debug("Failed to resolve session ref", exc_info=True)

    reason = (
        "Before stopping, briefly review what you learned this session.\n"
        "\n"
        "Use `create_memory` (via gobby-memory MCP) for NEW insights:\n"
        "- Debugging insights, root causes, misleading errors\n"
        "- Architecture decisions and trade-offs\n"
        "- API/library gotchas, undocumented quirks\n"
        "- Project conventions, environment quirks\n"
        "\n"
        "If nothing new was learned, that's fine.\n"
        "**When done**, call:\n"
        f'`set_variable(name="pending_memory_review", value=false, session_id="{session_ref}")` on gobby-workflows'
    )

    logger.info("memory_review_gate: Blocking stop for session %s", session_id)

    return {"decision": "block", "reason": reason}


async def memory_extract_from_session(
    memory_manager: Any,
    session_manager: Any,
    llm_service: Any,
    transcript_processor: Any | None,
    session_id: str,
    max_memories: int = 5,
) -> dict[str, Any] | None:
    """Extract memories from a session transcript using LLM analysis.

    Daemon-side safety net — runs on session_end and pre_compact to catch
    memories the agent didn't explicitly save.

    Args:
        memory_manager: The memory manager instance
        session_manager: Session manager for session data
        llm_service: LLM service for analysis
        transcript_processor: Optional transcript processor
        session_id: Session to extract from
        min_importance: Minimum importance threshold
        max_memories: Maximum memories to extract

    Returns:
        Dict with extraction results or error
    """
    if not memory_manager:
        return {"error": "Memory Manager not available"}

    if not memory_manager.config.enabled:
        return None

    if not llm_service:
        return {"error": "LLM service not available"}

    try:
        from gobby.memory.extractor import SessionMemoryExtractor

        extractor = SessionMemoryExtractor(
            memory_manager=memory_manager,
            session_manager=session_manager,
            llm_service=llm_service,
            transcript_processor=transcript_processor,
        )

        candidates = await extractor.extract(
            session_id=session_id,
            max_memories=max_memories,
        )

        logger.info(
            "memory_extract_from_session: Extracted %s memories from session %s",
            len(candidates),
            session_id,
        )

        return {
            "extracted": len(candidates),
            "memories": [c.to_dict() for c in candidates],
        }

    except Exception as e:
        logger.error(
            "memory_extract_from_session: Failed for session %s: %s",
            session_id,
            e,
            exc_info=True,
        )
        return {"error": str(e)}


async def memory_inject_project_context(
    memory_manager: Any,
    session_manager: Any,
    session_id: str,
    limit: int = 10,
    min_importance: float = 0.7,
    state: Any | None = None,
) -> dict[str, Any] | None:
    """Inject top project memories at session start.

    Lists the most important memories for the current project (no query —
    just top N by importance) and injects them as context.

    Args:
        memory_manager: The memory manager instance
        session_manager: Session manager for project resolution
        session_id: Current session ID
        limit: Max memories to inject
        min_importance: Minimum importance threshold
        state: WorkflowState for tracking injected IDs

    Returns:
        Dict with inject_context and count, or None if disabled
    """
    if not memory_manager:
        return None

    if not memory_manager.config.enabled:
        return None

    # Resolve project_id from session
    project_id = None
    session = session_manager.get(session_id)
    if session:
        project_id = session.project_id

    if not project_id:
        logger.debug("memory_inject_project_context: No project_id for session %s", session_id)
        return None

    # Get already-injected memory IDs from state for deduplication
    injected_ids: set[str] = set()
    if state is not None:
        variables = getattr(state, "variables", None) or {}
        injected_ids = set(variables.get("_injected_memory_ids", []))

    try:
        memories = memory_manager.list_memories(
            project_id=project_id,
            min_importance=min_importance,
            limit=limit,
        )

        if not memories:
            logger.debug("memory_inject_project_context: No project memories found")
            return {"injected": False, "count": 0}

        # Filter out already-injected memories
        new_memories = [m for m in memories if m.id not in injected_ids]

        if not new_memories:
            logger.debug(
                "memory_inject_project_context: All %s memories already injected",
                len(memories),
            )
            return {"injected": False, "count": 0, "skipped": len(memories)}

        from gobby.memory.context import build_memory_context

        memory_context = build_memory_context(new_memories)

        # Track newly injected memory IDs in state
        if state is not None:
            new_ids = {m.id for m in new_memories}
            all_injected = injected_ids | new_ids
            if not hasattr(state, "variables") or state.variables is None:
                state.variables = {}
            state.variables["_injected_memory_ids"] = list(all_injected)

        logger.info(
            "memory_inject_project_context: Injecting %s project memories",
            len(new_memories),
        )

        return {
            "inject_context": memory_context,
            "injected": True,
            "count": len(new_memories),
        }

    except Exception as e:
        logger.error(
            "memory_inject_project_context: Failed for session %s: %s",
            session_id,
            e,
            exc_info=True,
        )
        return {"error": str(e)}
