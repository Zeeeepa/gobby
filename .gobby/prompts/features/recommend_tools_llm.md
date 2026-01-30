---
name: features-recommend-tools-llm
description: Prompt for pure LLM-based tool recommendations
version: "1.0"
variables:
  task_description:
    type: str
    required: true
    description: The task description to match tools for
  available_servers:
    type: str
    required: true
    description: Formatted list of available MCP servers with descriptions
---
You are an expert at selecting the right tools for a given task.
Task: {{ task_description }}

Available Servers: {{ available_servers }}

Please recommend which tools from these servers would be most useful for this task.
Return a JSON object with this structure:
{
  "recommendations": [
    {
      "server": "server_name",
      "tool": "tool_name",
      "reason": "Why this tool is useful"
    }
  ]
}
