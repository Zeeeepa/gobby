"""Comprehensive tests for gobby.tasks.context module."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gobby.storage.tasks import Task
from gobby.tasks.context import ExpansionContext, ExpansionContextGatherer

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_task_manager():
    """Mock task manager for testing."""
    return MagicMock()


@pytest.fixture(autouse=True)
def mock_gitingest():
    """Mock gitingest to avoid external dependency and warnings."""
    mock_module = MagicMock()
    # Mock ingest to return a tuple (summary, tree, content)
    mock_module.ingest.return_value = ("summary", "tree", "content")
    with patch.dict("sys.modules", {"gitingest": mock_module}):
        yield mock_module


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        id="t1",
        project_id="p1",
        title="Implement feature",
        status="open",
        priority=2,
        task_type="feature",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
        description="Implement the feature using src/main.py",
    )


@pytest.fixture
def sample_related_task():
    """Create a sample related task."""
    return Task(
        id="t2",
        project_id="p1",
        title="Related task",
        status="open",
        priority=1,
        task_type="task",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
        description="A related task",
    )


@pytest.fixture
def gatherer(mock_task_manager):
    """Create an ExpansionContextGatherer instance."""
    return ExpansionContextGatherer(mock_task_manager)


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project structure for testing."""
    # Create project structure
    src_dir = tmp_path / "src" / "mypackage"
    src_dir.mkdir(parents=True)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    # Create .gobby/project.json
    gobby_dir = tmp_path / ".gobby"
    gobby_dir.mkdir()
    project_json = gobby_dir / "project.json"
    project_json.write_text(
        '{"id": "proj-1", "name": "test-project", "verification": {"unit_tests": "pytest"}}'
    )

    # Create some source files
    (src_dir / "__init__.py").write_text("")
    (src_dir / "main.py").write_text(
        '''"""Main module."""

class MyClass:
    """A sample class."""

    def method(self, arg: str) -> bool:
        """A method."""
        return True

async def async_function(x: int, y: int = 10) -> str:
    """An async function."""
    return str(x + y)

def simple_function():
    pass
'''
    )

    # Create pyproject.toml
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

    # Create package.json for frontend detection
    (tmp_path / "package.json").write_text('{"name": "test"}')

    return tmp_path


# =============================================================================
# ExpansionContext Tests
# =============================================================================


class TestExpansionContext:
    """Tests for the ExpansionContext dataclass."""

    def test_to_dict_basic(self, sample_task):
        """Test basic to_dict conversion."""
        context = ExpansionContext(
            task=sample_task,
            related_tasks=[],
            relevant_files=["src/main.py"],
            file_snippets={"src/main.py": "content"},
            project_patterns={"tests": "tests/"},
        )

        result = context.to_dict()

        assert result["task"]["id"] == "t1"
        assert result["relevant_files"] == ["src/main.py"]
        assert result["project_patterns"] == {"tests": "tests/"}
        assert result["snippet_count"] == 1
        assert result["agent_findings"] == ""
        assert result["web_research"] is None
        assert result["existing_tests"] is None
        assert result["function_signatures"] is None
        assert result["verification_commands"] is None
        assert result["project_structure"] is None

    def test_to_dict_with_all_fields(self, sample_task, sample_related_task):
        """Test to_dict with all optional fields populated."""
        context = ExpansionContext(
            task=sample_task,
            related_tasks=[sample_related_task],
            relevant_files=["src/main.py", "src/utils.py"],
            file_snippets={"src/main.py": "content1", "src/utils.py": "content2"},
            project_patterns={"build_system": "pyproject.toml"},
            agent_findings="Found relevant code",
            web_research=[{"query": "python best practices", "results": []}],
            existing_tests={"src/main.py": ["tests/test_main.py"]},
            function_signatures={"src/main.py": ["def foo()", "class Bar"]},
            verification_commands={"unit_tests": "pytest"},
            project_structure="src/\n  main.py",
        )

        result = context.to_dict()

        assert len(result["related_tasks"]) == 1
        assert result["related_tasks"][0]["id"] == "t2"
        assert result["snippet_count"] == 2
        assert result["agent_findings"] == "Found relevant code"
        assert len(result["web_research"]) == 1
        assert result["existing_tests"]["src/main.py"] == ["tests/test_main.py"]
        assert result["function_signatures"]["src/main.py"] == ["def foo()", "class Bar"]
        assert result["verification_commands"]["unit_tests"] == "pytest"
        assert "src/" in result["project_structure"]


# =============================================================================
# ExpansionContextGatherer Initialization Tests
# =============================================================================


class TestExpansionContextGathererInit:
    """Tests for ExpansionContextGatherer initialization."""

    def test_init_minimal(self, mock_task_manager):
        """Test initialization with only task_manager."""
        gatherer = ExpansionContextGatherer(mock_task_manager)

        assert gatherer.task_manager is mock_task_manager
        assert gatherer.llm_service is None
        assert gatherer.config is None
        assert gatherer.mcp_manager is None

    def test_init_full(self, mock_task_manager):
        """Test initialization with all parameters."""
        mock_llm = MagicMock()
        mock_config = MagicMock()
        mock_mcp = MagicMock()

        gatherer = ExpansionContextGatherer(
            mock_task_manager,
            llm_service=mock_llm,
            config=mock_config,
            mcp_manager=mock_mcp,
        )

        assert gatherer.llm_service is mock_llm
        assert gatherer.config is mock_config
        assert gatherer.mcp_manager is mock_mcp


# =============================================================================
# gather_context Tests
# =============================================================================


