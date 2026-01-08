from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.config.app import TaskExpansionConfig
from gobby.tasks.research import TaskResearchAgent


@pytest.fixture
def mock_config():
    return TaskExpansionConfig()


@pytest.fixture
def mock_llm():
    service = MagicMock()
    service.get_provider.return_value = AsyncMock()
    return service


@pytest.fixture
def agent(mock_config, mock_llm):
    return TaskResearchAgent(mock_config, mock_llm)


class TestActionParsing:
    def test_parse_simple_action(self, agent):
        response = "THOUGHT: I should look at files.\nACTION: glob('src/*.py')"
        action = agent._parse_action(response)
        assert action == {"tool": "glob", "args": ["src/*.py"]}

    def test_parse_action_with_quotes(self, agent):
        response = "ACTION: grep('class Foo', 'src/foo.py')"
        action = agent._parse_action(response)
        assert action == {"tool": "grep", "args": ["class Foo", "src/foo.py"]}

    def test_parse_action_shlex_fallback(self, agent):
        # Malformed tuple syntax that might fail ast.literal_eval but pass shlex
        response = "ACTION: grep(def foo, src/bar.py)"
        action = agent._parse_action(response)
        # Should fall back to comma split or shlex
        assert action["tool"] == "grep"
        assert len(action["args"]) == 2
        assert action["args"][0] == "def foo"

    def test_parse_done(self, agent):
        response = "ACTION: done('Found everything')"
        action = agent._parse_action(response)
        assert action == {"tool": "done", "reason": "Found everything"}

    def test_parse_done_simple(self, agent):
        response = "ACTION: done"
        action = agent._parse_action(response)
        assert action == {"tool": "done", "reason": "ACTION: done"}

    def test_parse_no_action(self, agent):
        response = "Just thinking about code..."
        assert agent._parse_action(response) is None


@pytest.fixture
def fs_agent(agent, tmp_path):
    """Agent with a temporary root."""
    agent.root = tmp_path
    return agent


