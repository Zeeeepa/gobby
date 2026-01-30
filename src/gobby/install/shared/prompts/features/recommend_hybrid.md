---
name: features-recommend-tools-hybrid
description: Prompt for hybrid mode re-ranking of semantic search results
version: "1.0"
variables:
  task_description:
    type: str
    required: true
    description: The task description to match tools for
  candidate_list:
    type: str
    required: true
    description: Formatted list of candidate tools from semantic search
  top_k:
    type: int
    default: 5
    description: Number of top recommendations to return
---
You are an expert at selecting tools for tasks.
Task: {{ task_description }}

Candidate tools (ranked by semantic similarity):
{{ candidate_list }}

Re-rank these tools by relevance to the task and provide reasoning.
Return the top {{ top_k }} most relevant as JSON:
{
  "recommendations": [
    {
      "server": "server_name",
      "tool": "tool_name",
      "reason": "Why this tool is the best choice"
    }
  ]
}
