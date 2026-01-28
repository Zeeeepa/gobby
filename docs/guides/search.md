# Search Guide

Gobby provides a unified search system with multiple backends and automatic fallback for reliable search across memories, tasks, and skills.

## Quick Start

```bash
# Search memories
gobby memory search "authentication patterns"

# Search tasks
gobby tasks search "login bug" --status open

# Search skills
gobby skills search "git commit"
```

```python
# MCP: Search memories
call_tool(server_name="gobby-memory", tool_name="search_memories", arguments={
    "query": "authentication patterns",
    "limit": 10
})

# MCP: Search tasks
call_tool(server_name="gobby-tasks", tool_name="search_tasks", arguments={
    "query": "login bug",
    "status": ["open", "in_progress"],
    "limit": 20
})

# MCP: Search skills
call_tool(server_name="gobby-skills", tool_name="search_skills", arguments={
    "query": "git commit",
    "top_k": 5
})
```

## Concepts

### Search Backends

Gobby supports multiple search backends:

| Backend | Description | Dependencies | Use Case |
|---------|-------------|--------------|----------|
| **TF-IDF** | Term frequency-inverse document frequency | scikit-learn (bundled) | Offline, always available |
| **Embedding** | Semantic vector search | LiteLLM + API | High quality semantic matching |
| **Text** | Simple substring matching | None | Zero-dependency fallback |

### Search Modes

The unified searcher supports four modes:

| Mode | Behavior | Fallback | Use Case |
|------|----------|----------|----------|
| `tfidf` | TF-IDF only | None | Offline operation, guaranteed availability |
| `embedding` | Embedding only | Fails if unavailable | Maximum semantic quality |
| `auto` | Try embedding, fallback to TF-IDF | Automatic | **Recommended** for production |
| `hybrid` | Combine both with weighted scores | TF-IDF only | Highest quality when API available |

### Fallback Mechanism

In `auto` mode, the system gracefully degrades:

```text
1. Try embedding search
   ↓
2. If API unavailable → Emit FallbackEvent
   ↓
3. Reindex into TF-IDF
   ↓
4. Return TF-IDF results
```

Fallback triggers:
- No API key for embedding provider
- Embedding provider connection fails
- Rate limit or timeout during search
- Indexing exceptions

## Configuration

Configure search in `~/.gobby/config.yaml`:

```yaml
search:
  mode: auto                              # tfidf, embedding, auto, hybrid
  embedding_model: text-embedding-3-small # LiteLLM model string
  embedding_api_base: null                # For Ollama: http://localhost:11434/v1
  embedding_api_key: null                 # Uses env if not set
  tfidf_weight: 0.4                       # Weight in hybrid mode (0.0-1.0)
  embedding_weight: 0.6                   # Weight in hybrid mode (0.0-1.0)
  notify_on_fallback: true                # Log warning on fallback
```

### Embedding Providers

Using LiteLLM's unified API, the system supports multiple providers:

| Provider | Model Format | API Key | Config |
|----------|-------------|---------|--------|
| **OpenAI** | `text-embedding-3-small` | `OPENAI_API_KEY` | Default |
| **Ollama** | `openai/nomic-embed-text` | None (local) | `api_base: http://localhost:11434/v1` |
| **Azure** | `azure/azure-embedding-model` | `AZURE_API_KEY` | `api_base`, `api_version` |
| **Vertex AI** | `vertex_ai/text-embedding-004` | GCP credentials | Via env |
| **Gemini** | `gemini/text-embedding-004` | `GEMINI_API_KEY` | Default |
| **Mistral** | `mistral/mistral-embed` | `MISTRAL_API_KEY` | Default |

**Local with Ollama:**

```yaml
search:
  mode: auto
  embedding_model: openai/nomic-embed-text
  embedding_api_base: http://localhost:11434/v1
```

### TF-IDF Tuning

Advanced TF-IDF options (internal defaults):

| Option | Default | Description |
|--------|---------|-------------|
| `ngram_range` | (1, 2) | Min/max n-gram sizes |
| `max_features` | 10000 | Maximum vocabulary size |
| `min_df` | 1 | Minimum document frequency |
| `stop_words` | "english" | Language for stop word removal |
| `refit_threshold` | 10 | Updates before automatic refit |

## Searchable Entities

### Memory Search

Search across persistent memories with filtering:

```python
call_tool(server_name="gobby-memory", tool_name="search_memories", arguments={
    "query": "authentication",
    "project_id": "proj-123",        # Optional: filter by project
    "limit": 10,
    "min_importance": 0.5,           # Only important memories
    "tags_all": ["security"],        # Must have all tags
    "tags_any": ["critical", "high"] # Must have any tag
})
```

**Memory-specific config:**

```yaml
memory:
  search_backend: tfidf              # tfidf or text
  max_index_memories: 10000          # Maximum memories to index
```

### Task Search

Semantic search on task content:

