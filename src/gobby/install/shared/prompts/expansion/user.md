---
name: expansion-user
description: User prompt template for task expansion with context injection
version: "1.0"
variables:
  task_id:
    type: str
    required: true
    description: The parent task ID
  title:
    type: str
    required: true
    description: The parent task title
  description:
    type: str
    default: ""
    description: The parent task description
  context_str:
    type: str
    default: "No additional context available."
    description: Formatted context information (files, tests, patterns)
  research_str:
    type: str
    default: "No research performed."
    description: Agent research findings
---
Analyze and expand this task into subtasks.

## Parent Task
- **ID**: {{ task_id }}
- **Title**: {{ title }}
- **Description**: {{ description }}

## Context
{{ context_str }}

## Research Findings
{{ research_str }}

## Instructions

Return a JSON object with a "subtasks" array. Remember to:
1. Use `depends_on` with 0-based indices to specify dependencies
2. Include a category for each coding subtask
3. Order subtasks logically - dependencies before dependents
4. Output ONLY valid JSON - no markdown, no explanation

Return the JSON now.
