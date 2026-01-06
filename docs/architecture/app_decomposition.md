# App.py Decomposition Analysis

**File:** `src/gobby/config/app.py`
**Lines:** 1,773
**Classes:** 31 Pydantic config models + 5 utility functions
**Task:** gt-f2176f
**Parent:** gt-ef47cc (Decompose app.py into focused configuration modules)

## Current Structure Summary

The file contains all Pydantic configuration models for the Gobby daemon, plus YAML loading utilities.

## Class Inventory

| # | Class Name | Lines | Dependencies |
|---|------------|-------|--------------|
| 1 | WebSocketSettings | 56-91 | - |
| 2 | LoggingSettings | 93-143 | - |
| 3 | CompactHandoffConfig | 145-160 | - |
| 4 | ContextInjectionConfig | 162-208 | - |
| 5 | SessionSummaryConfig | 210-233 | - |
| 6 | CodeExecutionConfig | 235-314 | - |
| 7 | ToolSummarizerConfig | 316-358 | - |
| 8 | RecommendToolsConfig | 360-443 | - |
| 9 | ImportMCPServerConfig | 465-503 | - |
| 10 | MCPClientProxyConfig | 505-592 | - |
| 11 | GobbyTasksConfig | 594-615 | TaskExpansionConfig, TaskValidationConfig |
| 12 | LLMProviderConfig | 617-631 | - |
| 13 | LLMProvidersConfig | 633-690 | LLMProviderConfig |
| 14 | TitleSynthesisConfig | 692-711 | - |
| 15 | WebSocketBroadcastConfig | 713-733 | - |
| 16 | WebhookEndpointConfig | 735-778 | - |
| 17 | WebhooksConfig | 780-800 | WebhookEndpointConfig |
| 18 | PluginItemConfig | 803-814 | - |
| 19 | PluginsConfig | 816-835 | PluginItemConfig |
| 20 | HookExtensionsConfig | 837-852 | WebSocketBroadcastConfig, WebhooksConfig, PluginsConfig |
| 21 | TaskExpansionConfig | 854-921 | - |
| 22 | TaskValidationConfig | 923-1027 | - |
| 23 | WorkflowConfig | 1029-1056 | - |
| 24 | MessageTrackingConfig | 1058-1089 | - |
| 25 | SessionLifecycleConfig | 1091-1134 | - |
| 26 | MetricsConfig | 1136-1153 | - |
| 27 | MemoryConfig | 1155-1318 | - |
| 28 | MemorySyncConfig | 1320-1343 | - |
| 29 | SkillSyncConfig | 1345-1368 | - |
| 30 | SkillConfig | 1370-1410 | - |
| 31 | DaemonConfig | 1413-1596 | All above configs |

## Utility Functions

| Function | Lines | Purpose |
|----------|-------|---------|
| expand_env_vars | 24-53 | Environment variable substitution in config content |
| load_yaml | 1598-1644 | Load YAML/JSON config with env expansion |
| apply_cli_overrides | 1647-1678 | Apply CLI args over config dict |
| generate_default_config | 1681-1698 | Create default config file |
| load_config | 1701-1743 | Main config loading orchestration |
| save_config | 1746-1773 | Save config to YAML |

## Dependency Graph

```
DaemonConfig (root)
├── WebSocketSettings
├── LoggingSettings
├── CompactHandoffConfig
├── ContextInjectionConfig
├── SessionSummaryConfig
├── CodeExecutionConfig
├── ToolSummarizerConfig
├── RecommendToolsConfig
├── ImportMCPServerConfig
├── MCPClientProxyConfig
├── GobbyTasksConfig
│   ├── TaskExpansionConfig
│   └── TaskValidationConfig
├── LLMProvidersConfig
│   └── LLMProviderConfig
├── TitleSynthesisConfig
├── HookExtensionsConfig
│   ├── WebSocketBroadcastConfig
│   ├── WebhooksConfig
│   │   └── WebhookEndpointConfig
│   └── PluginsConfig
│       └── PluginItemConfig
├── WorkflowConfig
├── MessageTrackingConfig
├── SessionLifecycleConfig
├── MetricsConfig
├── MemoryConfig
├── MemorySyncConfig
├── SkillSyncConfig
└── SkillConfig
```

## Proposed Module Groupings

### Module 1: `config/network.py` (~150 lines)
**WebSocket and networking settings**
- WebSocketSettings
- WebSocketBroadcastConfig
- LoggingSettings

Dependencies: None (leaf configs)

