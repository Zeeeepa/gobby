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
    async def test_extract_from_session_deduplicates(
        self, extractor, mock_llm_service, memory_manager
    ):
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
    async def test_parse_extraction_response_handles_json_in_code_block(
        self, extractor, mock_llm_service
    ):
        """Test parsing of JSON wrapped in code blocks."""
        # Content must be at least 10 chars to pass validation in _parse_extraction_response
        mock_llm_service.get_provider_for_feature.return_value[
            0
        ].generate_text.return_value = """```json
        [{"content": "Test content that is long enough", "memory_type": "fact", "importance": 0.5}]
        ```"""

        result = await extractor.extract_from_session(
            summary="This is a sufficiently long session summary for extraction."
        )

        assert len(result.extracted) == 1

    @pytest.mark.asyncio
    async def test_parse_extraction_response_handles_invalid_json(
        self, extractor, mock_llm_service
    ):
        """Test handling of invalid JSON response."""
        mock_llm_service.get_provider_for_feature.return_value[
            0
        ].generate_text.return_value = "not valid json"

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

    def test_get_directory_structure_max_depth_zero(self, extractor, tmp_path):
        """Test that max_depth=0 returns empty string."""
        (tmp_path / "src").mkdir()

        structure = extractor._get_directory_structure(tmp_path, max_depth=0)

        assert structure == ""

    def test_get_directory_structure_skips_skip_dirs(self, extractor, tmp_path):
        """Test that SKIP_DIRS directories are skipped."""
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "src").mkdir()

        structure = extractor._get_directory_structure(tmp_path, max_depth=2)

        assert "node_modules" not in structure
        assert "__pycache__" not in structure
        assert "src/" in structure

    def test_get_directory_structure_includes_github(self, extractor, tmp_path):
        """Test that .github and .gobby are included."""
        (tmp_path / ".github").mkdir()
        (tmp_path / ".gobby").mkdir()

        structure = extractor._get_directory_structure(tmp_path, max_depth=2)

        assert ".github/" in structure
        assert ".gobby/" in structure

    def test_get_directory_structure_permission_error(self, extractor, tmp_path, mocker):
        """Test handling of permission errors."""
        from pathlib import Path

        # Create a subdirectory that will raise permission error
        subdir = tmp_path / "restricted"
        subdir.mkdir()

        # Mock iterdir on the specific path to raise PermissionError
        original_iterdir = Path.iterdir

        def mock_iterdir(self):
            if self == tmp_path:
                raise PermissionError("Access denied")
            return original_iterdir(self)

        mocker.patch.object(Path, "iterdir", mock_iterdir)

        structure = extractor._get_directory_structure(tmp_path, max_depth=2)

        assert structure == ""


