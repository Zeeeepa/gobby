---
name: research-step
description: ReAct loop prompt for codebase research
version: "1.0"
variables:
  task_title:
    type: str
    required: true
    description: Task title being researched
  task_description:
    type: str
    default: ""
    description: Task description
  found_files:
    type: list
    default: []
    description: List of files found so far
  snippets_keys:
    type: list
    default: []
    description: List of snippet keys/paths found
  history:
    type: str
    default: ""
    description: Formatted history of recent agent turns
  step:
    type: int
    required: true
    description: Current step number (1-indexed)
  max_steps:
    type: int
    default: 10
    description: Maximum number of steps
  search_tool_section:
    type: str
    default: ""
    description: Optional web search tool description if available
---
Task: {{ task_title }}
Description: {{ task_description }}

You are researching this task to identify relevant files and implementation details.
You have access to the following tools:

1. glob(pattern): Find files matching a pattern (e.g. "src/**/*.py")
2. grep(pattern, path): Search for text in files (e.g. "def login", "src/")
3. read_file(path): Read the content of a file
4. done(reason): Finish research
{{ search_tool_section }}

Current Context:
Found Files: {{ found_files }}
Snippets: {{ snippets_keys }}

History:
{{ history }}

Step {{ step }}/{{ max_steps }}. What is your next move? Respond with THOUGHT followed by ACTION.
