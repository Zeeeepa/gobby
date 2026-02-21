Fix the following issues. The issues can be from different files or can overlap on same lines in one file.

- Verify each finding against the current code and only fix it if needed.

In @README.md around lines 415 - 423, The documentation for the `--project` flag should be expanded: update the README section that shows the `uv run --project` examples to include a Windows path variant (e.g., C:\Users\you\Projects\gobby), add a short prerequisite note stating the Gobby daemon should be running (e.g., “ensure gobby daemon is started via `uv run gobby start`”), and add a one-line use-case distinction explaining when to use `uv run --project` (development/testing against a source checkout) versus `uv tool install` (global installation for regular use); adjust the prose around the `--project` flag to incorporate these three points.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 102 - 106, Add explicit exception classes and document which Registry API methods raise them: define CanvasError, CanvasNotFoundError, and CanvasAlreadyCompletedError and update resolve_interaction to raise CanvasNotFoundError if the canvas_id is missing and CanvasAlreadyCompletedError if canvas.completed is true; update get_canvas to be documented as returning None or raise CanvasNotFoundError if you prefer strict behavior (choose and document one), and document cancel_conversation_canvases as not raising for missing canvases (or raise CanvasNotFoundError if you choose strict behavior). Ensure the README/plan text lists these exception types next to each method (e.g., resolve_interaction -> CanvasNotFoundError | CanvasAlreadyCompletedError) so callers know what to catch.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 343 - 355, The canvas_event branch in the WebSocket handler (e.g., in useChat.ts) lacks validation and error handling for msg.canvas_id and update operations; add a guard to ensure msg.canvas_id exists and is a string before calling clearCanvasRevertTimeout, updateCanvasStatus, updateCanvasContent, or removeCanvas, validate msg.content before passing it to updateCanvasContent, and wrap the event handling in a try/catch that logs an informative error (including the canvas_id) to avoid uncaught exceptions during update operations.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 276, Clarify and implement payload size validation to use UTF-8 byte length rather than string length: when validating the `data-payload` before parsing, compute its byte size (using TextEncoder().encode(payloadStr).length) and compare that against `MAX_CANVAS_SIZE` (64KB), and if it exceeds the limit log/return (e.g., a console.warn mentioning the byte count) instead of using payloadStr.length or character count. Ensure this check runs early where `payloadStr`/`data-payload` is read and before parsing.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 66 - 67, In render_canvas, after calling nh3.clean(...) and before storing CanvasState or broadcasting canvas_event (event: "rendered"), compute sanitized_size = len(sanitized_content.encode('utf-8')) and compare it to MAX_CANVAS_SIZE; if it exceeds the limit, raise a ValueError (or return an appropriate error) to reject the payload—this complements the existing pre-sanitization check and prevents sanitization-induced expansion from storing or broadcasting oversized content.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 319 - 340, The current pattern creates a single pendingTimeout variable which can be overwritten by concurrent canvas interactions; introduce a per-canvas timeout store (e.g., canvasPendingTimeouts as a useRef<Map<string, Timeout>>) and when creating the timeout for updateCanvasStatus(canvasId, 'pending') call canvasPendingTimeouts.current.set(canvasId, timeoutId), ensure the timeout handler deletes that entry before calling updateCanvasStatus(canvasId, 'active'), and update clearCanvasRevertTimeout(canvasId) to look up the timeoutId from canvasPendingTimeouts.current, call clearTimeout(timeoutId) and delete the map entry; also ensure error paths (the catch block around ws.send) call clearCanvasRevertTimeout(canvasId) instead of clearing a single pendingTimeout variable.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 96 - 98, The rate limiter races because timestamps are stored in _render_timestamps keyed by conversation_id but the existing locks are per-canvas; update render_canvas to use a per-conversation lock (e.g., _rate_limiter_locks: dict[str, asyncio.Lock]) where you obtain the lock for the conversation_id (use setdefault to create one if missing), then async with that lock prune old timestamps from _render_timestamps[conversation_id], check len against MAX_RENDER_RATE, append now() if allowed, and only then release the lock and continue; ensure this check happens before payload sanitization/creation so oversized or rate-limited requests are rejected early.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 171 - 182, The depth check in _validate_payload_depth currently uses if current_depth > max_depth which, with current_depth starting at 0, permits one extra nesting level; change that condition to if current_depth >= max_depth (or otherwise compare against max_depth-1) so that max_depth (e.g., MAX_PAYLOAD_DEPTH = 10) truly limits nesting to the intended number of levels; update any callers or tests that rely on the previous behavior to reflect the corrected boundary.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 250 - 256, The depth check in validatePayloadDepth is off-by-one: change the guard from "if (depth > maxDepth) return false" to use a non-inclusive upper bound (e.g., "if (depth >= maxDepth) return false") so that starting at depth = 0 with maxDepth = 10 allows exactly 10 levels; update the check in validatePayloadDepth and run related tests/examples to confirm correct behavior.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 21, Update the nh3 version requirement in the a2ui-canvas plan to mandate a release that includes the ammonia 4.1.2 fix: replace the current minimum version string (`nh3>=0.2.14`) with at least `nh3>=0.3.1`, preferably `nh3>=0.3.3` to pick up the RUSTSEC-2025-0071 mutation-XSS patch; change the version spec in the security note mentioning nh3 so server-side allowlist sanitization uses the patched nh3 release and mention the preferred `nh3>=0.3.3` as the recommended stable pin.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/extensions.py around lines 271 - 288, The try/except around reading project.json in the block that computes project_json_path/project_config/hooks_disabled silently swallows json and IO errors; update the except (json.JSONDecodeError, OSError) handler inside the code that reads project_json_path so it logs the caught exception at debug level (including exception message and the path) instead of just passing, referencing the same symbols (project_json_path, project_config, hooks_disabled) and keeping hooks_disabled behavior unchanged on error.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/install.py around lines 1037 - 1049, The cleanup except block currently swallows OSError silently; update the except OSError in the global uninstall block (where project_flag, global_hooks_dir and fpath are used) to log the failure instead of pass — e.g., capture the exception as e and call a logger or click.echo to report "Failed to remove {fpath}: {e}" (or logger.warning/logger.exception) while keeping the best-effort behavior; ensure the change is made inside the loop that handles ("hook_dispatcher.py", "validate_settings.py") and keep the nosec comment if needed.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/installers/mcp_config.py at line 502, The npm package string in the installer args ("args": ["-y", "@playwright/mcp@0.0.68"]) references a non-existent version and will cause install failures; update the package spec in that args array (the "@playwright/mcp@0.0.68" token) to a valid published version such as "@playwright/mcp@latest" or a known existing version (e.g., "@playwright/mcp@0.0.64") so npm install succeeds.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/installers/neo4j.py around lines 32 - 42, The broad except in _resolve_neo4j_auth hides real failures from load_config; replace the blanket "except Exception: pass" with targeted exception handling (e.g., catch ImportError and the specific config-loading exception(s) raised by load_config) and log the error before falling back to the generated credential; preserve the fallback return f"neo4j:{_generate_password()}" but ensure failures in import/load_config are not silently swallowed by using processLogger or the module logger to record the exception and context.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/installers/neo4j.py around lines 78 - 84, The inline import of os inside the installer function should be moved to the module level: remove the "import os" from the function body and add a single "import os" with the other top-level imports; keep the existing logic that builds env = dict(os.environ) and sets env["GOBBY_NEO4J_PASSWORD"] from neo4j_auth.split(":", 1) so behavior remains unchanged (look for the block that references neo4j_auth, env, and sets GOBBY_NEO4J_PASSWORD).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/setup.py around lines 35 - 42, The initial assignment env["GOBBY_HOME"] = str(get_install_dir().parent.parent / ".gobby") is dead because it is immediately overwritten by the subsequent environment check; remove that line and leave the existing logic that sets env["GOBBY_HOME"] from os.environ.get("GOBBY_HOME") or falls back to Path.home() / ".gobby" (refer to the env dict and functions get_install_dir, os.environ.get, and Path.home used in this block to locate the code to edit).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/setup.py around lines 40 - 42, The local import of Path inside the else branch should be moved to the module-level imports (alongside os and shutil) to follow convention; update the import statement so Path is available throughout the module and then simplify the else block to set env["GOBBY_HOME"] = str(Path.home() / ".gobby") without an inline import. Ensure references to Path and env["GOBBY_HOME"] remain unchanged.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/sync.py around lines 94 - 100, The set-manipulation for computing skip_types when filtering by types is correct but unclear; update the block that computes requested = set(types) and assigns skip_types to either (VALID_CONTENT_TYPES - requested) or (VALID_CONTENT_TYPES - requested | (skip_types & requested)) with a concise inline comment explaining the intent: that when types are specified we compute which content types to skip by default (all types not requested) and, if skip_types already exists, preserve already-requested skips only for requested types (i.e., combine non-requested types with any pre-existing skips limited to the requested set). Add the comment immediately above or on the same lines as the existing logic (referencing variables types, requested, skip_types, and VALID_CONTENT_TYPES) so future readers understand the rationale.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/config/persistence.py around lines 107 - 109, Add a field validator for neo4j_graph_min_score to enforce the 0.0–1.0 range like crossref_threshold does: reuse the existing validate_probability implementation (or create a shared validator function) and register it for the neo4j_graph_min_score field using the same field_validator pattern used for crossref_threshold (place it near/after the existing validate_probability validator so invalid values for neo4j_graph_min_score are rejected).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/config/persistence.py around lines 111 - 114, Add validation to ensure neo4j_rrf_k is a positive integer: in the Pydantic model where neo4j_rrf_k is declared, enforce >0 either by changing its type to a constrained int (e.g., conint(gt=0)) or by adding a @validator for "neo4j_rrf_k" that checks value > 0 and raises ValueError for zero/negative values; update the Field declaration/validator in the same model so invalid configs are rejected at load time.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/event_handlers/_agent.py around lines 50 - 52, The except block that currently reads "except Exception:" around the agent prompt loading should be narrowed to only the exceptions you expect (e.g., ImportError/ModuleNotFoundError, FileNotFoundError/OSError, ValueError) instead of catching all Exceptions; update the handler in the agent prompt loader (the block that references logger.debug, name and fallback) to catch the specific exception tuple as e, then log the error (keep logger.debug with exc_info=True or include e) and return fallback—this avoids masking unrelated failures like programmer errors while preserving the existing fallback behavior.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/hooks/hook_dispatcher.py around lines 587 - 588, Replace the redundant condition "if result and result != {}:" with a single idiomatic truthiness check "if result:" so the block that calls print(json.dumps(result)) only runs when result is non-empty; update the condition that guards print(json.dumps(result)) in hook_dispatcher.py to use "if result:" referencing the existing 'result' variable.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/hooks/hook_dispatcher.py at line 3, Update the Python requirement annotation from ">=3.11" to ">=3.13" in the hook dispatcher header so it matches project guidelines; locate the requires-python line (the string "requires-python = \"...\"" in src/gobby/install/shared/hooks/hook_dispatcher.py) and change the version specifier to ">=3.13" (or a stricter 3.13+ form used by the repo) so the module's declared Python target aligns with the project's 3.13+ policy.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/hooks/hook_dispatcher.py around lines 459 - 478, _find_project_config currently performs synchronous file I/O (open/json.load) which blocks the event loop; make it async by changing the signature to async def _find_project_config(cwd: str) -> dict[str, Any] | None, use aiofiles.open to read the file (await f.read()), parse with json.loads, and preserve the same exception handling (catch json.JSONDecodeError and OSError and return None). Update all call sites (notably main()) to await _find_project_config(...) and ensure imports include aiofiles; if any caller runs before the event loop is started, either convert that caller to async or document/keep a small sync wrapper, but prefer the async version for consistency with the rest of the module.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/hooks/validate_settings.py around lines 165 - 168, The find_project_root function currently returns Path(__file__).parent.parent.parent which is brittle; update find_project_root to walk upward from __file__ (or its resolved symlink using Path(__file__).resolve()) checking each ancestor for expected project markers (e.g., .git, pyproject.toml, setup.cfg) and return the first ancestor that contains any marker, and if none found return a sensible fallback or raise a clear error; reference the find_project_root function and use Path.resolve(), parents iteration, and marker checks to locate the true project root robustly.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/hooks/validate_settings.py around lines 186 - 192, The open() call used to read JSON in the validate_settings.py try block does not specify an encoding; change the file open in the JSON syntax validation (the with open(settings_file) used before json.load) to include encoding="utf-8" so the settings are read consistently across platforms and avoid platform-dependent decoding errors.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/hooks/validate_settings.py around lines 230 - 242, The nested-structure branch assumes first_config["hooks"][0] exists; update the logic in the block guarded by config.nested (use symbols: config.nested, first_config, hook_configs, hook_type) to defensively verify that "hooks" is a key, that first_config["hooks"] is a list, and that it is non-empty before accessing index 0; if any of those checks fail, print a clear error (including hook_type) and return a non-zero code (e.g., 1) instead of indexing into a missing element so the function fails gracefully and avoids IndexError/KeyError.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/prompts/memory/digest_update.md around lines 1 - 7, Add a top-level name field to the YAML front matter of the memory/digest_update.md prompt (the template that currently has description/required_variables/optional_variables) so it matches other templates; for example add name: "memory.digest_update" or name: "digest_update" directly under the leading --- line, ensuring the name uniquely identifies this prompt for lookup and stays consistent with other files like skill-hint.md and skill-not-found.md.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/scripts/setup-firewall.sh around lines 9 - 11, The port variables HTTP_PORT, WS_PORT and UI_PORT are used directly in PF rule interpolation and must be validated to prevent injection; add a small validation routine in setup-firewall.sh that checks each of HTTP_PORT, WS_PORT and UI_PORT is composed only of digits and within the valid port range (1–65535) and exit with a non‑zero status if any fail, then use the validated variables when rendering PF rules; implement this by adding a validate_port function (e.g. validate_port VAR_NAME VAR_VALUE) that uses a POSIX-safe regex/digit check and numeric bounds check and call it for HTTP_PORT, WS_PORT and UI_PORT before any firewall rule generation.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/scripts/setup-firewall.sh around lines 44 - 51, The pfctl error output is being suppressed by redirecting stderr to stdout without surfacing it; update the setup-firewall.sh logic around the pfctl invocations (the lines that run "sudo pfctl -ef /etc/pf.conf" and the fallback "sudo pfctl -f /etc/pf.conf") to capture and display the command's stderr when it fails (e.g., capture the output into a variable or pipe it so you can include the actual error text in the echo/error log), and ensure the error message printed by the script includes that captured stderr so the root cause is visible before exiting.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/skills/expand/SKILL.md around lines 71 - 81, The regex r'^### (\d+\.\d+)\s+' and the loop building plan_sections only matches two-level numeric headings and will miss single-level (### 1), three-level (### 1.1.1) or non-numeric headings (### Task 1); update the guidance in SKILL.md by either broadening/parametrizing the regex (or providing multiple patterns) and documenting the exact expected heading formats, and mark extract_section_content as pseudocode (or describe its behavior) so implementers know to extract content from the current heading up to the next same-or-higher-level heading; reference plan_sections, the for-heading regex, and extract_section_content in the note so reviewers can find and implement the real extraction function or adjust the pattern.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/install/shared/skills/expand/SKILL.md around lines 197 - 209, Add a short "Long plan handling" guidance immediately after the Anti-summarization rule (the rule that mandates including every line from plan sections) that prescribes a clear, consistent policy for extremely long plan sections: set a soft length threshold (e.g., 200–500 lines or N kilobytes) and if a plan section exceeds it, require the author/agent to either split the plan into multiple numbered subtasks (using 0-based dependency indices) or attach the full original plan as a separate machine-readable artifact (e.g., a file/blob reference) while including a concise index in the subtask; define a mandatory "embed-full" override tag to force inlining when truly necessary, require metadata on the subtask noting original line/byte count, and mandate that all code/config/schema blocks be preserved verbatim by referencing file paths or attachments rather than inline truncation so agents can still access the full content without bloating task descriptions.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/llm/sdk_compat.py around lines 37 - 38, The module-level mutable _last_rate_limit dict is not thread-safe; wrap accesses with a synchronization primitive or make it request-scoped: either introduce a threading.Lock (e.g., _last_rate_limit_lock) and acquire/release it around all reads/writes to _last_rate_limit in the message-parsing code, or replace the global with thread-local storage (threading.local) or a per-request attribute so concurrent streaming handlers cannot race when writing _last_rate_limit. Ensure every place that reads or writes _last_rate_limit uses the chosen safe access pattern.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/llm/sdk_compat.py around lines 57 - 60, The current fallback uses truthiness which skips valid falsy values (e.g., 0); update the assignments for retry_after, resets_at, limit, and remaining to choose the first key present in data rather than the first truthy value — e.g., replace "a = data.get('a') or data.get('b')" with an explicit presence check or a small helper like _get_first(data, 'retry_after','retryAfter') that returns data[k] if k in data else None; apply this pattern to retry_after, resets_at, limit, and remaining so zero or other falsy-but-valid values are preserved.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/llm/sdk_compat.py around lines 61 - 67, The log call in sdk_compat.py currently uses positional formatting; change it to structured logging by replacing the formatted logger.info call with a call that uses a simple human message and an extra dict containing retry_after, resets_at, limit, and remaining (e.g., logger.info("Rate limit event", extra={...})). Locate the logger.info invocation in sdk_compat.py (the block referencing retry_after, resets_at, limit, remaining) and pass those variables via extra so the context is machine-parseable while keeping a concise message.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent.py around lines 78 - 80, In the TimeoutError except block in spawn_agent.py (where proc.kill() is called), await the process reaping by calling await proc.wait() after proc.kill() so the subprocess transport is cleaned up and avoids resource warnings; ensure the except handles any exceptions from wait (e.g., CancelledError) if needed and still returns True to preserve the current behavior of the surrounding function.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/worktrees.py around lines 135 - 136, Two ValueError handlers are inconsistent: the handler that returns None, None, f"Failed to initialize git manager for {resolved_path}: {e}" should be aligned with the other ValueError handler that currently uses "Invalid git repository: {e}". Update the message in the except block that references resolved_path (the block catching ValueError from WorktreeGitManager initialization) so both handlers use the same format and include the path, e.g. "Invalid git repository for {resolved_path}: {e}" (or change the other handler to match whichever phrasing you prefer) to ensure consistent error wording across WorktreeGitManager error handling.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/memory/manager.py around lines 540 - 542, The loop over merged_ids is calling the synchronous self.storage.get_memory(memory_id) (and the repeated calls later) which can block the event loop; change these to non-blocking lookups by using an async storage API if available (e.g., await self.storage.get_memory_async(id) or a batch method like await self.storage.get_memories(list_of_ids)), or offload the synchronous calls to the threadpool with asyncio.get_running_loop().run_in_executor and use asyncio.gather to perform them concurrently; update the code that references merged_ids and self.storage.get_memory to use the chosen async/batched approach and apply the same fix to the later occurrences of get_memory in this function/class.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/memory/manager.py at line 386, Replace the runtime assertion "assert self._kg_service is not None" with an explicit conditional check that raises a clear exception (e.g., RuntimeError or ValueError) when self._kg_service is None; update the code in the method where this assert appears to perform "if self._kg_service is None: raise RuntimeError('...')" with a descriptive message mentioning _kg_service so the failure is not stripped by optimized bytecode and is easier to debug.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/memory/neo4j_client.py around lines 396 - 418, The ensure_vector_index method interpolates the similarity parameter directly into the Cypher string causing possible injection; fix by validating/sanitizing similarity before interpolation: in ensure_vector_index validate that similarity is one of an explicit allowlist (e.g., "cosine", "euclidean") and raise a ValueError for invalid inputs (also ensure dimensions is an int > 0 if not already enforced), then use the validated value when building the cypher; keep using _validate_cypher_identifier for index_name and do not allow arbitrary similarity strings.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/memory/services/knowledge_graph.py around lines 328 - 351, The loop over entity_rows creates an N+1 query pattern by calling self._neo4j.query per entity to fetch memory_ids; instead, gather all non-empty names from entity_rows, run a single batched Cypher query (using UNWIND $names AS name MATCH ({name: name})-[:MENTIONED_IN]->(m:Memory) RETURN name, collect(m.memory_id) AS memory_ids) via self._neo4j.query, build a mapping from name->memory_ids, and then iterate entity_rows to populate results using that mapping (falling back to an empty list if a name has no entries); update references to memory_ids and the existing logger handling accordingly so behavior stays the same but with two queries instead of N+1.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/memory/services/knowledge_graph.py around lines 437 - 456, The code checks self._embed_fn for None in the vector-search path but the constructor's type hint says embed_fn is required; either make the embed function optional in the type or remove the None check. Update the constructor/type declaration for embed_fn/_embed_fn to Callable[..., Any] | None (and document optional) if None is a valid runtime state, or remove the defensive `if self._embed_fn is not None:` check and assume embed_fn is always present and used in methods like search_entities_by_vector and the embedding call in this block; ensure you adjust any callers and tests to match the chosen invariant.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/memory/services/maintenance.py around lines 58 - 70, The current get_stats sync flow sets stats["vector_count"] = -1 when an event loop is running; change this by adding an async variant that actually awaits the vector store count: implement async def get_stats_async(...) that awaits vector_store.count() and populates stats["vector_count"], and keep a synchronous get_stats(...) wrapper that calls asyncio.run(get_stats_async(...)) when no loop is running to preserve CLI behavior; reference the existing get_stats function and vector_store.count() when making the changes and ensure any callers that are async use get_stats_async instead of the sync get_stats.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/chat_session_helpers.py at line 59, The _load_chat_system_prompt function currently types its db parameter as Any which loses type safety; change the signature to accept a more specific type (e.g., Optional[DatabaseClient] or a Protocol that declares the methods/attributes this function actually uses) and update imports accordingly (from typing import Optional, Protocol) or use your existing DB connection class/interface; adjust callers if needed so type-checkers know the concrete type and ensure the method calls inside _load_chat_system_prompt match the chosen type's API.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/chat_session_helpers.py around lines 74 - 76, The except block in chat_session_helpers.py uses f-string interpolation in logger.warning which violates structured-logging guidelines; update the except Exception as e handler (the logger.warning call that currently interpolates the exception and returns _FALLBACK_SYSTEM_PROMPT) to use structured logging with context (e.g., pass the exception and any context as separate arguments or keyword fields to logger.warning/exception) so the message and exception are recorded without formatting into the string while preserving the return of _FALLBACK_SYSTEM_PROMPT.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/chat_session_permissions.py around lines 236 - 245, The set_chat_mode method uses a redundant elif condition; change the second branch from "elif mode != \"plan\"" to a plain "else" to make intent clearer while keeping behavior: in set_chat_mode, assign self.chat_mode = mode, and when mode == "plan" or otherwise, ensure self._plan_approved and self._plan_feedback are reset as currently done for both branches (references: set_chat_mode, chat_mode, _plan_approved, _plan_feedback).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/chat_session_permissions.py at line 135, Replace the f-string logging in the timeout path with structured logging to match the style used elsewhere: instead of logger.warning(f"AskUserQuestion timed out for session {self.conversation_id}"), call logger.warning with a static message and pass context via the extra dict (include conversation_id from self.conversation_id and any other relevant keys used on lines 311-313) so the log uses the same structured format as the other entries in the ChatSessionPermissions class.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/admin.py around lines 817 - 831, The handler get_setup_state performs synchronous file I/O (state_path.exists() and state_path.read_text()) which can block the event loop; change it to use asyncio.to_thread to run those Path operations off the loop (import asyncio), e.g. await asyncio.to_thread(state_path.exists) and await asyncio.to_thread(state_path.read_text) so you still parse JSON and set data["exists"]=True and preserve the current exception handling (catch json.JSONDecodeError and OSError) around the awaited read; keep the same return shapes.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/admin.py around lines 836 - 852, The handler update_setup_state is performing synchronous file I/O via Path.read_text() and Path.write_text(), which blocks the event loop; change these to async calls using asyncio.to_thread (e.g., await asyncio.to_thread(state_path.read_text) and await asyncio.to_thread(state_path.write_text, json.dumps(..., indent=2))) and add the asyncio import in the function scope; keep the same json.loads/json.dumps and exception handling, and do not alter the logic that updates data["web_onboarding_complete"] to preserve behavior.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/chat.py around lines 685 - 691, The code is dynamically adding _accumulated_output_tokens and _accumulated_cost_usd to the session object; instead, declare these as typed attributes on the ChatSession class and initialize them (e.g., in ChatSession.__init__) to default values (0 and 0.0) so IDEs and type checkers recognize them; then keep the existing update logic in the handler that uses session._accumulated_output_tokens and session._accumulated_cost_usd (or replace getattr with direct attribute access) to update totals in the event handling code shown.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/chat.py around lines 839 - 846, Replace the f-string logs with structured logging using the logger's extra parameter: for the "Plan approved" and "Plan changes requested" branches, call logger.info with a static message and pass conversation_id (use conversation_id or conversation_id[:8] as a context field) and decision as keys in extra; ensure you still call session.set_plan_feedback(feedback) when provided. Update both occurrences where logger.info is used and keep the same message text but move dynamic data into extra for structured context.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/chat.py at line 819, Replace the plain warning call that logs the raw conversation id with a structured log using logger.warning's extra parameter: locate the logger.warning invocation that references conversation_id_raw (the "plan_approval_response for unknown conversation" message) and change it to pass a concise message string and an extra dict containing the conversation_id (use the variable conversation_id_raw as the value) so the log becomes structured and consistent with other logs in this module.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/chat.py around lines 564 - 569, The local assignment "content = event.content" shadows the function parameter named content; rename the local variable (e.g., event_content or evt_content) and use that new name in the subsequent logic (the after_tool_call check, the prefixing with "\n\n", and the accumulated_text += operation) so the parameter and the event value are not confused; ensure all references in this block that previously used the local content are updated to the new variable name and behavior remains unchanged.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/chat.py around lines 814 - 821, The condition currently checks "session is None or conversation_id_raw is None" redundantly because self._chat_sessions.get(conversation_id_raw) already returns None for a None key; simplify the guard to check only "if session is None:" and then explicitly narrow conversation_id_raw before assigning conversation_id (e.g., if conversation_id_raw is None: logger.warning(...); return). Also add logging for unrecognized decisions by inspecting the "decision" variable and calling logger.warning with context when it contains an unexpected value so you can debug unknown decisions (reference variables conversation_id_raw, session, decision, self._chat_sessions, and logger.warning).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/chat.py around lines 971 - 972, Replace the unstructured f-string log in the except block where it handles "Failed to sync mode_level on mode change" to use structured logging: call logger.warning with a static message and pass the exception details in the extra parameter (e.g., extra={"error": str(e), "context":"mode_level_sync"}) and include exc_info=True if you want the traceback (so: logger.warning("Failed to sync mode_level on mode change", extra={"error": str(e), "context":"mode_level_sync"}, exc_info=True)). Use the existing logger and exception variable e in this change.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/sessions/lifecycle.py around lines 108 - 111, Remove the redundant inner exception handling inside _purge_soft_deleted_definitions so the outer try/except in the caller (the block that calls await self._purge_soft_deleted_definitions()) is the single place that catches and logs errors; specifically, delete the inner try/except that catches Exception and calls logger.error in _purge_soft_deleted_definitions (the internal logger.error call), leaving any necessary cleanup but letting exceptions propagate to the caller's try/except for centralized logging.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/sessions/lifecycle.py around lines 179 - 190, _purge_soft_deleted_definitions is calling synchronous DB methods (LocalWorkflowDefinitionManager.purge_deleted and LocalAgentDefinitionManager.purge_deleted) directly inside an async function which blocks the event loop; fix by importing asyncio if not present and calling these sync methods via asyncio.to_thread (await asyncio.to_thread(...)) or run them concurrently with await asyncio.gather(asyncio.to_thread(wf_mgr.purge_deleted, older_than_days=30), asyncio.to_thread(agent_mgr.purge_deleted, older_than_days=30)); keep the existing try/except and logger.error usage and only change the direct calls to use asyncio.to_thread so the purge runs off the event loop.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/agent_definitions.py around lines 356 - 366, The purge_deleted method constructs a SQLite datetime modifier from older_than_days which can produce invalid strings for zero or negative values; add input validation at the start of purge_deleted (the function named purge_deleted and its parameter older_than_days) to ensure older_than_days is a positive integer (e.g., raise ValueError or normalize to a minimum of 1), then proceed to build the SQL modifier (f"-{older_than_days} days") and execute the DELETE against the agent_definitions table (deleted_at column) as before; keep the db.transaction usage and logging of count unchanged.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/agent_definitions.py around lines 344 - 354, The restore() method is missing the bundled-scope guard used by delete(), hard_delete(), and update(); call self._check_bundled_writable(definition_id) at the start of restore() (before performing the DB transaction/UPDATE) to enforce the same dev-only bundled record rule and keep behavior consistent with delete()/hard_delete()/update(); keep the rest of the existing logic (timestamp, UPDATE, rowcount check, and return of self.get(definition_id)).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/watchdog.py around lines 264 - 266, The log currently reports elapsed time as ((i + 1) * 2) before the sleep, which overstates time by one sleep interval; update the logger.info in the loop that prints "Waiting for daemon startup..." to use i * 2 to reflect completed loop sleep time, or if you want to include the initial grace period add that constant (e.g., initial_grace + i * 2) instead — modify the logger.info call near the time.sleep(2.0) and keep the surrounding loop and variable i unchanged.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/enforcement/task_policy.py around lines 21 - 35, The substring check using "{{" is brittle: update _resolve_message to skip the fragile if "{{" in template check and instead attempt to render when context is provided (call TemplateEngine().render(template, context)) so templates using other delimiters still work; wrap the render call in a try/except that falls back to returning the original template on render errors, and keep the existing behavior of returning default when messages is missing or key not present—use the existing TemplateEngine and render method names in your change.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/memory_actions.py around lines 556 - 560, The wrapper call in handle_memory_recall_with_synthesis passes limit=kwargs.get("limit", 3) which conflicts with the underlying memory_recall_with_synthesis signature default of limit: int = 5; update the wrapper to use the same default (change 3 to 5) or remove the explicit default so it forwards kwargs.get("limit") to memory_recall_with_synthesis, ensuring the default behavior of memory_recall_with_synthesis (limit=5) is preserved; modify the call site that constructs the kwargs for memory_recall_with_synthesis accordingly.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/memory_actions.py around lines 361 - 368, The code currently swallows all exceptions when resolving a provider for digest_config by using except (ValueError, Exception) and falling back silently; change this to only catch ValueError (e.g., except ValueError as e) when calling llm_service.get_provider_for_feature(digest_config), and log the exception details (use logging.exception or logger.error(..., exc_info=True)) before falling back to llm_service.get_default_provider() and setting model = None; do not catch broad Exception so other unexpected errors can propagate.