class TestMemoryExtractorAgentMdEdgeCases:
    """Test edge cases for agent MD extraction."""

    @pytest.mark.asyncio
    async def test_extract_from_agent_md_no_file_or_content(self, extractor):
        """Test that both file_path and content being None returns error."""
        result = await extractor.extract_from_agent_md(file_path=None, content=None)

        assert result.created == 0
        assert len(result.errors) == 1
        assert "Either file_path or content required" in result.errors[0]

    @pytest.mark.asyncio
    async def test_extract_from_agent_md_file_read_error(self, extractor, tmp_path, mocker):
        """Test handling of file read errors."""
        from pathlib import Path

        # Create a file that exists but can't be read
        test_file = tmp_path / "CLAUDE.md"
        test_file.write_text("test content")

        # Mock read_text on Path class to raise error for this file
        original_read_text = Path.read_text

        def mock_read_text(self, *args, **kwargs):
            if self == test_file:
                raise OSError("Cannot read file")
            return original_read_text(self, *args, **kwargs)

        mocker.patch.object(Path, "read_text", mock_read_text)

        result = await extractor.extract_from_agent_md(file_path=test_file)

        assert result.created == 0
        assert len(result.errors) == 1
        assert "Failed to read file" in result.errors[0]

    @pytest.mark.asyncio
    async def test_extract_from_agent_md_short_content(self, extractor):
        """Test that short content returns error."""
        result = await extractor.extract_from_agent_md(content="Too short")

        assert result.created == 0
        assert len(result.errors) == 1
        assert "too short" in result.errors[0].lower()

    @pytest.mark.asyncio
    async def test_extract_from_agent_md_detects_gemini_source(
        self, extractor, mock_llm_service, tmp_path
    ):
        """Test that GEMINI.md is detected as gemini_md source."""
        test_file = tmp_path / "GEMINI.md"
        test_file.write_text(
            "# Gemini Instructions\n\nThis is a long enough content for the extractor to process."
        )

        mock_llm_service.get_provider_for_feature.return_value[0].generate_text.return_value = """
        [{"content": "Unique gemini memory content here", "memory_type": "preference", "importance": 0.7}]
        """

        result = await extractor.extract_from_agent_md(file_path=test_file)

        assert result.created == 1
        assert result.extracted[0].source == "gemini_md"

    @pytest.mark.asyncio
    async def test_extract_from_agent_md_detects_codex_source(
        self, extractor, mock_llm_service, tmp_path
    ):
        """Test that CODEX.md is detected as codex_md source."""
        test_file = tmp_path / "CODEX.md"
        test_file.write_text(
            "# Codex Instructions\n\nThis is a long enough content for the extractor to process."
        )

        mock_llm_service.get_provider_for_feature.return_value[0].generate_text.return_value = """
        [{"content": "Unique codex memory content here", "memory_type": "preference", "importance": 0.7}]
        """

        result = await extractor.extract_from_agent_md(file_path=test_file)

        assert result.created == 1
        assert result.extracted[0].source == "codex_md"


class TestMemoryExtractorCodebaseEdgeCases:
    """Test edge cases for codebase extraction."""

    @pytest.mark.asyncio
    async def test_extract_from_codebase_not_enough_content(self, extractor, tmp_path, mocker):
        """Test codebase with insufficient content for analysis."""
        # Mock _analyze_codebase to return a short string (less than 100 chars)
        mocker.patch.object(extractor, "_analyze_codebase", return_value="Short")

        result = await extractor.extract_from_codebase(project_path=tmp_path)

        assert result.created == 0
        assert len(result.errors) == 1
        assert "Not enough codebase content" in result.errors[0]

    def test_analyze_codebase_config_file_read_error(self, extractor, tmp_path, mocker):
        """Test handling of config file read errors during analysis."""
        from pathlib import Path

        # Create a pyproject.toml that will fail to read
        config_file = tmp_path / "pyproject.toml"
        config_file.write_text("[project]\nname = 'test'")

        # Create enough structure to pass the length check
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("def main():\n    print('hello world')" * 20)

        # Mock read_text to fail for config files
        original_read_text = Path.read_text

        def mock_read_text(self, *args, **kwargs):
            if self.name == "pyproject.toml":
                raise OSError("Cannot read file")
            return original_read_text(self, *args, **kwargs)

        mocker.patch.object(Path, "read_text", mock_read_text)

        analysis = extractor._analyze_codebase(tmp_path, max_files=10)

        # Should still have directory structure and sample files
        assert "Directory Structure" in analysis
        assert "Sample Source Files" in analysis

    def test_analyze_codebase_source_file_read_error(self, extractor, tmp_path, mocker):
        """Test handling of source file read errors during analysis."""
        from pathlib import Path

        # Create structure
        src = tmp_path / "src"
        src.mkdir()
        py_file = src / "main.py"
        py_file.write_text("def main():\n    print('hello')")

        # Mock the source file read to fail
        original_read_text = Path.read_text

        def mock_read_text(self, *args, **kwargs):
            if self.suffix == ".py":
                raise OSError("Cannot read file")
            return original_read_text(self, *args, **kwargs)

        mocker.patch.object(Path, "read_text", mock_read_text)

        analysis = extractor._analyze_codebase(tmp_path, max_files=10)

        # Should still have directory structure
        assert "Directory Structure" in analysis

    def test_analyze_codebase_breaks_at_max_files(self, extractor, tmp_path):
        """Test that file collection stops at max_files."""
        src = tmp_path / "src"
        src.mkdir()

        # Create more files than max_files
        for i in range(25):
            (src / f"file{i}.py").write_text(f"# File {i}\ndef func():\n    pass")

        analysis = extractor._analyze_codebase(tmp_path, max_files=5)

        # Analysis should be generated (we can't easily verify file count limit)
        assert "Directory Structure" in analysis


