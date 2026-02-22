# Gobby Source Tree

> Updated: 2026-02-22

## Directory Structure

```
gobby/                                  # Project root
├── pyproject.toml                      # Project configuration, dependencies, build settings
├── README.md                           # Project overview with architecture diagram
├── CLAUDE.md                           # Claude Code development instructions
├── CONTRIBUTING.md                     # Contribution guidelines
├── SECURITY.md                         # Security policy
├── LICENSE.md                          # Apache 2.0 License
│
├── src/gobby/                          # Source code (~513 Python files)
│   ├── __init__.py                     # Package init with version export
│   ├── runner.py                       # Daemon process entry point
│   ├── runner_broadcasting.py          # WebSocket event broadcasting wiring
│   ├── runner_maintenance.py           # Background maintenance jobs
│   ├── app_context.py                  # Application context (shared state)
│   ├── watchdog.py                     # Process watchdog
│   │
│   ├── cli/                            # CLI commands (Click, ~25 modules)
│   │   ├── __init__.py                 # Main CLI group
│   │   ├── daemon.py                   # start, stop, restart, status
│   │   ├── agents.py                   # Agent management
│   │   ├── rules.py                    # Rule management
│   │   ├── sessions.py                 # Session management
│   │   ├── pipelines.py               # Pipeline management
│   │   ├── memory.py                  # Memory management
│   │   ├── worktrees.py               # Worktree management
│   │   └── ...                        # skills, conductor, cron, etc.
│   │
│   ├── adapters/                       # CLI-specific hook adapters
│   │   ├── base.py                     # BaseAdapter ABC
│   │   ├── claude_code.py              # Claude Code adapter
│   │   ├── gemini.py                   # Gemini CLI adapter
│   │   ├── cursor.py                   # Cursor adapter
│   │   ├── windsurf.py                 # Windsurf adapter
│   │   └── copilot.py                  # Copilot adapter
│   │
│   ├── agents/                         # Agent spawning and lifecycle (~20 modules)
│   │   ├── spawn.py                    # Agent spawner
│   │   ├── spawn_executor.py           # Spawn execution
│   │   ├── runner.py                   # AgentRunner process management
│   │   ├── definitions.py              # Agent definition models
│   │   ├── registry.py                 # Agent registry (DB-backed)
│   │   ├── isolation.py                # Worktree/clone isolation
│   │   ├── session.py                  # Agent session management
│   │   ├── context.py                  # Agent context injection
│   │   ├── lifecycle_monitor.py        # Agent lifecycle monitoring
│   │   └── ...                         # dry_run, sandbox, pty_reader
│   │
│   ├── workflows/                      # Rule engine and workflow system (~47 modules)
│   │   ├── rule_engine.py              # RuleEngine (declarative enforcement)
│   │   ├── definitions.py              # Rule/workflow/agent definition models
│   │   ├── safe_evaluator.py           # Safe expression evaluator (AST-based)
│   │   ├── engine.py                   # WorkflowEngine (on-demand state machines)
│   │   ├── engine_transitions.py       # Step transition logic
│   │   ├── engine_activation.py        # Workflow activation
│   │   ├── pipeline_executor.py        # PipelineExecutor
│   │   ├── pipeline_state.py           # Pipeline execution state
│   │   ├── loader.py                   # YAML workflow/rule loading
│   │   ├── actions.py                  # Workflow action implementations
│   │   └── ...                         # observers, templates, sync, etc.
│   │
│   ├── hooks/                          # Hook event system (~12 modules)
│   │   ├── hook_manager.py             # Central HookManager coordinator
│   │   ├── events.py                   # HookEvent, HookResponse models
│   │   ├── hook_types.py               # Hook type enums
│   │   ├── skill_manager.py            # Skill discovery for hooks
│   │   ├── broadcaster.py              # Event broadcasting
│   │   └── ...                         # git, health_monitor, verification
│   │
│   ├── servers/                        # HTTP and WebSocket servers
│   │   ├── http.py                     # FastAPI HTTP server
│   │   ├── routes/                     # HTTP API routes (~15 modules)
│   │   │   ├── tasks.py               # Task API
│   │   │   ├── sessions.py            # Session API
│   │   │   ├── agents.py              # Agent API
│   │   │   ├── rules.py               # Rule API
│   │   │   ├── memory.py             # Memory API
│   │   │   └── ...                    # admin, files, voice, etc.
│   │   └── websocket/                  # WebSocket server (~10 modules)
│   │       ├── server.py               # WebSocket server
│   │       ├── broadcast.py            # BroadcastMixin
│   │       ├── chat.py                 # Chat WebSocket
│   │       ├── voice.py                # Voice WebSocket
│   │       └── ...                     # auth, handlers, tmux
│   │
│   ├── mcp_proxy/                      # MCP proxy layer
│   │   ├── server.py                   # FastMCP server implementation
│   │   ├── manager.py                  # MCPClientManager (connection pooling)
│   │   ├── instructions.py             # MCP server instructions
│   │   ├── tools/                      # 20+ internal tool modules
│   │   └── transports/                 # HTTP, stdio, WebSocket transports
│   │
│   ├── sessions/                       # Session management
│   │   ├── manager.py                  # SessionManager
│   │   ├── lifecycle.py                # Background jobs
│   │   ├── processor.py                # SessionMessageProcessor
│   │   └── transcripts/                # Parsers for Claude/Gemini/Codex
│   │
│   ├── tasks/                          # Task system
│   │   ├── expansion.py                # TaskExpander (LLM-based decomposition)
│   │   ├── validation.py               # TaskValidator
│   │   └── prompts/                    # LLM prompts for expansion
│   │
│   ├── memory/                         # Persistent memory system
│   │   ├── manager.py                  # MemoryManager
│   │   └── embeddings.py               # Embedding-based recall
│   │
│   ├── conductor/                      # Orchestration daemon
│   │   ├── loop.py                     # Conductor loop
│   │   └── token_tracker.py            # Token budget tracking
│   │
│   ├── skills/                         # Skill management
│   │   ├── loader.py                   # SkillLoader (filesystem, GitHub, ZIP)
│   │   ├── parser.py                   # SKILL.md parser
│   │   └── sync.py                     # Bundled skill sync on startup
│   │
│   ├── storage/                        # SQLite storage layer (~20 modules)
│   │   ├── database.py                 # LocalDatabase (connection management)
│   │   ├── migrations.py               # Schema migrations
│   │   ├── sessions.py                 # Session CRUD
│   │   ├── tasks.py                    # Task CRUD
│   │   └── ...                         # memory, skills, agents, workflows
│   │
│   ├── llm/                            # Multi-provider LLM abstraction
│   │   ├── service.py                  # LLMService manager
│   │   ├── claude.py                   # Claude provider
│   │   ├── gemini.py                   # Gemini provider
│   │   └── litellm.py                  # LiteLLM fallback
│   │
│   ├── config/                         # Configuration (~15 modules)
│   │   ├── app.py                      # DaemonConfig (YAML config model)
│   │   ├── bootstrap.py                # Pre-DB bootstrap settings
│   │   └── ...                         # features, logging, mcp, tasks, etc.
│   │
│   ├── autonomous/                     # Autonomous execution support
│   ├── clones/                         # Git clone management
│   ├── scheduler/                      # Cron job scheduler
│   ├── search/                         # TF-IDF and semantic search
│   ├── sync/                           # Task/memory sync (JSONL)
│   ├── voice/                          # Voice chat support
│   ├── worktrees/                      # Git worktree management
│   ├── install/                        # CLI hook dispatcher files
│   │   └── shared/                     # Shared rules, skills, workflows
│   │       ├── rules/                  # 11 bundled rule groups (YAML)
│   │       ├── skills/                 # ~23 bundled skills
│   │       └── workflows/             # Built-in workflow definitions
│   └── utils/                          # Utilities (git, daemon client, etc.)
│
├── tests/                              # Test suite (~536 files)
│   ├── conftest.py                     # Pytest fixtures
│   ├── storage/                        # Storage layer tests
│   ├── mcp_proxy/                      # MCP proxy tests
│   ├── workflows/                      # Workflow and rule tests
│   ├── hooks/                          # Hook system tests
│   ├── agents/                         # Agent tests
│   └── ...                             # adapters, sessions, cli, etc.
│
├── web/                                # Web UI (React/TypeScript)
│
├── docs/                               # Documentation
│   ├── architecture/                   # Architecture docs
│   └── guides/                         # User and developer guides
│
└── .github/                            # GitHub configuration
    └── workflows/                      # CI/CD pipelines
```

## Code Statistics

| Metric | Value |
|--------|-------|
| **Source Python Files** | ~513 |
| **Test Python Files** | ~536 |
| **Top-Level Packages** | 30 |
| **Bundled Rule Groups** | 11 |
| **Bundled Skills** | 23 |
| **Test Coverage Target** | 80% |

## Module Dependencies

```
cli/
├── config/
├── runner.py
│   ├── servers/http.py
│   │   ├── servers/routes/*
│   │   ├── adapters/*
│   │   └── hooks/hook_manager.py
│   │       └── workflows/rule_engine.py
│   ├── servers/websocket/
│   ├── mcp_proxy/server.py
│   │   └── mcp_proxy/manager.py
│   └── agents/runner.py
├── storage/database.py
│   └── storage/migrations.py
└── utils/*
```
