"""Memory-related workflow actions.

Extracted from actions.py as part of strangler fig decomposition.
These functions handle memory injection, extraction, saving, and recall.
"""

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _content_fingerprint(content: str) -> str:
    """Generate a secure fingerprint of content for logging (avoids PII exposure)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


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
    logger.info(f"Memory sync import: {count} memories imported")
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
    logger.info(f"Memory sync export: {count} memories exported")
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
        session_id: Current session ID
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
            logger.debug(f"save_memory: Skipping duplicate: {content[:50]}...")
            return {"saved": False, "reason": "duplicate"}

        memory = await memory_manager.remember(
            content=content,
            memory_type=memory_type,
            importance=importance,
            project_id=project_id,
            source_type="workflow",
            source_session_id=session_id,
            tags=tags,
        )

        logger.info(f"save_memory: Created {memory_type} memory: {content[:50]}...")
        return {
            "saved": True,
            "memory_id": memory.id,
            "memory_type": memory_type,
            "importance": importance,
        }

    except Exception as e:
        logger.error(f"save_memory: Failed: {e}", exc_info=True)
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
        memories = memory_manager.recall(
            query=prompt_text,
            project_id=project_id,
            limit=limit,
            min_importance=min_importance,
            use_semantic=True,
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
                f"memory_recall_relevant: All {len(memories)} memories already injected, skipping"
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
                f"memory_recall_relevant: Tracking {len(new_ids)} new IDs, "
                f"{len(all_injected)} total injected"
            )

        logger.info(f"memory_recall_relevant: Injecting {len(new_memories)} relevant memories")

        return {
            "inject_context": memory_context,
            "injected": True,
            "count": len(new_memories),
        }

    except Exception as e:
        logger.error(f"memory_recall_relevant: Failed: {e}", exc_info=True)
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
        logger.info(f"reset_memory_injection_tracking: Cleared {cleared_count} injected memory IDs")

    return {"success": True, "cleared": cleared_count}


async def memory_extract(
    session_manager: Any,
    session_id: str,
    llm_service: Any,
    memory_manager: Any,
    transcript_processor: Any | None = None,
    min_importance: float = 0.7,
    max_memories: int = 5,
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Extract memories from a session transcript.

    Uses LLM analysis to identify high-value, reusable knowledge from
    session transcripts and stores them as memories.

    Args:
        session_manager: The session manager instance
        session_id: Current session ID
        llm_service: LLM service for analysis
        memory_manager: Memory manager for storage
        transcript_processor: Optional transcript processor
        min_importance: Minimum importance threshold (0.0-1.0)
        max_memories: Maximum memories to extract
        dry_run: If True, don't store memories

    Returns:
        Dict with extracted_count and memory details, or error
    """
    if not memory_manager:
        return {"error": "Memory Manager not available"}

    if not memory_manager.config.enabled:
        logger.debug("memory_extract: Memory system disabled")
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
            min_importance=min_importance,
            max_memories=max_memories,
            dry_run=dry_run,
        )

        if not candidates:
            logger.debug(f"memory_extract: No memories extracted from session {session_id}")
            return {"extracted_count": 0, "memories": []}

        logger.info(
            f"memory_extract: Extracted {len(candidates)} memories from session {session_id}"
        )

        return {
            "extracted_count": len(candidates),
            "memories": [c.to_dict() for c in candidates],
            "dry_run": dry_run,
        }

    except Exception as e:
        logger.error(f"memory_extract: Failed: {e}", exc_info=True)
        return {"error": str(e)}


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


async def handle_memory_extract(context: "ActionContext", **kwargs: Any) -> dict[str, Any] | None:
    """ActionHandler wrapper for memory_extract."""
    return await memory_extract(
        session_manager=context.session_manager,
        session_id=context.session_id,
        llm_service=context.llm_service,
        memory_manager=context.memory_manager,
        transcript_processor=context.transcript_processor,
        min_importance=kwargs.get("min_importance", 0.7),
        max_memories=kwargs.get("max_memories", 5),
        dry_run=kwargs.get("dry_run", False),
    )
