Fix the following issues. The issues can be from different files or can overlap on same lines in one file.

- Verify each finding against the current code and only fix it if needed.

In @.gobby/memories.jsonl at line 787, The memories.jsonl file contains corrupted/truncated memory records (for example the entry with id "6bf7e921-0388-5bb2-82ed-810f65bd54fd") which will degrade retrieval; open .gobby/memories.jsonl, locate and either remove or repair any malformed JSONL lines (ensure each line is a valid JSON object with fields id, content, type, tags, created_at, updated_at, source, source_id) and re-run your import/validation step to confirm all entries parse correctly and timestamps are ISO8601; after cleanup, re-index or re-import the file used by the memory loader to ensure downstream code (memory retrieval / hook_dispatcher ingestion) only sees well-formed memory entries.

- Verify each finding against the current code and only fix it if needed.

In @.gobby/memories.jsonl at line 1077, The entry with id "99baee92-e15d-564e-80f0-3a9b51827226" has the "tags" field as a single comma-delimited string; change that field to a JSON array of strings (e.g., ["daemon","config","restart"]) so it matches the rest of the file's string[] shape and consumers that iterate over tags will not break.

- Verify each finding against the current code and only fix it if needed.

In @.gobby/memories.jsonl around lines 1 - 1109, Malformed lines in .gobby/memories.jsonl mean the import/sync path needs a validation gate; add strict per-line JSON + schema validation in the memory import routine (e.g., the _import_memories_sync / import_sync path in the memory sync/maintenance flow) to reject invalid entries and surface line numbers. Specifically: parse each line with json.loads, verify required keys (id, content, memory_type/type, tags, created_at, updated_at, source, source_id), assert tags is a list (not a string), and add a short-content heuristic (content length < 40 or abrupt/truncated token pattern) that emits clear errors listing offending line numbers; wire this validation into the import path used by MemorySyncManager.import_sync() and the CLI/web import endpoints and fail fast (non-destructively) so pre-commit / sync jobs can block bad files before DB write.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/config/voice.py around lines 13 - 17, The docstring promises automatic normalization but the model_validator is missing and the secret field was renamed from elevenlabs_api_key to ELEVENLABS_API_KEY without backward compatibility; update the model that defines the secret field (the class containing ELEVENLABS_API_KEY) to import and use pydantic's @model_validator (or equivalent root validator for your pydantic version) to detect lowercase keys like "elevenlabs_api_key" in incoming data, map them to "ELEVENLABS_API_KEY", and populate the canonical field, or alternatively restore backward-compatibility by accepting both names (e.g., check for "elevenlabs_api_key" and set ELEVENLABS_API_KEY if present) so old persisted configs keep working.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/agent_messaging.py around lines 463 - 464, Add a log message when you sanitize an invalid poll_interval to avoid silently masking caller errors: in the code path that checks "if poll_interval <= 0: poll_interval = 5" emit a debug or warning log that includes the original invalid value and the replacement (e.g. "invalid poll_interval=%s, defaulting to 5"), using the module/class logger used elsewhere in this file (refer to the existing logger instance or add one named logger) so callers can trace why their value was overridden.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/search/embeddings.py around lines 244 - 248, SearchConfig uses an uppercase field EMBEDDING_API_KEY which breaks the class naming convention; rename the field to embedding_api_key in SearchConfig and update all references (including where config.EMBEDDING_API_KEY is used in the call to is_embedding_available inside embeddings.py) to use config.embedding_api_key, or alternatively document that uppercase denotes an env var and provide a clear accessor that maps the env var to a lowercase attribute; ensure consistency with existing fields embedding_model and embedding_api_base and update any imports/tests that reference EMBEDDING_API_KEY.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/search/models.py around lines 71 - 74, SearchConfig defines EMBEDDING_API_KEY in SCREAMING_CASE while other fields use snake_case; rename the field to embedding_api_key (or add a snake_case alias) and update usages accordingly: change EMBEDDING_API_KEY to embedding_api_key on the SearchConfig model and, if you must preserve the environment variable name, add a Pydantic alias (e.g., Field(..., alias="EMBEDDING_API_KEY") or use Config.env_prefix) so the env var still maps to the field; update all references to the field name in code to use embedding_api_key.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/chat_session.py at line 206, The downstream consumers still expect "prompt_text", so restore backward compatibility by including both keys when building the event payload in chat_session.py (the dict creation at data = {"prompt": ...}); set data["prompt_text"] = data["prompt"] so handlers like context_actions.py (handler around line referencing event_data.get("prompt_text")), memory_actions.py (fallbacks at .get("prompt") or .get("prompt_text")), hook_manager.py, mcp_dispatch.py, and broadcaster.py continue to work without changing all consumers; alternatively, if you choose to complete the migration, update those referenced handlers (functions in src/gobby/workflows/context_actions.py, memory_actions.py, hook_manager.py, mcp_dispatch.py, and broadcaster.py) to read "prompt" only and remove any manual mappings or fallback logic consistently across the codebase.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/agent_spawn.py around lines 207 - 208, Replace broad "except Exception" handlers in agent_spawn.py with specific exception types for each operation: where task_manager.get_task(req.task_id) currently uses except (ValueError, Exception) change to except (ValueError, KeyError, AttributeError) as e, log the failure (e.g., logger.warning(f"Failed to get task {req.task_id}: {e}")) and set task = None; similarly update handlers around task_manager.get_comments(req.task_id), dependency/assignee fetches, and other occurrences (lines referenced in the review) to catch only expected exceptions (ValueError, KeyError, AttributeError as appropriate), log with context and the exception variable, and preserve existing fallback behavior instead of swallowing all exceptions.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/agent_spawn.py around lines 101 - 103, Replace the permissive Any types on _build_task_prompt with concrete types: either import the real Task model used elsewhere or declare a small Protocol (e.g., TaskLike with seq_num: int, title: str, description: str) and a CommentLike/DependencyLike protocol that exposes the attributes your code reads (e.g., content: str or seq_num/title if deps are tasks). Update the signature to _build_task_prompt(task: TaskLike, deps: list[TaskLike] | None = None, comments: list[CommentLike] | None = None), add the Protocol definitions (from typing import Protocol) near related types, and adjust imports so mypy recognizes the new types; if a concrete Task class exists, prefer importing it instead of creating a Protocol.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/mcp/endpoints/server.py around lines 274 - 280, The broadcast currently sends only the string "bulk"; update the call to websocket_server.broadcast_mcp_event (accessed as ws / server.services.websocket_server) to include descriptive data from the import result—e.g., pass a list of imported server names or an object with relevant metadata extracted from result (IDs/names/count/timestamp); ensure you build that payload from the variable result used earlier in this function and send it instead of the literal "bulk" (or, if result can be very large, send a summarized payload such as names and count).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/sessions.py around lines 161 - 168, The _broadcast_session helper currently logs broadcast failures with logger.debug; change this to logger.warning so session broadcast errors are more visible in production. In the async function _broadcast_session (which uses server.services.websocket_server and calls ws.broadcast_session_event), update the exception handler to call logger.warning and include the event, session_id and the caught exception details in the message for better observability.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/skills.py around lines 93 - 100, The helper _broadcast_skill currently swallows all exceptions and logs them at debug level; update the except block to log at warning (e.g., logger.warning) and include the exception details and context (event, skill_id, and exception info) when ws.broadcast_skill_event fails (server.services.websocket_server and ws.broadcast_skill_event are the targets) so failures are visible in production logs.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/voice.py around lines 103 - 140, The tts_config function's signature declares -> dict[str, Any] but returns fastapi.responses.JSONResponse on error paths (in functions named tts_config and where JSONResponse is used), causing type errors; update the return annotation to a union that includes JSONResponse (for example Union[dict[str, Any], JSONResponse]) and add the corresponding import (typing.Union and fastapi.responses.JSONResponse or use fastapi.Response) so the signature matches the actual return types.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/voice.py around lines 131 - 132, The /tts-config endpoint (tts_config function) returns the ElevenLabs api_key in plaintext without enforcing the assumed localhost-only trust boundary; update tts_config to enforce access controls by either rejecting non-local requests (check request.client.host and allow only 127.0.0.1/::1) or require authentication regardless of global optional auth (consult AuthMiddleware behavior and explicitly require auth for this route), and add a clear error response when access is denied; also update any route metadata/comments to reflect the enforced requirement.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/workflows.py around lines 300 - 301, The broadcast call to _broadcast_workflow("workflows_bulk_changed", "bulk") uses a non-descriptive definition_id; update the call site in workflows.py where rows are present to pass a descriptive identifier or payload via kwargs (e.g., include the number of rows and/or template type) — e.g., call _broadcast_workflow("workflows_bulk_changed", definition_id=f"bulk:{len(rows)}", count=len(rows), template_type=template_type) or similar so consumers can trace bulk events; ensure you only change the arguments to _broadcast_workflow and keep the event name "workflows_bulk_changed" intact.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/server.py at line 97, Replace the weakly-typed Any annotations on the hook integration fields with the concrete types: import WorkflowHookHandler from gobby.workflows.hooks and EventHandlers from gobby.hooks.event_handlers, then change the instance attributes so workflow_handler uses WorkflowHookHandler | None and event_handlers uses EventHandlers | None (e.g., update the declarations for self.workflow_handler and self.event_handlers accordingly) to satisfy mypy and project typing rules.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/session_control.py at line 485, The log uses an f-string which breaks structured logging consistency; replace the f-string logger.info call with a structured logging call that uses a format string and passes context via the extra parameter (include conversation_id and agent_name, and keep the short conversation id in the message), mirroring how _handle_continue_in_chat uses extra={...}; update the logger.info invocation in session_control.py (the logger.info that currently references conversation_id and agent_name) to supply placeholders and an extra dict so downstream aggregation can consume the fields.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/sessions/token_tracker.py around lines 37 - 38, Replace the vague Any for session_storage with a Protocol that declares the required interface: create a SessionStorageProtocol (or similarly named Protocol) that includes the signature for get_sessions_since(self, since: datetime.datetime) -> Iterable[Session] (use appropriate Session type or Any if needed), import typing.Protocol and datetime, and then annotate the TokenTracker.session_storage field with that Protocol instead of Any so static type checkers can validate calls to get_sessions_since; update any imports and type hints (e.g., from typing import Protocol, Iterable) accordingly and ensure the Protocol is accessible where TokenTracker is defined.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/sessions/token_tracker.py around lines 49 - 50, The call to self.session_storage.get_sessions_since(...) is currently synchronous but performs DB I/O (self.db.fetchall()); change get_sessions_since in src/gobby/storage/sessions.py to be async and await self.db.fetchall(), then change get_usage_summary in src/gobby/sessions/token_tracker.py to be async and await self.session_storage.get_sessions_since(since); update all call sites (including where get_usage_summary is invoked) to await the new async methods and adjust any function signatures to async accordingly to propagate async usage through the call chain.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/skills/search.py around lines 359 - 362, The code repeatedly constructs set(filters.allowed_names) inside _passes_filters for each skill; instead compute the set once and reuse it—either add a cached attribute like allowed_names_set to the SearchFilters object (populate it when filters are created) or compute allowed_set once in search_async and pass it into _passes_filters; then replace set(filters.allowed_names) with membership checks against that prebuilt allowed set (still comparing meta.name) to avoid per-iteration allocations.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/sessions.py around lines 270 - 271, Update the inline comment above the seen: set[str] = set() in the cycle-detection code to correctly describe the performance benefit: replace "Using mutable set for O(1) insertions during cycle detection" with something like "Using a set for O(1) membership checks during cycle detection (to test parent_id in seen)"; reference the seen variable in your edit so reviewers can locate it.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/sessions.py around lines 312 - 313, Add an explicit type annotation for the class constant _VALID_CHAT_MODES (e.g., declare it as a ClassVar[FrozenSet[str]] or ClassVar[Set[str]]), and update imports to include ClassVar and FrozenSet/Set from typing if not already present; keep the value as {"plan", "accept_edits", "normal", "bypass"} but annotate it (reference symbol: _VALID_CHAT_MODES).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/agent_resolver.py around lines 118 - 120, Replace the broad except Exception handler around the json.loads()/Pydantic model instantiation with explicit exception handlers: catch json.JSONDecodeError as e for JSON parsing failures and pydantic.ValidationError as e for model validation failures, log each with logger.debug including agent_name and the exception details, and continue to return None; ensure you import JSONDecodeError (from json) and ValidationError (from pydantic) if not already imported.

