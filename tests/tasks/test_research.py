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
