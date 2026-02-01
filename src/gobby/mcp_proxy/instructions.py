"""Gobby MCP server instructions.

Provides XML-structured instructions that teach agents how to use Gobby correctly.
These instructions are injected into the MCP server via FastMCP's `instructions` parameter.
"""


def build_gobby_instructions() -> str:
    """Build compact instructions for Gobby MCP server.

    Provides minimal guidance for progressive tool disclosure and task rules.
    Startup sequence and skill discovery are now handled via workflow injection.

    Returns:
        XML-structured instructions string (~80 tokens)
    """
    return """<gobby_system>

<tool_discovery>
NEVER assume tool schemas. Use progressive disclosure:
1. `list_tools(server="...")` — Lightweight metadata (~100 tokens/tool)
2. `get_tool_schema(server, tool)` — Full schema when needed
3. `call_tool(server, tool, args)` — Execute
</tool_discovery>

<rules>
- Create/claim a task before using Edit, Write, or NotebookEdit tools
- Pass session_id to create_task (required), claim_task (required), and close_task (optional, for tracking)
- NEVER load all tool schemas upfront — use progressive disclosure
</rules>

</gobby_system>"""
