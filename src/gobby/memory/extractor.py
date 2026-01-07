"""
Memory extraction from various sources.

Provides LLM-powered extraction of memories from:
- Session summaries
- CLAUDE.md files
- Codebase patterns
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from gobby.llm.service import LLMService
    from gobby.memory.manager import MemoryManager

logger = logging.getLogger(__name__)

# Directories to skip when analyzing source files and directory structure
SKIP_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".next",
    }
)


@dataclass
class ExtractedMemory:
    """Represents a memory extracted from a source."""

    content: str
    memory_type: str = "fact"
    importance: float = 0.5
    tags: list[str] = field(default_factory=list)
    source: str = "extraction"

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "tags": self.tags,
            "source": self.source,
        }


@dataclass
class ExtractionResult:
    """Result of an extraction operation."""

    extracted: list[ExtractedMemory] = field(default_factory=list)
    created: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class MemoryExtractor:
    """
    Extracts memories from various sources using LLM.

    Supports extraction from:
    - Session summaries (facts, preferences, patterns)
    - Agent MD files (CLAUDE.md, GEMINI.md, CODEX.md)
    - Codebase patterns (conventions, architecture)

    Prompts are configurable via MemoryConfig:
    - extraction_prompt: For session summaries
    - agent_md_extraction_prompt: For agent MD files
    - codebase_extraction_prompt: For codebase scanning
    """

    # Supported agent markdown files
    AGENT_MD_FILES = ["CLAUDE.md", "GEMINI.md", "CODEX.md"]

    def __init__(
        self,
        memory_manager: "MemoryManager",
        llm_service: "LLMService | None" = None,
    ):
        """
        Initialize the memory extractor.

        Args:
            memory_manager: MemoryManager for storing extracted memories
            llm_service: LLM service for extraction (optional)
        """
        self.memory_manager = memory_manager
        self.llm_service = llm_service

    async def extract_from_session(
        self,
        summary: str,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> ExtractionResult:
        """
        Extract memories from a session summary.

        Args:
            summary: Session summary markdown
            project_id: Optional project ID for the memories
            session_id: Optional session ID for source tracking

        Returns:
            ExtractionResult with extracted memories
        """
        result = ExtractionResult()

        if not summary or len(summary.strip()) < 50:
            result.errors.append("Summary too short for extraction")
            return result

        # Get prompt from config
        prompt_template = getattr(
            self.memory_manager.config,
            "extraction_prompt",
            "{content}",  # Fallback
        )

        memories = await self._extract_with_llm(
            content=summary,
            prompt_template=prompt_template,
            source="session",
        )

        result.extracted = memories
        await self._store_memories(
            memories=memories,
            result=result,
            project_id=project_id,
            source_session_id=session_id,
        )

        return result

    async def extract_from_agent_md(
        self,
        file_path: str | Path | None = None,
        content: str | None = None,
        project_id: str | None = None,
        project_path: str | Path | None = None,
    ) -> ExtractionResult:
        """
        Extract memories from agent markdown files (CLAUDE.md, GEMINI.md, CODEX.md).

        Args:
            file_path: Path to specific agent MD file (or provide content directly)
            content: File content (alternative to file_path)
            project_id: Optional project ID for the memories
            project_path: Project root to scan for all agent MD files

        Returns:
            ExtractionResult with extracted memories
        """
        result = ExtractionResult()

        # If project_path provided, find all agent MD files
        if project_path is not None:
            root = Path(project_path)
            for md_file in self.AGENT_MD_FILES:
                md_path = root / md_file
                if md_path.exists():
                    sub_result = await self._extract_single_agent_md(
                        file_path=md_path,
                        project_id=project_id,
                    )
                    result.extracted.extend(sub_result.extracted)
                    result.created += sub_result.created
                    result.skipped += sub_result.skipped
                    result.errors.extend(sub_result.errors)
            return result

        # Single file or content
        return await self._extract_single_agent_md(
            file_path=file_path,
            content=content,
            project_id=project_id,
        )

    async def _extract_single_agent_md(
        self,
        file_path: str | Path | None = None,
        content: str | None = None,
        project_id: str | None = None,
    ) -> ExtractionResult:
        """Extract from a single agent MD file."""
        result = ExtractionResult()

        # Get content
        if content is None:
            if file_path is None:
                result.errors.append("Either file_path or content required")
                return result

            path = Path(file_path)
            if not path.exists():
                result.errors.append(f"File not found: {file_path}")
                return result

            try:
                content = path.read_text(encoding="utf-8")
            except Exception as e:
                result.errors.append(f"Failed to read file: {e}")
                return result

        if len(content.strip()) < 50:
            result.errors.append("Agent MD content too short")
            return result

        # Determine source from file path
        source = "agent_md"
        if file_path:
            name = Path(file_path).name.lower()
            if "claude" in name:
                source = "claude_md"
            elif "gemini" in name:
                source = "gemini_md"
            elif "codex" in name:
                source = "codex_md"

        # Get prompt from config
        prompt_template = getattr(
            self.memory_manager.config,
            "agent_md_extraction_prompt",
            "{content}",  # Fallback
        )

        memories = await self._extract_with_llm(
            content=content,
            prompt_template=prompt_template,
            source=source,
        )

        result.extracted = memories
        await self._store_memories(
            memories=memories,
            result=result,
            project_id=project_id,
        )

        return result

    async def extract_from_codebase(
        self,
        project_path: str | Path,
        project_id: str | None = None,
        max_files: int = 20,
    ) -> ExtractionResult:
        """
        Extract patterns from a codebase.

        Scans project structure, key files, and samples code to identify patterns.

        Args:
            project_path: Path to the project root
            project_id: Optional project ID for the memories
            max_files: Maximum number of files to sample

        Returns:
            ExtractionResult with extracted patterns
        """
        result = ExtractionResult()
        path = Path(project_path)

        if not path.exists():
            result.errors.append(f"Project path not found: {project_path}")
            return result

        # Build codebase analysis
        analysis = self._analyze_codebase(path, max_files)

        if len(analysis) < 100:
            result.errors.append("Not enough codebase content to analyze")
            return result

        # Get prompt from config
        prompt_template = getattr(
            self.memory_manager.config,
            "codebase_extraction_prompt",
            "{content}",  # Fallback
        )

        memories = await self._extract_with_llm(
            content=analysis,
            prompt_template=prompt_template,
            source="codebase",
        )

        result.extracted = memories
        await self._store_memories(
            memories=memories,
            result=result,
            project_id=project_id,
        )

        return result

    def _analyze_codebase(self, project_path: Path, max_files: int) -> str:
        """
        Analyze codebase structure and sample files.

        Args:
            project_path: Project root path
            max_files: Maximum files to sample

        Returns:
            Formatted analysis string for LLM
        """
        parts = []

        # 1. Directory structure
        parts.append("## Directory Structure\n")
        structure = self._get_directory_structure(project_path, max_depth=3)
        parts.append(structure)
        parts.append("")

        # 2. Key config files
        config_files = [
            "package.json",
            "pyproject.toml",
            "Cargo.toml",
            "go.mod",
            "requirements.txt",
            "setup.py",
            ".eslintrc",
            ".prettierrc",
            "tsconfig.json",
        ]

        parts.append("## Configuration Files\n")
        for config in config_files:
            config_path = project_path / config
            if config_path.exists():
                try:
                    content = config_path.read_text(encoding="utf-8")[:2000]
                    parts.append(f"### {config}\n```\n{content}\n```\n")
                except Exception:
                    pass
        parts.append("")

        # 3. Sample source files
        parts.append("## Sample Source Files\n")
        source_exts = {".py", ".ts", ".js", ".go", ".rs", ".java", ".tsx", ".jsx"}
        source_files: list[Path] = []

        for ext in source_exts:
            source_files.extend(project_path.rglob(f"*{ext}"))
            if len(source_files) >= max_files:
                break

        # Skip common non-source directories
        source_files = [f for f in source_files if not any(skip in f.parts for skip in SKIP_DIRS)][
            :max_files
        ]

        for source_file in source_files[:5]:  # Sample 5 files for patterns
            try:
                content = source_file.read_text(encoding="utf-8")[:1500]
                rel_path = source_file.relative_to(project_path)
                parts.append(f"### {rel_path}\n```\n{content}\n```\n")
            except Exception:
                pass

        return "\n".join(parts)

    def _get_directory_structure(self, path: Path, max_depth: int = 3, prefix: str = "") -> str:
        """Get directory tree structure."""
        if max_depth <= 0:
            return ""

        lines = []

        try:
            entries = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            for entry in entries[:30]:  # Limit entries per level
                if entry.name.startswith(".") and entry.name not in {".github", ".gobby"}:
                    continue
                if entry.name in SKIP_DIRS:
                    continue

                if entry.is_dir():
                    lines.append(f"{prefix}{entry.name}/")
                    sub = self._get_directory_structure(entry, max_depth - 1, prefix + "  ")
                    if sub:
                        lines.append(sub)
                else:
                    lines.append(f"{prefix}{entry.name}")
        except PermissionError:
            pass

        return "\n".join(lines)

    async def _extract_with_llm(
        self,
        content: str,
        prompt_template: str,
        source: str,
    ) -> list[ExtractedMemory]:
        """
        Use LLM to extract memories from content.

        Args:
            content: Content to analyze
            prompt_template: Prompt template with {content} placeholder
            source: Source identifier for extracted memories

        Returns:
            List of extracted memories
        """
        if not self.llm_service:
            logger.warning("No LLM service available for extraction")
            return []

        try:
            # Get provider
            memory_config = self.memory_manager.config
            provider, model, _ = self.llm_service.get_provider_for_feature(memory_config)

            # Build prompt - support both {content} and {summary} placeholders
            try:
                prompt = prompt_template.format(content=content, summary=content)
            except KeyError:
                prompt = prompt_template.format(content=content)

            # Call LLM
            response = await provider.generate_text(prompt=prompt, model=model)

            # Parse response
            return self._parse_extraction_response(response, source)

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return []

    def _parse_extraction_response(self, response: str, source: str) -> list[ExtractedMemory]:
        """Parse LLM response into ExtractedMemory objects."""
        # Clean response
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse extraction JSON: {e}")
            return []

        if not isinstance(data, list):
            logger.warning(f"Expected list, got {type(data).__name__}")
            return []

        memories = []
        for item in data:
            if not isinstance(item, dict):
                continue

            content = item.get("content", "").strip()
            if not content or len(content) < 10:
                continue

            memory = ExtractedMemory(
                content=content,
                memory_type=item.get("memory_type", "fact"),
                importance=float(item.get("importance", 0.5)),
                tags=item.get("tags", []),
                source=source,
            )
            memories.append(memory)

        return memories

    async def _store_memories(
        self,
        memories: list[ExtractedMemory],
        result: ExtractionResult,
        project_id: str | None = None,
        source_session_id: str | None = None,
    ) -> None:
        """Store extracted memories, handling deduplication."""
        for memory in memories:
            # Check for duplicate content
            if self.memory_manager.content_exists(memory.content, project_id):
                result.skipped += 1
                logger.debug(f"Skipping duplicate: {memory.content[:50]}...")
                continue

            try:
                await self.memory_manager.remember(
                    content=memory.content,
                    memory_type=memory.memory_type,
                    importance=memory.importance,
                    project_id=project_id,
                    source_type=memory.source,
                    source_session_id=source_session_id,
                    tags=memory.tags,
                )
                result.created += 1
            except Exception as e:
                result.errors.append(f"Failed to store: {e}")
                logger.error(f"Failed to store memory: {e}")

    def find_similar_memories(
        self,
        content: str,
        threshold: float = 0.8,
        project_id: str | None = None,
    ) -> list[tuple[Any, float]]:
        """
        Find memories similar to the given content.

        Uses semantic search if available, falls back to text matching.

        Args:
            content: Content to find similar memories for
            threshold: Similarity threshold (0.0-1.0)
            project_id: Optional project filter

        Returns:
            List of (memory, similarity_score) tuples
        """
        # Check exact match first
        if self.memory_manager.content_exists(content, project_id):
            # Get the exact match
            memories = self.memory_manager.recall(query=content, limit=1)
            if memories:
                return [(memories[0], 1.0)]

        # Try semantic search if enabled
        if getattr(self.memory_manager.config, "semantic_search_enabled", False):
            try:
                results = self.memory_manager.recall(
                    query=content,
                    project_id=project_id,
                    limit=5,
                    use_semantic=True,
                )
                # Filter by threshold (note: recall doesn't return scores directly)
                # For now, return all results as potentially similar
                return [(m, 0.8) for m in results]
            except Exception:
                pass

        return []