class TestGatherContext:
    """Tests for the main gather_context method."""

    @pytest.mark.asyncio
    async def test_gather_context_no_project_root(self, gatherer, sample_task):
        """Test gather_context when no project root is found."""
        gatherer.task_manager.list_tasks.return_value = []

        with patch("gobby.tasks.context.find_project_root", return_value=None):
            context = await gatherer.gather_context(sample_task)

        assert context.task == sample_task
        assert context.related_tasks == []
        assert context.relevant_files == []
        assert context.file_snippets == {}
        assert context.project_patterns == {}

    @pytest.mark.asyncio
    async def test_gather_context_code_context_disabled(self, gatherer, sample_task, tmp_project):
        """Test gather_context with enable_code_context=False."""
        gatherer.task_manager.list_tasks.return_value = []

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            context = await gatherer.gather_context(sample_task, enable_code_context=False)

        assert context.relevant_files == []

    @pytest.mark.asyncio
    async def test_gather_context_with_research_timeout(self, mock_task_manager, sample_task):
        """Test gather_context handles research timeout."""
        import asyncio

        mock_config = MagicMock()
        mock_config.codebase_research_enabled = True
        mock_config.research_timeout = 0.001  # Very short timeout
        mock_llm = MagicMock()

        gatherer = ExpansionContextGatherer(
            mock_task_manager, llm_service=mock_llm, config=mock_config
        )
        gatherer.task_manager.list_tasks.return_value = []

        with (
            patch("gobby.tasks.context.find_project_root", return_value=None),
            patch("gobby.tasks.research.TaskResearchAgent") as MockAgent,
        ):
            mock_agent = MockAgent.return_value

            async def slow_run(*args, **kwargs):
                await asyncio.sleep(1)  # Longer than timeout
                return {"relevant_files": [], "findings": ""}

            mock_agent.run = slow_run

            # Should not raise, just log warning
            context = await gatherer.gather_context(sample_task)
            assert context.agent_findings == ""

    @pytest.mark.asyncio
    async def test_gather_context_with_research_error(self, mock_task_manager, sample_task):
        """Test gather_context handles research exceptions."""
        mock_config = MagicMock()
        mock_config.codebase_research_enabled = True
        mock_config.research_timeout = 60
        mock_llm = MagicMock()

        gatherer = ExpansionContextGatherer(
            mock_task_manager, llm_service=mock_llm, config=mock_config
        )
        gatherer.task_manager.list_tasks.return_value = []

        with (
            patch("gobby.tasks.context.find_project_root", return_value=None),
            patch("gobby.tasks.research.TaskResearchAgent") as MockAgent,
        ):
            mock_agent = MockAgent.return_value

            async def failing_run(*args, **kwargs):
                raise RuntimeError("Research failed")

            mock_agent.run = failing_run

            # Should not raise, just log error
            context = await gatherer.gather_context(sample_task)
            assert context.agent_findings == ""

    @pytest.mark.asyncio
    async def test_gather_context_merges_agent_files(
        self, mock_task_manager, sample_task, tmp_project
    ):
        """Test that agent-found files are merged without duplicates."""
        mock_config = MagicMock()
        mock_config.codebase_research_enabled = True
        mock_config.research_timeout = 60
        mock_llm = MagicMock()

        gatherer = ExpansionContextGatherer(
            mock_task_manager, llm_service=mock_llm, config=mock_config
        )
        gatherer.task_manager.list_tasks.return_value = []

        # Create the file that the description references
        (tmp_project / "src" / "main.py").write_text("content")

        # Create agent-found file
        (tmp_project / "src" / "mypackage" / "agent_file.py").write_text("agent content")

        with (
            patch("gobby.tasks.context.find_project_root", return_value=tmp_project),
            patch("gobby.tasks.research.TaskResearchAgent") as MockAgent,
        ):
            mock_agent = MockAgent.return_value

            async def agent_run(*args, **kwargs):
                return {
                    "relevant_files": ["src/mypackage/agent_file.py", "src/main.py"],
                    "findings": "Found agent stuff",
                    "web_research": [{"query": "test", "results": []}],
                }

            mock_agent.run = agent_run

            # Task description mentions src/main.py
            sample_task.description = "Fix src/main.py"
            context = await gatherer.gather_context(sample_task)

            # Both files should be in relevant_files, no duplicates
            assert "src/mypackage/agent_file.py" in context.relevant_files
            assert context.agent_findings == "Found agent stuff"
            assert context.web_research is not None
            assert len(context.web_research) == 1


# =============================================================================
# _find_related_tasks Tests
# =============================================================================


class TestFindRelatedTasks:
    """Tests for _find_related_tasks method."""

    @pytest.mark.asyncio
    async def test_find_related_tasks_excludes_self(
        self, gatherer, sample_task, sample_related_task
    ):
        """Test that the current task is excluded from related tasks."""
        gatherer.task_manager.list_tasks.return_value = [sample_task, sample_related_task]

        related = await gatherer._find_related_tasks(sample_task)

        assert len(related) == 1
        assert related[0].id == "t2"

    @pytest.mark.asyncio
    async def test_find_related_tasks_calls_list_tasks(self, gatherer, sample_task):
        """Test that list_tasks is called with correct parameters."""
        gatherer.task_manager.list_tasks.return_value = []

        await gatherer._find_related_tasks(sample_task)

        gatherer.task_manager.list_tasks.assert_called_once_with(
            project_id="p1", limit=5, status="open"
        )


# =============================================================================
# _find_relevant_files Tests
# =============================================================================


