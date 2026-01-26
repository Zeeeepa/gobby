---
name: validation-criteria
description: Prompt for generating validation criteria from task description
version: "1.0"
variables:
  title:
    type: str
    required: true
    description: Task title
  description:
    type: str
    default: "(no description)"
    description: Task description
---
Generate validation criteria for this task.

Task: {{ title }}
Description: {{ description }}

CRITICAL RULES - You MUST follow these:
1. **Only stated requirements** - Include ONLY requirements explicitly written in the title or description
2. **No invented values** - Do NOT invent specific numbers, timeouts, thresholds, or limits unless they appear in the task
3. **No invented edge cases** - Do NOT add edge cases, error scenarios, or boundary conditions beyond what's described
4. **Proportional detail** - Vague tasks get vague criteria; detailed tasks get detailed criteria
5. **When in doubt, leave it out** - If something isn't mentioned, don't include it

For vague requirements like "fix X" or "add Y", use criteria like:
- "X no longer produces the reported error/warning"
- "Y functionality works as expected"
- "Existing tests continue to pass"
- "No regressions introduced"

DO NOT generate criteria like:
- "timeout defaults to 30 seconds" (unless 30 seconds is in the task description)
- "handles edge case Z" (unless Z is mentioned in the task)
- "logs with format X" (unless that format is specified)

Format as markdown checkboxes:
## Deliverable
- [ ] What the task explicitly asks for

## Functional Requirements
- [ ] Only requirements stated in the description

## Verification
- [ ] Tests pass (if applicable)
- [ ] No regressions