- Verify each finding against the current code and only fix it if needed.

In @tests/cli/test_setup.py around lines 1 - 26, Add a test category marker to the module by declaring a module-level pytest mark (e.g., pytestmark = pytest.mark.unit) so the test runner classifies these tests per guidelines; since the file already imports pytest and defines test_setup_command_exists, add the pytestmark assignment near the top of the file (module scope) rather than decorating individual tests.

- Verify each finding against the current code and only fix it if needed.

In @tests/memory/test_graph_search_integration.py around lines 254 - 266, Add a new assertion to test_clamps_max_hops that verifies find_related_memory_ids clamps values below 1 up to 1: call await service.find_related_memory_ids(entity_names=["A"], max_hops=0) (or add a separate small test using the same mock_neo4j) and assert that mock_neo4j.query was invoked with a pattern containing "*1.." (e.g., "*1..1" or at least "*1..") to confirm the lower bound clamping; keep using mock_neo4j.query = AsyncMock(return_value=[]) to capture the generated query.

- Verify each finding against the current code and only fix it if needed.

In @tests/memory/test_graph_search_integration.py at line 14, The module-level pytest marker only sets pytestmark = pytest.mark.unit but the test functions are async, so add the asyncio marker to module-level pytestmark (e.g., include pytest.mark.asyncio alongside pytest.mark.unit) so pytest-asyncio will run the async test coroutines; update the pytestmark variable referenced in this file to include both markers rather than leaving only pytest.mark.unit.

