---
name: features-import-mcp-search
description: User prompt for search-based MCP server import
version: "1.0"
variables:
  search_query:
    type: str
    required: true
    description: The search query for finding the MCP server
---
Search for MCP server: {{ search_query }}

Find the official documentation or GitHub repository for this MCP server.
Then fetch and read the README or installation docs.

After reading the documentation, extract the MCP server configuration as a JSON object.
