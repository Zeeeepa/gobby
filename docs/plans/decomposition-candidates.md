# Decomposition Candidates Report

**Date:** 2026-02-12
**Strategy:** Strangler Fig Pattern

This report identifies high-priority targets for code decomposition based on file size (>1000 lines), complexity of responsibilities ("God Object" pattern), and recent churn.

## Top Candidates

| Priority | File Path | Lines | Primary Responsibilities (To Split) |
| :--- | :--- | :--- | :--- |
| **1** | `src/gobby/workflows/loader.py` | 1249 | - **Workflow Discovery**: File system scanning, caching, mtime tracking.<br>- **Parsing**: YAML loading, schema validation, "agent definition" parsing.<br>- **Resolution**: Import handling, inheritance logic. |
| **2** | `src/gobby/memory/manager.py` | 1200 | - **Orchestration**: Managing memory lifecycle.<br>- **Embeddings**: Sync/Async generation, reindexing.<br>- **Search**: TF-IDF backend management.<br>- **media**: Image/Screenshot handling. |
| **3** | `src/gobby/workflows/engine.py` | 1120 | - **State Management**: Transitions, history.<br>- **Event Dispatch**: Hook handling, routing.<br>- **Context Building**: Variable resolution, project/session lookup.<br>- **Evaluation**: Rule checking, condition logic. |
| **4** | `src/gobby/cli/installers/shared.py` | 1063 | - **Multi-Target Logic**: Handling Claude/Gemini/Codex specifics.<br>- **Resource Copying**: Agents, workflows, skills.<br>- **Config Manipulation**: Editing JSON config files.<br>- **File Utils**: Symlink vs Copy logic. |
| **5** | `src/gobby/agents/runner.py` | 1022 | - **Execution Loop**: The actual agent run loop.<br>- **Database**: Creation of sessions/runs/states.<br>- **Tooling**: Tool handler logic.<br>- **Configuration**: AgentConfig resolution. |
| **6** | `src/gobby/cli/workflows.py` | 1000 | - **CLI Interface**: Click command definitions.<br>- **Business Logic**: Workflow activation, status retrieval.<br>- **Presentation**: Formatting tables, JSON output. |

## Detailed Analysis

### 1. `src/gobby/workflows/loader.py`
**Diagnosis:** This file has become a catch-all for anything related to "getting a workflow from disk to memory".
**Strangler Strategy:**
1.  Extract **Discovery** logic into `src/gobby/workflows/discovery/scanner.py`.
2.  Extract **Parsing** logic into `src/gobby/workflows/parsing/yaml_parser.py`.
3.  Extract **Cache** logic into `src/gobby/workflows/discovery/cache.py`.
4.  Keep `WorkflowLoader` as a thin facade that coordinates these.

### 2. `src/gobby/memory/manager.py`
**Diagnosis:** Allows too many low-level concerns (like how to process an image or how to calculate TF-IDF) to leak into the high-level manager.
**Strangler Strategy:**
1.  Extract **Image/Media** handling to `src/gobby/memory/services/media.py`.
2.  Extract **Embedding** orchestration to `src/gobby/memory/services/embeddings.py`.
3.  Extract **Search** management to `src/gobby/memory/services/search.py`.
4.  Refactor `MemoryManager` to delegate to these services.

### 3. `src/gobby/workflows/engine.py`
**Diagnosis:** The `WorkflowEngine` class is doing too much: it's both the runtime implementation AND the logic for deciding what happens next.
**Strangler Strategy:**
1.  Extract **Context Building** to `src/gobby/workflows/engine/context.py`.
2.  Extract **Event Handling** to `src/gobby/workflows/engine/dispatcher.py`.
3.  Extract **State Transitions** logic to `src/gobby/workflows/engine/transitions.py`.
4.  Keep `WorkflowEngine` as the main entry point.

### 4. `src/gobby/cli/installers/shared.py`
**Diagnosis:** A procedural script that has grown into a module.
**Strangler Strategy:**
1.  Create a `ContentInstaller` abstract base class.
2.  Implement `WorkflowInstaller`, `AgentInstaller`, `SkillInstaller`.
3.  Move generic file ops to `src/gobby/utils/filesystem.py`.

### 5. `src/gobby/agents/runner.py`
**Diagnosis:** Mixes database transactional logic with long-running execution loops.
**Strangler Strategy:**
1.  Extract **Preparation** (DB work) to `src/gobby/agents/services/run_preparer.py`.
2.  Extract **Execution** (Loop) to `src/gobby/agents/services/executor.py`.
3.  Extract **Tool Handling** into a specialized `RunToolHandler`.

### 6. `src/gobby/cli/workflows.py`
**Diagnosis:** View layer (CLI) is tightly coupled with Control Application layer.
**Strangler Strategy:**
1.  Move business logic (e.g. "activate workflow") to `src/gobby/workflows/service.py` or similar domain service.
2.  Move formatting logic to `src/gobby/cli/formatting/workflows.py`.
3.  Keep CLI commands as declarative wrappers.
