---
description: Update rolling session digest with current prompt context
required_variables:
  - current_prompt
optional_variables:
  - previous_digest
---
You are updating a rolling session digest. This digest tracks what the session is about in ~200 tokens.

{% if previous_digest %}
## Current Digest
{{ previous_digest }}
{% endif %}

## Latest User Prompt
{{ current_prompt }}

## Instructions
Update the digest to reflect the current state of the session. Output ONLY the updated digest in this exact format (no other text):

**Task**: [What the session is working on, including task refs like #N]
**Decisions**: [Key technical decisions made so far]
**Context**: [Files being edited, APIs being used, systems involved]
**Findings**: [Important discoveries, root causes, gotchas found]
**Domain**: [Technical domains: e.g., memory system, workflow actions, database migrations]

Keep each field to one line. Total output must stay under 200 tokens.
If a field has no content yet, write "None yet".