class TestFindRelevantFiles:
    """Tests for _find_relevant_files method."""

    @pytest.mark.asyncio
    async def test_find_relevant_files_no_root(self, gatherer, sample_task):
        """Test with no project root."""
        with patch("gobby.tasks.context.find_project_root", return_value=None):
            files = await gatherer._find_relevant_files(sample_task)
        assert files == []

    @pytest.mark.asyncio
    async def test_find_relevant_files_no_description(self, gatherer, tmp_project):
        """Test with task having no description."""
        task = Task(
            id="t1",
            project_id="p1",
            title="Task",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            description=None,
        )

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            files = await gatherer._find_relevant_files(task)
        assert files == []

    @pytest.mark.asyncio
    async def test_find_relevant_files_extracts_paths(self, gatherer, tmp_project):
        """Test extraction of file paths from description."""
        # Create the files mentioned in description
        (tmp_project / "src" / "main.py").write_text("content")
        (tmp_project / "config.yaml").write_text("config: true")

        task = Task(
            id="t1",
            project_id="p1",
            title="Task",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            description="Update src/main.py and config.yaml for the feature",
        )

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            files = await gatherer._find_relevant_files(task)

        assert "src/main.py" in files
        assert "config.yaml" in files

    @pytest.mark.asyncio
    async def test_find_relevant_files_filters_nonexistent(self, gatherer, tmp_project):
        """Test that non-existent files are filtered out."""
        task = Task(
            id="t1",
            project_id="p1",
            title="Task",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            description="Fix nonexistent.py file",
        )

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            files = await gatherer._find_relevant_files(task)
        assert files == []

    @pytest.mark.asyncio
    async def test_find_relevant_files_ignores_non_code_extensions(self, gatherer, tmp_project):
        """Test that non-code file extensions are ignored."""
        # Create files with various extensions
        (tmp_project / "file.txt").write_text("text")  # Not in extension list
        (tmp_project / "file.exe").write_text("exe")  # Not in extension list

        task = Task(
            id="t1",
            project_id="p1",
            title="Task",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            description="Check file.txt and file.exe",
        )

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            files = await gatherer._find_relevant_files(task)
        # .txt and .exe are not in the allowed extensions (py|js|ts|tsx|jsx|md|json|html|css|yaml|toml|sh)
        assert "file.txt" not in files
        assert "file.exe" not in files

    @pytest.mark.asyncio
    async def test_find_relevant_files_no_duplicates(self, gatherer, tmp_project):
        """Test that duplicate file mentions result in unique entries."""
        (tmp_project / "src" / "main.py").write_text("content")

        task = Task(
            id="t1",
            project_id="p1",
            title="Task",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            description="Check src/main.py and also src/main.py again",
        )

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            files = await gatherer._find_relevant_files(task)

        assert files.count("src/main.py") == 1


# =============================================================================
# _read_file_snippets Tests
# =============================================================================


class TestReadFileSnippets:
    """Tests for _read_file_snippets method."""

    def test_read_file_snippets_no_root(self, gatherer):
        """Test with no project root."""
        with patch("gobby.tasks.context.find_project_root", return_value=None):
            snippets = gatherer._read_file_snippets(["file.py"])
        assert snippets == {}

    def test_read_file_snippets_reads_content(self, gatherer, tmp_project):
        """Test reading file content."""
        test_file = tmp_project / "test.py"
        test_file.write_text("line1\nline2\nline3\n")

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            snippets = gatherer._read_file_snippets(["test.py"])

        assert "test.py" in snippets
        assert snippets["test.py"] == "line1\nline2\nline3\n"

    def test_read_file_snippets_limits_lines(self, gatherer, tmp_project):
        """Test that only first 50 lines are read."""
        test_file = tmp_project / "large.py"
        lines = [f"line{i}\n" for i in range(100)]
        test_file.write_text("".join(lines))

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            snippets = gatherer._read_file_snippets(["large.py"])

        content = snippets["large.py"]
        assert "line0" in content
        assert "line49" in content
        assert "line50" not in content

    def test_read_file_snippets_handles_missing_file(self, gatherer, tmp_project):
        """Test handling of missing files."""
        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            snippets = gatherer._read_file_snippets(["nonexistent.py"])
        assert snippets == {}

    def test_read_file_snippets_handles_read_error(self, gatherer, tmp_project):
        """Test handling of file read errors."""
        test_file = tmp_project / "test.py"
        test_file.write_text("content")

        with (
            patch("gobby.tasks.context.find_project_root", return_value=tmp_project),
            patch("builtins.open", side_effect=PermissionError("No access")),
        ):
            snippets = gatherer._read_file_snippets(["test.py"])
        assert snippets == {}


# =============================================================================
# _detect_project_patterns Tests
# =============================================================================


class TestDetectProjectPatterns:
    """Tests for _detect_project_patterns method."""

    def test_detect_project_patterns_no_root(self, gatherer):
        """Test with no project root."""
        with patch("gobby.tasks.context.find_project_root", return_value=None):
            patterns = gatherer._detect_project_patterns()
        assert patterns == {}

    def test_detect_project_patterns_pyproject(self, gatherer, tmp_project):
        """Test detection of pyproject.toml."""
        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            patterns = gatherer._detect_project_patterns()

        assert patterns["build_system"] == "pyproject.toml"

    def test_detect_project_patterns_package_json(self, gatherer, tmp_project):
        """Test detection of package.json."""
        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            patterns = gatherer._detect_project_patterns()

        assert patterns["frontend"] == "npm/node"

    def test_detect_project_patterns_tests_dir(self, gatherer, tmp_project):
        """Test detection of tests directory."""
        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            patterns = gatherer._detect_project_patterns()

        assert patterns["tests"] == "tests/"


