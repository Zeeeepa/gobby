---
name: codex-result-handling
description: Internal guidance for presenting Codex helper output back to the user
category: integration
tags:
  - gobby
metadata:
  gobby:
    audience: internal
    depth: 1
---

# Codex Result Handling

When presenting Codex output back to the user:

- Preserve the verdict, summary, findings, and next steps structure.
- For review output, present findings first and keep them ordered by severity.
- Use the file paths and line numbers exactly as Codex reports them.
- Preserve evidence boundaries. If Codex marked something as an inference, uncertainty, or follow-up question, keep that distinction.
- Preserve output sections when the prompt asked for them, such as observed facts, inferences, open questions, touched files, or next steps.
- If there are no findings, say that explicitly and keep the residual-risk note brief.
- If Codex made edits, say so explicitly and list the touched files when provided.
- Do not turn a failed or incomplete Codex run into a Claude-side implementation attempt. Report the failure and stop.
- If Codex was never successfully invoked, do not generate a substitute answer at all.
- **CRITICAL**: After presenting review findings, STOP. Do not make any code changes. Do not fix any issues. You MUST explicitly ask the user which issues, if any, they want fixed before touching a single file. Auto-applying fixes from a review is strictly forbidden, even if the fix is obvious.
- If the output is malformed or the Codex run failed, include the most actionable stderr lines and stop there instead of guessing.
- If setup or authentication is required, direct the user to run `/gobby skill codex-setup` and do not improvise alternate auth flows.
