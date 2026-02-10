# Mem0 Integration Guide

Gobby's memory system works standalone with local SQLite storage and TF-IDF/embedding search. Optionally, you can add [mem0](https://mem0.ai) for enhanced semantic search, graph memory, and a visual memory UI.

**Mem0 is entirely optional.** The standalone memory system covers most use cases. Mem0 adds:

- Graph memory (entity relationships via Neo4j)
- Mem0's own embedding pipeline and search
- Web UI for browsing memories at `http://localhost:8888/docs`
- Category auto-assignment

## Prerequisites

- **Docker** with Docker Compose v2 (`docker compose version`)
- An **embedding API key** (e.g., `OPENAI_API_KEY`) — required by mem0 for its embedding pipeline
- ~2 GB disk space for Docker images (mem0, PostgreSQL + pgvector, Neo4j)

## Local Install

### Install

```bash
gobby install --mem0
```

This will:

1. Check that Docker is available
2. Copy the bundled `docker-compose.mem0.yml` to `~/.gobby/services/mem0/`
3. Run `docker compose up -d` to start three containers:
   - **mem0** API server (port 8888)
   - **PostgreSQL + pgvector** for vector storage (port 8432)
   - **Neo4j** for graph memory (ports 8474, 8687)
4. Wait for the mem0 health check (`GET http://localhost:8888/docs`)
5. Update `~/.gobby/config.yaml` with `memory.mem0_url: http://localhost:8888`

### Verify

```bash
# Check gobby sees mem0
gobby status

# Should show mem0 status line: "mem0: healthy (http://localhost:8888)"
```

You can also visit `http://localhost:8888/docs` in your browser to see the mem0 API documentation.

### With an API Key

If your mem0 instance requires an API key:

```bash
gobby install --mem0 --api-key sk-your-key
```

Or set it in config after install:

```yaml
# ~/.gobby/config.yaml
memory:
  mem0_url: http://localhost:8888
  mem0_api_key: ${MEM0_API_KEY}  # Expanded from environment at load time
```

## Remote / Self-Hosted Install

Skip Docker entirely and point to an existing mem0 instance:

```bash
# Remote mem0 (hosted platform or your own server)
gobby install --mem0 --remote https://api.mem0.ai --api-key sk-your-key

# Self-hosted mem0 on another machine
gobby install --mem0 --remote http://mem0.internal:8888
```

This verifies the remote URL is reachable, then updates config — no Docker containers are started.

## How It Works

### Dual-Write Architecture

SQLite is always the source of truth. Mem0 is a search enhancement layer.

```
remember("user prefers dark mode")
  ├─ 1. Store in SQLite (LocalMemoryManager)     ← always
  ├─ 2. Generate local embedding (if configured)  ← always
  └─ 3. Index in mem0 (POST /memories)            ← when mem0 is configured
```

On recall:
1. Query mem0 for semantic results
2. Enrich with local metadata (tags, decay, importance)
3. Apply gobby filters (project scope, importance threshold)
4. If mem0 is unreachable, fall back to local search (TF-IDF/embeddings)

### Project Scoping

Memories are scoped to projects via metadata:

- On create: `metadata.project_id` is set to the current project
- On search: `filters.project_id` restricts results to the active project
- Mem0 uses `user_id="gobby"` as a namespace across all projects

### Graceful Fallback

If mem0 becomes unreachable at any point:

- **remember()**: Stores in SQLite only. `mem0_id` stays NULL (marks as unsynced).
- **recall()**: Falls back to local search. Logs a warning once per session.
- **forget()/update()**: Applied to SQLite. Mem0 operations are skipped with a warning.
- **Lazy sync**: On next successful mem0 connection, unsynced memories (where `mem0_id IS NULL`) are automatically indexed in mem0.

## Lifecycle Management

Mem0 containers are **persistent services** — they run independently of the gobby daemon and survive reboots via `restart: unless-stopped`.

### Default Behavior

```bash
gobby start    # Starts gobby daemon only (mem0 containers untouched)
gobby stop     # Stops gobby daemon only (mem0 containers keep running)
gobby restart  # Restarts gobby daemon only
gobby status   # Shows daemon status + mem0 health indicator
```