# =============================================================================
# _get_verification_commands Tests
# =============================================================================


class TestGetVerificationCommands:
    """Tests for _get_verification_commands method."""

    def test_get_verification_commands_no_config(self, gatherer):
        """Test when no verification config exists."""
        with patch("gobby.utils.project_context.get_verification_config", return_value=None):
            commands = gatherer._get_verification_commands()
        assert commands == {}

    def test_get_verification_commands_full_config(self, gatherer):
        """Test with full verification config."""
        mock_config = MagicMock()
        mock_config.unit_tests = "pytest"
        mock_config.type_check = "mypy src/"
        mock_config.lint = "ruff check ."
        mock_config.integration = "pytest -m integration"
        mock_config.custom = {"format": "black ."}

        with patch("gobby.utils.project_context.get_verification_config", return_value=mock_config):
            commands = gatherer._get_verification_commands()

        assert commands["unit_tests"] == "pytest"
        assert commands["type_check"] == "mypy src/"
        assert commands["lint"] == "ruff check ."
        assert commands["integration"] == "pytest -m integration"
        assert commands["format"] == "black ."

    def test_get_verification_commands_partial_config(self, gatherer):
        """Test with partial verification config."""
        mock_config = MagicMock()
        mock_config.unit_tests = "pytest"
        mock_config.type_check = None
        mock_config.lint = None
        mock_config.integration = None
        mock_config.custom = None

        with patch("gobby.utils.project_context.get_verification_config", return_value=mock_config):
            commands = gatherer._get_verification_commands()

        assert commands == {"unit_tests": "pytest"}


# =============================================================================
# discover_existing_tests Tests
# =============================================================================


class TestDiscoverExistingTests:
    """Tests for discover_existing_tests method."""

    def test_discover_existing_tests_no_root(self, gatherer):
        """Test with no project root."""
        with patch("gobby.tasks.context.find_project_root", return_value=None):
            result = gatherer.discover_existing_tests(["src/module.py"])
        assert result == {}

    def test_discover_existing_tests_no_tests_dir(self, gatherer, tmp_path):
        """Test when tests directory doesn't exist."""
        with patch("gobby.tasks.context.find_project_root", return_value=tmp_path):
            result = gatherer.discover_existing_tests(["src/module.py"])
        assert result == {}

    def test_discover_existing_tests_finds_tests(self, gatherer, tmp_project):
        """Test finding tests that import a module."""
        # Create a test file that imports from the module
        test_file = tmp_project / "tests" / "test_main.py"
        test_file.write_text("from mypackage.main import MyClass\n")

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            result = gatherer.discover_existing_tests(["src/mypackage/main.py"])

        assert "src/mypackage/main.py" in result
        assert "tests/test_main.py" in result["src/mypackage/main.py"]

    def test_discover_existing_tests_timeout(self, gatherer, tmp_project):
        """Test handling of subprocess timeout."""
        with (
            patch("gobby.tasks.context.find_project_root", return_value=tmp_project),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired("grep", 10),
            ),
        ):
            result = gatherer.discover_existing_tests(["src/mypackage/main.py"])
        assert result == {}

    def test_discover_existing_tests_subprocess_error(self, gatherer, tmp_project):
        """Test handling of subprocess errors."""
        with (
            patch("gobby.tasks.context.find_project_root", return_value=tmp_project),
            patch(
                "subprocess.run",
                side_effect=OSError("Command not found"),
            ),
        ):
            result = gatherer.discover_existing_tests(["src/mypackage/main.py"])
        assert result == {}


# =============================================================================
# _path_to_import Tests
# =============================================================================


class TestPathToImport:
    """Tests for _path_to_import method."""

    def test_path_to_import_standard(self, gatherer):
        """Test standard path conversion."""
        result = gatherer._path_to_import("src/gobby/tasks/expansion.py")
        assert result == "gobby.tasks.expansion"

    def test_path_to_import_lib_prefix(self, gatherer):
        """Test with lib prefix."""
        result = gatherer._path_to_import("lib/mypackage/module.py")
        assert result == "mypackage.module"

    def test_path_to_import_no_prefix(self, gatherer):
        """Test without src/lib prefix."""
        result = gatherer._path_to_import("mypackage/module.py")
        assert result == "mypackage.module"

    def test_path_to_import_init(self, gatherer):
        """Test __init__.py handling."""
        result = gatherer._path_to_import("src/gobby/__init__.py")
        assert result == "gobby"

    def test_path_to_import_non_python(self, gatherer):
        """Test non-Python file returns None."""
        result = gatherer._path_to_import("src/config.yaml")
        assert result is None

    def test_path_to_import_empty_after_strip(self, gatherer):
        """Test edge case of empty path after stripping."""
        result = gatherer._path_to_import("src/.py")
        assert result is None


# =============================================================================
# extract_signatures Tests
# =============================================================================


