# Skill

Learn a new skill from this session using gobby-skills MCP tools.

# 3. **Verify**: Use `list_skills` to confirm the new skill exists.

### Example: Learning from a Session

```python
# Learn skills from a successful coding session
tool_call("gobby-skills", "learn_skills_from_session", {
    "session_id": "sess_12345"
})
```gobby-skills` server.

The skill will be extracted from the current session's work patterns and saved for future use.

After learning, show the skill details and suggest exporting to .claude/skills/ or .codex/skills/.
