"""Tests for MemoryExtractor class."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.config.app import MemoryConfig
from gobby.memory.extractor import ExtractedMemory, ExtractionResult, MemoryExtractor
from gobby.memory.manager import MemoryManager
from gobby.storage.database import LocalDatabase
from gobby.storage.migrations import run_migrations


@pytest.fixture
def db(tmp_path):
    database = LocalDatabase(tmp_path / "test.db")
    run_migrations(database)
    yield database
    database.close()


@pytest.fixture
def memory_manager(db):
    config = MemoryConfig()
    return MemoryManager(db, config)


@pytest.fixture
def mock_llm_service():
    """Create a mock LLM service."""
    service = MagicMock()
    provider = MagicMock()
    provider.generate_text = AsyncMock()
    service.get_provider_for_feature.return_value = (provider, "test-model", None)
    return service


@pytest.fixture
def extractor(memory_manager, mock_llm_service):
    return MemoryExtractor(memory_manager, mock_llm_service)


class TestExtractedMemory:
    def test_to_dict(self):
        memory = ExtractedMemory(
            content="Test content",
            memory_type="fact",
            importance=0.7,
            tags=["test"],
            source="session",
        )
        result = memory.to_dict()
        assert result["content"] == "Test content"
        assert result["memory_type"] == "fact"
        assert result["importance"] == 0.7
        assert result["tags"] == ["test"]
        assert result["source"] == "session"


class TestExtractionResult:
    def test_default_values(self):
        result = ExtractionResult()
        assert result.extracted == []
        assert result.created == 0
        assert result.skipped == 0
        assert result.errors == []


class TestMemoryExtractor:
    @pytest.mark.asyncio
    async def test_extract_from_session_creates_memories(self, extractor, mock_llm_service):
        """Test session extraction creates memories from LLM response."""
        # Mock LLM response
        mock_llm_service.get_provider_for_feature.return_value[0].generate_text.return_value = """
        [
            {"content": "Project uses Python 3.11", "memory_type": "fact", "importance": 0.7, "tags": ["python"]},
            {"content": "User prefers pytest", "memory_type": "preference", "importance": 0.6, "tags": ["testing"]}
        ]
        """

        result = await extractor.extract_from_session(
            summary="This session we worked on Python project using pytest for testing."
        )

        assert len(result.extracted) == 2
        assert result.created == 2
        assert result.skipped == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_extract_from_session_skips_short_summary(self, extractor):
        """Test that short summaries are rejected."""
        result = await extractor.extract_from_session(summary="Short")

        assert len(result.extracted) == 0
        assert "too short" in result.errors[0].lower()

    @pytest.mark.asyncio
    async def test_extract_from_session_handles_empty_response(self, extractor, mock_llm_service):
        """Test handling of empty LLM response."""
        mock_llm_service.get_provider_for_feature.return_value[0].generate_text.return_value = "[]"

        result = await extractor.extract_from_session(
            summary="This is a sufficiently long session summary with some content."
        )

        assert len(result.extracted) == 0
        assert result.created == 0

    @pytest.mark.asyncio
    async def test_extract_from_session_deduplicates(self, extractor, mock_llm_service, memory_manager):
        """Test that duplicate content is skipped."""
        # First, create an existing memory
        await memory_manager.remember(content="Project uses Python 3.11", importance=0.5)

        # Mock LLM response with duplicate
        mock_llm_service.get_provider_for_feature.return_value[0].generate_text.return_value = """
        [
            {"content": "Project uses Python 3.11", "memory_type": "fact", "importance": 0.7},
            {"content": "New unique fact", "memory_type": "fact", "importance": 0.6}
        ]
        """

        result = await extractor.extract_from_session(
            summary="This is a sufficiently long session summary with some content about Python."
        )

        assert result.created == 1  # Only new fact
        assert result.skipped == 1  # Duplicate skipped

    @pytest.mark.asyncio
    async def test_extract_from_agent_md_with_content(self, extractor, mock_llm_service):
        """Test extraction from agent MD content."""
        mock_llm_service.get_provider_for_feature.return_value[0].generate_text.return_value = """
        [
            {"content": "Always use type hints", "memory_type": "preference", "importance": 0.8}
        ]
        """

        result = await extractor.extract_from_agent_md(
            content="# Project Instructions\n\nAlways use type hints in Python code."
        )

        assert len(result.extracted) == 1
        assert result.created == 1

    @pytest.mark.asyncio
    async def test_extract_from_agent_md_file_not_found(self, extractor):
        """Test handling of missing file."""
        result = await extractor.extract_from_agent_md(file_path="/nonexistent/CLAUDE.md")

        assert result.created == 0
        assert "not found" in result.errors[0].lower()

    @pytest.mark.asyncio
    async def test_extract_from_agent_md_scans_project(self, extractor, mock_llm_service, tmp_path):
        """Test scanning project for all agent MD files."""
        # Create test files (need >50 chars to pass length check)
        (tmp_path / "CLAUDE.md").write_text(
            "# Claude Instructions\n\nThis project uses Python 3.11 with type hints everywhere."
        )
        (tmp_path / "GEMINI.md").write_text(
            "# Gemini Instructions\n\nThis project uses TypeScript with strict mode enabled."
        )

        # Use side_effect to return different content for each file to avoid deduplication
        call_count = [0]

        async def mock_generate(*args, **kwargs):
            call_count[0] += 1
            return f"""
            [{{"content": "Unique memory from file {call_count[0]}", "memory_type": "fact", "importance": 0.5}}]
            """

        mock_llm_service.get_provider_for_feature.return_value[0].generate_text = mock_generate

        result = await extractor.extract_from_agent_md(project_path=tmp_path)

        # Should have extracted from both files
        assert result.created == 2

    @pytest.mark.asyncio
    async def test_extract_from_codebase(self, extractor, mock_llm_service, tmp_path):
        """Test codebase pattern extraction."""
        # Create test project structure
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("def main():\n    print('hello')")
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        mock_llm_service.get_provider_for_feature.return_value[0].generate_text.return_value = """
        [{"content": "Project uses pyproject.toml", "memory_type": "fact", "importance": 0.6}]
        """

        result = await extractor.extract_from_codebase(project_path=tmp_path)

        assert result.created == 1

    @pytest.mark.asyncio
    async def test_extract_from_codebase_missing_path(self, extractor):
        """Test handling of missing project path."""
        result = await extractor.extract_from_codebase(project_path="/nonexistent/path")

        assert result.created == 0
        assert "not found" in result.errors[0].lower()

    @pytest.mark.asyncio
    async def test_parse_extraction_response_handles_json_in_code_block(self, extractor, mock_llm_service):
        """Test parsing of JSON wrapped in code blocks."""
        # Content must be at least 10 chars to pass validation in _parse_extraction_response
        mock_llm_service.get_provider_for_feature.return_value[0].generate_text.return_value = """```json
        [{"content": "Test content that is long enough", "memory_type": "fact", "importance": 0.5}]
        ```"""

        result = await extractor.extract_from_session(
            summary="This is a sufficiently long session summary for extraction."
        )

        assert len(result.extracted) == 1

    @pytest.mark.asyncio
    async def test_parse_extraction_response_handles_invalid_json(self, extractor, mock_llm_service):
        """Test handling of invalid JSON response."""
        mock_llm_service.get_provider_for_feature.return_value[0].generate_text.return_value = "not valid json"

        result = await extractor.extract_from_session(
            summary="This is a sufficiently long session summary for extraction."
        )

        assert len(result.extracted) == 0

    @pytest.mark.asyncio
    async def test_no_llm_service(self, memory_manager):
        """Test extraction without LLM service."""
        extractor = MemoryExtractor(memory_manager, llm_service=None)

        result = await extractor.extract_from_session(
            summary="This is a sufficiently long session summary for extraction."
        )

        assert len(result.extracted) == 0

    def test_analyze_codebase_structure(self, extractor, tmp_path):
        """Test codebase analysis produces structured output."""
        # Create test structure
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("# App code")
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        analysis = extractor._analyze_codebase(tmp_path, max_files=10)

        assert "Directory Structure" in analysis
        assert "pyproject.toml" in analysis

    def test_get_directory_structure(self, extractor, tmp_path):
        """Test directory tree generation."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").touch()
        (tmp_path / "tests").mkdir()

        structure = extractor._get_directory_structure(tmp_path, max_depth=2)

        assert "src/" in structure
        assert "tests/" in structure

    def test_get_directory_structure_skips_hidden(self, extractor, tmp_path):
        """Test that hidden directories are skipped."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "src").mkdir()

        structure = extractor._get_directory_structure(tmp_path, max_depth=2)

        assert ".git" not in structure
        assert "src/" in structure
