---
description: This skill should be used when the user asks to "/memory", "remember", "recall", "forget memory". Manage persistent memories across sessions - store, search, delete, and list memories.
---

# /memory - Memory Management Skill

This skill manages persistent memories via the gobby-memory MCP server. Parse the user's input to determine which subcommand to execute.

## Subcommands

### `/memory remember <content>` - Store a memory
Call `gobby-memory.remember` with:
- `content`: The memory content to store
- `tags`: Optional array of tags (extract from content if mentioned, e.g., "remember [testing] use pytest")
- `importance`: Optional importance score 0-1 (default 0.5, use higher for critical facts)

Example: `/memory remember Always use pytest fixtures for test setup`
→ `remember(content="Always use pytest fixtures for test setup", tags=["testing"])`

Example: `/memory remember [critical] Never commit .env files`
→ `remember(content="Never commit .env files", tags=["critical", "security"], importance=0.9)`

### `/memory recall <query>` - Search/recall memories
Call `gobby-memory.recall` with:
- `query`: Search query text
- `limit`: Optional max results (default 10)
- `tags`: Optional tag filter

Returns memories matching the query, ranked by relevance.

Example: `/memory recall testing best practices` → `recall(query="testing best practices")`
Example: `/memory recall tag:security` → `recall(tags=["security"])`

### `/memory forget <memory-id>` - Delete a memory
Call `gobby-memory.forget` with:
- `memory_id`: The memory ID to delete (e.g., mm-abc123)

Example: `/memory forget mm-abc123` → `forget(memory_id="mm-abc123")`

### `/memory list` - List all memories
Call `gobby-memory.list_memories` with:
- `limit`: Optional max results (default 20)
- `tags`: Optional tag filter

Returns all stored memories, most recent first.

Example: `/memory list` → `list_memories(limit=20)`
Example: `/memory list tag:workflow` → `list_memories(tags=["workflow"])`

### `/memory stats` - Show memory statistics
Call `gobby-memory.get_stats` to retrieve:
- Total memory count
- Memories by tag
- Storage usage
- Recent activity

Example: `/memory stats` → `get_stats()`

## Response Format

After executing the appropriate MCP tool, present the results clearly:
- For remember: Confirm storage with memory ID
- For recall: List matching memories with ID, content snippet, and relevance
- For forget: Confirm deletion
- For list: Display memories with ID, content, tags, and creation date
- For stats: Show statistics in a readable summary

## Tag Extraction

When storing memories, extract implicit tags from content:
- `[tag]` syntax → explicit tag
- `testing`, `test` → tag: testing
- `security`, `auth` → tag: security
- `workflow`, `process` → tag: workflow
- `code`, `implementation` → tag: code

## Error Handling

If the subcommand is not recognized, show available subcommands:
- remember, recall, forget, list, stats
