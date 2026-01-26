---
name: features-import-mcp-github
description: User prompt for GitHub-based MCP server import
version: "1.0"
variables:
  github_url:
    type: str
    required: true
    description: The GitHub repository URL
---
Fetch the README from this GitHub repository and extract MCP server configuration:

{{ github_url }}

If the URL doesn't point directly to a README, try to find and fetch the README.md file.

After reading the documentation, extract the MCP server configuration as a JSON object.
