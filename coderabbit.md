Fix the following issues. The issues can be from different files or can overlap on same lines in one file.

- Verify each finding against the current code and only fix it if needed.

In @.gitignore at line 249, Add a dedicated Node.js/frontend section in .gitignore (separate from the "Moat task system" block) and include the TypeScript incremental build artifact pattern by adding "*.tsbuildinfo" alongside the existing "node_modules/" entry so Vite/TypeScript build artifacts in the web/ subtree are ignored.

- Verify each finding against the current code and only fix it if needed.

In @.gobby/memories.jsonl at line 2, Update or remove the stale memory entry about generate_handoff and create_handoff: either delete the memory with id f3849c98 or edit its content to reflect that the handoff consolidation (task #9112) was completed in commit 91b58384 and the functions were removed; ensure the revised memory references generate_handoff, create_handoff, task #9112 and commit 91b58384 so agents won't receive conflicting records.

- Verify each finding against the current code and only fix it if needed.

In @.gobby/memories.jsonl at line 9, The file .gobby/memories.jsonl contains sensitive operational guidance and hardcoded enforcement details—specifically the "memory-review-gate" escape-hatch threshold (< 3) and the exact bypass command set_variable('pending_memory_review', False, 'session')—which must be removed or protected; update the repo by removing or redacting any entries that disclose gate bypass procedures or hardcoded thresholds (search for the memory id bda21375 and the bypass invocation), and either move runtime-derived session memories to an untracked runtime-only store (add .gobby/memories.jsonl or session-derived entries to .gitignore) or sanitize these entries before committing so that enforcement logic (memory-review-gate) is not publicly reversible and no escape-hatch values remain hardcoded in repository-tracked data.

- Verify each finding against the current code and only fix it if needed.

In @.gobby/memories.jsonl around lines 1 - 70, The .gobby/memories.jsonl file currently contains plaintext session UUIDs in the source_id field for entries where "source" == "session" or "mcp_tool"; remove or anonymize those IDs before committing by changing the exporter/writer that produces .gobby/memories.jsonl to either drop source_id for session-sourced entries or replace it with a non-reversible hash (HMAC with a repo-specific salt) and update any consumers that expect original UUIDs; alternatively add a pre-commit filter that scrubs source_id only for lines matching `"source": "session"` or `"source": "mcp_tool"` to prevent accidental commits.

- Verify each finding against the current code and only fix it if needed.

In @.gobby/memories.jsonl around lines 5 - 7, Remove the duplicate memory entry with id "1be52935-5155-5df2-b2c2-8f8a74898634" (the older, near-identical soft-delete/unq constraint note) and keep the entry "e13e3687-74c2-55d2-8f93-aedd4ed816c5" which is slightly more descriptive; ensure the .gobby/memories.jsonl file contains only the retained record and that no other duplicate entries from the same session id "e23c9bb8-fb60-4787-b846-46f9c067a44b" remain.

- Verify each finding against the current code and only fix it if needed.

In @agent-death-match-r1.md around lines 1 - 159, The file agent-death-match-r1.md should be moved out of the repository root into a docs location to avoid top-level clutter; relocate it to docs/design-notes/ (or docs/) and update any references (e.g., README or index) that point to agent-death-match-r1.md so links still resolve, and add an entry in the docs navigation or table-of-contents if one exists.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/event_handlers/_agent.py around lines 178 - 188, Replace the bare "except Exception: pass" with structured logging: catch the exception as "except Exception as e" and log it using the instance logger (e.g. self._logger.exception or self._logger.error(..., exc_info=True)) including context like session_id and the operation (calling self._session_manager.get_session and processing step_vars/active skill filtering for skills). Ensure you still swallow or re-raise as desired after logging, but do not leave the exception silently ignored.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/event_handlers/_session.py around lines 534 - 535, The code merges agent_body.workflows.variables directly into changes which allows agent-defined keys to overwrite reserved internal keys (e.g., _agent_type, _active_rule_names); update the logic around changes.update(agent_body.workflows.variables) to first validate/filter keys against a reserved set (e.g., reserved_keys = {"_agent_type","_active_rule_names", ...}) and either reject/log any collisions or rename/prefix offending agent variable keys before merging (or explicitly copy only non-reserved keys). Locate the merge in _session.py where agent_body.workflows.variables is used and implement the filter/rename step to prevent accidental overwrites.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/event_handlers/_session.py around lines 474 - 552, The method _activate_default_agent currently constructs ConfigStore, LocalWorkflowDefinitionManager, and SkillManager on every call; refactor to accept or cache these dependencies instead: add attributes (e.g. self._config_store, self._def_manager, self._skill_mgr) initialized in the containing class constructor or as lazy cached properties, replace inline instantiations (ConfigStore(), LocalWorkflowDefinitionManager(self._session_storage.db), SkillManager(self._session_storage.db)) with those cached/injected instances, and remove the corresponding lazy imports inside _activate_default_agent so the method uses self._config_store.get_daemon_config(), self._def_manager.list_all(...), and self._skill_mgr.list_skills() to avoid repeated DB/IO creation and simplify unit testing.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/event_handlers/_session.py around lines 545 - 550, The except block silently swallows JSONDecodeError when parsing var_row.definition_json, dropping corrupted variables; change the except to "except json.JSONDecodeError as e:" and emit a warning including the variable name (var_row.name), the exception message (e), and a short context of the offending definition_json so callers can debug why the variable was skipped (use the module logger or logging.warning to report this instead of pass).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/skill_manager.py around lines 140 - 145, Replace the hardcoded magic number in the storage.list_skills call by adding a module-level constant MAX_SKILL_LOAD_LIMIT = 10_000 and use that constant as the limit argument in the call (the list_skills invocation in skill_manager.py); after loading, check the returned db_skills length and, if it equals MAX_SKILL_LOAD_LIMIT, emit a warning via the module logger (or process logger) indicating the result may be truncated so callers/operators are alerted. Ensure the constant is documented with a short comment and that the warning references the list_skills call so it’s clear which load was truncated.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/skill_manager.py around lines 24 - 59, Change the untyped parameter of _db_skill_to_parsed to use the storage Skill type (imported under TYPE_CHECKING) or make attribute access defensive: import Skill in a TYPE_CHECKING block and annotate the function as def _db_skill_to_parsed(skill: "Skill") -> ParsedSkill, or if you prefer resilience use getattr(skill, "name", None) / defaults for other fields inside _db_skill_to_parsed and validate metadata before accessing nested keys; ensure you reference the same attribute names used currently (name, description, content, version, license, compatibility, allowed_tools, metadata, source_path, source_type, source_ref, always_apply, injection_format) and return ParsedSkill with defaults when attributes are missing.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/rules/auto-task/guide-task-continuation.yaml at line 9, The condition currently hardcodes a fallback literal 8 in variables.get('max_stop_attempts', 8) which duplicates the default declared elsewhere; remove the inline fallback so the expression uses variables.get('max_stop_attempts') (letting a missing variable surface as an error) and leave other fallbacks (e.g., variables.get('stop_attempts', 0)) as-is; update the when expression that references variables.get('auto_task_ref'), task_tree_complete(variables.get('auto_task_ref')), variables.get('stop_attempts', 0) and variables.get('max_stop_attempts') accordingly so the default in max_stop_attempts.yaml remains authoritative.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/rules/auto-task/init-auto-task-ref.yaml around lines 6 - 14, The description and effect for the rule are contradictory: the rule currently triggers on event: session_start and when variables.get('auto_task_ref') is not None but its effect is type: set_variable with variable: auto_task_ref value: '' (clearing the ref) while the description claims the agent will not stop until the task is closed. Decide the intended behavior and fix accordingly: either (A) if the intent is to clear stale refs, change the description to state this rule resets/clears auto_task_ref at session_start to avoid stale blocking, or (B) if the intent is to enforce a task-completion gate, replace the effect (type: set_variable) with an appropriate blocking effect (e.g., a rule effect that prevents session end or sets a session-block flag) so the rule actually blocks stopping when auto_task_ref is set; reference the rule fields event: session_start, when: variables.get('auto_task_ref'), variable: auto_task_ref, and type: set_variable to locate and update the YAML.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/rules/auto-task/init-auto-task-ref.yaml at line 10, The rule's when condition currently uses "variables.get('auto_task_ref') is not None", which still matches empty strings; update the condition for the auto_task_ref check to require a non-empty/truthy value (e.g. replace the is not None guard with a truthiness check or an explicit non-empty check) so the rule only fires when auto_task_ref contains a non-empty value.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/rules/auto-task/notify-task-tree-complete.yaml around lines 13 - 18, The template message contains a truncated sentence ("Any errors or warnings") — update the notify-task-tree-complete.yaml template (message that references variables.auto_task_ref and close_task()) to complete that sentence so it reads clearly for users, e.g., "If there are any errors or warnings, please review and resolve them before closing the task." Ensure the new sentence flows with the surrounding lines ("Task {{ variables.auto_task_ref or '(unknown)' }} complete!... You may now close the task using close_task().") and preserves punctuation and spacing.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/rules/memory-lifecycle/memory-capture-after-close.yaml at line 9, The when-expression uses the unsafe pattern of wrapping intermediate lookups with "or {}" (the fragment using event.data.get('tool_input') or {} and .get('arguments') or {}) which will fail if tool_input or arguments are non-dict truthy values; change it to perform chained .get calls that supply an explicit default dict at each step (i.e., call event.data.get('tool_input', {}) then .get('arguments', {}) then .get('commit_sha')) to safely handle missing or non-dict values, and apply the same replacement in the related rule file suggest-memory-after-close.yaml so both rules use the safer nested dict access form.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/rules/memory-lifecycle/memory-capture-nudge.yaml around lines 13 - 19, In memory-capture-nudge.yaml, remove the word "convention" from the save-trigger list ("a preference, fact, convention, or instruction") so the list reads "a preference, fact, or instruction", making it consistent with the later directive "Do NOT generalize one-time instructions into conventions"; update any nearby wording if needed to avoid reintroducing the same meaning elsewhere in the same block.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/rules/progressive-disclosure/require-schema-before-call.yaml around lines 13 - 15, The rule's agent-facing "reason" text in require-schema-before-call.yaml was made generic and removed the actionable corrective step; update the reason field in the progressive-disclosure/require-schema-before-call rule to explicitly instruct agents to call get_tool_schema(...) (or the precise corrective call previously used) so the agent knows how to remediate the violation, and add a brief changelog/ADR note documenting this behavioral change so downstream users know the rule became stricter.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/rules/progressive-disclosure/require-server-listed-for-schema.yaml around lines 13 - 14, Update the YAML rule's reason text to restore actionable recovery steps instead of the generic message: replace "You did not follow progressive disclosure." with a concise instruction that tells the agent to call list_mcp_servers() first, then call list_tools(server) for the selected server, and finally call get_tool_schema() for the chosen tool (e.g., "You must follow progressive disclosure: call list_mcp_servers(), then list_tools(server) for a selected server, then get_tool_schema() for the chosen tool."). Ensure the rule referencing progressive-disclosure/require-server-listed-for-schema.yaml includes these exact function names to guide automated agents.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/rules/progressive-disclosure/require-servers-listed.yaml around lines 13 - 14, Restore an actionable reason in the progressive-disclosure rule by replacing the vague message "You did not follow progressive disclosure." with an explicit recovery sequence: instruct the agent to call list_mcp_servers() first, then call list_tools(), and only call get_tool_schema() when the tool is actually needed; keep the progressive-disclosure framing but include these concrete steps so agents know to retry list_tools after listing MCP servers and to defer get_tool_schema() until required.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/rules/stop-gates/require-task-close.yaml at line 9, Update the fallback for max_stop_attempts in the stop-gate rule that currently uses variables.get('max_stop_attempts', 3); change that default to 8 so it matches the canonical value used in other stop-gate rules (e.g., require-task-close, require-error-triage). Locate the when expression in block-stop-after-tool-block.yaml (the condition using variables.get('max_stop_attempts', 3)) and replace the 3 with 8, keeping the rest of the condition unchanged.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/skills/canvas/SKILL.md around lines 54 - 79, The JSON example contains an inline comment that makes it invalid JSON; update the code fence or remove the comment so readers can copy/parse it. Specifically, edit the code block around the sample components (the object with "components", "root_id", "data_model", etc.) and either change the opening/closing fence from ```json to ```jsonc to allow the leading comment, or delete the comment line "// 1. Define a flat component surface map" so the fence can remain ```json; ensure the fence markers still match and the sample object (root, username-field, save-btn, data_model) remains unchanged.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/skills/frontend-style/SKILL.md around lines 272 - 284, The fenced code block containing the directory tree in SKILL.md lacks a language specifier; update the opening fence to include "text" (i.e., change the triple-backtick that starts the web/src/ tree to ```text) so the block is correctly marked as plain text and satisfies MD040; locate the directory-tree block in SKILL.md and replace its opening fence accordingly.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/skills/frontend-style/SKILL.md around lines 92 - 101, The fenced code block in SKILL.md that lists the variable mappings (the plain-text block containing lines like "background  → var(--bg-primary)" and others) lacks a language specifier; update that opening fence to declare the language as text (use ```text) to satisfy markdownlint MD040 so the block is treated as plain text.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/variables/chat_mode.yaml around lines 1 - 3, The chat_mode variable is set to "bypass" but lacks documentation of what "bypass" means and what other values are allowed; update the chat_mode definition to include a clear description enumerating accepted values (e.g., "bypass", "strict", "interactive" or whatever your system supports), and explain the semantics of "bypass" (what behavior it triggers) so downstream rules and UI code can rely on the documented modes; reference the variable name chat_mode and its current value bypass when adding the expanded description.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/variables/max_stop_attempts.yaml around lines 1 - 3, You increased variable max_stop_attempts from 3 to 8 which could extend runaway sessions; inspect the stop-gate logic (require-error-triage) and ensure it has explicit safeguards—add or verify cost caps, elapsed-time or token-usage limits, and progress-detection checks so sessions cannot loop indefinitely; update the stop-gate implementation to enforce a hard global cap (e.g., token or time budget) and/or detect lack of meaningful progress before allowing further attempts, and add unit/integration tests around require-error-triage to assert behavior when max_stop_attempts is reached.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/variables/require_commit_before_close.yaml around lines 1 - 3, Update the YAML description for the variable require_commit_before_close to explain the intent and behavior instead of restating the default; change the description from "Default require_commit_before_close to true" to something like "Require an uncommitted diff to exist before a session can be closed" (or similar) so readers understand what gating behavior this variable controls and when to override it.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/server.py around lines 170 - 178, call_context is declared as None then later assigned a dict which breaks strict mypy; give call_context an explicit optional dictionary type (e.g. Optional[Dict[str, str]] or dict[str, str] | None) where it is declared so assignments in _resolve_and_set_project_context/session handling are type-correct, and add the necessary typing import (Optional/Dict or use PEP 604 union) so usage in the block that checks self._session_manager and session.external_id type-checks cleanly.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/server.py around lines 175 - 178, The call_tool code is redundantly calling self._session_manager.get(session_id) even though _resolve_and_set_project_context already fetched it; modify _resolve_and_set_project_context to return the resolved session (or None) and update call_tool to reuse that returned session instead of calling session_manager.get again, then set call_context = {"session_id": session_id, "conversation_id": session.external_id} only when the returned session is truthy (preserving current behavior for missing sessions).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/agent_messaging.py around lines 316 - 345, In get_inter_session_messages validate the direction parameter against the set {"inbox","sent","all"} and raise ValueError for invalid values instead of silently defaulting; replace the bare except Exception with specific exception handlers (e.g., except ValueError as e, except DatabaseError as e — or other concrete errors thrown by message_manager.list_messages/_resolve) and log/return those errors; and return a total field (not just count of the page) by calling a total-count helper on message_manager (e.g., message_manager.count_messages or similar) so the response includes {"success": True, "messages": [...], "count": len(messages), "total": total} to enable proper pagination handling.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/canvas.py around lines 426 - 429, Remove the leftover implementation-note comments around the canvas copy logic: delete the draft lines referencing "we'll implement this mounting in http.py", the discussion about using /tmp, and "Let's use ~/.gobby/canvas" so only concise, final comments remain; locate the block that mentions canvas_dir (the copy-to-canvas_dir section in src/gobby/mcp_proxy/tools/canvas.py) and replace the draft notes with a single clear comment or none at all.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/canvas.py around lines 62 - 65, The module defines process-global mutable state (_canvases, _canvas_locks, _rate_counters, _broadcaster_ref) which is unsafe for multi-process deployments; either refactor these into a per-application singleton or manager class (e.g., CanvasManager) or attach them to an explicit app/state object so each worker has its own instance (move logic that touches _canvases, _canvas_locks, _rate_counters, _broadcaster_ref into methods on that manager or into app.state), or if you intentionally only support single-process for Phase 1, add a clear top-of-file comment stating the single-process assumption and why; update all usages (functions that reference _canvases/_canvas_locks/_rate_counters/_broadcaster_ref) to obtain them from the new manager/app state rather than from module globals.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/canvas.py around lines 250 - 259, The broadcast payload uses camelCase keys but the frontend expects snake_case; locate the broadcaster invocation where _broadcaster_ref["func"] is assigned to bc and replace the keyword arguments dataModel and rootComponentId with snake_case names data_model and root_component_id so the call is await bc(event="surface_update", canvas_id=actual_canvas_id, conversation_id=actual_convo_id, surface=components, data_model=actual_data_model, root_component_id=root_id); make the identical change for the other surface_update broadcast call elsewhere in the file that uses the same argument names.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/canvas.py around lines 420 - 422, The canvas_present function currently accepts any absolute file path (source_path) and copies it, so restrict source_path to the repository/workspace by resolving both source_path and the workspace/project root (e.g., workspace_root or project_root) via Path.resolve(strict=True) and ensure source_path is a descendant (use Path.is_relative_to or compare resolved path parts) before proceeding; also keep the is_file/readable checks and reject paths that escape via symlinks or are outside the workspace with a descriptive error, e.g., return {"success": False, "error": "file path outside workspace"}.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/internal.py around lines 254 - 258, The current check "if context:" treats an empty dict as falsy and skips injecting _context, causing a TypeError when a tool requires _context; change the guard to explicitly check for None (e.g., use "if context is not None:") around the inspect.signature(tool.func) and coerced_arguments["_context"] = types.SimpleNamespace(**context) injection so empty dicts are accepted; keep using inspect.signature, tool.func, and coerced_arguments["_context"] as the referenced symbols.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/skills/__init__.py around lines 112 - 123, The current heuristic of calling storage.list_skills(..., limit=limit * 5 if active_names is not None else limit) can under- or over-fetch; change the call in the block that constructs skills so that when active_names is provided you fetch either without a limit or with a sufficiently large upper bound (e.g., pass None or a very large number) instead of limit * 5, then apply the existing post-filter using active_set = set(active_names) and skills = [s for s in skills if s.name in active_set][:limit] to enforce the final cap; update the storage.list_skills invocation (and its limit argument) accordingly so the post-filter reliably returns up to limit active skills.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/skills/__init__.py around lines 96 - 123, Replace the bare "except Exception: pass" around session resolution with targeted error handling: catch the specific exceptions that indicate "session not found" or "invalid reference" and handle them by leaving active_names as None, and for all other exceptions log the error at debug (or error) level including exception details; apply the same change to the identical pattern in search_skills. Update the handlers that wrap session_manager.resolve_session_reference and session_manager.get (and the corresponding block in search_skills) to avoid swallowing unexpected exceptions and to emit a debug log with the exception info when non-expected errors occur.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent/_factory.py around lines 48 - 50, Replace the eager f-string logging in the AgentResolutionError handler with structured logging that preserves the exception; in the except AgentResolutionError as e block (in _factory.py) call logger.error with a format string and the exception as an argument (e.g. "Agent resolution failed: %s", e) or pass exc_info=e to capture the traceback, rather than using f"...", so the message is lazily formatted and the exception chain is preserved.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent/_factory.py around lines 44 - 50, resolve_agent currently has a bare except and manager.get_by_name can raise DB/attribute exceptions that will propagate; update resolve_agent to replace the bare "except Exception:" with specific exception handlers (e.g., catch the DB client error type and AttributeError) and re-raise or wrap unknown errors into AgentResolutionError so callers get a predictable exception; additionally, in the caller that invokes resolve_agent (the spawn-agent factory code that currently only catches AgentResolutionError), add a broad except Exception handler around the resolve_agent(...) call to log the unexpected error (including the exception details) and return None so database/attribute/runtime errors don’t bubble up as unhandled 500s.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent/_implementation.py around lines 197 - 205, Replace the runtime assert with an explicit check: if agent_body is None raise a clear exception (e.g., ValueError) instead of using assert, and modify the call to _handle_self_persona to accept and receive the existing self_step_variables (the dict built earlier containing agent_name, assigned_task_id, session_task) so that _handle_self_persona merges these variables into whatever step variables it uses and calls session_manager.update_step_variables with the merged result; update _handle_self_persona signature and its internal logic to merge incoming self_step_variables before invoking session_manager.update_step_variables, mirroring how _handle_self_mode receives and forwards self_step_variables.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent/_modes.py around lines 110 - 116, The function _handle_self_persona currently types agent_body, session_manager, and db as Any; replace those Any annotations with the concrete types used in the codebase: annotate agent_body: AgentDefinitionBody, session_manager: LocalSessionManager, and db: DatabaseProtocol, and add the necessary imports for those symbols at the top of the module; ensure the function signature and any internal uses align with those types so mypy passes.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent/_modes.py around lines 143 - 147, Replace the raw SQL/db.fetchall call that builds all_rules with a call to the repository/manager: use LocalWorkflowDefinitionManager (or its list_all(workflow_type="rule") method) to retrieve workflow definitions and then apply the enabled and not-deleted filters (enabled == True and deleted_at is None) if the manager does not accept those filters directly; specifically replace the db.fetchall + WorkflowDefinitionRow.from_row usage in _modes.py with LocalWorkflowDefinitionManager.list_all(workflow_type="rule") (or manager.list_all(...)) and map/convert results into WorkflowDefinitionRow objects only if needed so schema access stays confined to the manager.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/workflows/_rules.py around lines 185 - 188, The code currently calls def_manager.hard_delete(deleted_row.id) on any soft-deleted result from def_manager.get_by_name(name, include_deleted=True) without checking its type; update the logic in the block using get_by_name, deleted_row and hard_delete to first verify deleted_row.workflow_type == "rule" (and that deleted_row.deleted_at is set) before invoking def_manager.hard_delete, so only soft-deleted rows of workflow_type "rule" are permanently removed.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/chat_session_permissions.py around lines 342 - 358, The fallback currently builds plan_dirs from Path(".gobby/plans") and Path(".claude/plans") which resolve against CWD; change it to resolve those relative paths against the session's project directory when available (e.g., use self.project_path or self._project_path if present) so you search the intended project; keep the existing logic that also checks Path.home(), collect candidates, pick newest, set self._plan_file_path and return newest.read_text(), but construct plan_dirs as (Path(self.project_path) / ".gobby" / "plans") and (Path(self.project_path) / ".claude" / "plans") when project_path exists, otherwise fall back to the current behavior.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/chat_session_permissions.py around lines 295 - 300, Declare and initialize the missing attribute _on_mode_persist on the ChatSession class (add it to the attribute stubs/dataclass as an Optional[Callable] defaulting to None) so accessing self._on_mode_persist cannot raise AttributeError, and replace the fire-and-forget call in the method that currently references _on_mode_persist (same block with the try/except) with a guarded call (e.g., if self._on_mode_persist: self._on_mode_persist(mode)) and change the bare except to catch Exception as e and log the error (use the existing logger on the class, e.g., self._logger or a module logger) instead of silently passing.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/http.py around lines 431 - 440, Canvas broadcaster currently swallows failures because _canvas_broadcaster does nothing when no WebSocket server or method exists and doesn't log exceptions; update the _canvas_broadcaster closure used by set_broadcaster to (1) check for ws = self.services.websocket_server or self.websocket_server and if missing or if not hasattr(ws, "broadcast_canvas_event") call logger.warning or logger.error with context that canvas event could not be delivered and include the kwargs (or a concise representation), and (2) wrap the await ws.broadcast_canvas_event(**kwargs) call in a try/except that catches exceptions and calls logger.exception with a descriptive message referencing _canvas_broadcaster and the event details so delivery failures are visible for debugging.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/http.py around lines 550 - 560, The StaticFiles mount of canvas (app.mount("/__gobby__/canvas", StaticFiles(...)) serving files from canvas_dir) exposes user-written HTML and bypasses auth/CORS protections; replace the direct StaticFiles mount with a dedicated route handler or APIRouter endpoint that (1) enforces authentication/authorization before serving, (2) validates file extensions (allow only safe types like .txt/.json or reject .html/.htm), and (3) sets strict response headers (e.g., Content-Security-Policy: "sandbox; default-src 'self'", X-Frame-Options: DENY, and a safe Content-Type such as text/plain when returning user files) or alternatively serve files as text and recommend client-side sandboxed iframe rendering; update any references in canvas.py that write .html files to either restrict output extensions or mark them unsafe so the handler will block them. Ensure you modify the code paths around canvas_dir, app.mount, and any canvas-serving function to implement these checks and headers so the auth middleware and header protections apply.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/admin.py around lines 484 - 535, The inline restarter_script builds a subprocess start block that opens log files with bare open() and force-kills the old process with SIGKILL after a 30s wait; update the script so the log and err file handles used when launching subprocess.Popen are opened with with-context managers around the Popen and pid-file write (refer to restarter_script and variables log_file/err_file/pid_file/proc) to ensure deterministic close on exceptions, and change the shutdown escalation sequence in the PID-wait loop (the os.kill logic using signal.SIGKILL) to first send signal.SIGTERM, wait a short second or two for graceful exit, and only then send signal.SIGKILL if the process still exists.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/admin.py around lines 456 - 566, The restart handler (router.post("/restart") -> restart()) lacks any authentication/authorization check, allowing public access to a sensitive operation; add an auth guard at the top of restart() (before reading _restart_in_progress and spawning the restarter) that mirrors the pattern used for /admin/shutdown or /test/* endpoints: validate the request (e.g. check a test_mode flag or an admin token/header/session via your existing auth utility) and return an HTTP 403/unauthorized response if the caller is not allowed; ensure the guard runs before any side effects (setting _restart_in_progress, launching subprocesses, or calling server._process_shutdown()) so unauthorized requests do nothing.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/configuration.py around lines 779 - 795, The PUT handler save_ui_settings currently ignores None values so clients cannot delete an individual UI setting; update save_ui_settings to detect explicit clears (e.g., when a field is present and None, or when you choose an agreed sentinel like empty string) and remove those keys from config_store instead of skipping them: when building entries from _UI_SETTINGS_KEYS check request.__dict__ or the Pydantic/Dataclass presence indicator (or check for "" sentinel) so that explicit clears are collected into a deletions list and call config_store.delete or config_store.delete_many for keys like f"{_UI_SETTINGS_PREFIX}{key}", while continuing to call config_store.set_many(entries, source="ui") for non-null values. Ensure both code paths reference the same _UI_SETTINGS_PREFIX and keys so removals are per-key rather than wiping the whole store.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/rules.py around lines 240 - 241, Replace the broad except Exception in the block that raises HTTPException with a specific catch for pydantic.ValidationError: import ValidationError from pydantic and change the handler so it only catches ValidationError (and still raises HTTPException(status_code=400, detail=f"Invalid rule definition: {e}") from e) to avoid masking other errors (keep the existing HTTPException symbol and the "from e" chaining).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/rules.py around lines 236 - 251, The code calls RuleDefinitionBody.model_validate(definition) but ignores the returned validated model; capture the validated instance (e.g., validated = RuleDefinitionBody.model_validate(definition)) and when preparing stored JSON use validated.model_dump() (or model_dump_json()) instead of the raw definition dict so any field validators/transformations are applied before serializing into fields["definition_json"]; still pop "name" and extract description/enabled/priority/tags from the validated data (or from the validated.model_dump()) to avoid losing transformed values.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/broadcast.py around lines 290 - 300, The broadcast_canvas_event function currently accepts **kwargs; change its signature to explicitly require event: str, canvas_id: str, conversation_id: str (plus **kwargs: Any) and update the docstring accordingly; then build the message using those parameters ("type": "canvas_event", "timestamp": ..., "event": event, "canvas_id": canvas_id, "conversation_id": conversation_id, **kwargs) and call self.broadcast(message) so callers that always pass those fields match the peer methods like broadcast_pipeline_event and broadcast_agent_message.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/chat.py around lines 306 - 319, The broadcast is always using reason "session_restored" even for new sessions; change the creation flow so you know whether the session was actually restored (e.g., have _create_chat_session return (session, restored) or set a session.is_restored flag), then build mode_msg with reason set to "session_restored" only when restored is True (otherwise use "session_created" or omit the reason), and send that conditional mode_msg to all clients in the existing loop that iterates self.clients.keys() and calls ws.send.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/chat.py around lines 254 - 260, _persist_mode currently does synchronous DB I/O by calling _sm.update_chat_mode on the event-loop thread; change it to perform the DB call off-thread (e.g., make _persist_mode async and call await asyncio.to_thread(_sm.update_chat_mode, _db_sid, mode)) or schedule a background task (e.g., use asyncio.create_task with asyncio.to_thread) so the event loop isn't blocked, and if you make the callback async update the permissions mixin's set_chat_mode to await session._on_mode_persist (or keep it fire-and-forget and use create_task) — refer to _persist_mode, _sm.update_chat_mode, session._on_mode_persist, set_chat_mode, and _can_use_tool when applying the change.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/server.py around lines 256 - 265, The handler _handle_canvas_interaction currently returns silently when canvas_id or action is missing and does not report resolve_interaction failures; update _handle_canvas_interaction to validate inputs and send an error message back to the client via the websocket (use the same send/send_json pattern used by other handlers such as _handle_stop_request) when canvas_id or action is missing, and wrap the await resolve_interaction(canvas_id, action) call in a try/except that catches exceptions, logs/creates a canvas-specific error payload and sends that error back to the client before rethrowing or returning; reference the websocket parameter, the data dict, the canvas_id/action variables and the resolve_interaction import to locate where to add the validation, error send and exception handling.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/server.py around lines 321 - 328, The import statement "from gobby.mcp_proxy.tools.canvas import cancel_conversation_canvases" should be moved out of the loop to avoid repeated imports; place that import once either at module top or immediately before the for loop that iterates over self._chat_sessions (the loop using conv_id, session) and then call cancel_conversation_canvases(conv_id) inside the loop as before; update references to the function name cancel_conversation_canvases so the loop body simply invokes it without the inline import.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/session_control.py around lines 635 - 638, The current removal uses substring matching ("session_id in s") which can over-remove; change the filter to only match session_id as a distinct token within subscription strings (not any substring). Replace the comprehension that builds to_remove with a token-aware check (e.g., use re.search with re.escape(session_id) and word-boundary/separator checks or split the subscription string on known delimiters and compare segments) so only subscriptions where the session_id is an exact token are removed; update imports to include re if using regex and keep variable names subs, to_remove, session_id and the subtraction subs -= to_remove.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/session_control.py around lines 583 - 587, The WebSocketClient protocol declares subscriptions: set[str] but _handle_connection never initializes websocket.subscriptions, causing repeated defensive checks in session_control.py and handlers.py; fix by initializing websocket.subscriptions = set() inside _handle_connection when you set other client metadata so all handlers (e.g., session_control.py using websocket.subscriptions and any code in handlers.py) can rely on the invariant that subscriptions exists and is non-None.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/skills/injector.py around lines 214 - 217, Update the SkillInjector class docstring to document the new sources filter: add a step describing that if config.sources is set, the injector verifies context.source is contained in config.sources and returns False otherwise (reference symbols: SkillInjector, config.sources, context.source). Keep the ordering consistent with the existing numbered matching steps and briefly state the purpose of the gate (restricts injection by source) so readers know this check is part of the matching contract.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/skills/search.py at line 42, _search.py's SearchFilters.allowed_names is never used because _passes_filters only checks category, tags_any, and tags_all; add a guard in _passes_filters to return False when allowed_names is set and the candidate's name is not in that list. Specifically, inside the _passes_filters function add a check referencing SearchFilters.allowed_names (and the candidate object's name property used elsewhere in the function) to short-circuit and exclude items whose name is not present in allowed_names; preserve existing behavior when allowed_names is None or empty.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/skills/sync.py around lines 49 - 58, The three identical blocks computing needs_update (comparing description, content, version, license, compatibility, allowed_tools, metadata, always_apply, injection_format) are duplicated; extract a single helper function named _needs_content_update(existing, parsed) that returns the boolean comparison of those fields and replace each needs_update assignment (where variables like installed and parsed are used) with a call to _needs_content_update(installed, parsed); ensure the helper lives near related sync logic and is used in all three spots so adding a new ParsedSkill field requires one change only.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/inter_session_messages.py around lines 238 - 293, The list_messages function calls self.db.fetchall(...) directly; wrap the read query in the SQLite connection context manager on the DB object (e.g., with self.db.connection: or the project's equivalent) before calling self.db.fetchall to satisfy the storage guidelines. Edit list_messages to open the DB context, run the SELECT (keeping the same query, params.extend([limit, offset]) and rows = self.db.fetchall(query, tuple(params))), then convert rows with InterSessionMessage.from_row and return the list — ensuring the fetch and conversion happen inside the connection context used by self.db.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/inter_session_messages.py around lines 267 - 275, The code currently treats any unknown direction as "all"; update the API to validate the direction parameter explicitly by typing it as Literal["inbox", "sent", "all"] and raising a ValueError for any other value instead of falling through to the else; in the function that builds the SQL filters (the block that uses direction, session_id, conditions, params) add an initial check that raises on invalid strings and keep the three explicit branches (direction == "inbox", direction == "sent", direction == "all") so callers receive a clear error for typos/unexpected values.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/session_models.py around lines 61 - 62, Change the chat_mode field from a plain str to a narrow Literal type or add runtime validation: update the annotation for chat_mode to typing.Literal["plan", "accept_edits", "normal", "bypass"] (and import Literal) in session_models.py so type checkers catch invalid values for chat_mode; alternatively, if runtime enforcement is preferred, add a small validator in the class constructor or a pydantic/attrs validator for the chat_mode attribute that raises a clear error when the value is not one of "plan", "accept_edits", "normal", or "bypass".

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/sessions.py around lines 396 - 408, The update_step_variables function currently does a non-atomic read via self.get(...) followed by a separate self.db.execute(...), which creates a TOCTOU race; wrap the operation in a DB transaction using the SQLite connection context manager and perform the read-and-write inside that transaction (e.g., begin a transaction, re-fetch the session row for update, merge step_variables, json.dumps the merged value, update updated_at and write the row), or if supported emulate SELECT ... FOR UPDATE before calling the UPDATE; ensure you use the same transactional connection rather than separate self.get calls so concurrent updates cannot be lost.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/sessions.py around lines 313 - 318, update_chat_mode currently writes chat_mode directly and returns None; change it to run inside the SQLite transaction context (use self.db as context manager), validate chat_mode against the allowed set (e.g., {"plan","accept_edits","normal","bypass"}) and raise or reject invalid values, update the sessions row to also set updated_at = CURRENT_TIMESTAMP, and after executing the UPDATE return the refreshed Session (use existing helper like get_session_by_id or the class method that loads a Session by id) or return None if no row was updated; reference the update_chat_mode method, the sessions table, self.db transaction context, and the get_session_by_id loader in your changes.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/skills.py around lines 470 - 475, The code silently mutates the caller-provided source when project_id is set (currently in create_skill: the project_id/source check and assignment), so stop overriding the input; instead, validate and enforce an explicit source for project-scoped skills: do not assign to the parameter source, introduce a local stored_source (or require source to equal "project") and either raise a ValueError when a disallowed source (e.g., "installed") is passed with project_id, or log a clear warning and use stored_source only for internal IDs (e.g., keep source unchanged for the returned object but use stored_source for generate_prefixed_id), referencing the existing symbols create_skill, project_id, source, stored_source (new), and generate_prefixed_id to locate and update the logic.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/skills.py around lines 850 - 870, install_from_template creates a skill with source="installed" but create_skill auto-changes source to "project" when project_id is set, causing mismatched existence checks; add a boolean parameter (e.g., skip_auto_source=False) to create_skill and, when True, prevent the auto-set logic that changes source based on project_id, then call create_skill(..., source="installed", skip_auto_source=True) from install_from_template (and update any callers/tests if needed) so the existence check and created skill use the same source value; alternatively, if you prefer to keep auto-setting, make the existence check in install_from_template treat an existing skill with source="project" as equivalent to "installed" for the same template (adjust the lookup to check both sources).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/agent_resolver.py around lines 110 - 116, The current try/except in the agent definition loader swallows parsing/validation errors and returns None; update the except block in the code that parses row.definition_json and constructs AgentDefinitionBody to log the failure with structured context (include row.name and/or row.id and the raw definition_json) and the exception details (use logger.exception or logger.error(..., exc_info=True)) before returning None so consumers can distinguish parse errors from "not found"; keep using the same logger instance and ensure the log message names the function (e.g., the AgentDefinitionBody construction/parse) for searchable context.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/definitions.py around lines 196 - 201, resolve_agent() currently resolves the provider sentinel but leaves base_branch="inherit" untouched, so change resolve_agent() to also check for and replace the "inherit" sentinel for base_branch (similar to the existing provider logic) before returning the agent/execution config; ensure the resolved base_branch value (actual branch name or None) is passed downstream so the isolation handling (worktree/clone in the execution flow) receives a real branch name instead of the literal "inherit".

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/rule_engine.py around lines 114 - 118, The code uses the first resolved effect type (body.resolved_effects[0].type) as the heuristic for fail-open vs fail-closed when evaluating a rule-level condition (body.when) via _evaluate_condition; add a concise inline comment next to that logic explaining the rationale (e.g., that the first effect determines whether a condition error should skip the entire rule or treat it as blocking) and note the consequence for mixed-effect rules (e.g., [inject_context, block]) so future readers understand why the first effect is chosen and the expected behavior on evaluation errors.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/rule_engine.py around lines 357 - 377, The two synchronous helpers _has_pending_messages and _pending_message_count perform blocking self.db.fetchone calls inside an async evaluation path; convert them into async functions (e.g., async def _has_pending_messages(...), async def _pending_message_count(...)) and replace the blocking self.db.fetchone usages with non-blocking alternatives—either await an async DB API if available (e.g., await self.db.fetchone_async(...)) or run the synchronous call in a thread executor (e.g., await asyncio.to_thread(lambda: self.db.fetchone(...))). Update all callers (notably the async evaluate method) to await these new async helpers so DB I/O does not block the event loop.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/rule_engine.py around lines 237 - 246, The functions _apply_effect, _should_block, and _apply_set_variable currently type the effect parameter as Any; change their signatures to use the concrete RuleEffect type (e.g., effect: RuleEffect) to satisfy strict typing and enable IDE/mypy checks, import RuleEffect where needed, and update any internal usages or helper function signatures that assume RuleEffect so the code compiles under mypy (no behavior changes required).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/selectors.py around lines 154 - 163, Move the inline "import json" out of the loop to module level and stop silently swallowing all exceptions in resolve_variables_for_agent (and mirror the fix in resolve_rules_for_agent): replace the broad except with catching json.JSONDecodeError (and/or TypeError if needed), log a warning (or use an existing logger) about the malformed var.definition_json including the variable identifier, then continue to the next iteration; this targets the loop that inspects var.definition_json inside resolve_variables_for_agent and should be applied similarly to resolve_rules_for_agent.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/selectors.py around lines 23 - 36, The dim == "*" branch in _match_rule is dead because parse_selector("*") currently returns ("name","*"); to restore/support the explicit "*" selector either remove the unreachable branch or (preferred) update parse_selector to return ("*","*") when the raw selector is exactly "*" so _match_rule will receive dim=="*" and short-circuit True; update the parse_selector implementation (and any tests) to handle the "*" input and ensure callers still expect the same tuple shape so _match_rule(name/source/tag/group/*) works as intended.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/selectors.py around lines 58 - 67, Move the "import json" out of the loop to module level and stop swallowing parse errors: in the loop that iterates over all_rules, replace the bare "except Exception: pass" around json.loads(rule.definition_json) with a specific except json.JSONDecodeError as e and log a structured warning including the rule identity (e.g., rule.id or rule.name) and the error before falling back to an empty dict; reference the all_rules loop and rule.definition_json so you update the parsing logic there and ensure you use the module logger (or logging.getLogger(__name__)) for the message.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/sync.py around lines 637 - 846, sync_bundled_variables duplicates the same control flow as sync_bundled_workflows and sync_bundled_rules; refactor by extracting a shared helper (e.g. _sync_bundled_definitions) that takes parameters for db, variables_path (or path), workflow_type ("variable"/"workflow"/"rule"), key_field ("variable"/"name"/"rules"), a validator callable/class (VariableDefinitionBody etc.), and callbacks for propagate/tag enforcement (_propagate_to_installed, _ensure_gobby_tag_on_installed); move YAML load/validate/upsert/restore/skip/orphan cleanup/logging into that helper and have sync_bundled_variables call it with the appropriate arguments, ensuring you reuse LocalWorkflowDefinitionManager methods (get_by_name, create, update, restore, delete) and preserve existing behaviors like include_deleted/include_templates and priority/source/tags handling.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/sync.py around lines 680 - 688, Replace the f-string log in the except block for VariableDefinitionBody validation: instead of f"Invalid variable definition in {yaml_file.name}" pass a static message string to logger.warning and put the filename (yaml_file.name) and the error (ve or str(ve)) into the extra dict to match structured logging used elsewhere; update the logger.warning call (the one that currently references VariableDefinitionBody validation) to include extra={"filename": yaml_file.name, "error": str(ve)} and keep appending the human-readable error to result["errors"] as before.

- Verify each finding against the current code and only fix it if needed.

In @tests/mcp_proxy/tools/test_agent_messaging.py around lines 332 - 337, The assertion is a no-op due to operator precedence; fix the check on mock_command_manager.create_command call args by explicitly branching on the positional args length: inspect call_kwargs = mock_command_manager.create_command.call_args and if len(call_kwargs[0]) > 3 assert call_kwargs[0][3] == ["Read", "Grep"] else assert call_kwargs[1].get("allowed_tools") == ["Read", "Grep"]; use those exact symbols (call_kwargs and mock_command_manager.create_command) so the test fails if the allowed_tools value is wrong.

- Verify each finding against the current code and only fix it if needed.

In @tests/mcp_proxy/tools/test_agent_messaging.py around lines 89 - 156, The fixtures mock_session_manager, mock_message_manager, mock_command_manager, mock_session_var_manager, mock_db should each declare return type -> MagicMock and messaging_registry should declare -> InternalToolRegistry; update the function signatures for mock_session_manager, mock_message_manager, mock_command_manager, mock_session_var_manager, mock_db to include the MagicMock return annotation and update messaging_registry to return InternalToolRegistry so static checks pass (refer to the fixture function names: mock_session_manager, mock_message_manager, mock_command_manager, mock_session_var_manager, mock_db, messaging_registry and the called helper add_messaging_tools).

- Verify each finding against the current code and only fix it if needed.

In @tests/mcp_proxy/tools/test_agent_messaging_broadcast.py around lines 20 - 22, Extract the duplicated mock classes (MockSession, MockMessage, MockCommand, MockWebSocket) into a shared test fixture module (e.g., a tests conftest or tools/shared_tests module) and import them into both test_agent_messaging_broadcast.py and test_agent_messaging.py; update the tests to use the imported fixtures/classes instead of their local copies, ensure any helper factory names/signatures are preserved (or adapt callers) so tests using MockSession/MockMessage/MockCommand/MockWebSocket continue to work without further changes.

- Verify each finding against the current code and only fix it if needed.

In @tests/mcp_proxy/tools/test_canvas.py around lines 208 - 218, Remove the dead assertion that checks canvas_mod._canvases.get("canv-close") is None (it duplicates get_canvas("canv-close") check) and instead assert that the canvas state was updated to indicate completion before it was removed: capture the canvas state (the object stored under key "canv-close") prior to the pop (or inspect the state change via the same API used to mutate it) and assert its completed/closed flag is True; keep the existing assertions on get_canvas("canv-close") being None and on broadcaster.events[0]["event"] == "close_canvas".

- Verify each finding against the current code and only fix it if needed.

In @tests/mcp_proxy/tools/test_canvas.py around lines 1 - 16, This test module is missing a pytest marker; add a module-level pytestmark variable to mark these as unit tests (e.g., set pytestmark = pytest.mark.unit) near the top of tests/mcp_proxy/tools/test_canvas.py (the file already imports pytest), so the test runner and linters recognize the category for functions like cancel_conversation_canvases, create_canvas_registry, get_canvas, resolve_interaction, and sweep_expired.

- Verify each finding against the current code and only fix it if needed.

In @tests/mcp_proxy/tools/test_canvas.py around lines 19 - 32, Add missing type hints to the fixture and helper functions: annotate the pytest fixture clean_canvas_state with a return type of Iterator[None] (import typing.Iterator), update MockBroadcaster.__init__ to annotate self and any params and give it -> None, annotate MockBroadcaster.__call__ with appropriate parameter types and a return type (e.g., -> None or -> Awaitable[None] depending on implementation), and add explicit return type annotations to the broadcaster and registry functions (e.g., -> Callable[..., Any] or the concrete callable/type they return). Ensure required typing imports (Iterator, Callable, Any, Awaitable) are added at the top of the test module.

- Verify each finding against the current code and only fix it if needed.

In @tests/mcp_proxy/tools/test_internal_action_tools.py around lines 255 - 262, Add a new async test in tests/mcp_proxy/tools/test_internal_action_tools.py that covers the automated path for set_handoff_context: call session_registry.call("set_handoff_context", {"session_id": "sess-1"}) without the "content" key and assert the returned result has result["success"] is True and result["mode"] == "automated"; mirror the existing test_agent_authored_path structure, use the same pytest.mark.asyncio decorator and session_registry fixture so both branches (agent_authored and automated) are exercised.

- Verify each finding against the current code and only fix it if needed.

In @tests/servers/routes/test_admin.py around lines 145 - 168, The module-level flag _restart_in_progress in the admin.restart() closure is persisting across tests causing order-dependent failures; add an autouse pytest fixture in the test module that imports the admin module and resets admin._restart_in_progress = False before each test (or yield and reset after), ensuring tests like test_restart_endpoint and test_restart_endpoint_double_restart_guard run isolated; reference the admin.restart closure flag _restart_in_progress and use the test module-level fixture to clear it before each test.

- Verify each finding against the current code and only fix it if needed.

In @tests/skills/test_injector.py around lines 401 - 419, Add a unit test named test_sources_empty_list_behavior that constructs SkillAudienceConfig(audience="all", sources=[]) and an AgentContext(source="claude") and asserts injector._matches_audience(config, ctx) is False to document that an explicit empty sources list rejects all sources; if tests fail, update the _matches_audience implementation to treat sources=None as permissive but sources==[] as a concrete empty allowlist (return False for any non-None ctx.source), and ensure handling of ctx.source is consistent (ctx.source None should remain rejected when sources is a non-empty list or empty list).

- Verify each finding against the current code and only fix it if needed.

In @tests/skills/test_parser.py around lines 235 - 265, Add tests to cover invalid and empty `sources` cases for parse_skill_text: create one test passing an unexpected type (e.g., metadata.gobby.sources: 123 or a dict) and assert the parser either raises the expected exception or results in a predictable state (e.g., skill.audience_config is None or sources is an empty list) and another test where sources: [] ensures the parser handles empty lists (either preserves empty list or coerces to None based on existing contract). Use the existing test style and reference parse_skill_text and skill.audience_config.sources to locate where to add assertions.

- Verify each finding against the current code and only fix it if needed.

In @tests/storage/test_inter_session_messages.py around lines 453 - 478, The test relies on time.sleep(0.01) to order messages which is fragile; instead pass explicit sent_at timestamps when calling mgr.create_message for m1, m2, m3 to guarantee ordering (use increasing datetime values), and remove the nested Setup class by returning a types.SimpleNamespace (or a small dataclass) with attributes alpha, beta, manager, messages so the fixture is idiomatic; keep existing calls to mgr.mark_read(m1.id) and mgr.mark_delivered(m1.id) unchanged while replacing the Setup block with the SimpleNamespace return.

- Verify each finding against the current code and only fix it if needed.

In @tests/storage/test_inter_session_messages.py around lines 433 - 435, The pytest fixture function setup is missing a return type annotation; update the @pytest.fixture def setup(self, temp_db: LocalDatabase) signature to include an explicit return type (e.g., -> None if it only sets up state and returns nothing, or -> Iterator[T] / -> Generator[T, None, None] with the appropriate T if it yields a value) so it complies with the project's type-hinting rules; modify the signature in the setup fixture accordingly (use -> None for simple setup-only fixtures or the specific Iterator/Generator type matching what setup yields/returns).

- Verify each finding against the current code and only fix it if needed.

In @tests/storage/test_sessions_chat_mode.py around lines 79 - 91, Add a test that covers an unsupported chat_mode: create a session via LocalSessionManager.register (same pattern as test_all_modes), then call sm.update_chat_mode(session.id, "invalid_mode") and assert the call rejects invalid values (e.g., raises ValueError) so callers/DB don’t silently persist typos; if the current implementation accepts arbitrary strings, update LocalSessionManager.update_chat_mode to validate against the allowed set ("plan","accept_edits","normal","bypass") and raise a clear exception, then make the test expect that exception.

- Verify each finding against the current code and only fix it if needed.

In @tests/storage/test_skill_sync.py around lines 346 - 354, The helper _create_test_project currently inserts directly via raw SQL; if a higher-level API exists (e.g., ProjectManager.create_project, ProjectService.create, or a create_project utility) use that instead to create the test project so tests don't depend on schema details—replace the raw SQL block in _create_test_project with a call to the appropriate project creation API (passing project_id and a name) and fall back to the raw SQL only if no such API is available.

- Verify each finding against the current code and only fix it if needed.

In @tests/workflows/test_observers_detection.py around lines 195 - 210, Update the test_detects_plan_mode_outside_conversation_history prompt so the <conversation-history> block itself contains the "Plan mode is active" indicator and then place a separate non-historical <system-reminder> afterwards (so the old regex-based findall(r"<system-reminder>(.*?)</system-reminder>", ...) would have matched the history and produced a false positive while the fixed detect_plan_mode_from_context should ignore the historical block and detect only the current reminder); keep the call to detect_plan_mode_from_context(workflow_state) and the assert workflow_state.variables.get("mode_level") == 0 unchanged.

- Verify each finding against the current code and only fix it if needed.

In @tests/workflows/test_observers_detection.py around lines 168 - 193, The test test_ignores_plan_mode_inside_conversation_history is vacuous because the nested text "You are in PLAN MODE." does not match the case-sensitive entries in detect_plan_mode_from_context's plan_mode_indicators, so change the embedded plan-mode string inside the <conversation-history> block to one of the real exact indicator texts (e.g. "You are in plan mode" or "Plan mode is active") so the test actually exercises the stripping/detection logic and then assert that workflow_state.variables does not gain "mode_level".

- Verify each finding against the current code and only fix it if needed.

In @web/package.json around lines 46 - 49, Move the CLI-only ink packages out of runtime dependencies: remove "ink", "ink-select-input", "ink-spinner", and "ink-text-input" from the dependencies block and add them under devDependencies in package.json; ensure the only consumer is the setup script (tsx src/setup/cli.tsx) and there are no runtime imports elsewhere before making this change, and verify the package.json diff shows them deleted from dependencies and added to devDependencies (not merely marked changed) to avoid the inconsistent merge artifact.

- Verify each finding against the current code and only fix it if needed.

In @web/package.json at line 75, The package.json currently pins "esbuild": "^0.25.0" which conflicts with Vite 6.0.3's dependency range; either downgrade the esbuild entry to "^0.24.0" or remove the explicit "esbuild" dependency if Vite's bundled esbuild suffices for your build:setup script—update package.json accordingly and then run package manager install to verify no version conflicts remain (look for the "esbuild" key and the "build:setup" script to decide whether the explicit dependency is needed).

- Verify each finding against the current code and only fix it if needed.

In @web/package.json at line 61, The peer/type mismatch risk: change the "three" dependency spec in package.json from ">=0.118.0 <1" to a narrowed semver that matches @types/three (e.g. "^0.182.0") so runtime three and @types/three resolve to the same minor range; update the "three" entry and run install/lockfile update, noting that three-spritetext and react-force-graph-3d are compatible with this tighter "^0.182.0" range.

- Verify each finding against the current code and only fix it if needed.

In @web/src/App.tsx around lines 392 - 399, The effect suppresses exhaustive-deps and can capture stale closures for updateChatMode and sendMode; to fix, ensure those callbacks are stable by memoizing them (or wrapping their latest implementation in refs) so the effect can safely omit them from deps, and reference stable values for settings.defaultChatMode and webChatSessions (e.g., derive restoredMode from a memoized selector or snapshot) before calling updateChatMode/sendMode; specifically, stabilize the functions updateChatMode and sendMode (or expose stable wrappers) and ensure the restoredMode computation uses a stable webChatSessions value so the useEffect depending only on conversationId and sessionsHook.isLoading is safe.

- Verify each finding against the current code and only fix it if needed.

In @web/src/App.tsx around lines 226 - 239, The useEffect that fetches UI settings should create an AbortController and pass its signal to fetch (inside the effect where you build baseUrl and call fetch(`${baseUrl}/api/config/ui-settings`)), then call controller.abort() in the cleanup instead of only toggling the cancelled flag; also update the .catch to ignore AbortError (or check error.name === 'AbortError') so aborted requests don't log or try to update state, leaving the existing localStorage try/catch logic intact.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/ConfigurationPage.tsx around lines 313 - 315, The Restart Now button lacks an explicit type and swallows fetch errors; change the element in ConfigurationPage.tsx to use type="button" and replace the inline onClick with an async handler (e.g., handleRestart or restartNow) that performs fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/admin/restart`, { method: 'POST' }), checks response.ok before calling setShowRestart(false), and handles failures by catching network errors and surfacing them (e.g., set a local error state or show an alert) so the banner is only dismissed on a successful restart response.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/ConfigurationPage.tsx around lines 730 - 732, The Restart button's onClick handler in ConfigurationPage (the button that calls fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/admin/restart`, ...) and then calls setShowRestart(false)) needs two fixes: add type="button" to the <button> to satisfy the Biome lint rule (a11y/useButtonType), and replace the unguarded .then(...) with proper error handling so setShowRestart(false) is only called on a successful network/HTTP response. Implement this by extracting the handler into an async function (or a promise chain) that awaits fetch, checks response.ok and handles non-OK statuses and fetch errors (using try/catch or .catch) before calling setShowRestart(false); ensure any caught errors are surfaced/logged instead of being silently ignored.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/MemoryPage.tsx around lines 364 - 367, The fallback button in MemoryPage.tsx (the element that calls setViewMode('graph')) lacks an explicit type attribute and will default to "submit"; update that button element to include type="button" so clicking it doesn't submit surrounding forms—locate the button using the onClick handler referencing setViewMode('graph') and add the type attribute.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/SessionDetail.tsx around lines 253 - 265, In SessionDetail (the JSX rendering the "Watch in Chat" button inside the dropdown), add an explicit type="button" attribute to the button element that uses onWatchInChat so it doesn't default to type="submit" and accidentally submit a surrounding form; update the button with the type prop alongside existing props (disabled, title, onClick) where setDropdownOpen(false) and onWatchInChat(session) are called.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/SessionDetail.tsx around lines 312 - 319, The WatchIcon SVG is decorative and missing accessibility annotations; update the WatchIcon component so the root <svg> element includes aria-hidden="true" (and remove or avoid adding a <title>) to satisfy lint/a11y/noSvgWithoutTitle; locate the WatchIcon function and add the aria-hidden attribute to the <svg> tag so the icon is hidden from assistive tech while the surrounding "Watch in Chat" button remains the accessible label.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/Settings.tsx around lines 96 - 103, The button elements in Settings.tsx (rendering each mode with variables m, settings.defaultChatMode and handler onDefaultChatModeChange) are missing an explicit type and will default to type="submit" inside forms; update the button JSX for the mode buttons (the element using className `theme-option` and onClick={() => onDefaultChatModeChange(m.id)}) to include type="button" to prevent unintended form submissions.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/Settings.tsx at line 93, The <label>Default Mode</label> element is not associated with a form control; update the Settings component to either replace the literal "<label>Default Mode</label>" with a non-semantic "<span>" or make the button group accessible by giving the container div a role="group" and an id and then referencing that id via aria-labelledby on the container; locate the markup with the "<label>Default Mode</label>" text in Settings.tsx and apply one of these fixes so the label is either non-semantic or correctly associated with the group of buttons.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/SkillsGrid.tsx around lines 135 - 143, The toggle currently rendered in SkillsGrid as a div with class "workflows-toggle" and an onClick handler must be made keyboard-accessible: replace the div with a semantic <button> (or add role="switch", tabIndex=0) and ensure onKeyDown handles Enter and Space to call onToggle (preserving e.stopPropagation()), add aria-checked={skill.enabled} (or aria-pressed if using button) and an accessible name or aria-label, and keep the existing className logic that uses skill.enabled so styling and state remain consistent.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/SkillsGrid.tsx around lines 23 - 28, The getCategory function performs an unsafe cast of skill.metadata.category to string; update getCategory (used with GobbySkill) to verify that skill.metadata exists and that typeof skill.metadata.category === 'string' before returning it, otherwise return null — replace the current "as string" cast with a runtime typeof check to ensure non-string values (numbers, booleans, objects) don't get returned as strings.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/SkillsGrid.tsx around lines 91 - 95, The card currently rendered in the SkillsGrid component is an interactive <div> with an onClick handler but no keyboard support or semantic role; update the JSX to make this element accessible by either converting the outer <div> to a <button> (preferred) or adding role="button", tabIndex={0}, and an onKeyDown handler that invokes the same onSelect handler for Enter and Space keys; ensure the element keeps the conditional class names (workflows-card, workflows-card--template, workflows-card--deleted) and that onClick and onSelect remain wired so keyboard and pointer activation behave identically.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/SkillsGrid.tsx around lines 169 - 193, The SVG icons EditIcon, DeleteIcon, and DownloadIcon are missing accessibility attributes; mark each top-level <svg> as decorative by adding aria-hidden="true" to the <svg> element in the EditIcon, DeleteIcon, and DownloadIcon functions (since their parent <button> already has an aria-label) so screen readers ignore the redundant graphic.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/SkillsPage.tsx around lines 276 - 299, In SkillsPage.tsx, several <button> elements (the tab buttons that call setActiveTab, and toolbar buttons that call setShowImport, handleRestore, and handleCreate inside the SkillsPage component) lack an explicit type attribute which can cause accidental form submissions; update each of these buttons to include type="button" (i.e., the two tab buttons rendering LibraryIcon and HubIcon, the Import and Restore buttons that call setShowImport and handleRestore, and the New button that calls handleCreate — and the other button at the later occurrence flagged on line 349) to ensure they do not default to submit.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/SkillsPage.tsx around lines 263 - 265, The error toast currently renders as a non-interactive <div> with an onClick handler (in SkillsPage, className "skills-error-toast" showing errorMessage and calling setErrorMessage(null)), which is not keyboard-accessible; fix by making the element accessible: either replace the <div> with a semantic <button> styled via "skills-error-toast" and keep the onClick to call setErrorMessage(null), or add role="alert" (or role="button" if dismissible) plus tabindex="0" and keyDown handler that treats Enter/Space to call setErrorMessage(null), and ensure an appropriate aria-label for screen readers.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/SkillsPage.tsx around lines 241 - 246, The use of window.prompt inside handleMoveToProject produces poor UX and no validation; replace it with a controlled modal/project-picker UI that opens from handleMoveToProject, lets the user select or type a valid Project ID (or choose from a dropdown), validates the input (non-empty and, if applicable, matches the project's ID format like UUID) and then calls moveToProject(skillId, selectedPid); on failure call showError('Failed to move skill to project') as before and close/cancel the modal appropriately. Update handleMoveToProject to trigger the modal (instead of prompt), pass the skillId into the modal state, and ensure moveToProject and showError remain in the useCallback dependency array.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/SkillsPage.tsx around lines 132 - 136, The handleRefresh function currently sets refreshing true then calls refreshSkills() without awaiting it and clears the spinner with a fixed setTimeout; change handleRefresh to await the async refreshSkills() call and move setRefreshing(false) into a finally block so the spinner is cleared only after refreshSkills completes (remove the setTimeout), e.g., use try { await refreshSkills() } finally { setRefreshing(false) } while keeping the function async and preserving the useCallback dependency on refreshSkills.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/SkillsPage.tsx around lines 458 - 478, LibraryIcon and HubIcon SVGs are missing accessible titles; update each component (LibraryIcon and HubIcon) to provide an accessible name by either adding a <title> element inside the SVG and wiring it with aria-labelledby (generate a unique id per icon) or by adding role="img" and an aria-label prop passed from the parent button; ensure the title/aria-labelledby id is unique if multiple icons render and prefer aria-labelledby over title-only to guarantee screen readers announce the icon.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.css around lines 316 - 319, The .workflows-card-type--skill background (#1a2a3a) collides visually with .workflows-card-badge--source; update the CSS for .workflows-card-type--skill to use a slightly different background color (e.g., tweak the blue channel or lighten/darken slightly) so the skill pill is clearly distinct from the source badge while keeping the same contrast with its text color (#38bdf8); locate and modify the .workflows-card-type--skill rule in WorkflowsPage.css and test the two pills together to confirm sufficient visual distinction and accessibility contrast.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/A2UIRenderer.tsx around lines 33 - 49, CanvasErrorBoundary currently latches hasError forever via getDerivedStateFromError; add a recovery path so the boundary can reset when its child changes. In the CanvasErrorBoundary class (getDerivedStateFromError / render), implement componentDidUpdate(prevProps) that compares prevProps.children (or a dedicated resetKey prop) to this.props.children and calls this.setState({ hasError: false }) when they differ, or alternatively accept a prop like resetKey and reset when it changes so individual RenderComponent mounts can recover without unmounting the whole boundary.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/A2UIRenderer.tsx around lines 60 - 70, The renderer currently returns null when a component definition is missing (surface[componentId] is falsy) which is inconsistent with the Unknown-type error UI; in A2UIRenderer update the missing-definition branch (where def is checked) to render a visible error node like the existing Unknown type message (include the missing componentId in the message) and also emit a console.warn or logger.warn noting the missing definition and surface/componentId to aid debugging; keep the MAX_RENDER_DEPTH and existing unknown-type logic unchanged and reuse the same styling/markup used for the Unknown type error.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/CanvasPanel.tsx around lines 28 - 33, The iframe in CanvasPanel.tsx currently uses state.url directly; add a validation step before rendering the <iframe> that only permits safe schemes (e.g., blob:, data:, or https:) and for https:// enforce same-origin by comparing the URL's origin to window.location.origin; if validation fails, render a safe fallback UI instead of the iframe. Implement this by parsing state.url with the URL constructor (catching errors), checking url.protocol for "blob:" or "data:" or "https:", and when protocol is "https:" require url.origin === window.location.origin; integrate this check into the CanvasPanel render logic that decides whether to output the iframe (src={state.url}) or the fallback. Ensure any thrown parse errors are handled and do not allow unvalidated state.url into the iframe.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/CanvasPanelHeader.tsx around lines 20 - 22, In the CanvasPanelHeader component, the decorative close icon SVG inside the Button (the <svg> element used alongside the Button with aria-label="Close Canvas") should be marked aria-hidden="true" so assistive tech ignores it; update the SVG element within CanvasPanelHeader (the close icon path block) to include aria-hidden="true" (and remove any title if present) to satisfy accessibility lint (noSvgWithoutTitle) and avoid double announcement.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/components/A2UIButton.tsx around lines 14 - 25, The handler only dispatches the first action (def.actions[0]) so additional actions are ignored; update handleClick to iterate over def.actions (e.g., forEach) and for each actionDef call resolveActionContext(actionDef.context, dataModel) and invoke onAction with the action name, sourceComponentId (componentId), timestamp (new Date().toISOString()) and the resolved context; ensure you handle an empty/undefined def.actions the same way and consider preserving ordering and per-action timestamps.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/components/A2UICheckBox.tsx at line 9, The checked calculation uses strict === true which fails for truthy non-boolean bound values returned by resolveBoundValue; update the expression in A2UICheckBox (the checked variable that references resolveBoundValue(def.checked, dataModel) and def.checked?.literalString) to normalise the bound value to a boolean (for example by wrapping resolveBoundValue(...) with Boolean(...) or using a truthy check) so that string "true", number 1, and other truthy values mark the checkbox checked consistently with the literalString === 'true' branch.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/components/A2UIIcon.tsx around lines 20 - 24, The SVG returned by the A2UIIcon component lacks a <title>, causing an accessibility violation; update the A2UIIcon component to render a <title> element (text derived from the resolved icon name) and wire it into the SVG via an id and aria-labelledby so screen readers can announce it. Inside A2UIIcon, generate a stable title id (e.g., with React's useId or a simple unique string), render <title id={titleId}>{resolvedIconName}</title> before {iconPath}, and add aria-labelledby={titleId} and role="img" to the <svg> (remove or conditionally set aria-hidden only if there is no title). Ensure you reference the existing symbols sizeClass, color, iconPath, and resolvedIconName when making the change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/components/A2UIImage.tsx around lines 19 - 29, In A2UIImage, enable lazy loading and provide an error fallback: add loading="lazy" to the <img> and implement an onError handler inside the A2UIImage component (using local state or a fallbackSrc prop) to swap src to a fallback image or a neutral placeholder/hidden state when the browser fails to load the original; update references to src/alt/def in A2UIImage to use the fallback state so broken URLs no longer show the default broken-image icon.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/components/A2UIList.tsx around lines 9 - 14, Remove the redundant local variable and null-guard: delete the `const childDef = surface[childId];` assignment and the `if (!childDef) return null;` check in A2UIList — `RenderChildren` already re-resolves the child from `surface` and handles missing keys, so simply render the <li key={childId}> with <RenderChildren childrenSpec={{ explicitList: [childId] }} ... /> directly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/components/A2UIText.tsx at line 12, A2UIText currently renders an <h1> for style="title1", which can produce multiple top-level headings; update the A2UIText component so it no longer unconditionally emits an <h1> for title1—add support for an "as" or "role" prop (or default to a non-heading element like <p> or <span> for title1) and render the tag based on that prop (preserve visual classes like "text-xl font-bold"). Locate the return that outputs <h1> in A2UIText and change it to render a configurable element (or default to <p>/<span>) while keeping the styling, and only render <h1> when the caller explicitly requests it via the new prop.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/components/A2UITextField.tsx at line 11, In A2UITextField ensure the computed value passed to the controlled <Input> is never undefined: when path is truthy and resolveBoundValue(def.text, dataModel) may return undefined, coerce that result to a safe string (e.g., ''), so replace the current expression that sets value with a fallback that uses resolveBoundValue(def.text, dataModel) ?? '' (or equivalent) and similarly ensure def.text?.literalString falls back to '' so value is always a string; update references to value, resolveBoundValue, def.text, dataModel and path accordingly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/components/A2UITextField.tsx at line 21, The label in A2UITextField is not associated with the Input control; update the component (A2UITextField) to ensure accessibility by generating or accepting an id and wiring it to both the label's htmlFor and the Input's id prop: add an optional id prop (or use React's useId/useRef to create one when not supplied), set htmlFor on the <label> to that id and pass the same id down to the <Input> element so screen readers and click-to-focus work correctly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/hooks/useA2UIDataModel.ts around lines 3 - 4, Replace loose any types in useA2UIDataModel with unknown: change the signature and internal state from Record<string, any> to Record<string, unknown> (update initialDataModel, dataModel, setDataModel types), and update the updateField parameter `value` to be unknown so callers must explicitly narrow before use; adjust any local usage sites in the hook (e.g., within updateField and any helpers) to perform type guards/casts before operating on values to satisfy strict TypeScript typing.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/hooks/useA2UIDataModel.ts at line 16, In updateField inside useA2UIDataModel, guard against an empty path after stripping the leading slash so you don't end up setting a property with the empty-string key; e.g. after computing parts (from path.replace(/^\//, "")...) check if parts.length === 0 || (parts.length === 1 && parts[0] === "") and handle that case explicitly (either apply the update to the root object, return/throw an error, or no-op depending on intended semantics) instead of continuing to index current[""]; update tests or callers accordingly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/hooks/useA2UIDataModel.ts around lines 7 - 9, The effect using initialDataModel causes re-render loops because object props change by reference; update useA2UIDataModel to initialize state from initialDataModel instead of syncing on every render: replace the useEffect + setDataModel with useState(() => initialDataModel || {}) so DataModel is set once on mount, or if you must accept updates, gate updates with a proper equality check (e.g., deep-equal) comparing previousInitialRef to initialDataModel before calling setDataModel; refer to useA2UIDataModel, setDataModel, and initialDataModel when making the change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/hooks/useCanvasPanel.ts around lines 17 - 22, The effect that reads STORAGE_KEY uses setPanelWidthState(parseInt(...)) which bypasses the component's clamp logic and doesn't guard against NaN; instead, parse the stored value into a number, validate it's finite (not NaN), clamp it to the allowed range [400, 1200] (or call the existing setPanelWidth helper if present) and only then call setPanelWidthState with the sanitized value so stale or non-numeric localStorage entries cannot set an invalid panelWidth.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/types.ts around lines 78 - 83, The function resolveBoundValue currently returns undefined when bv is missing but "" when a resolved path is missing, causing asymmetry; update resolveBoundValue (and related types BoundValue/resolvePath usage) to return a consistent value for both cases—either always undefined or always ""—by changing the path fallback (the resolvePath(...) ?? "") and the final return to match the chosen consistent value; locate resolveBoundValue and adjust its last two return branches accordingly (and update any callers that rely on the old asymmetry).

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/canvas/types.ts around lines 62 - 76, The comment above resolvePath is hedging; replace it with a concise contract: state that resolvePath accepts a path string using either '/'-separated or '.'-separated segments (it strips a single leading '/' if present), navigates object properties by those segments, and returns undefined for empty path or when any intermediate value is null/undefined; update the comment near the resolvePath function to reflect this exact behavior and remove the deliberative text.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ChatPage.tsx around lines 132 - 137, The Detach button (className "session-observation-detach", onClick handler chat.onDetachFromSession) is missing an explicit type attribute and will default to type="submit" inside forms; add type="button" to the button element to prevent unintended form submissions and resolve the accessibility/behavior issue.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ToolCallCard.tsx around lines 536 - 550, The interactive header divs in ToolCallCard (and similarly in CanvasSurfaceCard and ToolCallGroupHeader) must be made keyboard-accessible: add role="button" and tabIndex={0} to the header divs and implement an onKeyDown handler that triggers the same toggle as onClick when Enter or Space is pressed (mirror the setExpanded(!expanded) behavior); reuse the same pattern used in ToolCallItem for consistency. Also update StatusIcon SVGs to include accessible titles (a <title> per SVG) so screen readers announce the icon state. Apply these changes across the flagged components (ToolCallCard, CanvasSurfaceCard, ToolCallGroupHeader, ToolCallItem, and StatusIcon) to cover all occurrences.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ToolCallCard.tsx around lines 644 - 690, The current groupKey in ToolCallCards uses `${segment.calls[0].id}-${segment.toolName}`, which changes when new calls prepend and causes expandedGroups to be lost; change the stable key generation to rely on an invariant identifier (e.g., `segment.toolName` or a provided `segment.groupId`/`segment.toolId`) instead of the first call's id so keys remain stable as the stream updates, and update the references to groupKey (where you call toggleGroup and pass expandedGroups.has(groupKey) and as the key prop on ToolCallGroupHeader) accordingly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/command-browser/SkillBrowserModal.tsx around lines 77 - 83, In SkillBrowserModal, the Close, skill item, and mobile Back buttons lack explicit types which can cause accidental form submissions; update the button elements (the close button rendering <XIcon />, the skill item buttons in the list rendering each skill, and the mobile back button) to include type="button" on their <button> tags so they are non-submit by default.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/command-browser/SkillBrowserModal.tsx around lines 20 - 37, The fetch in useEffect (inside fetchSkills) currently swallows errors and leaves skills empty, causing the UI to show "No enabled skills found." instead of an error; add an error state (e.g., error / setError) and set it in the catch block of fetchSkills, ensure setIsLoading(false) still runs, and update the component render to display the error when error is set; reference the existing useEffect/fetchSkills and state setters (setSkills, setIsLoading) when making these changes so failure paths explicitly set error state and avoid misleading empty-results messaging.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/command-browser/ToolArgumentForm.tsx around lines 162 - 168, The current onChange handler in ToolArgumentForm.tsx parses input on every keystroke which causes type flicker between string and object; instead keep a local raw string state (e.g., rawValue) updated directly from the onChange handler and defer JSON.parse until onBlur (or after a short debounce), then call handleChange with either the parsed object (if JSON.parse succeeds) or the raw string; update the component to add an onBlur handler that attempts JSON.parse(rawValue) and calls handleChange accordingly (or implement a debounced parse instead if you prefer debouncing).

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/command-browser/ToolArgumentForm.tsx around lines 132 - 136, The onChange handler currently parses inputs with parseInt/parseFloat and can pass NaN to handleChange; update the handler used in ToolArgumentForm so after computing value = prop.type === 'integer' ? parseInt(raw, 10) : parseFloat(raw) you check Number.isNaN(value) and call handleChange(undefined) (or otherwise ignore the update) instead of passing NaN; ensure this validation is applied wherever the same onChange logic is used so handleChange never receives NaN.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/command-browser/ToolArgumentForm.tsx around lines 68 - 73, The label constant in ToolArgumentForm is not associated with its form control; generate a stable fieldId (e.g., based on name and index) inside ToolArgumentForm and set label to use htmlFor={fieldId}, then ensure every rendered control (the Input component, any <select>, and any <textarea> output paths in ToolArgumentForm) receives id={fieldId}; preserve the existing isRequired asterisk logic and use the same fieldId wherever the label/name pairing is used so the noLabelWithoutControl rule is satisfied.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/command-browser/ToolBrowserModal.tsx around lines 278 - 327, The SVG icons in XIcon, ChevronIcon, ChevronLeftIcon, ToolsIcon, and SpinnerIcon are missing accessible <title> elements; update each component to either include a descriptive <title> (and ensure the SVG has role="img" and a unique id referenced by aria-labelledby when used in interactive contexts like buttons) for meaningful icons (e.g., XIcon, ChevronIcon, ChevronLeftIcon, ToolsIcon), or mark purely decorative icons (e.g., SpinnerIcon if only visual) with aria-hidden="true" to silence the a11y lint; ensure title IDs are unique if multiple instances may render.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/command-browser/ToolBrowserModal.tsx around lines 120 - 127, In ToolBrowserModal.tsx there are multiple <button> elements (e.g., the close button that calls onClose and renders <XIcon />) missing an explicit type, causing them to default to type="submit"; update every <button> in this component (including the ones around lines referenced: the close/XIcon button and the other three buttons) to include type="button" to prevent unintended form submission.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/command-browser/ToolBrowserModal.tsx around lines 72 - 82, The handler handleSelectTool currently awaits fetchToolSchema but lacks error handling so setSchemaLoading(false) may never run; wrap the fetchToolSchema call in a try/catch/finally inside handleSelectTool (or return a promise chain with .catch/.finally) so that setSchemaLoading(false) is always called in finally, and in catch set schema to null (setSchema(null)), clear form/result state (setFormValues({}), setResult(null)) and log or surface the error; keep existing calls to setSelectedServer and setSelectedTool at the start so the UI remains consistent.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useChat.ts around lines 397 - 420, The updater passed to setCanvasSurfaces currently performs a side effect by calling setCanvasPanel inside the callback; refactor so the updater is pure: iterate ev.surfaces first (outside the setCanvasSurfaces callback) to build the Map of A2UISurfaceState entries and separately determine any HTML panel payload (canvasId, title, url) for setCanvasPanel, then call setCanvasSurfaces(nextMap) and, if needed, setCanvasPanel(panel) as two distinct calls; keep setCanvasSurfaces' callback only responsible for returning the new Map and do not invoke setCanvasPanel from within it.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useChat.ts around lines 360 - 421, Replace the unsafe cast "const ev = data as any" with a properly typed discriminated union or interface (e.g., CanvasEventMessage) that covers the canvas_event variants (surface_update, interaction_confirmed, close_canvas, panel_present, canvas_rehydrate) and the event-specific fields (canvas_id, conversation_id, mode, surface, data_model, root_component_id, completed, title, html_url, width, height, surfaces); update the handler to accept ev: CanvasEventMessage and use type narrowing on ev.event so property access inside the branches (in setCanvasSurfaces, setCanvasPanel, and the canvas_rehydrate loop) is checked at compile time and removes any remaining any casts.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useChat.ts around lines 1198 - 1228, In detachFromSession, capture the current DB session id before clearing it (e.g. const prevDbSid = loadDbSessionId() or read from dbSessionIdRef/state) and use that captured prevDbSid for the restore fetch instead of calling loadDbSessionId() after setDbSessionId(null); update detachFromSession to call setDbSessionId(null) only after you stash prevDbSid (and keep using attachedSessionIdRef.current, wsRef, setAttachedSessionId, setAttachedSessionMeta, setMessages, setSessionRef as before), so the restore fetch does not depend on React batching or the saveDbSessionId effect.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSettings.ts around lines 53 - 61, The fetchUISettings function currently returns res.json() as Partial<Settings> without runtime validation; add a lightweight schema check (e.g., using zod or a manual validator) to validate the shape/types before returning. Update fetchUISettings to parse the JSON, validate it against a Settings schema (or a Partial<Settings> schema) and only return the object if validation succeeds; otherwise log/handle the validation error and return null so malformed responses don’t pollute state. Reference fetchUISettings and the Settings type when adding the validator and use it wherever the API result is consumed to guarantee runtime safety.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSettings.ts around lines 128 - 138, The persist effect currently runs on every settings change (useEffect with settings) causing redundant API PUTs when non-persistable fields like chatMode change; modify the effect that uses isFirstRender/useEffect to compute a shallow subset of settings restricted to PERSISTABLE_KEYS (or derive a stable persistableSettings object) and only call saveUISettings when that subset actually differs from the last-saved value (or debounce the API call briefly). Keep saveToLocalStorage(settings) for all changes but replace the unconditional saveUISettings(settings) with a conditional compare-and-save using the persistable keys (refer to isFirstRender, useEffect, saveToLocalStorage, saveUISettings, updateChatMode and PERSISTABLE_KEYS to locate and implement the change).

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSettings.ts at line 85, The initialized ref in the useSettings hook is written to (initialized.current = true) but never read, making it dead code; either remove the ref and its assignment or wire it up to guard the persist effect (e.g., check initialized.current before running the effect and set it after first run). Locate the const initialized = useRef(false) and the assignment initialized.current = true in useSettings and either delete both occurrences (and any related comments) or add a conditional read of initialized.current where the persist/reset effect runs so it actually prevents the effect on initial mount.

- Verify each finding against the current code and only fix it if needed.

In @web/src/styles/index.css around lines 12917 - 12931, Add an explicit keyboard focus style for the detach control (.session-observation-detach) by adding a :focus and/or :focus-visible rule that mirrors the hover affordance for keyboard users: set a visible outline or box-shadow (using accessible contrast color, e.g., var(--focus) or a solid color), ensure outline-offset or border change doesn’t shift layout, and preserve background/color changes used in .session-observation-detach:hover so keyboard focus looks consistent with hover. Apply to .session-observation-detach:focus and .session-observation-detach:focus-visible and keep the hover rules intact.

- Verify each finding against the current code and only fix it if needed.

In @web/src/types/chat.ts around lines 89 - 98, Extract the inline type used by attachedSessionMeta into a named interface (for example, SessionMeta) and replace the inline object type with that interface in the type declarations; specifically create an interface SessionMeta { ref: string | null; source: string; title: string | null; status: string; model: string | null; externalId: string } and change attachedSessionMeta?: { ... } | null to attachedSessionMeta?: SessionMeta | null so consumers and IDEs get better reuse and tooltips while keeping attachedSessionId and onDetachFromSession unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/types/chat.ts around lines 60 - 61, The two type-only imports (A2UISurfaceState, UserAction, CanvasPanelState) are declared mid-file; move those import type statements to the top of the file with the other imports and remove the duplicate import lines currently at lines 60-61 so all imports are grouped together and the types (A2UISurfaceState, UserAction, CanvasPanelState) are imported once at file-start.

- Verify each finding against the current code and only fix it if needed.

In @web/vite.config.ts around lines 36 - 38, Enable Vitest globals by setting the test config's "globals" option to true in vite.config.ts (inside the existing test: { ... } block) so tests can use describe/it/expect without importing them; additionally, update your web/tsconfig.json (or tsconfig.app.json) compilerOptions.types to include "vitest/globals" so TypeScript recognizes the global types.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/rules/stop-gates/reset-stop-cycle-on-tool.yaml around lines 14 - 15, The rule in reset-stop-cycle-on-tool.yaml redundantly resets the variable tool_block_pending to false which duplicates the unconditional reset already present in session-lifecycle.yaml on every after_tool event; remove the duplicate by either deleting the tool_block_pending reset from reset-stop-cycle-on-tool.yaml or removing the unconditional reset in session-lifecycle.yaml (or consolidate into clear-tool-block-on-tool.yaml) so only one location (single source of truth) clears tool_block_pending on after_tool, and update any references to after_tool handlers to reflect the chosen single implementation.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/rules/stop-gates/reset-stop-cycle-on-tool.yaml around lines 11 - 12, The rule that unconditionally sets variable stop_attempts to 0 broadens the reset scope compared to session-lifecycle.yaml; update the reset-stop-cycle rule that assigns "variable: stop_attempts value: 0" to include a guard "when: not event.data.get('mcp_tool')" so it only resets for non‑MCP tool calls (or alternatively add a comment documenting intentional scope change), ensuring behavior matches the stop_attempts handling in session-lifecycle.yaml.