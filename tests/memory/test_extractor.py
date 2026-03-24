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
            tags=["test", "memory"],
        )
        result = candidate.to_dict()
        assert result == {
            "content": "Test memory content",
            "memory_type": "fact",
            "tags": ["test", "memory"],
        }

    def test_no_importance_field(self) -> None:
        """MemoryCandidate should not have an importance field."""
        candidate = MemoryCandidate(
            content="Test",
            memory_type="fact",
            tags=[],
        )
        assert not hasattr(candidate, "importance")
        assert "importance" not in candidate.to_dict()


class TestSessionMemoryExtractor:
    """Tests for SessionMemoryExtractor."""

    @pytest.fixture
    def mock_memory_manager(self):
        """Create a mock memory manager."""
        manager = MagicMock()
        manager.config.enabled = True
        manager.content_exists.return_value = False
        manager.create_memory = AsyncMock(return_value=MagicMock(id="mem-123"))
        return manager

    @pytest.fixture
    def mock_session_manager(self):
        """Create a mock session manager."""
        manager = MagicMock()
        session = MagicMock()
        session.project_id = "proj-123"
        session.transcript_path = None
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
    "tags": ["testing", "pytest"]
  },
  {
    "content": "User prefers explicit type hints",
    "memory_type": "preference",
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
        mock_loader = MagicMock()
        mock_loader.render.return_value = "Extract memories from this session. Return JSON array."
        return SessionMemoryExtractor(
            memory_manager=mock_memory_manager,
            session_manager=mock_session_manager,
            llm_service=mock_llm_service,
            prompt_loader=mock_loader,
        )

    def test_parse_llm_response_valid(self, extractor) -> None:
        """Test parsing valid LLM response."""
        response = """
```json
[
  {"content": "Test fact", "memory_type": "fact", "tags": ["test"]}
]
```
"""
        candidates = extractor._parse_llm_response(response)
        assert len(candidates) == 1
        assert candidates[0].content == "Test fact"
        assert candidates[0].memory_type == "fact"
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

    def test_parse_llm_response_jsonl_fallback(self, extractor) -> None:
        """Test JSONL fallback when objects lack commas between them."""
        response = """[
  {"content": "First memory", "memory_type": "fact", "tags": ["a"]}
  {"content": "Second memory", "memory_type": "pattern", "tags": ["b"]}
]"""
        candidates = extractor._parse_llm_response(response)
        assert len(candidates) == 2
        assert candidates[0].content == "First memory"
        assert candidates[0].memory_type == "fact"
        assert candidates[1].content == "Second memory"
        assert candidates[1].memory_type == "pattern"

    def test_parse_jsonl_fallback_method(self, extractor) -> None:
        """Test _parse_jsonl_fallback directly with various formats."""
        # Compact JSONL (no outer brackets)
        json_str = '{"content": "One", "tags": []}\n{"content": "Two", "tags": []}'
        candidates = extractor._parse_jsonl_fallback(json_str)
        assert len(candidates) == 2

    def test_parse_jsonl_fallback_with_invalid_fragments(self, extractor) -> None:
        """Test JSONL fallback skips invalid fragments gracefully."""
        # One valid object followed by a malformed one
        json_str = '[{"content": "Valid", "tags": []}\n{"broken: invalid json}]'
        candidates = extractor._parse_jsonl_fallback(json_str)
        assert len(candidates) == 1
        assert candidates[0].content == "Valid"

    def test_parse_llm_response_normalizes_types(self, extractor) -> None:
        """Test that invalid memory types are normalized to 'fact'."""
        response = '[{"content": "Test", "memory_type": "invalid"}]'
        candidates = extractor._parse_llm_response(response)
        assert len(candidates) == 1
        assert candidates[0].memory_type == "fact"

    def test_parse_llm_response_ignores_importance(self, extractor) -> None:
        """Test that importance field in LLM response is ignored."""
        response = '[{"content": "Test", "importance": 0.9, "tags": ["x"]}]'
        candidates = extractor._parse_llm_response(response)
        assert len(candidates) == 1
        assert not hasattr(candidates[0], "importance")

    def test_is_similar_high_overlap(self, extractor) -> None:
        """Test similarity detection with high overlap."""
        content1 = "Use pytest to test code in this project"
        content2 = "Use pytest to test code in this repo"
        assert extractor._is_similar(content1, content2, threshold=0.7) is True

    def test_is_similar_low_overlap(self, extractor) -> None:
        """Test similarity detection with low overlap."""
        content1 = "The project uses pytest for testing"
        content2 = "User prefers explicit type hints in code"
        assert extractor._is_similar(content1, content2) is False

    @pytest.mark.asyncio
    async def test_filter_and_dedupe_removes_existing(self, extractor, mock_memory_manager):
        """Test that existing memories are skipped."""
        mock_memory_manager.content_exists.side_effect = lambda c, p: c == "Existing"
        candidates = [
            MemoryCandidate("New", "fact", []),
            MemoryCandidate("Existing", "fact", []),
        ]
        filtered = await extractor._filter_and_dedupe(candidates, project_id=None)
        assert len(filtered) == 1
        assert filtered[0].content == "New"

    @pytest.mark.asyncio
    async def test_filter_and_dedupe_removes_batch_duplicates(self, extractor):
        """Test that similar candidates in the same batch are deduplicated."""
        candidates = [
            MemoryCandidate("The project uses pytest for testing", "fact", []),
            MemoryCandidate("The project uses pytest for testing", "fact", []),
        ]
        filtered = await extractor._filter_and_dedupe(candidates, project_id=None)
        assert len(filtered) == 1
        assert "pytest" in filtered[0].content

    @pytest.mark.asyncio
    async def test_extract_dry_run(self, extractor, mock_memory_manager, mock_session_manager):
        """Test extract with dry_run=True doesn't store memories."""
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
            mock_memory_manager.create_memory.assert_not_called()

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
            assert mock_memory_manager.create_memory.call_count == 2

    @pytest.mark.asyncio
    async def test_extract_no_session(self, extractor, mock_session_manager):
        """Test extract returns empty when session not found."""
        mock_session_manager.get.return_value = None
        candidates = await extractor.extract(session_id="nonexistent")
        assert len(candidates) == 0

    def test_parse_llm_response_empty_content_skipped(self, extractor) -> None:
        """Items with empty content are skipped."""
        response = '[{"content": "", "memory_type": "fact", "tags": []}]'
        candidates = extractor._parse_llm_response(response)
        assert len(candidates) == 0

    def test_parse_llm_response_non_dict_items_skipped(self, extractor) -> None:
        """Non-dict items in the array are skipped."""
        response = '["just a string", 42, null]'
        candidates = extractor._parse_llm_response(response)
        assert len(candidates) == 0

    def test_parse_llm_response_not_a_list(self, extractor) -> None:
        """Response that parses as dict instead of list returns empty."""
        response = '{"content": "test"}'
        candidates = extractor._parse_llm_response(response)
        assert len(candidates) == 0

    def test_parse_llm_response_tags_non_list(self, extractor) -> None:
        """Tags that are not a list are replaced with empty list."""
        response = '[{"content": "Test", "tags": "not-a-list"}]'
        candidates = extractor._parse_llm_response(response)
        assert len(candidates) == 1
        assert candidates[0].tags == []

    def test_parse_llm_response_tags_with_non_strings(self, extractor) -> None:
        """Tags with non-string elements are converted to strings."""
        response = '[{"content": "Test", "tags": [1, 2, 3]}]'
        candidates = extractor._parse_llm_response(response)
        assert len(candidates) == 1
        assert candidates[0].tags == ["1", "2", "3"]

    def test_parse_llm_response_valid_memory_types(self, extractor) -> None:
        """All valid memory types are preserved."""
        for mem_type in ("fact", "pattern", "preference", "context"):
            response = f'[{{"content": "Test", "memory_type": "{mem_type}"}}]'
            candidates = extractor._parse_llm_response(response)
            assert len(candidates) == 1
            assert candidates[0].memory_type == mem_type

    def test_is_similar_empty_content(self, extractor) -> None:
        """Empty content returns False for similarity."""
        assert extractor._is_similar("", "some words") is False
        assert extractor._is_similar("some words", "") is False
        assert extractor._is_similar("", "") is False

    def test_is_similar_identical(self, extractor) -> None:
        """Identical content returns True."""
        assert extractor._is_similar("exact same words", "exact same words") is True

    def test_is_similar_custom_threshold(self, extractor) -> None:
        """Custom threshold changes similarity detection."""
        content1 = "a b c d e f g"
        content2 = "a b c x y z w"
        # Default threshold 0.8 should be False
        assert extractor._is_similar(content1, content2, threshold=0.8) is False
        # Lower threshold 0.2 should be True
        assert extractor._is_similar(content1, content2, threshold=0.2) is True

    @pytest.mark.asyncio
    async def test_analyze_with_llm_error(self, extractor) -> None:
        """_analyze_with_llm returns empty list on error."""
        extractor.llm_service.get_default_provider().generate_text = AsyncMock(
            side_effect=RuntimeError("LLM error")
        )
        result = await extractor._analyze_with_llm("test prompt")
        assert result == []

    @pytest.mark.asyncio
    async def test_analyze_with_config_provider(
        self, mock_memory_manager, mock_session_manager
    ) -> None:
        """_analyze_with_llm uses config provider when available."""
        mock_llm_service = MagicMock()
        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(return_value='[{"content": "Test", "tags": []}]')
        mock_llm_service.get_provider_for_feature.return_value = (mock_provider, "model-1", {})
        mock_loader = MagicMock()
        mock_loader.render.return_value = "prompt"

        config = MagicMock()
        extractor = SessionMemoryExtractor(
            memory_manager=mock_memory_manager,
            session_manager=mock_session_manager,
            llm_service=mock_llm_service,
            prompt_loader=mock_loader,
            config=config,
        )
        result = await extractor._analyze_with_llm("test prompt")
        assert len(result) == 1
        mock_llm_service.get_provider_for_feature.assert_called_once_with(config)

    @pytest.mark.asyncio
    async def test_analyze_with_config_provider_fallback(
        self, mock_memory_manager, mock_session_manager
    ) -> None:
        """_analyze_with_llm falls back to default provider when config provider fails."""
        mock_llm_service = MagicMock()
        mock_llm_service.get_provider_for_feature.side_effect = ValueError("No provider")
        mock_provider = MagicMock()
        mock_provider.generate_text = AsyncMock(
            return_value='[{"content": "Fallback", "tags": []}]'
        )
        mock_llm_service.get_default_provider.return_value = mock_provider
        mock_loader = MagicMock()
        mock_loader.render.return_value = "prompt"

        config = MagicMock()
        extractor = SessionMemoryExtractor(
            memory_manager=mock_memory_manager,
            session_manager=mock_session_manager,
            llm_service=mock_llm_service,
            prompt_loader=mock_loader,
            config=config,
        )
        result = await extractor._analyze_with_llm("test prompt")
        assert len(result) == 1
        assert result[0].content == "Fallback"

    @pytest.mark.asyncio
    async def test_store_memories_with_null_project_id(
        self, extractor, mock_memory_manager
    ) -> None:
        """_store_memories logs warning when project_id is None."""
        candidates = [MemoryCandidate("Test memory", "fact", ["tag"])]
        await extractor._store_memories(candidates, session_id="sess-1", project_id=None)
        mock_memory_manager.create_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_memories_handles_create_error(
        self, extractor, mock_memory_manager
    ) -> None:
        """_store_memories handles individual memory creation failures."""
        mock_memory_manager.create_memory = AsyncMock(side_effect=RuntimeError("Create fail"))
        candidates = [MemoryCandidate("Test memory", "fact", ["tag"])]
        # Should not raise
        await extractor._store_memories(candidates, session_id="sess-1", project_id="proj-1")

    @pytest.mark.asyncio
    async def test_extract_no_candidates(self, extractor, mock_memory_manager) -> None:
        """Extract returns empty when LLM produces no candidates."""
        extractor.llm_service.get_default_provider().generate_text = AsyncMock(
            return_value="No memories found here."
        )
        with patch.object(extractor, "_get_session_context") as mock_ctx:
            mock_ctx.return_value = SessionContext(
                session_id="sess-1",
                project_id="proj-1",
                project_name="Test",
                task_refs="",
                files_modified="",
                tool_summary="",
                transcript_summary="Test transcript",
            )
            result = await extractor.extract(session_id="sess-1")
        assert result == []

    def test_parse_jsonl_fallback_empty_content_skipped(self, extractor) -> None:
        """JSONL fallback skips items with empty content."""
        json_str = '[{"content": "", "tags": []}]'
        result = extractor._parse_jsonl_fallback(json_str)
        assert len(result) == 0

    def test_parse_jsonl_fallback_invalid_memory_type(self, extractor) -> None:
        """JSONL fallback normalizes invalid memory types."""
        json_str = '[{"content": "Test", "memory_type": "invalid", "tags": []}]'
        result = extractor._parse_jsonl_fallback(json_str)
        assert len(result) == 1
        assert result[0].memory_type == "fact"

    def test_parse_jsonl_fallback_non_dict_skipped(self, extractor) -> None:
        """JSONL fallback skips non-dict items."""
        json_str = '["just a string"]'
        result = extractor._parse_jsonl_fallback(json_str)
        assert len(result) == 0

    def test_parse_jsonl_fallback_tags_non_list(self, extractor) -> None:
        """JSONL fallback handles tags that are not a list."""
        json_str = '[{"content": "Test", "tags": "notlist"}]'
        result = extractor._parse_jsonl_fallback(json_str)
        assert len(result) == 1
        assert result[0].tags == []


class TestGetSessionContext:
    """Tests for _get_session_context."""

    @pytest.fixture
    def mock_memory_manager(self):
        manager = MagicMock()
        manager.content_exists.return_value = False
        manager.create_memory = AsyncMock(return_value=MagicMock(id="mem-123"))
        return manager

    @pytest.fixture
    def mock_llm_service(self):
        service = MagicMock()
        provider = MagicMock()
        provider.generate_text = AsyncMock(return_value="[]")
        service.get_default_provider.return_value = provider
        return service

    @pytest.mark.asyncio
    async def test_session_not_found(self, mock_memory_manager, mock_llm_service) -> None:
        """Returns None when session not found."""
        mock_session_manager = MagicMock()
        mock_session_manager.get.return_value = None
        mock_loader = MagicMock()
        extractor = SessionMemoryExtractor(
            memory_manager=mock_memory_manager,
            session_manager=mock_session_manager,
            llm_service=mock_llm_service,
            prompt_loader=mock_loader,
        )
        result = await extractor._get_session_context("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_session_without_transcript(self, mock_memory_manager, mock_llm_service) -> None:
        """Returns context even without transcript path."""
        mock_session_manager = MagicMock()
        session = MagicMock()
        session.project_id = "proj-1"
        session.transcript_path = None
        mock_session_manager.get.return_value = session
        mock_loader = MagicMock()
        extractor = SessionMemoryExtractor(
            memory_manager=mock_memory_manager,
            session_manager=mock_session_manager,
            llm_service=mock_llm_service,
            prompt_loader=mock_loader,
        )
        result = await extractor._get_session_context("sess-1")
        assert result is not None
        assert result.session_id == "sess-1"
        assert result.transcript_summary == ""

    @pytest.mark.asyncio
    async def test_session_with_transcript(
        self, mock_memory_manager, mock_llm_service, tmp_path
    ) -> None:
        """Returns context with transcript data parsed."""
        import json

        transcript_file = tmp_path / "transcript.jsonl"
        turns = [
            {
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Edit", "input": {"file_path": "/tmp/foo.py"}},
                        {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                    ]
                }
            },
            {
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "update_task", "input": {"task_id": "task-1"}},
                    ]
                }
            },
        ]
        with open(transcript_file, "w") as f:
            for turn in turns:
                f.write(json.dumps(turn) + "\n")

        mock_session_manager = MagicMock()
        session = MagicMock()
        session.project_id = None
        session.transcript_path = str(transcript_file)
        mock_session_manager.get.return_value = session
        mock_loader = MagicMock()
        extractor = SessionMemoryExtractor(
            memory_manager=mock_memory_manager,
            session_manager=mock_session_manager,
            llm_service=mock_llm_service,
            prompt_loader=mock_loader,
        )
        result = await extractor._get_session_context("sess-1")
        assert result is not None
        assert "/tmp/foo.py" in result.files_modified
        assert "task-1" in result.task_refs
        assert "Edit" in result.tool_summary
        assert "Bash" in result.tool_summary

    @pytest.mark.asyncio
    async def test_session_with_transcript_processor(
        self, mock_memory_manager, mock_llm_service, tmp_path
    ) -> None:
        """Uses transcript_processor.extract_turns_since_clear when available."""
        import json

        transcript_file = tmp_path / "transcript.jsonl"
        turn = {"message": {"content": "hello"}}
        with open(transcript_file, "w") as f:
            f.write(json.dumps(turn) + "\n")

        mock_session_manager = MagicMock()
        session = MagicMock()
        session.project_id = "proj-1"
        session.transcript_path = str(transcript_file)
        mock_session_manager.get.return_value = session

        mock_processor = MagicMock()
        mock_processor.extract_turns_since_clear.return_value = [turn]

        mock_loader = MagicMock()
        extractor = SessionMemoryExtractor(
            memory_manager=mock_memory_manager,
            session_manager=mock_session_manager,
            llm_service=mock_llm_service,
            prompt_loader=mock_loader,
            transcript_processor=mock_processor,
        )
        result = await extractor._get_session_context("sess-1")
        assert result is not None
        mock_processor.extract_turns_since_clear.assert_called_once()