### Module 2: `config/session.py` (~200 lines)
**Session lifecycle and messaging**
- CompactHandoffConfig
- ContextInjectionConfig
- SessionSummaryConfig
- SessionLifecycleConfig
- MessageTrackingConfig

Dependencies: None (leaf configs)

### Module 3: `config/tasks.py` (~280 lines)
**Task management configuration**
- TaskExpansionConfig
- TaskValidationConfig
- GobbyTasksConfig (depends on above)

Dependencies: TaskExpansionConfig, TaskValidationConfig → GobbyTasksConfig

### Module 4: `config/mcp.py` (~200 lines)
**MCP client/proxy configuration**
- MCPClientProxyConfig
- ImportMCPServerConfig
- ToolSummarizerConfig

Dependencies: None (leaf configs)

### Module 5: `config/llm.py` (~200 lines)
**LLM providers and AI features**
- LLMProviderConfig
- LLMProvidersConfig
- TitleSynthesisConfig
- CodeExecutionConfig
- RecommendToolsConfig

Dependencies: LLMProviderConfig → LLMProvidersConfig

### Module 6: `config/hooks.py` (~180 lines)
**Hook extensions, webhooks, plugins**
- WebhookEndpointConfig
- WebhooksConfig
- PluginItemConfig
- PluginsConfig
- HookExtensionsConfig

Dependencies: WebhookEndpointConfig → WebhooksConfig, PluginItemConfig → PluginsConfig → HookExtensionsConfig

### Module 7: `config/memory.py` (~230 lines)
**Memory and skills**
- MemoryConfig
- MemorySyncConfig
- SkillSyncConfig
- SkillConfig

Dependencies: None (leaf configs)

### Module 8: `config/workflow.py` (~50 lines)
**Workflow engine**
- WorkflowConfig
- MetricsConfig

Dependencies: None (leaf configs)

### Module 9: `config/loader.py` (~180 lines)
**Config loading utilities**
- expand_env_vars()
- load_yaml()
- apply_cli_overrides()
- generate_default_config()
- load_config()
- save_config()

Dependencies: DaemonConfig (for type hints and default generation)

### Module 10: `config/app.py` (main module, ~200 lines)
**DaemonConfig and re-exports**
- DaemonConfig (main class)
- ENV_VAR_PATTERN constant
- Re-exports from all modules for backwards compatibility

Dependencies: All modules above

## Extraction Order

Based on dependency analysis, extract in this order (leaf nodes first):

1. **config/network.py** - No dependencies
2. **config/session.py** - No dependencies
3. **config/memory.py** - No dependencies
4. **config/workflow.py** - No dependencies
5. **config/mcp.py** - No dependencies
6. **config/llm.py** - LLMProviderConfig → LLMProvidersConfig (internal dep)
7. **config/hooks.py** - Internal hierarchy deps
8. **config/tasks.py** - TaskExpansionConfig, TaskValidationConfig → GobbyTasksConfig
9. **config/loader.py** - Needs DaemonConfig for type hints
10. **config/app.py** - Imports and re-exports all, defines DaemonConfig

## Strangler Fig Strategy

### Phase 1: Extract leaf configs
Move standalone config classes (no dependencies) to new modules. Update imports in app.py to re-export from new locations.

### Phase 2: Extract grouped configs
Move grouped configs with internal dependencies. Ensure proper import ordering.

### Phase 3: Extract loader utilities
Move loader functions after all configs are extracted.

### Phase 4: Slim down app.py
Final app.py contains only DaemonConfig + re-exports.

## Test Strategy

For each extraction:
1. Create module with configs
2. Add re-exports to app.py's `__all__`
3. Update any direct imports in codebase
4. Run `uv run pytest` to verify no regressions
5. Run `uv run mypy src/gobby/config/` for type checking

## Notes

- All configs use Pydantic BaseModel with Field() for validation
- Many configs have field validators (`@field_validator`)
- DaemonConfig has `model_config = {"populate_by_name": True}` for alias support
- ENV_VAR_PATTERN is used by expand_env_vars(), should stay with loader
- DEFAULT_IMPORT_MCP_SERVER_PROMPT constant (lines 446-462) belongs with ImportMCPServerConfig

## Risk Assessment

**Low Risk:**
- Leaf configs with no dependencies
- Utility functions (pure functions)

**Medium Risk:**
- Configs with internal dependencies (need correct import order)
- DaemonConfig (many fields reference other configs)

**High Risk:**
- None identified - configs are self-contained Pydantic models
