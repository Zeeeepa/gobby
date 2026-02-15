"""
Deduplication service for memory creation.

Extracts atomic facts from content via LLM, searches for similar existing
memories in Qdrant, then uses LLM to decide ADD/UPDATE/DELETE/NOOP actions.
Falls back to simple storage when LLM is unavailable.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from gobby.prompts.loader import PromptLoader

if TYPE_CHECKING:
    from gobby.llm.base import LLMProvider
    from gobby.memory.vectorstore import VectorStore
    from gobby.storage.memories import LocalMemoryManager, Memory

logger = logging.getLogger(__name__)

FACT_EXTRACTION_PROMPT = "memory/fact_extraction"
DEDUP_DECISION_PROMPT = "memory/dedup_decision"


@dataclass
class Action:
    """A dedup decision for a single fact."""

    event: Literal["ADD", "UPDATE", "DELETE", "NOOP"]
    text: str
    memory_id: str | None = None


@dataclass
class DedupResult:
    """Result of the dedup pipeline."""

    added: list[Memory] = field(default_factory=list)
    updated: list[Memory] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


class DedupService:
    """
    LLM-based fact extraction and deduplication for memories.

    Pipeline:
    1. Extract atomic facts from content (LLM)
    2. Embed each fact, search Qdrant for similar existing memories
    3. Decide actions (ADD/UPDATE/DELETE/NOOP) via LLM
    4. Execute actions against storage

    Falls back to simple store on any LLM failure.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        vector_store: VectorStore,
        storage: LocalMemoryManager,
        embed_fn: Callable[..., Any],
        prompt_loader: PromptLoader | None = None,
    ):
        self.llm_provider = llm_provider
        self.vector_store = vector_store
        self.storage = storage
        self.embed_fn = embed_fn
        self.prompt_loader = prompt_loader or PromptLoader()

    async def process(
        self,
        content: str,
        project_id: str | None = None,
        memory_type: str = "fact",
        tags: list[str] | None = None,
        source_type: str = "user",
        source_session_id: str | None = None,
    ) -> DedupResult:
        """
        Run the full dedup pipeline on content.

        Args:
            content: Raw content to process
            project_id: Optional project scope
            memory_type: Memory type for new memories
            tags: Optional tags
            source_type: Origin of memory
            source_session_id: Origin session

        Returns:
            DedupResult with lists of added, updated, and deleted memories
        """
        result = DedupResult()

        # Step 1: Extract facts
        facts = await self._extract_facts(content)
        if not facts:
            # Fallback: store raw content directly
            return await self._fallback_store(
                content, project_id, memory_type, tags, source_type, source_session_id
            )

        # Step 2: For each fact, embed and search for similar existing memories
        existing_memories = await self._find_similar_memories(facts, project_id)

        # Step 3: Decide actions via LLM
        actions = await self._decide_actions(facts, existing_memories)
        if not actions:
            # Fallback: store raw content directly
            return await self._fallback_store(
                content, project_id, memory_type, tags, source_type, source_session_id
            )

        # Step 4: Execute actions
        for action in actions:
            try:
                if action.event == "ADD":
                    memory = self.storage.create_memory(
                        content=action.text,
                        memory_type=memory_type,
                        project_id=project_id,
                        source_type=source_type,
                        source_session_id=source_session_id,
                        tags=tags,
                    )
                    # Embed and upsert to VectorStore
                    await self._embed_and_upsert(memory.id, action.text, project_id)
                    result.added.append(memory)

                elif action.event == "UPDATE" and action.memory_id:
                    memory = self.storage.update_memory(
                        memory_id=action.memory_id,
                        content=action.text,
                    )
                    # Re-embed with updated content
                    await self._embed_and_upsert(memory.id, action.text, project_id)
                    result.updated.append(memory)

                elif action.event == "DELETE" and action.memory_id:
                    self.storage.delete_memory(action.memory_id)
                    try:
                        await self.vector_store.delete(action.memory_id)
                    except Exception as e:
                        logger.warning(f"VectorStore delete failed: {e}")
                    result.deleted.append(action.memory_id)

                # NOOP: do nothing
            except Exception as e:
                logger.warning(f"Failed to execute {action.event} action: {e}")

        return result

    async def _extract_facts(self, content: str) -> list[str]:
        """Extract atomic facts from content via LLM.

        Returns:
            List of fact strings, or empty list on failure.
        """
        try:
            prompt = self.prompt_loader.render(
                FACT_EXTRACTION_PROMPT,
                {"content": content},
            )
            response = await self.llm_provider.generate_json(prompt)
            facts = response.get("facts", [])
            return [str(f) for f in facts if f]
        except Exception as e:
            logger.warning(f"Fact extraction failed: {e}")
            return []

    async def _find_similar_memories(
        self,
        facts: list[str],
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Embed facts and search Qdrant for similar existing memories.

        Returns:
            List of {"id": ..., "text": ...} dicts for existing memories.
        """
        seen_ids: set[str] = set()
        existing: list[dict[str, Any]] = []

        for fact in facts:
            try:
                embedding = await self.embed_fn(fact)
                filters = {"project_id": project_id} if project_id else None
                results = await self.vector_store.search(
                    query_embedding=embedding,
                    limit=5,
                    filters=filters,
                )
                for memory_id, _score in results:
                    if memory_id not in seen_ids:
                        seen_ids.add(memory_id)
                        memory = self.storage.get_memory(memory_id)
                        if memory:
                            existing.append(
                                {
                                    "id": memory.id,
                                    "text": memory.content,
                                }
                            )
            except Exception as e:
                logger.warning(f"Similarity search failed for fact: {e}")

        return existing

    async def _decide_actions(
        self,
        new_facts: list[str],
        existing_memories: list[dict[str, Any]],
    ) -> list[Action]:
        """Use LLM to decide ADD/UPDATE/DELETE/NOOP for each fact.

        Returns:
            List of Action objects, or empty list on failure.
        """
        try:
            prompt = self.prompt_loader.render(
                DEDUP_DECISION_PROMPT,
                {
                    "new_facts": json.dumps(new_facts),
                    "existing_memories": json.dumps(existing_memories),
                },
            )
            response = await self.llm_provider.generate_json(prompt)
            raw_actions = response.get("memory", [])

            actions: list[Action] = []
            for item in raw_actions:
                if not isinstance(item, dict):
                    continue
                event = item.get("event", "").upper()
                if event not in ("ADD", "UPDATE", "DELETE", "NOOP"):
                    continue
                actions.append(
                    Action(
                        event=event,
                        text=item.get("text", ""),
                        memory_id=item.get("id"),
                    )
                )

            return actions
        except Exception as e:
            logger.warning(f"Dedup decision failed: {e}")
            return []

    async def _embed_and_upsert(
        self,
        memory_id: str,
        content: str,
        project_id: str | None = None,
    ) -> None:
        """Embed content and upsert to VectorStore."""
        try:
            embedding = await self.embed_fn(content)
            await self.vector_store.upsert(
                memory_id=memory_id,
                embedding=embedding,
                payload={
                    "content": content,
                    "project_id": project_id,
                },
            )
        except Exception as e:
            logger.warning(f"Embed/upsert failed for {memory_id}: {e}")

    async def _fallback_store(
        self,
        content: str,
        project_id: str | None,
        memory_type: str,
        tags: list[str] | None,
        source_type: str,
        source_session_id: str | None,
    ) -> DedupResult:
        """Fallback: store content directly without dedup."""
        logger.info("Falling back to simple memory store (LLM unavailable)")
        memory = self.storage.create_memory(
            content=content,
            memory_type=memory_type,
            project_id=project_id,
            source_type=source_type,
            source_session_id=source_session_id,
            tags=tags,
        )
        await self._embed_and_upsert(memory.id, content, project_id)
        return DedupResult(added=[memory])
