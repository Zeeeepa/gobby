"""
Session memory extractor.

Automatically extracts meaningful, reusable memories from session transcripts.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gobby.prompts.loader import PromptLoader
from gobby.workflows.summary_actions import format_turns_for_llm

if TYPE_CHECKING:
    from gobby.llm.service import LLMService
    from gobby.memory.manager import MemoryManager
    from gobby.storage.sessions import LocalSessionManager

logger = logging.getLogger(__name__)

# Prompt path in the prompts collection
EXTRACT_PROMPT_PATH = "memory/extract"


@dataclass
class MemoryCandidate:
    """A candidate memory extracted from a session."""

    content: str
    memory_type: str  # fact, pattern, preference, context
    importance: float
    tags: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "tags": self.tags,
        }


@dataclass
class SessionContext:
    """Context extracted from a session for memory extraction."""

    session_id: str
    project_id: str | None
    project_name: str
    task_refs: str
    files_modified: str
    tool_summary: str
    transcript_summary: str


class SessionMemoryExtractor:
    """Extract meaningful memories from session transcripts.

    Uses LLM analysis to identify high-value, reusable knowledge from
    session transcripts and stores them as memories.
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        session_manager: LocalSessionManager,
        llm_service: LLMService,
        prompt_loader: PromptLoader | None = None,
        transcript_processor: Any | None = None,
    ):
        """Initialize the extractor.

        Args:
            memory_manager: Manager for storing extracted memories
            session_manager: Manager for session data
            llm_service: LLM service for analysis
            prompt_loader: Optional custom prompt loader
            transcript_processor: Optional transcript processor for parsing
        """
        self.memory_manager = memory_manager
        self.session_manager = session_manager
        self.llm_service = llm_service
        self.prompt_loader = prompt_loader or PromptLoader()
        self.transcript_processor = transcript_processor

    async def extract(
        self,
        session_id: str,
        min_importance: float = 0.7,
        max_memories: int = 5,
        dry_run: bool = False,
    ) -> list[MemoryCandidate]:
        """Extract memories from a session.

        Args:
            session_id: The session to extract memories from
            min_importance: Minimum importance threshold (0.0-1.0)
            max_memories: Maximum number of memories to extract
            dry_run: If True, don't store memories, just return candidates

        Returns:
            List of extracted memory candidates
        """
        # 1. Get session context
        context = await self._get_session_context(session_id)
        if not context:
            logger.warning(f"Could not get context for session {session_id}")
            return []

        # 2. Load and render prompt
        prompt = self._render_prompt(
            context=context,
            min_importance=min_importance,
            max_memories=max_memories,
        )

        # 3. LLM analysis
        candidates = await self._analyze_with_llm(prompt)
        if not candidates:
            logger.debug(f"No memory candidates extracted from session {session_id}")
            return []

        # 4. Quality filter + deduplicate
        filtered = await self._filter_and_dedupe(
            candidates=candidates,
            min_importance=min_importance,
            project_id=context.project_id,
        )

        # 5. Store (unless dry_run)
        if not dry_run and filtered:
            await self._store_memories(
                candidates=filtered,
                session_id=session_id,
                project_id=context.project_id,
            )

        return filtered

    async def _get_session_context(self, session_id: str) -> SessionContext | None:
        """Get context from the session for memory extraction.

        Args:
            session_id: The session ID

        Returns:
            SessionContext with extracted information, or None if not available
        """
        session = self.session_manager.get(session_id)
        if not session:
            logger.warning(f"Session not found for memory extraction: {session_id}")
            return None

        # Get project info - log for debugging NULL project_id issues
        project_id = session.project_id
        logger.debug(
            f"Memory extraction context: session={session_id}, "
            f"project_id={project_id!r} (type={type(project_id).__name__})"
        )
        project_name = "Unknown Project"

        if project_id:
            # Try to get project name from project manager
            try:
                from gobby.storage.projects import LocalProjectManager

                project_mgr = LocalProjectManager(self.memory_manager.db)
                project = project_mgr.get(project_id)
                if project and project.name:
                    project_name = project.name
            except Exception as e:
                logger.debug(f"Could not get project name: {e}")

        # Get transcript content
        transcript_path = getattr(session, "jsonl_path", None)
        transcript_summary = ""
        task_refs = ""
        files_modified = ""
        tool_summary_parts: list[str] = []

        if transcript_path and Path(transcript_path).exists():
            turns = self._load_transcript(transcript_path)

            # Extract turns since last clear (or all if no clear)
            if self.transcript_processor:
                recent_turns = self.transcript_processor.extract_turns_since_clear(
                    turns, max_turns=50
                )
            else:
                recent_turns = turns[-50:] if len(turns) > 50 else turns

            # Format for LLM
            transcript_summary = format_turns_for_llm(recent_turns)

            # Extract file modifications and tool usage from turns
            files_set: set[str] = set()
            task_set: set[str] = set()

            for turn in recent_turns:
                message = turn.get("message", {})
                content = message.get("content", [])

                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_name = block.get("name", "")
                            tool_input = block.get("input", {})

                            # Track file modifications
                            if tool_name in ("Edit", "Write", "NotebookEdit"):
                                file_path = tool_input.get("file_path", "")
                                if file_path:
                                    files_set.add(file_path)

                            # Track task references
                            if tool_name in ("update_task", "create_task", "close_task"):
                                task_id = tool_input.get("task_id", "")
                                if task_id:
                                    task_set.add(task_id)

                            # Track key tool actions
                            if tool_name in ("Edit", "Write", "Bash", "Grep", "Glob"):
                                tool_summary_parts.append(tool_name)

            files_modified = ", ".join(sorted(files_set)) if files_set else "None"
            task_refs = ", ".join(sorted(task_set)) if task_set else "None"

        # Create tool summary (count of each tool type)
        tool_counts: dict[str, int] = {}
        for tool in tool_summary_parts:
            tool_counts[tool] = tool_counts.get(tool, 0) + 1
        tool_summary = ", ".join(f"{k}({v})" for k, v in sorted(tool_counts.items()))

        return SessionContext(
            session_id=session_id,
            project_id=project_id,
            project_name=project_name,
            task_refs=task_refs,
            files_modified=files_modified,
            tool_summary=tool_summary or "None",
            transcript_summary=transcript_summary,
        )

    def _load_transcript(self, transcript_path: str) -> list[dict[str, Any]]:
        """Load transcript turns from JSONL file.

        Args:
            transcript_path: Path to the transcript file

        Returns:
            List of turn dictionaries
        """
        turns: list[dict[str, Any]] = []
        try:
            with open(transcript_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        turns.append(json.loads(line))
        except Exception as e:
            logger.warning(f"Failed to load transcript: {e}")
        return turns

    def _render_prompt(
        self,
        context: SessionContext,
        min_importance: float,
        max_memories: int,
    ) -> str:
        """Render the extraction prompt with context.

        Args:
            context: Session context
            min_importance: Minimum importance threshold
            max_memories: Maximum memories to extract

        Returns:
            Rendered prompt string
        """
        return self.prompt_loader.render(
            EXTRACT_PROMPT_PATH,
            {
                "project_name": context.project_name,
                "task_refs": context.task_refs,
                "files": context.files_modified,
                "tool_summary": context.tool_summary,
                "transcript_summary": context.transcript_summary,
                "min_importance": min_importance,
                "max_memories": max_memories,
            },
        )

    async def _analyze_with_llm(self, prompt: str) -> list[MemoryCandidate]:
        """Call LLM to analyze transcript and extract memories.

        Args:
            prompt: Rendered prompt for the LLM

        Returns:
            List of memory candidates extracted from LLM response
        """
        try:
            provider = self.llm_service.get_default_provider()
            response = await provider.generate_text(prompt)

            # Parse JSON from response
            candidates = self._parse_llm_response(response)
            return candidates

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return []

    def _parse_llm_response(self, response: str) -> list[MemoryCandidate]:
        """Parse LLM response to extract memory candidates.

        Args:
            response: Raw LLM response text

        Returns:
            List of memory candidates
        """
        candidates: list[MemoryCandidate] = []

        # Try to find JSON array in response
        try:
            # Look for JSON array markers
            start_idx = response.find("[")
            end_idx = response.rfind("]")

            if start_idx == -1 or end_idx == -1:
                logger.warning("No JSON array found in LLM response")
                return []

            json_str = response[start_idx : end_idx + 1]
            data = json.loads(json_str)

            if not isinstance(data, list):
                logger.warning("LLM response is not a list")
                return []

            for item in data:
                if not isinstance(item, dict):
                    continue

                content = item.get("content", "").strip()
                if not content:
                    continue

                memory_type = item.get("memory_type", "fact")
                if memory_type not in ("fact", "pattern", "preference", "context"):
                    memory_type = "fact"

                raw_importance = item.get("importance", 0.7)
                try:
                    importance = float(raw_importance)
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Invalid importance value '{raw_importance}' in memory item "
                        f"(content: {content[:50]}...): {e}. Using default 0.7"
                    )
                    importance = 0.7
                importance = max(0.0, min(1.0, importance))

                tags = item.get("tags", [])
                if not isinstance(tags, list):
                    tags = []
                tags = [str(t) for t in tags]

                candidates.append(
                    MemoryCandidate(
                        content=content,
                        memory_type=memory_type,
                        importance=importance,
                        tags=tags,
                    )
                )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
        except Exception as e:
            logger.warning(f"Error parsing LLM response: {e}")

        return candidates

    async def _filter_and_dedupe(
        self,
        candidates: list[MemoryCandidate],
        min_importance: float,
        project_id: str | None,
    ) -> list[MemoryCandidate]:
        """Filter candidates by importance and deduplicate against existing memories.

        Args:
            candidates: Raw candidates from LLM
            min_importance: Minimum importance threshold
            project_id: Project ID for deduplication

        Returns:
            Filtered and deduplicated candidates
        """
        filtered: list[MemoryCandidate] = []

        for candidate in candidates:
            # Skip low importance
            if candidate.importance < min_importance:
                continue

            # Check for duplicates in existing memories
            if self.memory_manager.content_exists(candidate.content, project_id):
                logger.debug(f"Skipping duplicate memory: {candidate.content[:50]}...")
                continue

            # Check for near-duplicates in this batch
            is_duplicate = False
            for existing in filtered:
                if self._is_similar(candidate.content, existing.content):
                    is_duplicate = True
                    break

            if not is_duplicate:
                filtered.append(candidate)

        return filtered

    def _is_similar(self, content1: str, content2: str, threshold: float = 0.8) -> bool:
        """Check if two content strings are similar enough to be considered duplicates.

        Uses a simple word overlap heuristic.

        Args:
            content1: First content string
            content2: Second content string
            threshold: Similarity threshold (0.0-1.0)

        Returns:
            True if contents are similar
        """
        words1 = set(content1.lower().split())
        words2 = set(content2.lower().split())

        if not words1 or not words2:
            return False

        # Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)

        similarity = intersection / union if union > 0 else 0
        return similarity >= threshold

    async def _store_memories(
        self,
        candidates: list[MemoryCandidate],
        session_id: str,
        project_id: str | None,
    ) -> None:
        """Store extracted memories.

        Args:
            candidates: Memory candidates to store
            session_id: Source session ID
            project_id: Project ID for the memories
        """
        # Log project_id for debugging NULL project_id issues
        if project_id is None:
            logger.warning(
                f"Storing memories with NULL project_id for session {session_id}. "
                "This may cause duplicate detection issues."
            )
        else:
            logger.debug(f"Storing {len(candidates)} memories with project_id={project_id}")

        for candidate in candidates:
            try:
                await self.memory_manager.remember(
                    content=candidate.content,
                    memory_type=candidate.memory_type,
                    importance=candidate.importance,
                    project_id=project_id,
                    source_type="session",
                    source_session_id=session_id,
                    tags=candidate.tags,
                )
                logger.debug(f"Stored memory: {candidate.content[:50]}...")
            except Exception as e:
                logger.warning(f"Failed to store memory: {e}")
