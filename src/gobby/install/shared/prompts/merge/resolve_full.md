---
description: Resolve all merge conflicts in a full file
required_variables:
  - file_path
  - content_with_markers
---
Resolve all merge conflicts in the following file {{ file_path }}. Return the FULL resolved file content.

{{ content_with_markers }}
