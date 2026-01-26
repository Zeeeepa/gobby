---
name: features-server-description
description: Prompt for generating MCP server descriptions from tools
version: "1.0"
variables:
  server_name:
    type: str
    required: true
    description: The MCP server name
  tools_list:
    type: str
    required: true
    description: Formatted list of tools on the server
---
Write a single concise sentence describing what the '{{ server_name }}' MCP server does based on its tools.

Tools:
{{ tools_list }}

Description (1 sentence, try to keep under 100 characters):
