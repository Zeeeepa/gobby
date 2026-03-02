"""Session digest pipeline — turn recording, boundary summaries, and memory extraction.

Relocated from workflows/memory_actions.py as part of dead-code cleanup.
These functions handle the per-turn digest pipeline (build_turn_and_digest),
session boundary summaries, memory extraction from sessions, and sync operations.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LIFECYCLE_CMDS = ("/clear", "/exit", "/compact")


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


def _read_last_turn_from_transcript(jsonl_path: str, source: str) -> tuple[str, str]:
    """Read the last user prompt and assistant response from a transcript file.

    Args:
        jsonl_path: Path to the JSONL transcript file
        source: CLI source (claude, gemini, codex, etc.)

    Returns:
        Tuple of (prompt_text, response_text). Empty strings if not found.
    """
    transcript_file = Path(jsonl_path)
    if not transcript_file.exists():
        return "", ""

    try:
        from gobby.sessions.transcripts import get_parser

        parser = get_parser(source)
        turns: list[dict[str, Any]] = []
        with open(transcript_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    turns.append(json.loads(line))

        if not turns:
            return "", ""

        # Extract last user/assistant pair
        messages = parser.extract_last_messages(turns, num_pairs=1)
        prompt_text = ""
        response_text = ""
        for msg in messages:
            if msg["role"] == "user":
                prompt_text = msg["content"]
            elif msg["role"] == "assistant":
                response_text = msg["content"]

        return prompt_text, response_text
    except Exception as e:
        logger.warning("Failed to read transcript %s: %s", jsonl_path, e)
        return "", ""


def _read_undigested_turns(
    jsonl_path: str, source: str, digested_count: int
) -> list[tuple[str, str]]:
    """Read user/assistant pairs from transcript that haven't been digested yet.

    Uses extract_turns_since_clear() to respect /clear boundaries, then
    extract_last_messages() to get all pairs from the current segment.
    Returns only pairs after digested_count.

    Args:
        jsonl_path: Path to the JSONL transcript file
        source: CLI source (claude, gemini, codex, etc.)
        digested_count: Number of pairs already digested

    Returns:
        List of (prompt, response) tuples for undigested exchanges.
        Empty list if nothing new to digest.
    """
    transcript_file = Path(jsonl_path)
    if not transcript_file.exists():
        return []

    try:
        from gobby.sessions.transcripts import get_parser

        parser = get_parser(source)
        turns: list[dict[str, Any]] = []
        with open(transcript_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    turns.append(json.loads(line))

        if not turns:
            return []

        # Get current conversation segment (respects /clear boundaries)
        segment = parser.extract_turns_since_clear(turns, max_turns=50)
        if not segment:
            return []

        # Extract all user/assistant messages from the segment
        messages = parser.extract_last_messages(segment, num_pairs=50)
        if not messages:
            return []

        # Pair messages into (prompt, response) tuples
        pairs: list[tuple[str, str]] = []
        current_prompt = ""
        for msg in messages:
            if msg["role"] == "user":
                # Consecutive user message means previous had no response (interrupted)
                if current_prompt:
                    pairs.append((current_prompt, ""))
                current_prompt = msg["content"]
            elif msg["role"] == "assistant":
                pairs.append((current_prompt or "", msg["content"]))
                current_prompt = ""
        # Trailing user message without response
        if current_prompt:
            pairs.append((current_prompt, ""))

        # Filter out lifecycle commands
        pairs = [
            (p, r)
            for p, r in pairs
            if not any(
                p.strip().lower() == c or p.strip().lower().startswith(c + " ")
                for c in _LIFECYCLE_CMDS
            )
        ]

        if not pairs:
            return []

        # Return undigested pairs
        if digested_count < len(pairs):
            return pairs[digested_count:]

        # Transcript has fewer pairs than digested (e.g., /clear reset) —
        # fall back to the last pair so we don't lose the current exchange
        return [pairs[-1]]

    except Exception as e:
        logger.warning("Failed to read undigested turns from %s: %s", jsonl_path, e)
        return []


def _get_next_turn_number(previous_digest: str | None) -> int:
    """Parse existing digest to determine the next turn number.

    Args:
        previous_digest: The existing digest_markdown content

    Returns:
        Next turn number (1-based)
    """
    if not previous_digest:
        return 1

    # Find all "### Turn N" headers
    turn_numbers = re.findall(r"^### Turn (\d+)", previous_digest, re.MULTILINE)
    if not turn_numbers:
        return 1

    return max(int(n) for n in turn_numbers) + 1


def _build_turn_record_prompt(prompt_text: str, response_text: str) -> str:
    """Build the turn record prompt inline (fallback when DB prompts unavailable)."""
    return (
        "Given a conversation turn, produce a detailed, human-readable record.\n\n"
        f"## User Prompt\n{prompt_text}\n\n"
        f"## Agent Response\n{response_text}\n\n"
        "## Instructions\n"
        "Produce a structured record of this turn in chronological order:\n"
        "- What the user asked or requested\n"
        "- What the agent found, decided, or accomplished\n"
        "- Each tool used and its purpose (file reads, edits, searches, commands)\n"
        "- Files created, modified, or deleted\n"
        "- Commits made (with refs)\n"
        "- Task operations (created, claimed, closed)\n"
        "- Key technical findings or decisions\n\n"
        "Write in concise past tense. Include specifics (file paths, function names,\n"
        "task refs like #N, commit SHAs). No filler. Target 200-400 words."
    )


def _build_title_synthesis_prompt(digest_markdown: str) -> str:
    """Build the title synthesis prompt inline (fallback when DB prompts unavailable)."""
    return (
        "Given a session's turn-by-turn digest, produce a 3-5 word title\n"
        "reflecting the current focus of the session.\n\n"
        f"## Session Digest\n{digest_markdown}\n\n"
        "Output only the title, nothing else."
    )


async def _extract_memories_from_turn(
    turn_text: str,
    session_id: str,
    memory_manager: Any,
    provider: Any,
    model: str | None = None,
) -> list[str]:
    """Extract reusable facts/patterns from a turn record.

    Uses LLM to identify high-value memories from a single turn's record,
    then stores them via memory_manager.

    Args:
        turn_text: The last_turn_markdown content
        session_id: Session ID for memory attribution
        memory_manager: Memory manager for storage
        provider: LLM provider for extraction
        model: Model override (e.g., "haiku")

    Returns:
        List of memory IDs created
    """
    if not turn_text or len(turn_text) < 50:
        return []

    extraction_prompt = (
        "Analyze this turn record from a coding session. Extract ONLY memories that would\n"
        "save a future session more than 5 minutes of investigation.\n\n"
        "## Turn Record\n"
        f"{turn_text}\n\n"
        "## Rules\n"
        "- Extract 0-3 memories (0 is fine if nothing is worth saving)\n"
        "- Each memory must be a specific, verifiable fact or recurring pattern\n"
        "- NO generic programming knowledge\n"
        "- NO information already in project docs or README\n"
        "- Include file paths, function names, and specifics\n\n"
        "## Output Format\n"
        "Output each memory as a JSON object on its own line, no other text:\n"
        '{"content": "...", "memory_type": "fact|pattern", "tags": ["tag1", "tag2"]}\n\n'
        "If nothing is worth saving, output exactly: NONE"
    )

    response = await provider.generate_text(extraction_prompt, model=model)
    response = response.strip()

    if response.upper() == "NONE" or not response:
        return []

    memory_ids: list[str] = []
    # Resolve project_id from session
    session = (
        memory_manager.storage.db.fetchone(
            "SELECT project_id FROM sessions WHERE id = ?", (session_id,)
        )
        if hasattr(memory_manager, "storage")
        else None
    )
    project_id = session["project_id"] if session else None

    for line in response.splitlines():
        line = line.strip()
        if not line or line.upper() == "NONE":
            continue
        try:
            candidate = json.loads(line)
            if not isinstance(candidate, dict) or "content" not in candidate:
                continue

            content = candidate["content"]
            if not content or len(content) < 10:
                continue

            # Deduplicate against existing memories
            if memory_manager.content_exists(content, project_id=project_id):
                logger.debug("Skipping duplicate memory: %s...", content[:50])
                continue

            memory = await memory_manager.create_memory(
                content=content,
                memory_type=candidate.get("memory_type", "fact"),
                project_id=project_id,
                source_type="auto_extract",
                source_session_id=session_id,
                tags=candidate.get("tags"),
            )
            memory_ids.append(memory.id)
            logger.info("Extracted memory from turn: %s", content[:80])
        except (json.JSONDecodeError, Exception) as e:
            logger.debug("Failed to parse memory candidate: %s", e)
            continue

    return memory_ids


async def build_turn_and_digest(
    memory_manager: Any,
    session_manager: Any,
    session_id: str,
    prompt_text: str | None = None,
    llm_service: Any | None = None,
    db: Any | None = None,
    config: Any | None = None,
) -> dict[str, Any] | None:
    """Build a detailed turn record, append to digest, synthesize title, and extract memories.

    This is the core per-turn pipeline, fired after each agent response (stop event).
    It reads the last user/assistant exchange from the transcript, generates a structured
    turn record via LLM, appends it to the session's rolling digest, synthesizes a title,
    and extracts reusable memories.

    Args:
        memory_manager: The memory manager instance
        session_manager: The session manager instance
        session_id: Platform session ID
        prompt_text: Optional user prompt (usually None for stop events, read from transcript)
        llm_service: LLM service for generation
        db: Database for prompt template loading
        config: DaemonConfig for digest provider/model selection

    Returns:
        Dict with turn_num and pipeline results, or None if skipped
    """
    if not memory_manager or not memory_manager.config.enabled:
        return None

    if not llm_service:
        return None

    # Check DigestConfig.enabled
    digest_config = getattr(config, "digest", None) if config else None
    if digest_config and not digest_config.enabled:
        return None

    try:
        # 1. Get session and resolve transcript path
        session = session_manager.get(session_id) if session_manager else None
        if not session:
            logger.warning("build_turn_and_digest: Session %s not found", session_id)
            return None

        # 2. Read undigested turns from transcript or fall back to prompt_text
        undigested_pairs: list[tuple[str, str]] = []

        if session.jsonl_path:
            previous_digest = getattr(session, "digest_markdown", None) or ""
            digested_count = _get_next_turn_number(previous_digest) - 1
            undigested_pairs = _read_undigested_turns(
                session.jsonl_path, session.source, digested_count
            )

        if not undigested_pairs:
            # Fallback: use prompt_text argument (non-transcript path)
            user_prompt = prompt_text or ""
            if not user_prompt:
                logger.debug("build_turn_and_digest: No turn content for session %s", session_id)
                return None
            # Skip lifecycle commands
            _stripped = user_prompt.strip()
            if any(
                _stripped.lower() == c or _stripped.lower().startswith(c + " ")
                for c in _LIFECYCLE_CMDS
            ):
                return None
            undigested_pairs = [(user_prompt, "")]

        # Idempotency check: hash covers all undigested content
        combined_content = "||".join(f"{p}||{r}" for p, r in undigested_pairs)
        input_hash = hashlib.sha256(combined_content.encode()).hexdigest()[:16]
        if session.last_digest_input_hash == input_hash:
            logger.debug(
                "build_turn_and_digest: Skipping duplicate digest for session %s (hash=%s)",
                session_id,
                input_hash,
            )
            return None

        # 3. Resolve LLM provider/model
        if digest_config:
            try:
                provider, model, _ = llm_service.get_provider_for_feature(digest_config)
            except (ValueError, Exception):
                provider = llm_service.get_default_provider()
                model = None
        else:
            provider = llm_service.get_default_provider()
            model = None

        # 4. Build last_turn_markdown via LLM
        # Truncate inputs to keep LLM costs reasonable
        max_prompt_chars = 4000
        max_response_chars = 8000

        if len(undigested_pairs) == 1:
            truncated_prompt = undigested_pairs[0][0][:max_prompt_chars]
            truncated_response = undigested_pairs[0][1][:max_response_chars]
        else:
            # Multiple exchanges (catch-up from interrupted turns)
            per_prompt = max_prompt_chars // len(undigested_pairs)
            per_response = max_response_chars // len(undigested_pairs)
            parts = []
            for i, (p, r) in enumerate(undigested_pairs, 1):
                parts.append(f"## Exchange {i}\nUser: {p[:per_prompt]}\nAgent: {r[:per_response]}")
            truncated_prompt = "\n\n".join(parts)
            truncated_response = ""

        try:
            from gobby.prompts.loader import PromptLoader

            loader = PromptLoader(db=db)
            turn_prompt = loader.render(
                "memory/turn_record",
                {"prompt_text": truncated_prompt, "response_text": truncated_response},
            )
        except Exception:
            turn_prompt = _build_turn_record_prompt(truncated_prompt, truncated_response)

        last_turn = await provider.generate_text(turn_prompt, model=model)
        last_turn = last_turn.strip()

        # 5. Persist last_turn_markdown (overwrites previous)
        session_manager.update_last_turn_markdown(session_id, last_turn)

        # 6. Append to digest_markdown with turn number
        previous_digest = getattr(session, "digest_markdown", None) or ""
        turn_num = _get_next_turn_number(previous_digest)
        entry = f"### Turn {turn_num}\n{last_turn}"
        updated_digest = f"{previous_digest}\n\n{entry}" if previous_digest else entry
        session_manager.update_digest_markdown(session_id, updated_digest)

        # Persist input hash for idempotency (prevents double-digest on plan mode turns)
        session_manager.update_last_digest_input_hash(session_id, input_hash)

        logger.info(
            "build_turn_and_digest: Turn %d recorded (%d chars) for session %s",
            turn_num,
            len(last_turn),
            session_id,
        )

        result: dict[str, Any] = {
            "turn_num": turn_num,
            "turn_length": len(last_turn),
            "digest_length": len(updated_digest),
        }

        # 7. Synthesize title from updated digest
        try:
            try:
                from gobby.prompts.loader import PromptLoader

                loader = PromptLoader(db=db)
                title_prompt = loader.render(
                    "memory/title_synthesis",
                    {"digest_markdown": updated_digest},
                )
            except Exception:
                title_prompt = _build_title_synthesis_prompt(updated_digest)

            title = await provider.generate_text(title_prompt, model=model)
            title = title.strip().strip('"').strip("'")
            if title and len(title) < 80:
                session_manager.update_title(session_id, title)
                result["title"] = title

                # Rename tmux window
                from gobby.workflows.summary_actions import _rename_tmux_window

                await _rename_tmux_window(session, title)
        except Exception as e:
            logger.warning("build_turn_and_digest: Title synthesis failed: %s", e)

        # 8. Extract memories from turn record
        try:
            extracted = await _extract_memories_from_turn(
                last_turn, session_id, memory_manager, provider, model=model
            )
            if extracted:
                result["memories_extracted"] = len(extracted)
        except Exception as e:
            logger.warning("build_turn_and_digest: Memory extraction failed: %s", e)

        return result

    except Exception as e:
        logger.error(
            "build_turn_and_digest: Failed for session %s: %s",
            session_id,
            e,
            exc_info=True,
        )
        return {"error": str(e)}


async def generate_session_boundary_summaries(
    session_id: str,
    session_manager: Any,
    llm_service: Any,
    db: Any | None = None,
    config: Any | None = None,
) -> dict[str, Any] | None:
    """Generate compact_markdown and summary_markdown from digest at session boundary.

    Called on /clear, /exit, or session expiry. Produces both handoff context
    and archival summary in a single LLM call from the accumulated digest.

    Args:
        session_id: Platform session ID
        session_manager: Session manager
        llm_service: LLM service for generation
        db: Database for prompt template loading
        config: DaemonConfig

    Returns:
        Dict with results, or None if no digest available
    """
    if not session_manager or not llm_service:
        return None

    session = session_manager.get(session_id)
    if not session:
        return None

    digest = getattr(session, "digest_markdown", None)
    if not digest or len(digest.strip()) < 50:
        return None

    # Resolve provider/model
    digest_config = getattr(config, "digest", None) if config else None
    if digest_config:
        try:
            provider, model, _ = llm_service.get_provider_for_feature(digest_config)
        except (ValueError, Exception):
            provider = llm_service.get_default_provider()
            model = None
    else:
        provider = llm_service.get_default_provider()
        model = None

    try:
        try:
            from gobby.prompts.loader import PromptLoader

            loader = PromptLoader(db=db)
            boundary_prompt = loader.render(
                "memory/session_boundary",
                {"digest_markdown": digest},
            )
        except Exception:
            boundary_prompt = (
                "Given a session's complete turn-by-turn digest, produce two outputs.\n\n"
                "You MUST separate the two outputs with the exact line "
                "===SECTION_BREAK=== on its own line (no extra whitespace). "
                "This marker is required for machine parsing — do not omit it, "
                "rename it, or wrap it in markdown formatting.\n\n"
                f"## Session Digest\n{digest}\n\n"
                "---\n\n"
                "## Output A: Handoff Context\n"
                "What the next session needs to know to continue this work.\n"
                "Include: current state, open problems, key decisions, relevant file paths.\n"
                "Keep under 500 words.\n\n"
                "===SECTION_BREAK===\n\n"
                "## Output B: Session Summary\n"
                "Archival summary of what was accomplished.\n"
                "Include: goals, outcomes, commits, tasks closed, key findings.\n"
                "Keep under 800 words."
            )

        response = await provider.generate_text(boundary_prompt, model=model)
        response = response.strip()

        # Parse the two sections
        if "===SECTION_BREAK===" in response:
            parts = response.split("===SECTION_BREAK===", 1)
            compact = parts[0].strip()
            summary = parts[1].strip() if len(parts) > 1 else ""
        else:
            # Fallback: try splitting on Output B header variants
            compact = ""
            summary = ""
            header_match = re.search(r"\n(?=#{1,3}\s*Output\s*B\b)", response, re.IGNORECASE)
            if header_match:
                compact = response[: header_match.start()].strip()
                summary = response[header_match.start() :].strip()
            else:
                # Last resort: full response is summary, compact gets
                # only the first 500 words to avoid bloating context
                summary = response
                words = response.split()
                compact = " ".join(words[:500]) if len(words) > 500 else response
            logger.warning(
                "Session boundary response missing ===SECTION_BREAK=== marker "
                "for session %s, used fallback parsing",
                session_id,
            )

        # Persist
        if compact:
            session_manager.update_compact_markdown(session_id, compact)
        if summary:
            session_manager.update_summary(session_id, summary_markdown=summary)

        logger.info(
            "Session boundary summaries generated for %s (compact=%d, summary=%d chars)",
            session_id,
            len(compact),
            len(summary),
        )

        return {
            "compact_length": len(compact),
            "summary_length": len(summary),
        }

    except Exception as e:
        logger.error(
            "generate_session_boundary_summaries: Failed for session %s: %s",
            session_id,
            e,
            exc_info=True,
        )
        return {"error": str(e)}


async def memory_extract_from_session(
    memory_manager: Any,
    session_manager: Any,
    llm_service: Any,
    transcript_processor: Any | None,
    session_id: str,
    max_memories: int = 5,
    config: Any | None = None,
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
        max_memories: Maximum memories to extract
        config: Optional MemoryExtractionConfig for provider/model selection

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
            config=config,
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
