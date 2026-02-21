# Plan: Simplify Workflow Engine with Abstract Rule Actions

**Task**: #7335
**Context**: The workflow engine has organically grown 6 distinct conditional evaluation patterns, each with different semantics, evaluators, and context shapes. This creates a steep learning curve for workflow authors, makes rules non-composable, and splits implementation across two different evaluators (one safe, one using `eval()`). This plan unifies these patterns into a coherent architecture with a single evaluator, composable named rules, and a hybrid observer registry.

---

## Current State

### What Exists

| Component | Location | Issue |
| :--- | :--- | :--- |
| block_tools rules | `workflows/enforcement/blocking.py` | Uses `SafeExpressionEvaluator` (AST) — the safe one |
| Step rules | `WorkflowStep.rules` in `definitions.py` | Uses `ConditionEvaluator` (eval) — the unsafe one |
| Transitions | `WorkflowStep.transitions` in `definitions.py` | Uses `ConditionEvaluator` (eval) |
| Exit conditions | `evaluator.py:470-535` | Custom dispatch with 4 sub-types |
| Action when clauses | Lifecycle triggers in YAML | Uses `ConditionEvaluator` (eval) |
| Detection helpers | `detection_helpers.py` | Hardcoded imperative Python |

### Key Problems

1. **Two evaluators**: `ConditionEvaluator` uses Python `eval()` with restricted globals. `SafeExpressionEvaluator` uses AST parsing. A `when: "..."` clause gets different evaluation depending on where it lives.
2. **Rules aren't composable**: `developer.yaml` repeats `blocked_mcp_tools` and `blocked_commands` across 5 of 8 steps. Can't share rules between steps or workflows.
3. **Detection helpers leak the abstraction**: `detect_task_claim()` is ~160 lines of imperative Python doing what YAML should express. Every new state-tracking need adds another `detect_*` function.
4. **Step rules vs block_tools rules**: Two different systems for conditional tool blocking with different capabilities.
5. **Exit conditions have 4 sub-types**: `variable_set`, `expression`, `user_approval`, `webhook` — when most are just expressions.

---

## Phase 1: Unify Evaluators

**Goal**: Single evaluation engine for all `when` conditions.

**Tasks:**
- [ ] Extend `SafeExpressionEvaluator` with helper functions from `ConditionEvaluator` (task_tree_complete, mcp_called, mcp_result_is_null, mcp_failed, mcp_result_has, has_stop_signal, task_needs_user_review, plugin conditions)
- [ ] Replace `ConditionEvaluator.evaluate()` internals with `SafeExpressionEvaluator` — keep public API, swap eval backend
- [ ] Verify all existing `when` expressions work with AST evaluator (audit YAML files)
- [ ] Remove `eval()` usage from `ConditionEvaluator`

**Key files**: `src/gobby/workflows/evaluator.py`, `src/gobby/workflows/safe_evaluator.py`

**Constraints**: No syntactic changes to existing `when` expressions. All patterns (boolean ops, comparisons, `.get()` calls, function calls, attribute access) already supported by AST evaluator.

## Phase 2: Named Rule Definitions

**Goal**: Define rules once, reference by name. Three-tier inheritance with DB as central repository.

**Tasks:**
- [ ] Define `RuleDefinition` Pydantic model (block_tools format: tools/mcp_tools/when/reason/command_pattern)
- [ ] Add `rule_definitions` dict field to `WorkflowDefinition`
- [ ] Add `check_rules` list field to `WorkflowStep`
- [ ] Add `imports` list field to `WorkflowDefinition` for cross-file rule imports
- [ ] Create DB schema for rules table (bundled/user/project tiers)
- [ ] Add rule sync on daemon start (bundled → DB)
- [ ] Add rule resolution logic: file-local > project DB > user DB > bundled DB
- [ ] Engine resolves `check_rules` names at evaluation time, merges with inline rules
- [ ] Migrate `developer.yaml` to use `rule_definitions` + `check_rules` (removes repetition across 5 steps)

**Key files**: `src/gobby/workflows/definitions.py` (new models), `src/gobby/workflows/engine.py` (resolution), `src/gobby/workflows/loader.py` (import loading), `src/gobby/storage/` (new rules table)

**Follow-up (separate task)**: Web UI rules CRUD on the workflow page.

## Phase 3: tool_rules Shorthand

**Goal**: Promote block_tools rules to a first-class YAML field.

**Tasks:**
- [ ] Add `tool_rules` list field to `WorkflowDefinition`
- [ ] Engine evaluates `tool_rules` on BEFORE_TOOL events (delegates to `block_tools()`)
- [ ] Both forms work: `tool_rules` field and `action: block_tools` in triggers