class TestLoadTranscript:
    """Tests for _load_transcript."""

    @pytest.fixture
    def extractor(self):
        mock_loader = MagicMock()
        return SessionMemoryExtractor(
            memory_manager=MagicMock(),
            session_manager=MagicMock(),
            llm_service=MagicMock(),
            prompt_loader=mock_loader,
        )

    def test_load_valid_transcript(self, extractor, tmp_path) -> None:
        """Load valid JSONL transcript."""
        import json

        path = tmp_path / "transcript.jsonl"
        with open(path, "w") as f:
            f.write(json.dumps({"message": "hello"}) + "\n")
            f.write(json.dumps({"message": "world"}) + "\n")
        result = extractor._load_transcript(str(path))
        assert len(result) == 2

    def test_load_nonexistent_file(self, extractor) -> None:
        """Load nonexistent file returns empty list."""
        result = extractor._load_transcript("/nonexistent/path.jsonl")
        assert result == []

    def test_load_empty_lines_skipped(self, extractor, tmp_path) -> None:
        """Empty lines in transcript are skipped."""
        import json

        path = tmp_path / "transcript.jsonl"
        with open(path, "w") as f:
            f.write(json.dumps({"message": "hello"}) + "\n")
            f.write("\n")
            f.write("  \n")
            f.write(json.dumps({"message": "world"}) + "\n")
        result = extractor._load_transcript(str(path))
        assert len(result) == 2
