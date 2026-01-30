"""Tests for Gobby MCP server instructions builder."""
import pytest

pytestmark = pytest.mark.unit


class TestBuildGobbyInstructions:
    """Test build_gobby_instructions() function."""

    def test_returns_non_empty_string(self) -> None:
        """Instructions should return a non-empty string."""
        from gobby.mcp_proxy.instructions import build_gobby_instructions

        result = build_gobby_instructions()

        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_gobby_system_tags(self) -> None:
        """Instructions should be wrapped in <gobby_system> tags."""
        from gobby.mcp_proxy.instructions import build_gobby_instructions

        result = build_gobby_instructions()

        assert "<gobby_system>" in result
        assert "</gobby_system>" in result

    def test_contains_startup_section(self) -> None:
        """Instructions should include <startup> section."""
        from gobby.mcp_proxy.instructions import build_gobby_instructions

        result = build_gobby_instructions()

        assert "<startup>" in result
        assert "</startup>" in result
        # Startup should mention discovering servers and skills
        assert "list_mcp_servers" in result
        assert "list_skills" in result

    def test_contains_tool_discovery_section(self) -> None:
        """Instructions should include <tool_discovery> section."""
        from gobby.mcp_proxy.instructions import build_gobby_instructions

        result = build_gobby_instructions()

        assert "<tool_discovery>" in result
        assert "</tool_discovery>" in result
        # Should mention progressive disclosure pattern
        assert "list_tools" in result
        assert "get_tool_schema" in result
        assert "call_tool" in result

    def test_contains_skill_discovery_section(self) -> None:
        """Instructions should include <skill_discovery> section."""
        from gobby.mcp_proxy.instructions import build_gobby_instructions

        result = build_gobby_instructions()

        assert "<skill_discovery>" in result
        assert "</skill_discovery>" in result
        # Should mention skill discovery pattern
        assert "get_skill" in result
        assert "search_skills" in result

    def test_contains_rules_section(self) -> None:
        """Instructions should include <rules> section."""
        from gobby.mcp_proxy.instructions import build_gobby_instructions

        result = build_gobby_instructions()

        assert "<rules>" in result
        assert "</rules>" in result
        # Should mention key rules
        assert "task" in result.lower()  # task before editing
        assert "session_id" in result  # session_id required

    def test_emphasizes_progressive_disclosure(self) -> None:
        """Instructions should emphasize progressive disclosure pattern."""
        from gobby.mcp_proxy.instructions import build_gobby_instructions

        result = build_gobby_instructions()

        # Should discourage loading all schemas upfront
        assert "NEVER" in result
        # Should mention the pattern
        assert "progressive" in result.lower() or "disclosure" in result.lower()