**Key files**: `src/gobby/workflows/definitions.py`, `src/gobby/workflows/lifecycle_evaluator.py`

## Phase 4: Hybrid Observer Registry

**Goal**: Declarative registry for state tracking. Simple observers in YAML, complex observers reference Python behaviors.

**Tasks:**
- [ ] Define `Observer` Pydantic model: `{name, on, match, set}` for YAML observers, `{name, behavior}` for behavior refs
- [ ] Add `observers` list field to `WorkflowDefinition`
- [ ] Create `src/gobby/workflows/observers.py` — observer engine (match events, execute set/behavior)
- [ ] Create YAML observer engine: match tool/mcp_server/mcp_tool, set variables
- [ ] Create behavior registry: `task_claim_tracking`, `detect_plan_mode`, `mcp_call_tracking`
- [ ] Refactor `detect_task_claim()` into `task_claim_tracking` behavior (preserving all edge cases)
- [ ] Refactor `detect_plan_mode_from_context()` into `detect_plan_mode` behavior
- [ ] Refactor `detect_mcp_call()` into `mcp_call_tracking` behavior
- [ ] Wire observer evaluation into lifecycle_evaluator (after_tool events)
- [ ] Update `session-lifecycle.yaml` to declare observers
- [ ] Plugin support: plugins can register custom behaviors

**Key files**: `src/gobby/workflows/definitions.py`, `src/gobby/workflows/detection_helpers.py` (refactor), new `src/gobby/workflows/observers.py`

**Design decisions**:
- **Hybrid over pure-YAML**: `detect_task_claim` edge cases (UUID resolution, CC missing tool_result, auto-linking, multi-format error checking) would require a YAML programming language. Behaviors keep complex logic in Python.
- **Hybrid over keeping detect_* as-is**: Detection helpers violate the engine's design principle. The hybrid makes all observers visible in YAML even when implementations are in Python.
- **Analogy**: Mirrors how actions work — `block_tools` is Python but invoked from YAML.

## Phase 5: Simplify Exit Conditions

**Goal**: Replace 4-subtype exit condition system with expressions.

**Tasks:**
- [ ] Add `exit_when` string field to `WorkflowStep` (single expression, AND-ed)
- [ ] Support string items in `exit_conditions` list as expression shorthand
- [ ] Add `approval:` and `webhook:` sugar syntax for special exit types
- [ ] Deprecate `type: variable_set` and `type: expression` (still supported)
- [ ] Migrate existing exit_conditions usage

**Key files**: `src/gobby/workflows/evaluator.py:470-535`, `src/gobby/workflows/definitions.py`

---

## Architecture

```
                ┌──────────────────────────────────┐
                │     SafeExpressionEvaluator       │
                │  (AST-based, single eval engine)  │
                └──────────┬───────────────────────┘
                           │ used by all:
      ┌────────────────────┼────────────────────┐
      │                    │                    │
┌─────▼─────┐      ┌──────▼──────┐      ┌─────▼─────┐
│ Transitions│      │  Rules      │      │  Action   │
│  (when)    │      │  (when)     │      │  (when)   │
└───────────┘      └─────────────┘      └───────────┘

┌──────────────────────────────────────────────────┐
│              Named Rule Registry                  │
│  DB-backed: bundled > user > project tiers        │
│  check_rules: [name, ...] on steps               │
│  tool_rules: [...] on workflow (lifecycle sugar)  │
│  Web UI CRUD (separate task)                      │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│              Observer Registry                     │
│  YAML observers (on/match/set) for simple cases   │
│  behavior: <name> for complex cases (Python)      │
│  Replaces detect_* as the state-tracking layer    │
└──────────────────────────────────────────────────┘
```

## Task Mapping

| Plan Item | Task Refs | Status |
|-----------|-----------|--------|
| Phase 1: Unify Evaluators | #7989, #7990, #7991 | pending |
| Phase 2: Named Rule Definitions | #7992, #7993, #7994, #7995, #7996, #7997 | pending |
| Phase 3: tool_rules Shorthand | #7998 | pending |
| Phase 4: Hybrid Observer Registry | #7999, #8000, #8001, #8002, #8003, #8004, #8005 | pending |
| Phase 5: Simplify Exit Conditions | #8006, #8007 | pending |
| Web UI Rules CRUD | — | separate task |

## Implementation Notes

- All phases are additive/non-breaking (except Phase 5 which deprecates old exit condition format)
- Each phase is independently valuable and can be shipped without the others
- Phase 1 is prerequisite for consistency but not technically required by others
- Phase 2 delivers the most immediate DRY value for workflow authors
- Phase 4 is the biggest lift but eliminates the most technical debt
