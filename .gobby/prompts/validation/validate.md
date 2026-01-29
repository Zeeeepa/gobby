---
name: validation-validate
description: Base prompt for validating task completion against criteria
version: "1.0"
variables:
  title:
    type: str
    required: true
    description: Task title
  category_section:
    type: str
    default: ""
    description: Optional category/test strategy section
  criteria_text:
    type: str
    required: true
    description: Validation criteria or task description
  changes_section:
    type: str
    required: true
    description: Summary of changes made (files, diffs, etc.)
  file_context:
    type: str
    default: ""
    description: Optional file content context
---
Validate if the following changes satisfy the requirements.

Task: {{ title }}
{% if category_section %}
{{ category_section }}
{% endif %}
{{ criteria_text }}

{{ changes_section }}
IMPORTANT: Return ONLY a JSON object, nothing else. No explanation, no preamble.
Format: {"status": "valid", "feedback": "..."} or {"status": "invalid", "feedback": "..."}
{% if file_context %}
File Context:
{{ file_context }}
{% endif %}