- Verify each finding against the current code and only fix it if needed.

In @tests/memory/test_manager_graph_search.py around lines 118 - 144, The async test functions (e.g., test_returns_direct_memory_ids, test_deduplicates_traversed_ids, test_returns_empty_when_no_entities, test_parallel_search_with_rrf_merge, test_graceful_degradation_graph_failure, test_qdrant_only_when_graph_search_disabled, test_qdrant_only_when_no_kg_service, test_user_source_boost_applied, test_fire_background_graph_receives_memory_id) need the @pytest.mark.asyncio decorator so pytest-asyncio runs them; add @pytest.mark.asyncio above each async def and ensure pytest is imported in the test module if not already present.

- Verify each finding against the current code and only fix it if needed.

In @tests/memory/test_neo4j_vector_search.py around lines 28 - 41, The async tests (e.g., test_creates_index_with_defaults, test_creates_index_with_custom_params) in this file are missing the pytest-asyncio marker; add @pytest.mark.asyncio to the test class or directly above the async test functions (apply to the class containing test_creates_index_with_defaults and the TestVectorSearch class) so pytest-asyncio runs these async def tests correctly, ensuring the decorator import (pytest) is present at the top of the file.

- Verify each finding against the current code and only fix it if needed.

In @tests/memory/test_vectorstore_init.py around lines 163 - 169, The test_default_qdrant_path currently only builds a Path and checks "qdrant" is contained, which doesn't validate the new services directory structure or the code producing the default path; update test_default_qdrant_path to assert the full expected path structure (e.g., assert default_path.endswith(os.path.join(".gobby","services","qdrant")) or the equivalent string) or, better, call the function/config that returns the default qdrant path and assert its value equals the expected Path (referencing the test function name test_default_qdrant_path and the local variable default_path to locate where to change the assertion).