```python
call_tool(server_name="gobby-tasks", tool_name="search_tasks", arguments={
    "query": "fix login bug",
    "status": ["open", "in_progress"],  # Filter by status
    "task_type": "bug",                  # Filter by type
    "priority": 1,                       # Filter by priority
    "limit": 20,
    "min_score": 0.0                     # Minimum relevance score
})
```

Task search indexes: title, description, labels, type.

### Skill Search

Search skills by description, tags, and category:

```python
call_tool(server_name="gobby-skills", tool_name="search_skills", arguments={
    "query": "git commit",
    "top_k": 5,
    "category": "vcs",                   # Filter by category
    "tags_any": ["git"],                 # Filter by tags
    "tags_all": ["recommended"]
})
```

### Artifact Search

Search session artifacts:

```python
call_tool(server_name="gobby-sessions", tool_name="search_artifacts", arguments={
    "query": "authentication",
    "session_id": "#42",                 # Optional: filter by session
    "artifact_type": "code",             # Filter by type
    "limit": 20
})
```

## CLI Commands

### Memory Search

```bash
gobby memory search QUERY [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--limit N` | Maximum results |
| `--tags` | Filter by tags |
| `--min-importance` | Minimum importance threshold |
| `--json` | Output as JSON |

### Task Search

```bash
gobby tasks search QUERY [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--status` | Filter by status |
| `--type` | Filter by task type |
| `--priority` | Filter by priority |
| `--limit N` | Maximum results |

### Skill Search

```bash
gobby skills search QUERY [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--category` | Filter by category |
| `--tags` | Filter by tags |
| `--limit N` | Maximum results |

## Hybrid Mode Details

In hybrid mode, results are combined using weighted scores:

```text
final_score = (tfidf_weight × tfidf_score) + (embedding_weight × embedding_score)
```

**Example configuration:**

```yaml
search:
  mode: hybrid
  tfidf_weight: 0.4
  embedding_weight: 0.6
```

**Hybrid behavior:**
1. Index into both TF-IDF and embedding backends
2. On search, get results from both
3. If embedding unavailable, use TF-IDF only
4. Merge and rank by weighted scores

## MCP Tool Recommendations

Gobby also uses search for tool discovery:

```yaml
mcp_client_proxy:
  search_mode: llm                       # llm, semantic, hybrid
  embedding_provider: openai
  embedding_model: text-embedding-3-small
  min_similarity: 0.3
  top_k: 10
```

```python
# Recommend tools for a task
call_tool(server_name="gobby", tool_name="recommend_tools", arguments={
    "task_description": "I need to search for files",
    "search_mode": "hybrid",
    "top_k": 10,
    "min_similarity": 0.3
})

# Semantic tool search
call_tool(server_name="gobby", tool_name="search_tools", arguments={
    "query": "file search",
    "top_k": 10,
    "min_similarity": 0.3,
    "server": "filesystem"               # Optional: filter by server
})
```

## Statistics & Monitoring

Get search backend statistics:

```python
# All searchers provide get_stats() returning:
{
    "fitted": True,                      # Index is ready
    "item_count": 1500,                  # Number of indexed items
    "active_backend": "embedding",       # Current backend
    "using_fallback": False,             # Using TF-IDF fallback
    "fallback_reason": None,             # Why fallback occurred
    # Backend-specific:
    "vocabulary_size": 5000,             # TF-IDF only
    "model": "text-embedding-3-small"    # Embedding only
}
```

## Performance Tuning

### For Speed

```yaml
search:
  mode: tfidf                            # No API calls
```

### For Quality

```yaml
search:
  mode: embedding
  embedding_model: text-embedding-3-large
```

### For Reliability + Quality

```yaml
search:
  mode: auto                             # Best of both
  notify_on_fallback: true               # Know when degraded
```

### For Maximum Quality with Fallback

```yaml
search:
  mode: hybrid
  tfidf_weight: 0.3
  embedding_weight: 0.7
```

## Best Practices

### Do

- Use `auto` mode in production for reliability
- Set `notify_on_fallback: true` to monitor degradation
- Configure Ollama for local embedding without API costs
- Use task/memory filters to narrow search scope

### Don't

- Use `embedding` mode without fallback in critical paths
- Ignore fallback notifications (may indicate API issues)
- Index too many items in TF-IDF (max_features limits vocabulary)
- Rely on exact matches (use filters for that)

## Troubleshooting

### Search returns no results

1. Check if items are indexed: `get_stats()` shows `item_count`
2. Verify search mode supports your query type
3. Lower `min_similarity` threshold
4. Check filters aren't too restrictive

### Fallback keeps occurring

1. Verify API key is set: `echo $OPENAI_API_KEY`
2. Check embedding provider is reachable
3. Review logs for rate limiting
4. Consider using Ollama for local embeddings

### Poor search quality

1. Switch from `tfidf` to `auto` or `embedding`
2. Use a larger embedding model
3. In hybrid mode, adjust weights toward embedding
4. Ensure content is descriptive (short titles search poorly)

## See Also

- [memory.md](memory.md) - Memory system
- [tasks.md](tasks.md) - Task management
- [skills.md](skills.md) - Skill system
- [configuration.md](configuration.md) - Full config reference