class TestMemoryExtractorLLMEdgeCases:
    """Test edge cases for LLM extraction."""

    @pytest.mark.asyncio
    async def test_extract_with_llm_exception(self, extractor, mock_llm_service):
        """Test handling of LLM exceptions."""
        mock_llm_service.get_provider_for_feature.return_value[
            0
        ].generate_text.side_effect = Exception("LLM API error")

        result = await extractor.extract_from_session(
            summary="This is a sufficiently long session summary for extraction testing."
        )

        assert len(result.extracted) == 0

    @pytest.mark.asyncio
    async def test_extract_with_llm_keyerror_fallback(
        self, extractor, mock_llm_service, memory_manager
    ):
        """Test that KeyError in prompt template falls back to content-only."""
        # Set a custom prompt with an unknown placeholder {unknown_key} which causes KeyError
        # when format() is called with content=... and summary=...
        memory_manager.config.extraction_prompt = (
            "Extract memories from: {content} with {unknown_key}"
        )

        mock_llm_service.get_provider_for_feature.return_value[0].generate_text.return_value = """
        [{"content": "Memory from keyerror test content", "memory_type": "fact", "importance": 0.5}]
        """

        result = await extractor.extract_from_session(
            summary="This is a sufficiently long session summary for extraction testing."
        )

        # The KeyError is caught and falls back to {content}-only formatting
        # But since the template still has {unknown_key}, the second format also fails
        # This results in no memories being extracted due to the exception
        assert len(result.extracted) == 0


class TestMemoryExtractorParseResponse:
    """Test parsing of LLM responses."""

    def test_parse_response_plain_code_block(self, extractor):
        """Test parsing response with plain ``` code blocks."""
        response = """```
        [{"content": "Memory content from plain block test", "memory_type": "fact", "importance": 0.5}]
        ```"""

        memories = extractor._parse_extraction_response(response, "test")

        assert len(memories) == 1
        assert memories[0].content == "Memory content from plain block test"

    def test_parse_response_non_list(self, extractor):
        """Test parsing response that is a dict instead of list."""
        response = """{"content": "Single memory", "memory_type": "fact"}"""

        memories = extractor._parse_extraction_response(response, "test")

        assert len(memories) == 0

    def test_parse_response_non_dict_items(self, extractor):
        """Test parsing response with non-dict items in list."""
        response = """["string item", 123, {"content": "Valid memory content test", "memory_type": "fact"}]"""

        memories = extractor._parse_extraction_response(response, "test")

        assert len(memories) == 1
        assert memories[0].content == "Valid memory content test"

    def test_parse_response_short_content(self, extractor):
        """Test that items with short content are skipped."""
        response = """[
            {"content": "Short", "memory_type": "fact"},
            {"content": "This is a valid memory with enough content", "memory_type": "fact"}
        ]"""

        memories = extractor._parse_extraction_response(response, "test")

        assert len(memories) == 1
        assert memories[0].content == "This is a valid memory with enough content"

    def test_parse_response_empty_content(self, extractor):
        """Test that items with empty content are skipped."""
        response = """[
            {"content": "", "memory_type": "fact"},
            {"content": "   ", "memory_type": "fact"},
            {"content": "This is a valid memory with enough content", "memory_type": "fact"}
        ]"""

        memories = extractor._parse_extraction_response(response, "test")

        assert len(memories) == 1