- Verify each finding against the current code and only fix it if needed.

In @tests/config/test_memory_config.py around lines 25 - 28, Update the test docstring to reference the actual attribute name used in the assertion: change the docstring in test_qdrant_api_key_defaults_to_none() to mention that MemoryConfig.QDRANT_API_KEY should default to None (instead of "qdrant_api_key"), so the description matches the assertion using config.QDRANT_API_KEY.

- Verify each finding against the current code and only fix it if needed.

In @tests/mcp_proxy/tools/test_wait_for_command.py around lines 214 - 239, The test TestWaitForCommandTimeout::test_timeout_returns_none currently hard-codes mock_time.side_effect = [0.0, 0.0, 601.0, 601.0], which breaks if the implementation changes the number of time.monotonic() calls; replace that fixed list with a stateful side-effect function (or iterator) that returns 0.0 for the initial calls and 601.0 afterwards so the patched time.monotonic used in the patch("time.monotonic") block reliably models "before timeout" then "after timeout" regardless of exact call count; keep the rest of the test logic (mock_command_manager.list_commands, messaging_registry.call with wait_for_command) unchanged.

- Verify each finding against the current code and only fix it if needed.

In @tests/sessions/test_token_tracker.py around lines 239 - 261, Add a new unit test mirroring test_can_spawn_agent_unlimited_budget but using a negative daily_budget_usd to ensure negative budgets are treated as unlimited; create a MagicMock session (e.g., id="sess-expensive" with usage_total_cost_usd > 0 and token fields present), set mock_session_storage.get_sessions_since.return_value to that session, instantiate SessionTokenTracker with daily_budget_usd=-1.0 and call can_spawn_agent(), then assert can_spawn is True and reason is None; name the test something like test_can_spawn_agent_negative_budget_is_unlimited to match existing style and use the SessionTokenTracker class and its can_spawn_agent() method.

