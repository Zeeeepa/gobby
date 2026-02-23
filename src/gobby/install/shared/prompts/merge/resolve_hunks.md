---
description: Resolve merge conflict hunks in a file
required_variables:
  - file_path
  - conflict_hunks
---
Resolve the following merge conflicts in {{ file_path }}. Return ONLY the resolved code content for each hunk.

{{ conflict_hunks }}

Provide the resolved code for each conflict hunk, separated by '---HUNK SEPARATOR---'.