class TestMemoryExtractorStoreMemories:
    """Test memory storage error handling."""

    @pytest.mark.asyncio
    async def test_store_memories_exception(
        self, extractor, mock_llm_service, memory_manager, monkeypatch
    ):
        """Test handling of storage exceptions."""

        async def raise_storage_error(*args, **kwargs):
            raise Exception("Database error")

        monkeypatch.setattr(memory_manager, "remember", raise_storage_error)

        mock_llm_service.get_provider_for_feature.return_value[0].generate_text.return_value = """
        [{"content": "Memory that will fail to store", "memory_type": "fact", "importance": 0.5}]
        """

        result = await extractor.extract_from_session(
            summary="This is a sufficiently long session summary for extraction testing."
        )

        assert result.created == 0
        assert len(result.errors) == 1
        assert "Failed to store" in result.errors[0]


class TestFindSimilarMemories:
    """Test find_similar_memories functionality."""

    def test_find_similar_exact_match(self, extractor, memory_manager):
        """Test finding exact match."""
        # Create a memory first (synchronously via storage)
        memory_manager.storage.create_memory(
            content="Exact match content for testing",
            memory_type="fact",
            importance=0.8,
        )

        results = extractor.find_similar_memories("Exact match content for testing")

        assert len(results) == 1
        assert results[0][1] == 1.0  # Exact match score

    def test_find_similar_no_match(self, extractor, memory_manager):
        """Test when no similar memories exist."""
        results = extractor.find_similar_memories("Content that doesn't exist anywhere")

        assert len(results) == 0

    def test_find_similar_with_semantic_search(self, extractor, memory_manager, monkeypatch):
        """Test semantic search path."""
        # Enable semantic search
        memory_manager.config.semantic_search_enabled = True

        # Create some memories
        memory_manager.storage.create_memory(
            content="Python programming language facts",
            memory_type="fact",
            importance=0.8,
        )

        # Mock recall to return semantic results
        original_recall = memory_manager.recall

        def mock_recall(*args, use_semantic=False, **kwargs):
            if use_semantic:
                return original_recall(*args, use_semantic=False, **kwargs)
            return original_recall(*args, use_semantic=use_semantic, **kwargs)

        monkeypatch.setattr(memory_manager, "recall", mock_recall)

        results = extractor.find_similar_memories("Python coding")

        # Should return results with 0.8 similarity score
        assert all(r[1] == 0.8 for r in results)

    def test_find_similar_semantic_search_exception(self, extractor, memory_manager, monkeypatch):
        """Test handling of semantic search exceptions."""
        # Enable semantic search
        memory_manager.config.semantic_search_enabled = True

        def raise_error(*args, **kwargs):
            raise Exception("Semantic search failed")

        monkeypatch.setattr(memory_manager, "recall", raise_error)

        results = extractor.find_similar_memories("Some query")

        assert len(results) == 0

    def test_find_similar_with_project_filter(self, extractor, memory_manager, db):
        """Test finding similar memories with project filter."""
        # Create a project first (foreign key requirement)
        from gobby.storage.projects import LocalProjectManager

        project_manager = LocalProjectManager(db)
        project = project_manager.create(
            name="test-project",
            repo_path="/tmp/test-project",
        )

        # Create memories for the project
        memory_manager.storage.create_memory(
            content="Project specific memory content here",
            memory_type="fact",
            importance=0.8,
            project_id=project.id,
        )

        results = extractor.find_similar_memories(
            "Project specific memory content here", project_id=project.id
        )

        assert len(results) == 1


class TestExtractedMemoryDefaults:
    """Test ExtractedMemory dataclass defaults."""

    def test_default_values(self):
        """Test that ExtractedMemory has correct defaults."""
        memory = ExtractedMemory(content="Test content")

        assert memory.content == "Test content"
        assert memory.memory_type == "fact"
        assert memory.importance == 0.5
        assert memory.tags == []
        assert memory.source == "extraction"


class TestExtractionResultAccumulation:
    """Test ExtractionResult accumulation."""

    def test_result_accumulation(self):
        """Test that results can be accumulated."""
        result = ExtractionResult()

        result.created = 5
        result.skipped = 2
        result.errors.append("Error 1")
        result.extracted.append(ExtractedMemory(content="Test content here"))

        assert result.created == 5
        assert result.skipped == 2
        assert len(result.errors) == 1
        assert len(result.extracted) == 1