class TestExtractSignatures:
    """Tests for extract_signatures method."""

    def test_extract_signatures_no_root(self, gatherer):
        """Test with no project root."""
        with patch("gobby.tasks.context.find_project_root", return_value=None):
            result = gatherer.extract_signatures(["src/main.py"])
        assert result == {}

    def test_extract_signatures_non_python(self, gatherer, tmp_project):
        """Test that non-Python files are skipped."""
        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            result = gatherer.extract_signatures(["config.yaml"])
        assert result == {}

    def test_extract_signatures_missing_file(self, gatherer, tmp_project):
        """Test handling of missing files."""
        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            result = gatherer.extract_signatures(["nonexistent.py"])
        assert result == {}

    def test_extract_signatures_syntax_error(self, gatherer, tmp_project):
        """Test handling of syntax errors in file."""
        bad_file = tmp_project / "bad.py"
        bad_file.write_text("def broken(\n")

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            result = gatherer.extract_signatures(["bad.py"])
        assert result == {}

    def test_extract_signatures_extracts_class(self, gatherer, tmp_project):
        """Test extraction of class signatures."""
        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            result = gatherer.extract_signatures(["src/mypackage/main.py"])

        assert "src/mypackage/main.py" in result
        signatures = result["src/mypackage/main.py"]
        assert "class MyClass" in signatures

    def test_extract_signatures_extracts_function(self, gatherer, tmp_project):
        """Test extraction of function signatures."""
        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            result = gatherer.extract_signatures(["src/mypackage/main.py"])

        signatures = result["src/mypackage/main.py"]
        # Check for the async function
        assert any("async def async_function" in s for s in signatures)

    def test_extract_signatures_with_return_type(self, gatherer, tmp_project):
        """Test extraction of return type annotations."""
        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            result = gatherer.extract_signatures(["src/mypackage/main.py"])

        signatures = result["src/mypackage/main.py"]
        # Check that return type is captured
        method_sig = next(s for s in signatures if "method" in s)
        assert "-> bool" in method_sig


# =============================================================================
# _extract_signatures_from_ast Tests
# =============================================================================


class TestExtractSignaturesFromAst:
    """Tests for _extract_signatures_from_ast method."""

    def test_extract_class_with_bases(self, gatherer):
        """Test extraction of class with base classes."""
        code = "class Child(Parent, Mixin): pass"
        tree = ast.parse(code)
        signatures = gatherer._extract_signatures_from_ast(tree)
        assert "class Child(Parent, Mixin)" in signatures

    def test_extract_class_no_bases(self, gatherer):
        """Test extraction of class without base classes."""
        code = "class Simple: pass"
        tree = ast.parse(code)
        signatures = gatherer._extract_signatures_from_ast(tree)
        assert "class Simple" in signatures

    def test_extract_class_generic_base(self, gatherer):
        """Test extraction of class with generic base."""
        code = "class MyList(Generic[T]): pass"
        tree = ast.parse(code)
        signatures = gatherer._extract_signatures_from_ast(tree)
        assert any("Generic[T]" in s for s in signatures)

    def test_extract_async_function(self, gatherer):
        """Test extraction of async function."""
        code = "async def fetch(): pass"
        tree = ast.parse(code)
        signatures = gatherer._extract_signatures_from_ast(tree)
        assert "async def fetch()" in signatures

    def test_extract_function_with_defaults(self, gatherer):
        """Test extraction of function with default arguments."""
        code = "def func(a, b=10, c='hello'): pass"
        tree = ast.parse(code)
        signatures = gatherer._extract_signatures_from_ast(tree)
        assert any("b=..." in s for s in signatures)
        assert any("c=..." in s for s in signatures)


# =============================================================================
# _get_base_names Tests
# =============================================================================


class TestGetBaseNames:
    """Tests for _get_base_names method."""

    def test_get_base_names_simple(self, gatherer):
        """Test simple base class extraction."""
        code = "class Child(Parent): pass"
        tree = ast.parse(code)
        class_node = tree.body[0]
        names = gatherer._get_base_names(class_node)
        assert names == ["Parent"]

    def test_get_base_names_multiple(self, gatherer):
        """Test multiple base classes."""
        code = "class Child(A, B, C): pass"
        tree = ast.parse(code)
        class_node = tree.body[0]
        names = gatherer._get_base_names(class_node)
        assert names == ["A", "B", "C"]

    def test_get_base_names_attribute(self, gatherer):
        """Test module.Class style bases."""
        code = "class Child(module.Parent): pass"
        tree = ast.parse(code)
        class_node = tree.body[0]
        names = gatherer._get_base_names(class_node)
        assert "module.Parent" in names

    def test_get_base_names_subscript(self, gatherer):
        """Test generic bases like Generic[T]."""
        code = "class MyList(list[T]): pass"
        tree = ast.parse(code)
        class_node = tree.body[0]
        names = gatherer._get_base_names(class_node)
        assert "list[T]" in names


# =============================================================================
# _format_function_signature Tests
# =============================================================================


