"""Gobby MCP server instructions.

Provides XML-structured instructions that teach agents how to use Gobby correctly.
These instructions are injected into the MCP server via FastMCP's `instructions` parameter.
"""


def build_gobby_instructions() -> str:
    """Build compact instructions for Gobby MCP server.

    Provides minimal guidance for progressive tool disclosure, caching, and task rules.
    Startup sequence and skill discovery are now handled via workflow injection.

    Returns:
        XML-structured instructions string (~120 tokens)
    """
    return """<gobby_system>

<tool_discovery>
NEVER assume tool schemas. Use progressive disclosure:
1. `list_mcp_servers()` — Discover server names (e.g., `gobby-tasks`, `gobby-sessions`)
2. `list_tools(server="...")` — Lightweight metadata (~100 tokens/tool)
3. `get_tool_schema(server, tool)` — Full schema when needed
4. `call_tool(server, tool, args)` — Execute

NOTE: Server names are internal sub-servers like `gobby-tasks`, `gobby-memory`, etc.
The name `"gobby"` is the MCP proxy namespace, not a server name.
</tool_discovery>

<caching>
Schema fetches are cached per session. Once you call `get_tool_schema(server, tool)`,
you can `call_tool` that same server:tool repeatedly WITHOUT re-fetching the schema.
Do NOT call list_tools or get_tool_schema before every call_tool — only on first use.
</caching>

<rules>
- Create/claim a task before using Edit, Write, or NotebookEdit tools
- Pass session_id to create_task (required), claim_task (required), and close_task (optional, for tracking)
- NEVER load all tool schemas upfront — use progressive disclosure
</rules>

</gobby_system>"""
