---
name: features-task-description
description: Prompt for generating task descriptions from spec sections
version: "1.0"
variables:
  task_title:
    type: str
    required: true
    description: The task title
  section_title:
    type: str
    default: ""
    description: The spec section title
  section_content:
    type: str
    default: ""
    description: The spec section content
  existing_context:
    type: str
    default: ""
    description: Any existing context about the task
---
Generate a concise task description for this task from a spec document.

Task title: {{ task_title }}
Section: {{ section_title }}
Section content: {{ section_content }}
Existing context: {{ existing_context }}

Write a 1-2 sentence description focusing on the goal and deliverable.
Do not add quotes, extra formatting, or implementation details.