- Verify each finding against the current code and only fix it if needed.

In @tests/sessions/test_token_tracker.py around lines 28 - 53, The mock sessions in the sessions list use MagicMock without setting usage_cache_creation_tokens and usage_cache_read_tokens, so attribute access yields truthy MagicMock objects and doesn't exercise the "or 0" fallback; update each MagicMock in the sessions list (or add a new dedicated test case) to explicitly set usage_cache_creation_tokens and usage_cache_read_tokens to None (or 0) so the code paths handling None/zero are tested, referencing the existing sessions list and MagicMock instances in test_token_tracker.py to locate where to make the change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useCronJobs.ts at line 96, debouncedRefetchRef holds a timeout ID but isn't cleared on unmount; add a cleanup to prevent leaked timers by adding a useEffect with no deps (or extending an existing effect) that on cleanup calls clearTimeout(debouncedRefetchRef.current) and sets debouncedRefetchRef.current = null. Update any places that reset/start the timer (where you call setTimeout and assign to debouncedRefetchRef.current) to coexist with this cleanup so timeouts are reliably cleared when the component unmounts or when starting a new timer.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useMcp.ts around lines 254 - 260, The WebSocket handler currently calls refreshAll() directly on every 'mcp_event' causing redundant fetches; change the handler to debounce refreshAll by 500ms (matching useCronJobs.ts) and pass the debounced function into useWebSocketEvent instead of the raw callback. Create the debounced callback (e.g., using lodash.debounce or your project's useDebouncedCallback) inside useMcp.ts, reference refreshAll when building the debounced function, memoize it with useCallback/useRef to avoid re-creating the debounced instance, and ensure you cancel/cleanup the debounce on unmount; replace the existing useWebSocketEvent('mcp_event', useCallback(() => { refreshAll() }, [refreshAll])) with the debounced variant.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSkills.ts around lines 517 - 527, The WebSocket handler registered via useWebSocketEvent reuses debounceRef (also used by searchSkills) which causes incoming skill_event timeouts to cancel active search debounces; create and use a separate ref (e.g., wsDebounceRef) inside the same hook for the WebSocket refresh logic, replace debounceRef with wsDebounceRef in the useWebSocketEvent callback, and ensure you clear and set wsDebounceRef the same way the existing debounceRef is handled so fetchSkills() and fetchStats() scheduling no longer interferes with searchSkills.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useVoice.ts around lines 367 - 379, Update the useVoice hook to surface TTS failures via the existing (or a new) voiceError state: when fetching '/api/voice/tts-config' returns !res.ok or the fetch throws, call setVoiceError with a user-friendly message and still allow STT/voice mode to remain enabled; when the fetch succeeds, clear voiceError (setVoiceError(null)), assign ttsConfigRef.current and call connectTTS(config) as before; ensure both the error path and success path reference the same state updater so the UI can read voiceError and show that TTS is unavailable while STT continues to work.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useWebSocketEvent.ts around lines 56 - 61, The reconnect logic in ws.onclose currently uses a fixed 3s delay; change it to use exponential backoff by tracking a reconnectAttempts counter (reset it on successful connect in connect() or on open) and scheduling reconnects with delay = Math.min(baseDelay * 2 ** reconnectAttempts, maxDelay) before calling connect; use reconnectTimer to setTimeout and increment reconnectAttempts on each scheduled retry, and reset reconnectAttempts to 0 when connection succeeds or when closed is set to true to avoid unbounded growth.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useWebSocketEvent.ts around lines 124 - 136, The cleanup currently sets closed = true then immediately resets closed = false, creating a race; change the reset so closed remains true until the connection is safely allowed to reconnect—either remove the immediate closed = false and instead reset closed inside ensureConnection(), or defer the reset to the next tick (e.g., setTimeout(() => { closed = false }, 0)) after clearing reconnectTimer and closing ws; ensure ensureConnection() and any reconnect timer callbacks check the closed flag before acting. Update references in useWebSocketEvent (handlers, closed, reconnectTimer, ws, ensureConnection) accordingly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/utils/sentenceBuffer.ts around lines 16 - 24, The loop using re.exec(this.buffer) never advances because re lacks the global flag and the lookbehind used is not universally supported; update the splitting logic in sentence buffering (the regex variable re and the loop that reads this.buffer and pushes into sentences) to avoid lookbehind and infinite loops—either use a safe split approach on sentence boundaries (split this.buffer by a pattern that matches a sentence terminator followed by whitespace) or make the regex global and remove the lookbehind (e.g., match the terminator with /[.!?\n]\s+/g) and iterate with matchAll or by tracking indices, then trim and push each sentence and update this.buffer accordingly. Ensure you update code paths that reference re, the exec loop, and this.buffer so Safari/older engines won’t throw and the loop terminates.

- Verify each finding against the current code and only fix it if needed.

In @web/src/utils/sentenceBuffer.ts around lines 1 - 6, The regex in sentenceBuffer.ts uses a lookbehind (?<=...) which is not supported in older Safari; either document this requirement (note that lookbehind needs Safari 16.4+ in the file header or project docs) OR replace the lookbehind-based split with a compatible approach: use a capture-group-based split (e.g., split on /([.!?\n])\s+/ and reattach the captured delimiter to the preceding chunk) or implement manual scanning in the function that emits sentences so no lookbehind is required; update the function that performs sentence splitting (the regex variable / splitting logic in sentenceBuffer.ts) accordingly and add the compatibility note to comments or README.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/agents/runner.py at line 80, Replace the redundant assignment using "or None": in the Runner (or relevant) class __init__ where you set self._workflow_loader = workflow_loader or None, change it to directly assign self._workflow_loader = workflow_loader (remove the unnecessary "or None") so the attribute reflects the passed-in value or None by default.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/agents/runner.py at line 60, Define a small Protocol for the expected loader interface and use it instead of Any for the workflow_loader parameter: create a WorkflowLoaderProtocol with a load_workflow_sync(self, workflow_name: str, project_path: str | None = None) -> Any | None signature and change the runner function/class constructor parameter type from Any to WorkflowLoaderProtocol so calls to workflow_loader.load_workflow_sync are properly typed; import typing.Protocol where you place the protocol and update the type annotation for workflow_loader in runner.py.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/agents/runner.py around lines 232 - 243, The current inline import of PipelineDefinition inside the if workflow_definition: block is acceptable; no change required—leave the import of PipelineDefinition as-is and keep the logging behavior that uses workflow_definition, effective_workflow, child_session, and self.logger unchanged so the conditional message for PipelineDefinition vs other workflow types remains intact.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent/_factory.py around lines 200 - 210, When loading the workflow via WorkflowLoader (wf_loader.load_workflow_sync) returns no wf_def for a non-empty effective_workflow, add a warning so failures aren’t silent: after calling wf_loader.load_workflow_sync(effective_workflow, project_path=project_path) check for falsy wf_def and log a warning that the workflow failed to load (include effective_workflow and project_path); also wrap the load_workflow_sync call in a try/except to log exceptions if it raises, before proceeding to the existing PipelineDefinition check and setting initial_variables["_assigned_pipeline"].

- Verify each finding against the current code and only fix it if needed.

In @tests/workflows/test_hooks.py around lines 796 - 798, Move the local imports of json and WorkflowState into the module-level imports: add "import json" with the other stdlib imports and "from gobby.workflows.definitions import WorkflowState" with the first-party imports, then delete the in-function imports so the test uses the module-level names; if those imports were placed locally to avoid a circular import, preserve the local import and add a short comment explaining why.