### Explicit Mem0 Control

Use the `--mem0` flag to also manage mem0 containers:

```bash
gobby start --mem0    # Start daemon AND mem0 containers
gobby stop --mem0     # Stop daemon AND mem0 containers
gobby restart --mem0  # Restart both
```

### Checking Status

`gobby status` always shows mem0 health when configured:

```
Gobby daemon: running (PID 12345, uptime: 2h 15m)
  Port: 60887
  Mem0: healthy (http://localhost:8888)
```

If mem0 is configured but unreachable:

```
  Mem0: unreachable (http://localhost:8888) — falling back to local search
```

## Uninstall

```bash
# Stop containers and remove config (keeps data volumes)
gobby uninstall --mem0

# Stop containers, remove config AND data volumes (permanent data loss!)
gobby uninstall --mem0 --volumes
```

Uninstall will:

1. Run `docker compose down` (with `-v` if `--volumes` is specified)
2. Remove `~/.gobby/services/mem0/`
3. Clear `mem0_url` and `mem0_api_key` from config
4. Memory system reverts to standalone mode automatically

## Docker Services

The bundled compose file starts three services on non-standard ports to avoid conflicts:

| Service | Image | Port | Purpose |
| ------- | ----- | ---- | ------- |
| mem0 | `mem0ai/mem0:latest` | 8888 | Mem0 API server |
| postgres | `pgvector/pgvector:pg16` | 8432 | Vector storage (pgvector) |
| neo4j | `neo4j:5` | 8474, 8687 | Graph memory |

Data is persisted in Docker volumes:
- `mem0_pgdata` — PostgreSQL data
- `mem0_neo4j_data` — Neo4j graph data

## Configuration Reference

All mem0-related config fields in `~/.gobby/config.yaml`:

```yaml
memory:
  # Mem0 connection (None = standalone mode)
  mem0_url: http://localhost:8888    # Set by 'gobby install --mem0'
  mem0_api_key: ${MEM0_API_KEY}      # Optional, supports env var expansion

  # These settings apply in both modes:
  importance_threshold: 0.7
  decay_enabled: true
  decay_rate: 0.05
  decay_floor: 0.1
  auto_crossref: false
  access_debounce_seconds: 60

  # These settings apply in standalone mode only
  # (mem0 uses its own search pipeline when available):
  search_backend: auto
  embedding_model: text-embedding-3-small
  embedding_weight: 0.6
  tfidf_weight: 0.4
```

## Troubleshooting

### Docker not found

```
Error: Docker not found. Install Docker to use local mem0.
```

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and ensure `docker compose version` works in your terminal.

### Port conflicts

The default ports are 8888, 8432, 8474, and 8687. If these conflict with existing services, edit the compose file at `~/.gobby/services/mem0/docker-compose.yml` and change the host-side ports (left of the colon):

```yaml
ports:
  - "9888:8080"  # Changed from 8888
```

Then update `mem0_url` in config to match.

### Health check failed

```
Error: Health check failed: mem0 did not become healthy in time
```

Check container logs:

```bash
docker compose -f ~/.gobby/services/mem0/docker-compose.yml logs mem0
docker compose -f ~/.gobby/services/mem0/docker-compose.yml logs postgres
```

Common causes:
- PostgreSQL hasn't finished initializing (wait and retry)
- Missing `OPENAI_API_KEY` in environment (mem0 needs it for embeddings)
- Insufficient memory for Neo4j (needs ~512 MB)

### Mem0 unreachable after install

If `gobby status` shows mem0 as unreachable:

```bash
# Check if containers are running
docker compose -f ~/.gobby/services/mem0/docker-compose.yml ps

# Restart containers
docker compose -f ~/.gobby/services/mem0/docker-compose.yml restart

# Or use gobby
gobby restart --mem0
```

### Fallback behavior

When mem0 is unreachable, gobby silently falls back to local search. Memories created while mem0 is down are stored locally and automatically synced to mem0 when the connection is restored. No data is lost.

## Related Documentation

- [Memory System Guide](memory.md) - Full memory system documentation
- [Memory V4 Plan](../plans/memory-v4.md) - Architecture and design decisions