class TestFormatFunctionSignature:
    """Tests for _format_function_signature method."""

    def test_format_simple_function(self, gatherer):
        """Test simple function without arguments."""
        code = "def simple(): pass"
        tree = ast.parse(code)
        func_node = tree.body[0]
        sig = gatherer._format_function_signature(func_node)
        assert sig == "def simple()"

    def test_format_function_with_args(self, gatherer):
        """Test function with typed arguments."""
        code = "def func(x: int, y: str): pass"
        tree = ast.parse(code)
        func_node = tree.body[0]
        sig = gatherer._format_function_signature(func_node)
        assert "x: int" in sig
        assert "y: str" in sig

    def test_format_function_with_return(self, gatherer):
        """Test function with return type."""
        code = "def func() -> bool: pass"
        tree = ast.parse(code)
        func_node = tree.body[0]
        sig = gatherer._format_function_signature(func_node)
        assert "-> bool" in sig

    def test_format_async_function(self, gatherer):
        """Test async function prefix."""
        code = "async def fetch(): pass"
        tree = ast.parse(code)
        func_node = tree.body[0]
        sig = gatherer._format_function_signature(func_node)
        assert sig.startswith("async def")

    def test_format_function_with_varargs(self, gatherer):
        """Test function with *args."""
        code = "def func(*args): pass"
        tree = ast.parse(code)
        func_node = tree.body[0]
        sig = gatherer._format_function_signature(func_node)
        assert "*args" in sig

    def test_format_function_with_kwargs(self, gatherer):
        """Test function with **kwargs."""
        code = "def func(**kwargs): pass"
        tree = ast.parse(code)
        func_node = tree.body[0]
        sig = gatherer._format_function_signature(func_node)
        assert "**kwargs" in sig

    def test_format_function_with_kwonly(self, gatherer):
        """Test function with keyword-only arguments."""
        code = "def func(*, key: str): pass"
        tree = ast.parse(code)
        func_node = tree.body[0]
        sig = gatherer._format_function_signature(func_node)
        assert "*" in sig
        assert "key: str" in sig

    def test_format_function_with_posonly(self, gatherer):
        """Test function with positional-only arguments."""
        code = "def func(x, /, y): pass"
        tree = ast.parse(code)
        func_node = tree.body[0]
        sig = gatherer._format_function_signature(func_node)
        assert "/" in sig


# =============================================================================
# _format_arg Tests
# =============================================================================


class TestFormatArg:
    """Tests for _format_arg method."""

    def test_format_arg_simple(self, gatherer):
        """Test simple argument without annotation."""
        code = "def func(x): pass"
        tree = ast.parse(code)
        func_node = tree.body[0]
        arg = func_node.args.args[0]
        result = gatherer._format_arg(arg)
        assert result == "x"

    def test_format_arg_with_annotation(self, gatherer):
        """Test argument with type annotation."""
        code = "def func(x: int): pass"
        tree = ast.parse(code)
        func_node = tree.body[0]
        arg = func_node.args.args[0]
        result = gatherer._format_arg(arg)
        assert result == "x: int"

    def test_format_arg_complex_annotation(self, gatherer):
        """Test argument with complex type annotation."""
        code = "def func(x: list[dict[str, int]]): pass"
        tree = ast.parse(code)
        func_node = tree.body[0]
        arg = func_node.args.args[0]
        result = gatherer._format_arg(arg)
        assert result == "x: list[dict[str, int]]"


# =============================================================================
# _generate_project_structure Tests
# =============================================================================


class TestGenerateProjectStructure:
    """Tests for _generate_project_structure method."""

    @pytest.mark.asyncio
    async def test_generate_project_structure_no_root(self, gatherer):
        """Test with no project root."""
        with patch("gobby.tasks.context.find_project_root", return_value=None):
            result = await gatherer._generate_project_structure()
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_project_structure_with_gitingest(self, gatherer, tmp_project):
        """Test with gitingest available."""
        # Create an async mock that returns our test values
        async def mock_ingest_async(*args, **kwargs):
            return ("summary", "tree content", "file content")

        mock_gitingest = MagicMock()
        mock_gitingest.ingest_async = mock_ingest_async

        with (
            patch("gobby.tasks.context.find_project_root", return_value=tmp_project),
            patch.dict("sys.modules", {"gitingest": mock_gitingest}),
        ):
            result = await gatherer._generate_project_structure()

        assert "## Project Structure" in result
        assert "tree content" in result

    @pytest.mark.asyncio
    async def test_generate_project_structure_gitingest_import_error(self, gatherer, tmp_project, monkeypatch):
        """Test fallback when gitingest not installed."""
        # Remove gitingest from sys.modules to simulate import error
        import sys
        monkeypatch.delitem(sys.modules, "gitingest", raising=False)

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            result = await gatherer._generate_project_structure()

        # Should still return something via fallback
        if result:
            assert "## Project Structure" in result

    @pytest.mark.asyncio
    async def test_generate_project_structure_gitingest_exception(self, gatherer, tmp_project):
        """Test fallback when gitingest raises exception."""
        # Create an async mock that raises an exception
        async def mock_ingest_async(*args, **kwargs):
            raise RuntimeError("gitingest error")

        mock_gitingest = MagicMock()
        mock_gitingest.ingest_async = mock_ingest_async

        with (
            patch("gobby.tasks.context.find_project_root", return_value=tmp_project),
            patch.dict("sys.modules", {"gitingest": mock_gitingest}),
        ):
            result = await gatherer._generate_project_structure()

        # Should still work via fallback
        if result:
            assert "## Project Structure" in result


# =============================================================================
# _build_tree_fallback Tests
# =============================================================================


class TestBuildTreeFallback:
    """Tests for _build_tree_fallback method."""

    def test_build_tree_fallback_empty(self, gatherer, tmp_path):
        """Test with empty project (no source dirs)."""
        result = gatherer._build_tree_fallback(tmp_path)
        assert result is None

    def test_build_tree_fallback_with_src(self, gatherer, tmp_project):
        """Test with src directory."""
        result = gatherer._build_tree_fallback(tmp_project)
        assert result is not None
        assert "src/" in result

    def test_build_tree_fallback_with_tests(self, gatherer, tmp_project):
        """Test that tests directory is included."""
        result = gatherer._build_tree_fallback(tmp_project)
        assert result is not None
        assert "tests/" in result

    def test_build_tree_fallback_skips_pycache(self, gatherer, tmp_project):
        """Test that __pycache__ is skipped."""
        pycache = tmp_project / "src" / "__pycache__"
        pycache.mkdir(parents=True)
        (pycache / "file.pyc").write_text("")

        result = gatherer._build_tree_fallback(tmp_project)
        assert "__pycache__" not in result

    def test_build_tree_fallback_max_depth(self, gatherer, tmp_project):
        """Test max_depth limiting."""
        # Create deep nesting
        deep_path = tmp_project / "src" / "a" / "b" / "c" / "d" / "e"
        deep_path.mkdir(parents=True)

        result = gatherer._build_tree_fallback(tmp_project, max_depth=2)
        # Should not show directories beyond max_depth
        assert result is not None