- Verify each finding against the current code and only fix it if needed.

In @tests/sync/test_integrity.py around lines 16 - 38, Add the pytest unit marker to the test classes by decorating TestIntegrityResult, TestVerifyBundledIntegrity, and TestGetDirtyContentTypes with @pytest.mark.unit; locate each class definition (e.g., class TestIntegrityResult:) and prepend the @pytest.mark.unit decorator so the test suite correctly categorizes these as unit tests.

- Verify each finding against the current code and only fix it if needed.

In @tests/workflows/test_task_enforcement.py at line 2498, Add the missing blank lines before the new top-level test section: insert two blank lines immediately before the comment that starts the new test section (i.e., before the comment line that marks the next set of tests) so that top-level test/class definitions are separated by two blank lines in accordance with PEP 8.

- Verify each finding against the current code and only fix it if needed.

In @web/scripts/build-setup.mjs around lines 17 - 20, The code currently reads pyproject.toml into pyproject and sets version to "0.0.0" silently when versionMatch is null; update the logic in build-setup.mjs around readFileSync(join(projectRoot, "pyproject.toml")) / pyproject / versionMatch so that if reading the file fails or versionMatch is falsy you emit a clear warning (e.g., console.warn or the project's logger) describing that pyproject.toml is missing or the version field couldn't be parsed and include the path (projectRoot) and contents or match result for diagnostics, then continue using the fallback "0.0.0".

- Verify each finding against the current code and only fix it if needed.

In @web/src/App.tsx around lines 184 - 187, The useEffect syncing project filter omits sessionsHook.setFilters from its dependency array; update the effect to include the setter (e.g., add sessionsHook.setFilters or destructure const { setFilters } = sessionsHook and include setFilters) alongside effectiveProjectId so ESLint exhaustive-deps is satisfied, or ensure the setter is a stable/memoized function before relying on it in useEffect; reference the useEffect that calls sessionsHook.setFilters and the effectiveProjectId variable when making the change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/AgentDefinitionsPage.tsx around lines 428 - 436, The checkbox input tied to showDeleted (checked={showDeleted} with onChange={e => setShowDeleted(e.target.checked)}) lacks an explicit accessible name; add either an aria-label (e.g., aria-label="Show deleted items") to the input or give the input an id and change the surrounding <label> to use htmlFor matching that id (keep className="agent-defs-show-deleted" and the existing behavior and ensure assistive tech reads "Show deleted").

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/MobileSessionDrawer.tsx around lines 35 - 39, The onKeyDown handler on the MobileSessionDrawer container is firing for key events that originate from nested controls (e.g., the refresh button), causing both refresh and toggle; update the handler used with role="button" (the onKeyDown that calls setIsOpen(!isOpen)) so it only toggles when the key event originates from the container itself—check that e.target === e.currentTarget (or validate e.composedPath()[0] === e.currentTarget) before calling preventDefault() and setIsOpen(!isOpen); keep the existing Enter/Space checks but gate them with this target check to avoid reacting to keydown from nested elements like the refresh button.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/PipelineEditor.css around lines 274 - 278, The :hover rule for .pipeline-editor-step-action--danger currently hardcodes colors (#3a1a1a, #f87171, #7f1d1d); change this to use CSS custom properties for theming consistency by replacing those literals with variables (e.g., --color-danger-bg-hover, --color-danger-text, --color-danger-border) and ensure defaults are defined (either in :root or a theme scope) so .pipeline-editor-step-action--danger:hover references the variables instead of hardcoded values.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/PipelineEditor.css around lines 74 - 83, Extract the hardcoded colors in .pipeline-editor-badge into CSS custom properties and use them instead of literals: define variables like --badge-bg and --badge-text (preferably on :root or a theme/container selector) and update the .pipeline-editor-badge rule to reference var(--badge-bg) and var(--badge-text); include sensible default fallbacks where appropriate so the badge keeps its appearance if the variables are not defined.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/PipelineEditor.tsx around lines 277 - 282, The map is using the array index as a React key (key={idx}) which breaks reconciliation when steps are reordered; update the JSX returned in the steps.map callback to use the unique identifier (step.id) as the key instead, ensuring the element that renders the step (the div with className "pipeline-editor-step") uses key={step.id} and keep the rest of logic (detectStepType(step), expandedIdx checks) unchanged; if step.id may be missing, add a guard to generate or assert a stable id before mapping.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/PipelineEditor.tsx around lines 155 - 164, The addStep closure captures steps.length at render time causing setExpandedIdx(steps.length) to be stale; change addStep to use functional updates: call setSteps with an updater (prev => { const ids = prev.map(s => s.id); const step = createDefaultStep(type, ids); const newIndex = prev.length; setExpandedIdx(newIndex); return [...prev, step]; }) and keep markDirty() (or call it after the functional update) so the expanded index uses the fresh previous length; update references to steps in the dependency array accordingly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/SessionDetail.tsx around lines 43 - 44, The current check in SessionDetail.tsx compares dur !== '—', which couples presentation to formatDuration's fallback; update by changing formatDuration (or its module) to return null (or an empty string) for invalid durations or export a named fallback constant (e.g., FALLBACK_DURATION) and then update the call site that assigns const dur = formatDuration(session.created_at, session.updated_at) to guard with a truthy check (if (dur) parts.push(dur)) or compare to the exported constant, so the component no longer relies on a magic em‑dash string; adjust formatDuration's signature/exports and update SessionDetail.tsx accordingly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/SessionDetail.tsx around lines 152 - 171, Move the interactive generate/regenerate buttons out of the <summary> in SessionDetail.tsx to avoid nested controls: remove the <button> elements with classes session-detail-generate-btn and session-detail-regenerate-btn from inside the element with class session-metadata-toggle and render them adjacent to the <summary> (or inside the collapsible content) while still using the existing onGenerateSummary handler and isGeneratingSummary/session.summary_markdown conditions; alternatively implement a toggle that separates the disclosure control from actions so the summary remains solely the toggle control and the action buttons are independent.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.tsx around lines 116 - 130, The handlers handleDelete and handleRestore can trigger a concurrent fetchWorkflows that races with the useEffect that also watches showDeleted; to fix, stop directly calling fetchWorkflows from the mutation callbacks and instead (a) introduce and set a local "isMutating" or "isRefreshing" state/ref when deleteWorkflow/restoreWorkflow starts and clear when finished to block concurrent fetches, or (b) remove the post-mutation fetchWorkflows call and rely on the existing useEffect by invalidating the workflows cache (or toggling a single refresh token) so the effect triggers a single consistent refresh; update handleDelete/handleRestore (and any callers of deleteWorkflow/restoreWorkflow) to use that single refresh mechanism and reference fetchWorkflows, showDeleted, handleDelete, handleRestore, deleteWorkflow, and restoreWorkflow when making the changes.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/WorkflowsPage.tsx around lines 389 - 399, Add a confirmation step before restoring a workflow to match the delete flow: update the Restore button's onClick to call a small wrapper (e.g., onRestoreClick or confirmRestore) that uses window.confirm("Restore this workflow?") and only calls the existing handleRestore(wf) when the user confirms; you can either implement the wrapper inline in the JSX or as a new helper function in the WorkflowsPage component so the restore flow is guarded by confirmation.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ToolCallCard.tsx around lines 202 - 218, The code calls resultStr.trimStart() twice when computing looksLikeJson; assign the trimmed string to a temporary variable (e.g., const trimmed = resultStr.trimStart()) and use trimmed.startsWith('{') || trimmed.startsWith('[') to compute looksLikeJson, leaving the rest of the rendering logic (SyntaxHighlighter and the pre block) unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/sessions/transcriptAdapter.ts around lines 62 - 65, Replace the brittle startsWith/includes heuristic in transcriptAdapter.ts with a safe JSON parse+validation: when msg.role === 'user', attempt to JSON.parse(content) inside a try/catch, ensure the parsed value is an array and that its items are objects (and at least one item contains a "tool_result" key or the expected structure), and only then continue/skip the message; on parse errors or non-matching structure, do not skip. This logic should target the block referencing msg.role and content so it only skips truly valid tool_result JSON arrays.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/sessions/transcriptAdapter.ts around lines 103 - 105, The two empty-content checks in transcriptAdapter.ts are redundant—remove the assistant-specific branch and collapse to a single check so messages with falsy content are skipped once; specifically delete the if (!content && msg.role === 'assistant') branch (or replace both with one unified guard) where the code iterates messages (references: variable content and msg.role inside the transcript processing function) so only a single if (!content) continue remains.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSlashCommands.ts at line 91, The concatenation setCommands([...localEntries, ...aliasEntries, ...cmds]) can produce duplicate entries when an alias (in aliasEntries) points to a command also present in cmds; update the logic in useSlashCommands (around setCommands) to filter cmds by removing any command whose identifier/name matches an alias target or whose display string equals an alias label so aliased commands do not appear twice; implement this by computing a Set of alias identifiers/labels from aliasEntries and using cmds.filter(...) before spreading into setCommands to ensure uniqueness.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/App.tsx around lines 116 - 119, currentIdx check returns an empty <Box /> when currentIdx >= STEPS.length which can cause layout shift; instead render a clear completion UI or redirect: replace the empty <Box /> in the completion branch with either a persistent completion component (e.g., <Completion /> or <Box><Text>All steps complete</Text></Box>) or trigger a navigation (useNavigate) to a success route, and ensure the replacement preserves expected container sizing to avoid layout jumps; update references in this component around currentIdx, STEPS, and the Box render branch.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/App.tsx around lines 86 - 110, Call loadState() once and reuse that result for all initializers: compute const initial = loadState() before the hooks, then initialize state with useState<SetupState>(() => initial), set stateRef = useRef(initial), and initialize currentIdx with useState<number>(() => { if (!initial.completed_step_id) return findNextActive(0, initial); const completedIdx = STEPS.findIndex(s => s.id === initial.completed_step_id); if (completedIdx < 0) return findNextActive(0, initial); return findNextActive(completedIdx + 1, initial); }); keep setState/setStateRaw and setCurrentIdx unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/AboutYou.tsx around lines 31 - 44, The onSubmit handler currently calls saveState(next) inside the setState updater, which is a side effect; compute the final state object (e.g., const next = { ...prev?, user_name: finalName, completed_step_id: "about-you" }) outside the setState updater, call setState(next) (or setState(() => next)), then call saveState(next) after setState completes (immediately after calling setState is fine for this sync prepared object), and keep setSubmitted(true) and setTimeout(onNext, 300) as-is; update the onSubmit function and references to onSubmit, setState, saveState, setSubmitted, onNext, defaultName, user_name, and completed_step_id accordingly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/Bootstrap.tsx around lines 16 - 50, The useEffect callback references the state setters setPhase and setError (and utility functions isGobbyInstalled, detectTool, execSync) but the dependency array is empty; update the effect to include the stable setters in the dependency array to satisfy linting and best practices—i.e., add setPhase and setError (and optionally isGobbyInstalled/detectTool/execSync if they are not stable or memoized) to the dependency list of the useEffect that performs the installation check and execSync call.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/Bootstrap.tsx around lines 35 - 49, The synchronous execSync call in Bootstrap.tsx blocks the event loop and freezes the Ink UI; replace execSync("uv tool install gobby", ...) with an asynchronous implementation (e.g., promisified child_process.exec or child_process.spawn wrapped in a Promise) and convert the surrounding logic to async/await so the spinner remains responsive; after the async command resolves, call isGobbyInstalled() and then call setPhase("done") or setError(...) and setPhase("error") as before, and ensure you handle timeout and capture stderr/stdout to include useful error messages when calling setError (referencing execSync, isGobbyInstalled, setPhase, and setError to locate the code).

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/CliHooks.tsx around lines 59 - 62, The render currently triggers a side effect via an IIFE that calls setTimeout(() => finish([]), 300) inside JSX; move that logic into a useEffect hook in the CliHooks component (or the component that defines finish) so the timer is scheduled only after mount: call const id = setTimeout(() => finish([]), 300) inside useEffect with an appropriate dependency array (likely [] if it should run once), return a cleanup function that clears the timeout (clearTimeout(id)), and remove the IIFE from the JSX so render remains pure.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/CliHooks.tsx around lines 85 - 106, The UI update is blocked because setPhase("installing") is followed by the synchronous runGobby call; make the install flow asynchronous and add error handling so the "installing" spinner can render and any thrown errors are caught. Change the block around setPhase("installing") → runGobby(...) to use an async function (or wrap the runGobby call in setTimeout(() => ...) if runGobby is sync), wrap the call in try/catch, populate lines/installed in the try branch, push error output in the catch, and ensure setResults(lines), setPhase("done") and finish(installed) are executed in a finally so UI state and callbacks always update; reference the existing symbols setPhase, runGobby, setResults, finish, CLI_FLAGS, CLI_LABELS when making the change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/Configuration.tsx around lines 95 - 109, The onSubmit handler for ports currently ignores invalid input; add explicit user feedback when parseInt yields NaN or the port is outside 1-65535 by setting an error state or invoking the form/toast error API before returning. Concretely: inside the onSubmit block that parses port, add an else branch that calls a new or existing error setter (e.g., setPortError or setInputError) with a clear message like "Enter a valid port between 1 and 65535" and ensure any UI showing editValue reads that error to display it; keep the existing behavior (setPorts, setEditingIdx, setEditValue, commit) unchanged for valid values. Ensure the error is cleared when a subsequent valid value is submitted (clear the error in the valid branch).

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/Launch.tsx at line 118, The function writeInitialSetupMd uses a complex inline conditional type (typeof import("../utils/state.js").loadState extends () => infer R ? R : never) which hurts readability; extract a named alias by adding SetupState in your types module (e.g., export type SetupState = ReturnType<typeof import("../utils/state.js").loadState>) and then change writeInitialSetupMd signature to accept state: SetupState — update any imports to reference the new SetupState type and ensure the types.ts (or types module) is exported for use in Launch.tsx.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/Launch.tsx around lines 18 - 29, runGobby(["start"], invoked inside the async run function in the useEffect, is fire-and-forget which can swallow startup failures; update the run function to await runGobby(["start"], { timeout: 15000 }) and handle its rejection or non-success result (wrap in try/catch or check the returned status), call process/state error handling (e.g., setPhase to an error state and log the error) and return early to avoid running checkHealth/writeInitialSetupMd on failed starts; reference runGobby, run (the async function), setPhase, setHealthy, checkHealth, and writeInitialSetupMd when making the change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/NetworkSecurity.tsx around lines 76 - 81, The destructuring of state.ports (const { http, ws, ui } = state.ports) can throw if state.ports is undefined; update the code around spawnSync to guard and provide safe defaults: check that state and state.ports exist (or use a fallback object) before destructuring, validate http/ws/ui are numbers/strings (or coerce with defaults) and only call spawnSync("sudo", ["bash", tmpScript, String(http), String(ws), String(ui)], ...) when ports are present; ensure tmpScript is validated as well and handle the error path (log/return) if ports are missing to avoid runtime exceptions in the NetworkSecurity component.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/NetworkSecurity.tsx around lines 72 - 94, The temp script tmpScript created with writeFileSync is never removed and the bare catch swallows errors; wrap the spawnSync call in a try/catch/finally so you always unlink the tmpScript (fs.unlinkSync or async unlink) in the finally block to avoid leaving artifacts, and change the catch to capture the error (e) and log it (e.g., console.error or your logger) and/or include the error message when calling setResult("failed")/finish(false) so failures surface; update the block around spawnSync, tmpScript, setResult, finish and setPhase to ensure cleanup and proper error logging.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/PersonalWorkspace.tsx around lines 33 - 46, The code currently performs side effects during render (mkdirSync and runGobby) when phase === "init" inside PersonalWorkspace.tsx; move those operations into a useEffect that watches phase and performs the work only when phase === "init" (use an async inner function), and guard against double execution in Strict Mode by using a ref flag (e.g., didInitRef) or making the operation idempotent; after the async work call setInitMsg(...) and setPhase("shortcut") inside the effect, and reference the existing functions/values (mkdirSync, runGobby, setInitMsg, setPhase, phase) so the logic is relocated out of the render path and only executes once.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/PersonalWorkspace.tsx around lines 90 - 93, The catch currently swallows errors; change it to catch the error (e.g., catch (err)) then still call setPhase("done") and finish(false) but also surface the error to the user by invoking the component's user-visible error mechanism (for example, call an existing notification/toast function or set a local error state like setErrorMessage(err.message) and render it). Update the catch in PersonalWorkspace.tsx to capture the error, pass the error message to the UI notifier or a new state (so users see why symlink creation failed), while preserving the existing setPhase("done") and finish(false) calls.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/ProjectDiscovery.tsx around lines 106 - 108, The list rendering uses the array index `i` as the React key in the initResults.map(...) rendering of <Text>, which can cause rendering issues if order changes; update the key to use the line content (the `line` string) instead — e.g., key={line} — and to be safe handle potential duplicate lines by combining the line value with the index (e.g., `${line}-${i}`) so the unique key uses `initResults`, `line`, and `i` when necessary.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/ProjectDiscovery.tsx around lines 26 - 37, In the finish function, remove the side effect saveState(next) from inside the setState updater: compute the next state object (as currently built using prev), call setState with that next object (or return it from the updater without invoking saveState), then invoke saveState(next) immediately after setState and finally setTimeout(onNext, 300); this ensures saveState is executed outside the setState callback and avoids unpredictable side effects (refer to the finish function and its usage of setState and saveState).

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/ProjectDiscovery.tsx around lines 67 - 74, The synchronous for-loop in ProjectDiscovery.tsx that calls runGobby blocks the UI; after calling setPhase("init") you should start the inits asynchronously so React can re-render the spinner. Replace the sequential loop with an async batch: map selected to an array of promises that call runGobby(repoPath, { cwd, timeout }), use Promise.allSettled (or a concurrency-limited p-map) to run them in parallel, build the results strings from each settled value (using basename(repoPath) and r.output for failures), then update the results state once the promises complete; ensure setPhase("init") is executed before awaiting the Promise.allSettled so the spinner shows.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/Services.tsx around lines 66 - 82, The TextInput is controlled with value="" and a no-op onChange, preventing typing; change it to a controlled input backed by component state (e.g., add const [promptValue, setPromptValue] = useState("") near the top of the component), pass value={promptValue} and onChange={setPromptValue} (or an event handler that calls setPromptValue) to TextInput, and keep the existing onSubmit logic that trims and routes to install(), setPhase("password"), or finish(false, false); ensure the state is initialized to "" and updated on every keystroke so onSubmit receives the user-entered choice.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/SystemCheck.tsx around lines 52 - 56, The branch that updates detected_tools and tool_versions via setState in SystemCheck does not persist the change; modify it to persist by creating the new state object (e.g., const newState = { ...prev, detected_tools: result.detected, tool_versions: result.versions }), call setState(newState) and then call saveState(newState) (or await saveState if it returns a promise) so detection results are saved consistently like the other branches that call saveState.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/Tailscale.tsx around lines 14 - 25, The finish function currently calls saveState inside the setState updater and starts a setTimeout for onNext; move the saveState call out of the setState updater so the updater only returns the new state (use setState(prev => next) then call saveState(next) immediately after), and replace the raw setTimeout(onNext, 300) with a cancellable timer stored in a ref (e.g., timerRef) and cleared in a useEffect cleanup to avoid firing after unmount; update references to finish, saveState, setState, setTimeout, and onNext accordingly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/Tailscale.tsx around lines 48 - 52, The code uses the blocking spawnSync call (spawnSync("tailscale", ["serve", "--bg", String(uiPort)], ...)) which freezes the Ink UI; replace it with a non-blocking variant (child_process.spawn or util.promisify(child_process.execFile)/execFile with promises) and await the async result so the UI remains responsive—locate the spawnSync invocation (variable r and uiPort) in Tailscale.tsx, call the async API, attach stdout/stderr/error handlers or use a promise to capture exit status and timeout, and propagate errors to the existing UI/error handling rather than blocking the event loop.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/Tailscale.tsx around lines 54 - 57, The code currently sets the bind host to "0.0.0.0" inside the r.status === 0 branch (see setBindHost("0.0.0.0")), which exposes the service to all network interfaces; change this to bind to the loopback address by calling setBindHost("127.0.0.1") instead so Tailscale Serve remains the only inbound path, leaving the rest of the success flow (setResult("success"); finish(true);) unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/steps/Welcome.tsx around lines 32 - 42, When handling onSelect for the "fresh" choice, the component updates state via setState but never calls saveState so the reset isn't persisted; change the handler to build the new state object (including completed_step_id: null and started_at: new Date().toISOString()) and then call setState(newState) followed by saveState(newState) before calling setAskingResume(false) and onNext(); this ensures the reset is immediately persisted (refer to onSelect, setState, saveState, setAskingResume, onNext and the completed_step_id/started_at fields).

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/utils/config.ts around lines 25 - 38, The patchPorts function uses an unsafe cast of readConfig() and doesn’t validate port values; fix by treating the result of readConfig() as unknown and defensively ensuring data is an object (create a new config object if not), then ensure nested objects exist before assigning (use keys daemon, websocket, ui), validate each port (httpPort, wsPort, uiPort) is a finite integer between 0 and 65535 and throw or return an error if invalid, and finally call writeConfig with the safely constructed config; reference the patchPorts function and the readConfig/writeConfig symbols when making these changes.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/utils/config.ts around lines 14 - 16, Replace the bare catch block that currently just does "catch { return {}; }" with a typed error handler: use "catch (err)" and check for expected errors (e.g., if (err?.code === 'ENOENT') return {};), otherwise log the error (e.g., console.error or processLogger.error) and rethrow or propagate it; update the catch surrounding the code that returns "{}" so unexpected errors are not silently swallowed.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/utils/detect.ts around lines 27 - 36, The helper function which is Unix-only and should handle Windows by using the where command; update the which function to detect platform (process.platform === "win32") and call execSync("where <cmd>") on Windows (keeping execSync("which <cmd>") on other platforms), preserve the existing timeout/encoding options and trimming behavior, and ensure errors still return null; reference the which function in detect.ts and make the platform conditional so Windows users get the correct lookup.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/utils/detect.ts around lines 59 - 60, The version check using the destructured [major, minor] from ver.split(".").map(Number) is wrong for future major versions; update the conditional that currently reads major >= 3 && minor >= 13 so it returns true when major is greater than 3 OR when major equals 3 and minor is at least 13 (i.e., allow any major > 3 or the 3.x series with minor >= 13), keeping the same variables ver, major, and minor in the same scope.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/utils/gobby.ts around lines 28 - 35, The isGobbyInstalled function should respect the configured GOBBY_BIN and be cross-platform: obtain the gobby binary path the same way runGobby does (use the exported or inlined gobbyBin lookup that checks process.env.GOBBY_BIN and defaults) and then verify it exists and is runnable in a cross-platform manner (e.g., if gobbyBin is an absolute/path string use fs.existsSync + fs.stat to ensure it's executable, or on platforms where PATH lookup is needed run the platform-appropriate command — use "where" on Windows or "which" on Unix — or try invoking the binary with a harmless flag like "--version" via execSync and catch errors). Update isGobbyInstalled to use that gobbyBin resolution (or export gobbyBin from the module) and return true only if the resolved binary is present and runnable.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/utils/state.ts around lines 83 - 85, The bare catch in the state loading code swallows all errors; update the catch to capture the error (e) and log it before returning the fallback state so failures (file missing, permission, JSON parse) are visible; reference the same return shape ({ ...DEFAULT_STATE, started_at }) and use the project logger if available (e.g., logger.error) or console.error as a fallback, then return the default state as currently done.

- Verify each finding against the current code and only fix it if needed.

In @web/src/setup/utils/state.ts around lines 24 - 27, DEFAULT_STATE currently sets started_at once at module load, causing all merged states like { ...DEFAULT_STATE, ...parsed } to inherit a stale timestamp; change DEFAULT_STATE.started_at to null (or omit it) and ensure the merge site that creates the runtime state (the { ...DEFAULT_STATE, ...parsed } expression) assigns started_at = parsed.started_at ?? new Date().toISOString() so a fresh timestamp is generated when parsed lacks started_at (keep the existing error-path override intact).

- Verify each finding against the current code and only fix it if needed.

In @web/src/styles/index.css around lines 11260 - 11280, The .agent-defs-btn--restore color (#4ade80) and its hover border (#22c55e) are low-contrast on the light theme; add a light-theme specific override that uses darker green tokens for the button text, border, and hover background/border (target .agent-defs-btn--restore and .agent-defs-btn--restore:hover) — for example place rules scoped under your light theme selector (e.g. :root[data-theme="light"] or .light-theme) and set a darker color for color and border-color and a slightly darker hover background to meet contrast for small text.