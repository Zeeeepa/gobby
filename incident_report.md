# Incident Report: Session Context vs. User Intent

## 1. Timeline of Events

*   **Turn 1 (User Input):** The user provided a prompt containing:
    *   System context (Date, OS, Directory).
    *   The full content of `GEMINI.md` (Project Context & Instructions).
    *   *implied* A specific request about the weather (likely "Check the weather for Little Rock..."). *Note: This specific text was obscured in the visible history but evidenced by the agent's subsequent tool usage.*
*   **Turn 2 (Agent Action):** The agent executed a mixed set of actions:
    *   **Context Adherence:** It read `pyproject.toml`, listed directories, and checked MCP servers (following the `GEMINI.md` "Start of Session" protocols).
    *   **Prompt Adherence:** It *also* called `google_web_search` for "weather forecast Little Rock AR".
*   **Turn 3 (User Feedback):** User asked, "can i ask why you didn't follow the prompt?" indicating the agent did too much or the wrong thing.
*   **Turn 4 (Agent Analysis - Incorrect):** The agent assumed the "failure" was a procedural one (missing schema validation steps defined in `GEMINI.md`) and attempted to "fix" the Gobby task workflow.
*   **Turn 5 (User Correction):** User clarified that the issue was the agent ignoring the *simple prompt* (weather) in favor of the *complex context* (Gobby task system).

## 2. Problem Description

The agent failed to prioritize the user's specific, immediate request (Weather) over the background context instructions (`GEMINI.md`). Instead of treating `GEMINI.md` as **reference material**, the agent treated it as **immediate executable instructions**.

### Specific Instructions that "Led Astray"

The `GEMINI.md` file contains imperative language that mimics a System Prompt. When included in the context, the model interprets these as active commands to be executed *immediately upon startup*.

1.  **"Start of Session" Protocol:**
    ```markdown
    ### 1. Start of Session
    1. **Check Context:**
       * `mcp_call_tool("gobby-tasks", "list_ready_tasks", {})`
       * ...
    ```
    *Why it caused the issue:* The agent recognized it was at the "Start of Session" and immediately executed this block, ignoring the fact that the user's prompt might be unrelated to the project.

2.  **"Agent Protocol (CRITICAL)"**:
    ```markdown
    You are operating within a Gobby-enabled environment. You **must** use the `gobby-tasks` system to track your work.
    ```
    *Why it caused the issue:* This creates a high-priority constraint that makes the agent feel it *cannot* act (even to check the weather) without first establishing a task context.

3.  **"Core Mandates"**:
    ```markdown
    You are an interactive CLI agent specializing in software engineering tasks.
    ```
    *Why it caused the issue:* This strong persona definition suppresses "casual" or "general assistant" behaviors (like checking weather) in favor of engineering workflows.

## 3. Suggestions for Correction

To prevent this "autopilot" behavior where the agent ignores the prompt to follow the context, you should structurally separate **Reference Context** from **Immediate Instructions**.

### A. Wrap Context in XML Tags
Do not paste `GEMINI.md` as raw text. Wrap it to lower its imperative weight.

**Current:**
```markdown
# Gobby - Project Context & Instructions
...
```

**Proposed:**
```xml
<project_context>
  <!-- Content of GEMINI.md -->
</project_context>
```

### B. Add a "Trigger Clause" to the Context
Modify `GEMINI.md` to condition the protocols on *intent* rather than *existence*.

**Change:**
> "1. Start of Session: Check Context..."

**To:**
> "1. Start of Session: **When the user asks you to begin work on the project**, perform the following checks..."

### C. Explicit Instruction Hierarchy (The "Prime Directive")
Add this to the very top of your System Prompt or `GEMINI.md`:

```markdown
# PRIORITY INSTRUCTIONS
1. **User Prompt is King:** Always fulfill the user's specific request in the prompt *first*.
2. **Context is Secondary:** Use the "Gobby Project Context" below *only* if the user's request requires software engineering work or project knowledge.
3. **No Autopilot:** Do not start the "Start of Session" protocol unless explicitly asked to "start work" or "check tasks".
```
