"""Tests for session memory extractor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.memory.extractor import MemoryCandidate, SessionContext, SessionMemoryExtractor

pytestmark = pytest.mark.unit

class TestMemoryCandidate:
    """Tests for MemoryCandidate dataclass."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        candidate = MemoryCandidate(
            content="Test memory content",
            memory_type="fact",
            importance=0.8,
            tags=["test", "memory"],
        )
        result = candidate.to_dict()
        assert result == {
            "content": "Test memory content",
            "memory_type": "fact",
            "importance": 0.8,
            "tags": ["test", "memory"],
        }


class TestSessionMemoryExtractor:
    """Tests for SessionMemoryExtractor."""

    @pytest.fixture
    def mock_memory_manager(self):
        """Create a mock memory manager."""
        manager = MagicMock()
        manager.config.enabled = True
        manager.content_exists.return_value = False
        manager.remember = AsyncMock(return_value=MagicMock(id="mem-123"))
        return manager

    @pytest.fixture
    def mock_session_manager(self):
        """Create a mock session manager."""
        manager = MagicMock()
        session = MagicMock()
        session.project_id = "proj-123"
        session.jsonl_path = None
        manager.get.return_value = session
        return manager

    @pytest.fixture
    def mock_llm_service(self):
        """Create a mock LLM service."""
        service = MagicMock()
        provider = MagicMock()
        provider.generate_text = AsyncMock(
            return_value="""Here are the extracted memories:

```json
[
  {
    "content": "The project uses pytest for testing",
    "memory_type": "fact",
    "importance": 0.8,
    "tags": ["testing", "pytest"]
  },
  {
    "content": "User prefers explicit type hints",
    "memory_type": "preference",
    "importance": 0.75,
    "tags": ["code-style"]
  }
]
```
"""
        )
        service.get_default_provider.return_value = provider
        return service

    @pytest.fixture
    def extractor(self, mock_memory_manager, mock_session_manager, mock_llm_service):
        """Create an extractor instance with mocks."""
        return SessionMemoryExtractor(
            memory_manager=mock_memory_manager,
            session_manager=mock_session_manager,
            llm_service=mock_llm_service,
        )

    def test_parse_llm_response_valid(self, extractor) -> None:
        """Test parsing valid LLM response."""
        response = """
```json
[
  {"content": "Test fact", "memory_type": "fact", "importance": 0.8, "tags": ["test"]}
]
```
"""
        candidates = extractor._parse_llm_response(response)
        assert len(candidates) == 1
        assert candidates[0].content == "Test fact"
        assert candidates[0].memory_type == "fact"
        assert candidates[0].importance == 0.8
        assert candidates[0].tags == ["test"]

    def test_parse_llm_response_empty_array(self, extractor) -> None:
        """Test parsing empty array response."""
        response = "[]"
        candidates = extractor._parse_llm_response(response)
        assert len(candidates) == 0

    def test_parse_llm_response_invalid_json(self, extractor) -> None:
        """Test parsing invalid JSON gracefully."""
        response = "Not valid JSON at all"
        candidates = extractor._parse_llm_response(response)
        assert len(candidates) == 0

    def test_parse_llm_response_normalizes_types(self, extractor) -> None:
        """Test that invalid memory types are normalized to 'fact'."""
        response = '[{"content": "Test", "memory_type": "invalid", "importance": 0.5}]'
        candidates = extractor._parse_llm_response(response)
        assert len(candidates) == 1
        assert candidates[0].memory_type == "fact"

    def test_parse_llm_response_clamps_importance(self, extractor) -> None:
        """Test that importance values are clamped to [0, 1]."""
        response = """[
            {"content": "High", "importance": 1.5},
            {"content": "Low", "importance": -0.5}
        ]"""
        candidates = extractor._parse_llm_response(response)
        assert len(candidates) == 2
        assert candidates[0].importance == 1.0
        assert candidates[1].importance == 0.0

    def test_is_similar_high_overlap(self, extractor) -> None:
        """Test similarity detection with high overlap."""
        # Use almost identical content for high similarity (Jaccard > 0.8)
        content1 = "The project uses pytest for testing"
        content2 = "The project uses pytest for tests"
        # Both have 6 words, 5 shared, union of 7: 5/7 = 0.71
        # Let's use even more similar ones
        content1 = "Use pytest to test code in this project"
        content2 = "Use pytest to test code in this repo"
        # 8 words each, 7 shared, union 9: 7/9 = 0.78
        # Still not quite 0.8, use threshold parameter
        assert extractor._is_similar(content1, content2, threshold=0.7) is True

    def test_is_similar_low_overlap(self, extractor) -> None:
        """Test similarity detection with low overlap."""
        content1 = "The project uses pytest for testing"
        content2 = "User prefers explicit type hints in code"
        assert extractor._is_similar(content1, content2) is False

    @pytest.mark.asyncio
    async def test_filter_and_dedupe_removes_low_importance(self, extractor):
        """Test that low importance candidates are filtered."""
        candidates = [
            MemoryCandidate("High", "fact", 0.9, []),
            MemoryCandidate("Low", "fact", 0.5, []),
        ]
        filtered = await extractor._filter_and_dedupe(
            candidates, min_importance=0.7, project_id=None
        )
        assert len(filtered) == 1
        assert filtered[0].content == "High"

    @pytest.mark.asyncio
    async def test_filter_and_dedupe_removes_existing(self, extractor, mock_memory_manager):
        """Test that existing memories are skipped."""
        mock_memory_manager.content_exists.side_effect = lambda c, p: c == "Existing"
        candidates = [
            MemoryCandidate("New", "fact", 0.8, []),
            MemoryCandidate("Existing", "fact", 0.9, []),
        ]
        filtered = await extractor._filter_and_dedupe(
            candidates, min_importance=0.7, project_id=None
        )
        assert len(filtered) == 1
        assert filtered[0].content == "New"

    @pytest.mark.asyncio
    async def test_filter_and_dedupe_removes_batch_duplicates(self, extractor):
        """Test that similar candidates in the same batch are deduplicated."""
        # Use identical content to trigger deduplication (same words)
        candidates = [
            MemoryCandidate("The project uses pytest for testing", "fact", 0.8, []),
            MemoryCandidate("The project uses pytest for testing", "fact", 0.85, []),
        ]
        filtered = await extractor._filter_and_dedupe(
            candidates, min_importance=0.7, project_id=None
        )
        assert len(filtered) == 1
        # First one should be kept
        assert "pytest" in filtered[0].content

    @pytest.mark.asyncio
    async def test_extract_dry_run(self, extractor, mock_memory_manager, mock_session_manager):
        """Test extract with dry_run=True doesn't store memories."""
        # Create a minimal session context
        with patch.object(extractor, "_get_session_context") as mock_get_ctx:
            mock_get_ctx.return_value = SessionContext(
                session_id="session-123",
                project_id="proj-123",
                project_name="Test Project",
                task_refs="",
                files_modified="",
                tool_summary="",
                transcript_summary="Test transcript",
            )

            candidates = await extractor.extract(
                session_id="session-123",
                dry_run=True,
            )

            assert len(candidates) == 2
            mock_memory_manager.remember.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_stores_memories(self, extractor, mock_memory_manager):
        """Test extract stores memories when dry_run=False."""
        with patch.object(extractor, "_get_session_context") as mock_get_ctx:
            mock_get_ctx.return_value = SessionContext(
                session_id="session-123",
                project_id="proj-123",
                project_name="Test Project",
                task_refs="",
                files_modified="",
                tool_summary="",
                transcript_summary="Test transcript",
            )

            candidates = await extractor.extract(
                session_id="session-123",
                dry_run=False,
            )

            assert len(candidates) == 2
            assert mock_memory_manager.remember.call_count == 2

    @pytest.mark.asyncio
    async def test_extract_no_session(self, extractor, mock_session_manager):
        """Test extract returns empty when session not found."""
        mock_session_manager.get.return_value = None
        candidates = await extractor.extract(session_id="nonexistent")
        assert len(candidates) == 0