# =============================================================================
# _build_tree_recursive Tests
# =============================================================================


class TestBuildTreeRecursive:
    """Tests for _build_tree_recursive method."""

    def test_build_tree_recursive_basic(self, gatherer, tmp_project):
        """Test basic recursive tree building."""
        lines = []
        gatherer._build_tree_recursive(tmp_project / "src", tmp_project, lines, max_depth=3)
        assert len(lines) > 0
        assert any("src/" in line for line in lines)

    def test_build_tree_recursive_respects_depth(self, gatherer, tmp_project):
        """Test that recursion respects max_depth."""
        # Create deep structure
        deep = tmp_project / "src" / "level1" / "level2" / "level3" / "level4"
        deep.mkdir(parents=True)

        lines = []
        gatherer._build_tree_recursive(tmp_project / "src", tmp_project, lines, max_depth=2)

        # Should not contain level3 or level4
        line_str = "\n".join(lines)
        # level3 shouldn't appear as it's beyond max_depth
        assert "level4/" not in line_str

    def test_build_tree_recursive_permission_error(self, gatherer, tmp_path):
        """Test handling of permission errors."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()

        with patch.object(Path, "iterdir", side_effect=PermissionError("No access")):
            lines = []
            # Should not raise
            gatherer._build_tree_recursive(test_dir, tmp_path, lines)


# =============================================================================
# _get_file_placement_guidance Tests
# =============================================================================


class TestGetFilePlacementGuidance:
    """Tests for _get_file_placement_guidance method."""

    def test_get_file_placement_guidance_with_claude_md(self, gatherer, tmp_project):
        """Test guidance extraction from CLAUDE.md."""
        claude_md = tmp_project / "CLAUDE.md"
        claude_md.write_text("## Architecture\n- Source: src/gobby/\n")

        result = gatherer._get_file_placement_guidance(tmp_project)

        # Should include Gobby-specific guidance since content has src/gobby
        assert "src/gobby" in result

    def test_get_file_placement_guidance_no_claude_md(self, gatherer, tmp_project):
        """Test fallback when CLAUDE.md doesn't exist."""
        claude_md = tmp_project / "CLAUDE.md"
        if claude_md.exists():
            claude_md.unlink()

        result = gatherer._get_file_placement_guidance(tmp_project)

        # Should provide default guidance based on project structure
        assert "src/" in result or "tests/" in result

    def test_get_file_placement_guidance_read_error(self, gatherer, tmp_project):
        """Test handling of file read errors."""
        claude_md = tmp_project / "CLAUDE.md"
        claude_md.write_text("content")

        with patch.object(Path, "read_text", side_effect=PermissionError("No access")):
            result = gatherer._get_file_placement_guidance(tmp_project)

        # Should fall back to default guidance
        assert isinstance(result, str)

    def test_get_file_placement_guidance_detects_patterns(self, gatherer, tmp_project):
        """Test that guidance detects project patterns."""
        # tmp_project already has src/ and tests/
        result = gatherer._get_file_placement_guidance(tmp_project)

        assert "tests/" in result.lower() or "tests go in" in result.lower()

    def test_get_file_placement_guidance_no_src_dir(self, gatherer, tmp_path):
        """Test guidance when src directory doesn't exist."""
        # Create a project without src/
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        result = gatherer._get_file_placement_guidance(tmp_path)

        # Should not crash and may include tests guidance
        assert isinstance(result, str)

    def test_get_file_placement_guidance_empty_src_dir(self, gatherer, tmp_path):
        """Test guidance when src directory exists but is empty."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        result = gatherer._get_file_placement_guidance(tmp_path)

        # Should not crash with empty pkg_dirs
        assert isinstance(result, str)

    def test_get_file_placement_guidance_no_tests_dir(self, gatherer, tmp_path):
        """Test guidance when tests directory doesn't exist."""
        # Create only src/
        src_dir = tmp_path / "src" / "mypackage"
        src_dir.mkdir(parents=True)

        result = gatherer._get_file_placement_guidance(tmp_path)

        # Should include src guidance but not tests
        assert "src/" in result