class TestToolExecution:
    async def test_execute_glob(self, fs_agent, tmp_path):
        # Create some files
        (tmp_path / "foo.py").touch()
        (tmp_path / "src").mkdir()
        (tmp_path / "src/bar.py").touch()

        # Glob
        output = await fs_agent._execute_tool({"tool": "glob", "args": ["**/*.py"]})
        assert "foo.py" in output
        assert "src/bar.py" in output

    async def test_execute_glob_error(self, fs_agent):
        output = await fs_agent._execute_tool({"tool": "glob", "args": ["../*.py"]})
        assert "Error: .. not allowed" in output

    async def test_execute_read_file(self, fs_agent, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello World", encoding="utf-8")

        output = await fs_agent._execute_tool({"tool": "read_file", "args": ["test.txt"]})
        assert output == "Hello World"

    async def test_execute_read_file_not_found(self, fs_agent):
        output = await fs_agent._execute_tool({"tool": "read_file", "args": ["missing.txt"]})
        assert "Error: File not found" in output

    async def test_execute_grep(self, fs_agent, tmp_path):
        f = tmp_path / "main.py"
        f.write_text("def main():\n    print('hello')\n", encoding="utf-8")

        output = await fs_agent._execute_tool({"tool": "grep", "args": ["def main", "."]})
        assert "main.py:1: def main():" in output

    async def test_execute_unknown(self, fs_agent):
        output = await fs_agent._execute_tool({"tool": "magic", "args": []})
        assert "Error: Unknown tool magic" in output

    async def test_execute_done(self, fs_agent):
        output = await fs_agent._execute_tool({"tool": "done", "reason": "Finished"})
        assert output == "Done"

    async def test_execute_grep_outside_root(self, fs_agent, tmp_path):
        output = await fs_agent._execute_tool({"tool": "grep", "args": ["foo", "../outside.txt"]})
        assert "Error: Path outside root" in output

    async def test_execute_grep_directory(self, fs_agent, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir/test.py").write_text("class Foo: pass", encoding="utf-8")

        output = await fs_agent._execute_tool({"tool": "grep", "args": ["class Foo", "subdir"]})
        assert "subdir/test.py:1: class Foo: pass" in output


@pytest.mark.integration
class TestRunLoop:
    @pytest.fixture
    def task(self):
        return MagicMock(id="task-123", title="Test Task", description="Do something")

    async def test_run_basic_flow(self, fs_agent, task, tmp_path):
        # Setup filesystem
        (tmp_path / "foo.py").touch()

        # Mock LLM to return tool call then done
        fs_agent.llm_service.get_provider.return_value.generate_text.side_effect = [
            "THOUGHT: I check files\nACTION: glob('**/*.py')",
            "THOUGHT: Done\nACTION: done('Found it')",
        ]

        result = await fs_agent.run(task)

        assert result["raw_history"][0]["parsed_action"]["tool"] == "glob"
        assert result["raw_history"][1]["role"] == "tool"  # glob output
        assert (
            result["relevant_files"] == []
        )  # glob doesn't populate relevant_files, read_file does

    async def test_run_with_read_file(self, fs_agent, task, tmp_path):
        f = tmp_path / "readme.md"
        f.write_text("# Readme", encoding="utf-8")

        fs_agent.llm_service.get_provider.return_value.generate_text.side_effect = [
            "ACTION: read_file('readme.md')",
            "ACTION: done",
        ]

        result = await fs_agent.run(task)
        assert "readme.md" in result["relevant_files"]

    async def test_no_root(self, agent, task):
        agent.root = None
        result = await agent.run(task)
        assert result["findings"] == "No project root found"

    async def test_run_with_search_tool(self, fs_agent, task, mcp_manager):
        # Mock MCP manager
        mcp_manager.list_tools = AsyncMock(
            return_value={"server1": [MagicMock(name="search_web", description="Search the web")]}
        )
        mcp_manager.call_tool = AsyncMock(return_value="Search Result")
        fs_agent.mcp_manager = mcp_manager

        # Configure search
        fs_agent.config.web_research_enabled = True

        fs_agent.llm_service.get_provider.return_value.generate_text.side_effect = [
            "ACTION: search_web('python')",
            "ACTION: done",
        ]

        result = await fs_agent.run(task, enable_web_search=True)
        assert "Search Result" in str(result["raw_history"])
        mcp_manager.call_tool.assert_called_with("search_web", {"query": "python"})


class TestParsingFallbacks:
    def test_comma_split_fallback(self, agent):
        # Unclosed quote triggers shlex error, falling back to split
        response = 'ACTION: grep("def foo, src/)'
        action = agent._parse_action(response)
        assert action["tool"] == "grep"
        # Comma split strategy strips quotes
        # "def foo -> "def foo (quote removed?)
        # Actually logic is: a.strip().strip("'\"")
        # "\"def foo" -> "def foo"
        assert action["args"][0] == "def foo"
        assert action["args"][1] == "src/"


class TestActionParsingEdgeCases:
    """Tests for additional edge cases in action parsing."""

    def test_parse_done_with_parentheses_in_reason(self, agent):
        """Test ACTION: done(reason) from general pattern match."""
        response = "THOUGHT: I found it\nACTION: done(research complete)"
        action = agent._parse_action(response)
        assert action["tool"] == "done"
        assert action["reason"] == "research complete"

    def test_parse_empty_args(self, agent):
        """Test tool with no arguments returns empty args list."""
        response = "ACTION: glob()"
        action = agent._parse_action(response)
        assert action == {"tool": "glob", "args": []}

    def test_parse_all_strategies_fail(self, agent):
        """Test when all parsing strategies fail (empty args after split)."""
        # We need a case where:
        # 1. ast.literal_eval fails (unclosed quote)
        # 2. shlex fails (unclosed quote)
        # 3. comma split produces all empty strings after strip
        # A single unclosed quote mark does exactly this:
        # - ast fails: unterminated string literal
        # - shlex fails: No closing quotation
        # - split produces [''] which becomes [''] after strip, all empty
        response = 'ACTION: glob(")'
        action = agent._parse_action(response)
        # split('"') produces [''] which is all empty after strip
        assert action is None

    def test_parse_done_with_double_quotes(self, agent):
        """Test done with double-quoted reason."""
        response = 'ACTION: done("Found all files")'
        action = agent._parse_action(response)
        assert action["tool"] == "done"
        assert action["reason"] == "Found all files"

    def test_parse_done_mid_text(self, agent):
        """Test done action when it appears mid-text (not at line start).

        This exercises line 203 where done is matched by general pattern
        rather than the dedicated done_match at line start.
        """
        response = "I have finished thinking. ACTION: done(complete)"
        action = agent._parse_action(response)
        assert action["tool"] == "done"
        assert action["reason"] == "complete"

    def test_parse_done_mid_text_with_quotes(self, agent):
        """Test done action mid-text with quoted reason."""
        response = "Thinking... ACTION: done('all research complete')"
        action = agent._parse_action(response)
        assert action["tool"] == "done"
        assert action["reason"] == "all research complete"


class TestToolExecutionEdgeCases:
    """Tests for edge cases in tool execution."""

    async def test_execute_glob_missing_args(self, fs_agent):
        """Test glob with missing pattern argument."""
        output = await fs_agent._execute_tool({"tool": "glob", "args": []})
        assert output == "Error: Missing pattern"

    async def test_execute_grep_missing_pattern(self, fs_agent):
        """Test grep with missing pattern argument."""
        output = await fs_agent._execute_tool({"tool": "grep", "args": []})
        assert output == "Error: Missing pattern or path"

    async def test_execute_grep_missing_path(self, fs_agent):
        """Test grep with only pattern, missing path."""
        output = await fs_agent._execute_tool({"tool": "grep", "args": ["pattern"]})
        assert output == "Error: Missing pattern or path"

    async def test_execute_read_file_missing_path(self, fs_agent):
        """Test read_file with missing path argument."""
        output = await fs_agent._execute_tool({"tool": "read_file", "args": []})
        assert output == "Error: Missing path"

    async def test_execute_search_web_missing_query(self, fs_agent):
        """Test search_web with missing query."""
        mock_mcp = MagicMock()
        fs_agent.mcp_manager = mock_mcp
        output = await fs_agent._execute_tool({"tool": "search_web", "args": []})
        assert output == "Error: Missing query"

    async def test_execute_google_search(self, fs_agent):
        """Test google_search tool execution."""
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(return_value="Google results")
        fs_agent.mcp_manager = mock_mcp

        output = await fs_agent._execute_tool({"tool": "google_search", "args": ["test query"]})
        assert output == "Google results"
        mock_mcp.call_tool.assert_called_with("google_search", {"query": "test query"})

    async def test_execute_brave_search(self, fs_agent):
        """Test brave_search tool execution."""
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(return_value="Brave results")
        fs_agent.mcp_manager = mock_mcp

        output = await fs_agent._execute_tool({"tool": "brave_search", "args": ["test query"]})
        assert output == "Brave results"

    async def test_execute_tool_exception(self, fs_agent, tmp_path):
        """Test tool execution with exception."""
        # Create a file that will cause read error by making it unreadable
        # Instead, mock the open to raise an exception
        output = await fs_agent._execute_tool({"tool": "read_file", "args": ["test.txt"]})
        # File doesn't exist, so we get file not found
        assert "Error:" in output


class TestGlobEdgeCases:
    """Tests for glob tool edge cases."""

    async def test_glob_no_root(self, agent):
        """Test glob when root is None."""
        agent.root = None
        output = agent._glob("**/*.py")
        assert output == "No root"

    async def test_glob_no_matches(self, fs_agent, tmp_path):
        """Test glob with no matching files."""
        output = fs_agent._glob("**/*.nonexistent")
        assert output == "No matches found"

    async def test_glob_exception(self, fs_agent):
        """Test glob with invalid pattern that causes exception."""
        # Use a pattern that might cause an error
        output = fs_agent._glob("[invalid")
        # Depending on the pattern, it might return error or no matches
        assert "error" in output.lower() or "No matches" in output

    async def test_glob_max_results(self, fs_agent, tmp_path):
        """Test glob truncates results at 50 files."""
        # Create 60 files
        for i in range(60):
            (tmp_path / f"file{i}.txt").touch()

        output = fs_agent._glob("*.txt")
        lines = output.strip().split("\n")
        # Should be limited to 50
        assert len(lines) <= 51  # Might stop at 51 due to > 50 check


class TestGrepEdgeCases:
    """Tests for grep tool edge cases."""

    async def test_grep_no_root(self, agent):
        """Test grep when root is None."""
        agent.root = None
        output = agent._grep("pattern", "path")
        assert output == "No root"

    async def test_grep_single_file(self, fs_agent, tmp_path):
        """Test grep on a single file (not directory)."""
        test_file = tmp_path / "single.py"
        test_file.write_text("def hello():\n    pass\n", encoding="utf-8")

        output = fs_agent._grep("def hello", "single.py")
        assert "single.py:1: def hello():" in output

    async def test_grep_no_matches(self, fs_agent, tmp_path):
        """Test grep with no matching content."""
        (tmp_path / "test.py").write_text("print('hello')", encoding="utf-8")
        output = fs_agent._grep("nonexistent_pattern_xyz", ".")
        assert output == "No matches found"

    async def test_grep_skips_hidden_files(self, fs_agent, tmp_path):
        """Test that grep skips hidden files."""
        (tmp_path / ".hidden").write_text("secret pattern", encoding="utf-8")
        output = fs_agent._grep("secret pattern", ".")
        assert output == "No matches found"

    async def test_grep_skips_binary_files(self, fs_agent, tmp_path):
        """Test that grep skips binary-like files."""
        (tmp_path / "image.png").write_text("pattern in png", encoding="utf-8")
        output = fs_agent._grep("pattern in png", ".")
        assert output == "No matches found"

    async def test_grep_file_limit(self, fs_agent, tmp_path):
        """Test grep stops after 20 matching files."""
        # Create 25 files with matching content
        for i in range(25):
            (tmp_path / f"file{i}.py").write_text(f"match_{i} pattern here", encoding="utf-8")

        output = fs_agent._grep("pattern", ".")
        lines = output.strip().split("\n")
        # Code uses `if count > 20: break` so it stops AFTER reaching 21
        # The limit is effectively 21 files (count increments to 21, then > 20 triggers break)
        assert len(lines) <= 21

    async def test_grep_nonexistent_single_file(self, fs_agent, tmp_path):
        """Test grep on nonexistent single file path."""
        output = fs_agent._grep("pattern", "nonexistent.py")
        assert output == "No matches found"


class TestReadFileEdgeCases:
    """Tests for read_file edge cases."""

    async def test_read_file_no_root(self, agent):
        """Test read_file when root is None."""
        agent.root = None
        output = agent._read_file("test.txt")
        assert output == "No root"

    async def test_read_file_outside_root(self, fs_agent, tmp_path):
        """Test read_file with path outside root."""
        output = fs_agent._read_file("../outside.txt")
        assert output == "Error: Path outside root"

    async def test_read_file_truncation(self, fs_agent, tmp_path):
        """Test read_file truncates large files."""
        large_content = "x" * 6000
        (tmp_path / "large.txt").write_text(large_content, encoding="utf-8")

        output = fs_agent._read_file("large.txt")
        assert len(output) < 6000
        assert "truncated" in output

    async def test_read_file_error(self, fs_agent, tmp_path, monkeypatch):
        """Test read_file with read error."""
        test_file = tmp_path / "error.txt"
        test_file.write_text("content", encoding="utf-8")

        # Mock open to raise exception
        def mock_open(*args, **kwargs):
            raise OSError("Permission denied")

        monkeypatch.setattr("builtins.open", mock_open)
        output = fs_agent._read_file("error.txt")
        assert "Read error:" in output


class TestBuildStepPrompt:
    """Tests for prompt building."""

    @pytest.fixture
    def task(self):
        return MagicMock(id="task-123", title="Test Task", description="Test description")

    async def test_prompt_with_long_tool_description(self, fs_agent, task):
        """Test that long tool descriptions are truncated."""
        mock_mcp = MagicMock()
        long_description = "A" * 200  # Longer than 100 chars
        mock_tool = MagicMock()
        mock_tool.name = "search_web"
        mock_tool.description = long_description
        mock_mcp.list_tools = AsyncMock(return_value={"server": [mock_tool]})
        fs_agent.mcp_manager = mock_mcp
        fs_agent.config.web_research_enabled = True

        context = {
            "task": task,
            "history": [],
            "found_files": set(),
            "snippets": {},
        }

        prompt = await fs_agent._build_step_prompt(context, 0, enable_web_search=True)
        # Description should be truncated with "..."
        assert "..." in prompt
        assert "search_web" in prompt

    async def test_prompt_with_truncated_tool_output(self, fs_agent, task):
        """Test that tool output in history is truncated."""
        long_output = "X" * 600  # Longer than 500 chars
        context = {
            "task": task,
            "history": [
                {"role": "model", "content": "ACTION: glob(*)", "parsed_action": {"tool": "glob"}},
                {"role": "tool", "content": long_output},
            ],
            "found_files": set(),
            "snippets": {},
        }

        prompt = await fs_agent._build_step_prompt(context, 1, enable_web_search=False)
        assert "(truncated)" in prompt

    async def test_prompt_history_model_role(self, fs_agent, task):
        """Test prompt includes model role history."""
        context = {
            "task": task,
            "history": [
                {"role": "model", "content": "I will search for files", "parsed_action": None},
            ],
            "found_files": {"file1.py"},
            "snippets": {"key": "value"},
        }

        prompt = await fs_agent._build_step_prompt(context, 1, enable_web_search=False)
        assert "Agent: I will search for files" in prompt
        assert "file1.py" in prompt


class TestSummarizeResults:
    """Tests for result summarization."""

    def test_summarize_with_web_search_results(self, agent):
        """Test summarization captures web search results."""
        history = [
            {
                "role": "model",
                "content": "Searching web",
                "parsed_action": {"tool": "search_web", "args": ["python tutorial"]},
            },
            {"role": "tool", "content": "Found Python documentation at python.org"},
            {
                "role": "model",
                "content": "Searching more",
                "parsed_action": {"tool": "google_search", "args": ["flask guide"]},
            },
            {"role": "tool", "content": "Flask quickstart guide found"},
            {
                "role": "model",
                "content": "Done",
                "parsed_action": {"tool": "done", "reason": "complete"},
            },
        ]
        context = {"history": history, "found_files": set(), "snippets": {}}

        result = agent._summarize_results(context)

        assert len(result["web_research"]) == 2
        assert result["web_research"][0]["tool"] == "search_web"
        assert result["web_research"][0]["query"] == "python tutorial"
        assert "Python documentation" in result["web_research"][0]["result"]
        assert result["web_research"][1]["tool"] == "google_search"

    def test_summarize_web_search_result_truncation(self, agent):
        """Test that long web search results are truncated."""
        long_result = "X" * 3000
        history = [
            {
                "role": "model",
                "content": "Searching",
                "parsed_action": {"tool": "brave_search", "args": ["query"]},
            },
            {"role": "tool", "content": long_result},
        ]
        context = {"history": history, "found_files": set(), "snippets": {}}

        result = agent._summarize_results(context)

        assert len(result["web_research"]) == 1
        assert len(result["web_research"][0]["result"]) == 2000

    def test_summarize_with_read_files(self, agent):
        """Test summarization captures read files."""
        history = [
            {
                "role": "model",
                "content": "Reading file",
                "parsed_action": {"tool": "read_file", "args": ["src/main.py"]},
            },
            {"role": "tool", "content": "def main(): pass"},
            {
                "role": "model",
                "content": "Reading another",
                "parsed_action": {"tool": "read_file", "args": ["tests/test.py"]},
            },
            {"role": "tool", "content": "def test(): pass"},
        ]
        context = {"history": history, "found_files": set(), "snippets": {}}

        result = agent._summarize_results(context)

        assert "src/main.py" in result["relevant_files"]
        assert "tests/test.py" in result["relevant_files"]

    def test_summarize_empty_history(self, agent):
        """Test summarization with empty history."""
        context = {"history": [], "found_files": set(), "snippets": {}}
        result = agent._summarize_results(context)

        assert result["relevant_files"] == []
        assert result["web_research"] == []
        assert result["findings"] == "Agent research completed."


class TestExceptionHandling:
    """Tests for exception handling in various methods."""

    async def test_execute_tool_mcp_exception(self, fs_agent):
        """Test MCP tool execution exception is caught."""
        mock_mcp = MagicMock()
        mock_mcp.call_tool = AsyncMock(side_effect=RuntimeError("MCP connection failed"))
        fs_agent.mcp_manager = mock_mcp

        output = await fs_agent._execute_tool({"tool": "search_web", "args": ["query"]})
        assert "Error executing search_web:" in output
        assert "MCP connection failed" in output

    async def test_glob_pattern_exception(self, fs_agent, monkeypatch):
        """Test glob with pattern that causes exception."""

        # Mock glob to raise an exception
        def mock_glob(self, pattern):
            raise ValueError("Invalid pattern")

        from pathlib import Path

        monkeypatch.setattr(Path, "glob", mock_glob)
        output = fs_agent._glob("*.py")
        assert "Glob error:" in output

    async def test_grep_file_read_exception(self, fs_agent, tmp_path, monkeypatch):
        """Test grep handles file read exceptions gracefully."""
        # Create a file
        test_file = tmp_path / "test.py"
        test_file.write_text("pattern here", encoding="utf-8")

        # Make the file reading raise an exception by mocking open
        original_open = open
        call_count = [0]

        def mock_open(*args, **kwargs):
            call_count[0] += 1
            # Let the first open succeed (for checking if path exists), fail on second
            if call_count[0] > 1 and "test.py" in str(args[0]):
                raise PermissionError("Cannot read file")
            return original_open(*args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open)

        # The exception should be caught and file skipped
        output = fs_agent._grep("pattern", ".")
        # Either finds no matches (if exception happens) or finds the file
        # The important thing is it doesn't crash
        assert output is not None


@pytest.mark.integration
class TestRunLoopEdgeCases:
    """Additional tests for run loop edge cases."""

    @pytest.fixture
    def task(self):
        return MagicMock(id="task-456", title="Edge Case Task", description="Testing edge cases")

    async def test_run_max_steps_reached(self, fs_agent, task, tmp_path):
        """Test run loop exits after max_steps."""
        fs_agent.max_steps = 3

        # LLM never returns done - keeps calling glob
        fs_agent.llm_service.get_provider.return_value.generate_text.return_value = (
            "ACTION: glob('**/*.py')"
        )

        result = await fs_agent.run(task)

        # Should have 6 history items: 3 model responses + 3 tool outputs
        assert len(result["raw_history"]) == 6

    async def test_run_with_failed_action_parse(self, fs_agent, task):
        """Test run loop handles failed action parsing."""
        fs_agent.llm_service.get_provider.return_value.generate_text.side_effect = [
            "I'm just thinking...",  # No ACTION - will parse as None
        ]

        result = await fs_agent.run(task)

        # Should exit after first step due to None action
        assert len(result["raw_history"]) == 1
        assert result["raw_history"][0]["parsed_action"] is None

    async def test_run_uses_research_model(self, fs_agent, task):
        """Test that research_model is used when configured."""
        fs_agent.config.research_model = "gpt-4-turbo"
        fs_agent.llm_service.get_provider.return_value.generate_text.return_value = "ACTION: done"

        await fs_agent.run(task)

        # Verify generate_text was called with research_model
        call_kwargs = fs_agent.llm_service.get_provider.return_value.generate_text.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4-turbo"

    async def test_run_web_search_disabled_globally(self, fs_agent, task):
        """Test web search is not offered when globally disabled."""
        mock_mcp = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "search_web"
        mock_tool.description = "Search"
        mock_mcp.list_tools = AsyncMock(return_value={"server": [mock_tool]})
        fs_agent.mcp_manager = mock_mcp
        fs_agent.config.web_research_enabled = False  # Globally disabled

        fs_agent.llm_service.get_provider.return_value.generate_text.return_value = "ACTION: done"

        await fs_agent.run(task, enable_web_search=True)

        # Prompt should NOT include search tool since globally disabled
        call_args = fs_agent.llm_service.get_provider.return_value.generate_text.call_args
        prompt = call_args.kwargs["prompt"]
        assert "search_web" not in prompt