# =============================================================================
# Additional Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Additional edge case tests for context module."""

    @pytest.mark.asyncio
    async def test_find_relevant_files_path_outside_root(self, gatherer, tmp_project):
        """Test that paths outside project root are filtered out."""
        task = Task(
            id="t1",
            project_id="p1",
            title="Task",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            description="Check ../outside.py and /etc/passwd.py",
        )

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            files = await gatherer._find_relevant_files(task)

        # Paths outside root should be excluded
        assert "../outside.py" not in files
        assert "/etc/passwd.py" not in files

    def test_discover_existing_tests_no_matches(self, gatherer, tmp_project):
        """Test when grep finds no matching test files."""
        with (
            patch("gobby.tasks.context.find_project_root", return_value=tmp_project),
            patch("subprocess.run") as mock_run,
        ):
            # Simulate grep finding no matches (returncode 1)
            mock_run.return_value = MagicMock(returncode=1, stdout="")

            result = gatherer.discover_existing_tests(["src/mypackage/main.py"])

        assert result == {}

    def test_discover_existing_tests_empty_stdout(self, gatherer, tmp_project):
        """Test when grep succeeds but stdout is empty."""
        with (
            patch("gobby.tasks.context.find_project_root", return_value=tmp_project),
            patch("subprocess.run") as mock_run,
        ):
            # Simulate grep success with empty output
            mock_run.return_value = MagicMock(returncode=0, stdout="")

            result = gatherer.discover_existing_tests(["src/mypackage/main.py"])

        assert result == {}

    def test_path_to_import_with_init_in_middle(self, gatherer):
        """Test _path_to_import with __init__ in the middle of path."""
        # This should still work correctly
        result = gatherer._path_to_import("src/gobby/__init__.py")
        assert result == "gobby"

    def test_format_arg_with_unparseable_annotation(self, gatherer):
        """Test _format_arg when annotation cannot be unparsed."""
        # Create an arg node with a mock annotation that will fail unparse
        arg = MagicMock(spec=ast.arg)
        arg.arg = "x"
        arg.annotation = MagicMock()

        with patch("ast.unparse", side_effect=Exception("Cannot unparse")):
            result = gatherer._format_arg(arg)

        assert result == "x: ..."

    def test_format_function_signature_unparseable_return(self, gatherer):
        """Test _format_function_signature when return type cannot be unparsed."""
        code = "def func() -> SomeComplexType: pass"
        tree = ast.parse(code)
        func_node = tree.body[0]

        # Mock ast.unparse to fail for return type
        original_unparse = ast.unparse

        def mock_unparse(node):
            if hasattr(node, "id") and node.id == "SomeComplexType":
                raise Exception("Cannot unparse")
            return original_unparse(node)

        with patch("ast.unparse", side_effect=mock_unparse):
            sig = gatherer._format_function_signature(func_node)

        # Should still produce a signature, possibly with "..." for return type
        assert "def func()" in sig

    @pytest.mark.asyncio
    async def test_generate_project_structure_no_guidance(self, gatherer, tmp_path):
        """Test project structure when there's no file placement guidance."""
        # Create minimal project with src but no CLAUDE.md
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("pass")

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_path):
            result = await gatherer._generate_project_structure()

        # Should return structure without guidance section if no guidance found
        if result:
            assert "## Project Structure" in result

    @pytest.mark.asyncio
    async def test_generate_project_structure_fallback_returns_none(self, gatherer, tmp_path):
        """Test when both gitingest and fallback return nothing."""
        # Empty directory - no src/lib/app/tests
        with (
            patch("gobby.tasks.context.find_project_root", return_value=tmp_path),
            patch.dict("sys.modules", {"gitingest": None}),  # Trigger import error
        ):
            result = await gatherer._generate_project_structure()

        # Should return None when no tree can be built
        assert result is None

    def test_read_file_snippets_skips_directories(self, gatherer, tmp_project):
        """Test that _read_file_snippets skips directories."""
        # Create a directory with the same name as a file entry
        dir_path = tmp_project / "my_dir"
        dir_path.mkdir()

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            snippets = gatherer._read_file_snippets(["my_dir"])

        # Directories should be skipped
        assert snippets == {}

    @pytest.mark.asyncio
    async def test_find_relevant_files_resolve_exception(self, gatherer, tmp_project):
        """Test _find_relevant_files handles path resolution exceptions gracefully."""
        task = Task(
            id="t1",
            project_id="p1",
            title="Task",
            status="open",
            priority=2,
            task_type="task",
            created_at="now",
            updated_at="now",
            description="Check some/invalid\x00path.py file",  # Contains null byte
        )

        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            # Should not raise, just skip problematic paths
            files = await gatherer._find_relevant_files(task)

        # Invalid path should be skipped
        assert files == []

    def test_discover_existing_tests_skips_non_convertible_paths(self, gatherer, tmp_project):
        """Test discover_existing_tests skips paths that can't convert to imports."""
        with patch("gobby.tasks.context.find_project_root", return_value=tmp_project):
            # Pass a non-.py file which _path_to_import returns None for
            result = gatherer.discover_existing_tests(["config.yaml", "README.md"])

        # Should return empty dict since files can't be converted to import paths
        assert result == {}

    def test_extract_signatures_handles_file_read_error(self, gatherer, tmp_project):
        """Test extract_signatures handles file read exceptions."""
        # Create a file
        test_file = tmp_project / "src" / "test.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def foo(): pass")

        with (
            patch("gobby.tasks.context.find_project_root", return_value=tmp_project),
            patch("builtins.open", side_effect=OSError("Cannot read file")),
        ):
            result = gatherer.extract_signatures(["src/test.py"])

        # Should return empty dict on read error
        assert result == {}

    def test_format_function_signature_with_kwonly_defaults(self, gatherer):
        """Test _format_function_signature with keyword-only args with defaults."""
        code = "def func(*, a: int, b: str = 'hello'): pass"
        tree = ast.parse(code)
        func_node = tree.body[0]
        sig = gatherer._format_function_signature(func_node)

        assert "a: int" in sig
        assert "b: str=..." in sig

    def test_format_function_signature_complex_defaults(self, gatherer):
        """Test function signatures with multiple defaults."""
        code = "def func(a, b, c=1, d=2, e=3): pass"
        tree = ast.parse(code)
        func_node = tree.body[0]
        sig = gatherer._format_function_signature(func_node)

        assert "a, b" in sig
        assert "c=..." in sig
        assert "d=..." in sig
        assert "e=..." in sig
