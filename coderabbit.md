Fix the following issues. The issues can be from different files or can overlap on same lines in one file.

- Verify each finding against the current code and only fix it if needed.

In @.gemini/skills/worktree-manager/SKILL.md around lines 569 - 584, Update the JSON example in SKILL.md to include the missing config fields present in config.json: add "skipPermissions" (boolean) and "registryPath" (string) to the example payload, provide sensible default values matching the codebase (e.g., skipPermissions: false and a default registryPath string), and add a short inline note about the security implications of "skipPermissions" per the Security Considerations section so readers are aware; ensure the rest of the example (claudeCommand, portPool, portsPerWorktree, worktreeBase, defaultCopyDirs, healthCheckTimeout, healthCheckRetries) remains unchanged.

- Verify each finding against the current code and only fix it if needed.

In @.gemini/skills/worktree-manager/SKILL.md around lines 343 - 357, The three terminal examples in SKILL.md are inconsistent: Ghostty and the tmux sample pass the --dangerously-skip-permissions flag while the iTerm2 sample does not; update the iTerm2 example to include --dangerously-skip-permissions (or alternatively remove the flag from Ghostty and tmux if you prefer the safer default) so all three examples are consistent—specifically edit the iTerm2 command string that writes "cd '$WORKTREE_PATH' && claude" to include the flag, matching the Ghostty and tmux usage of --dangerously-skip-permissions.

- Verify each finding against the current code and only fix it if needed.

In @.gemini/skills/worktree-manager/SKILL.md around lines 426 - 428, The current shell snippet unconditionally runs "uv sync" when pyproject.toml exists, which misdetects non-uv projects; change the detection order and logic so you check for uv.lock first, then for poetry.lock (and run "poetry install" or "poetry export" as appropriate), then fall back to a generic pyproject handler (e.g., pip install via PEP 517/pyproject or document the uv assumption). Concretely, update the conditional branches that include 'elif [ -f "uv.lock" ]; then uv sync' and 'elif [ -f "pyproject.toml" ]; then uv sync' to insert an 'elif [ -f "poetry.lock" ]; then poetry install' (or equivalent) before the pyproject.toml branch and make the pyproject.toml branch use a safer default (pip build/install) or add a comment documenting the uv-only assumption.

- Verify each finding against the current code and only fix it if needed.

In @.gemini/skills/worktree-manager/SKILL.md around lines 82 - 85, Update the example JSON in SKILL.md so the worktree path uses the canonical base path (~/.local/share/worktrees/) instead of /Users/rasmus/tmp/worktrees; specifically modify the "worktreePath" value in the example object (the entry containing "branch": "feature/auth" and "branchSlug": "feature-auth") to start with "~/.local/share/worktrees/feature-auth" to match the documented worktree base.

- Verify each finding against the current code and only fix it if needed.

In @.gemini/skills/worktree-manager/templates/worktree.json around lines 17 - 20, The template uses the field name "copyPaths" which conflicts with the SKILL.md example that shows "copyDirs"; update the template by renaming "copyPaths" to "copyDirs" in the worktree.json fragment (and any other occurrences) so the field name matches SKILL.md, and run a quick grep to update any code or tests that reference "copyPaths"; alternatively, if "copyPaths" is the intended canonical name, update SKILL.md to use "copyPaths" instead—choose one consistent name ("copyPaths" or "copyDirs") and apply it project-wide.

- Verify each finding against the current code and only fix it if needed.

In @.gobby/memories.jsonl around lines 324 - 326, Delete or re-export the three corrupted/concatenated JSONL memory records shown (IDs 6bf7e921-0388-5bb2-82ed-810f65bd54fd, 58b8f556-ad8e-5e24-8c13-6c630db9e55c, f3c42649-6ed1-5025-bdd2-9677ccd81fe6) from the source DB and replace them with a clean export (or remove them entirely) so .gobby/memories.jsonl contains only well-formed, single-record JSON objects; ensure the exported records retain correct fields (content, id, type, tags, timestamps, source) and then recommit the file.

- Verify each finding against the current code and only fix it if needed.

In @.gobby/memories.jsonl at line 297, The exported memories contain absolute, user-specific filesystem paths; update the gobby.sync.memories module so _sanitize_content() normalizes/removes home and temp paths (e.g., replace /Users/<user> or platform-specific temp roots and any /private/tmp/... segments) with safe placeholders like "~" or "<tmp>" using robust regexes, ensure export_memories()/memory export flow calls_sanitize_content() on each memory before writing, and add unit tests that assert user-identifying paths are redacted in the output.

- Verify each finding against the current code and only fix it if needed.

In @coderabbit.md around lines 19 - 36, Remove the sensitive, detailed vulnerability descriptions from the public doc and replace them with high-level, non-actionable notes (e.g., "security hardening applied" or "see private advisory"); move the specific findings and reproduction details into a private security advisory or internal issue tracker; in the public text remove or redact exact mentions of ALLOWED_TAGS including 'a'/'img', ALLOWED_ATTR, ALLOWED_URI_REGEXP, render_canvas implementation details, and explicit package-version gaps for dompurify/@types/dompurify, and instead reference that input sanitization, CSP, image/link proxying, CSS/style isolation, clickjacking mitigations, and pinned dependency updates were performed per internal security guidance; ensure the codebase fixes still reference the same symbols (ALLOWED_TAGS, ALLOWED_ATTR, render_canvas, RENDER_CANVAS_TIMEOUT_DEFAULT, dompurify, @types/dompurify) so reviewers can find and verify fixes via private advisory or PR before rephrasing public docs.

- Verify each finding against the current code and only fix it if needed.

In @coderabbit.md around lines 7 - 8, Remove the unrelated generic memory with id "8445a83b-cf6b-517d-ab75-5693599fd56e" and consolidate the duplicate FastAPI/WebSocket memory entries by keeping the canonical entry "8146a96b-9e41-5216-844a-9ac6d6b7a734" while deleting the redundant entries "7a3886e3-be66-56f7-8dc7-b8ea75b449db" and "aa7846cb-9d6c-5193-84ea-b6c56970ac6d"; if any of the redundant entries contain unique tags or metadata, merge those fields into the canonical entry ("8146a96b-9e41-5216-844a-9ac6d6b7a734") before removal so no metadata is lost.

- Verify each finding against the current code and only fix it if needed.

In @coderabbit.md around lines 1 - 10, Remove the off-topic generic memory with id "8445a83b-cf6b-517d-ab75-5693599fd56e" and consolidate the three FastAPI/WebSocket memories by keeping the canonical entry "8146a96b-9e41-5216-844a-9ac6d6b7a734": delete the redundant entries "7a3886e3-be66-56f7-8dc7-b8ea75b449db" and "aa7846cb-9d6c-5193-84ea-b6c56970ac6d" from .gobby/memories.jsonl, and if those deleted entries contain any unique tags or metadata merge those fields into the canonical memory "8146a96b-9e41-5216-844a-9ac6d6b7a734" instead of losing them.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 62, The blocking timeout for render_canvas is currently set to 600s; reduce it to a more reasonable default (e.g., 30–90 seconds) or make it configurable and update the wait on the asyncio.Event accordingly in render_canvas (and any code that constructs/awaits that Event), document the new default, and ensure CanvasState and canvas_event logic still handles timeout paths (returning a timeout status or non-blocking fallback) so resources are released when the Event wait expires.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 209 - 215, Document that JSON embedded in HTML data-payload attributes must be escaped and parsed safely: explain using single quotes for the attribute with double quotes inside JSON or HTML-escaping quotes (e.g., &quot;) when using double-quoted attributes, state whether server-side sanitization preserves data-attributes, and instruct the frontend parsing routine (referencing element.dataset.payload and JSON.parse) to wrap parsing in try/catch and fall back to an empty object; add these notes immediately after the existing example and include the recommended patterns and error-handling guidance.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 122 - 136, The sanitizeCanvasHtml function must validate input size and presence and guard DOMPurify calls: add a MAX_CANVAS_SIZE constant (e.g., 1MB), return '' for null/empty input, throw or reject when html.length exceeds MAX_CANVAS_SIZE, and wrap DOMPurify.sanitize(...) for sanitizeCanvasHtml in a try-catch that logs the error and returns a safe fallback string like '<p>Unable to render canvas content</p>'; also call DOMPurify.sanitize with explicit options including ALLOWED_TAGS, an ALLOWED_ATTR list (data-action, data-payload, data-element-id, class, id, name, type, value, placeholder, href, src, alt), and deny lists FORBID_TAGS (script, style) and FORBID_ATTR (onerror, onload, onclick) to prevent malformed or malicious input from crashing or rendering unsafe content.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 244 - 254, Add automated tests to replace the manual E2E/security checks: extend tests/tools/test_canvas.py to include XSS prevention unit tests that assert render_canvas strips <script>, onclick, and javascript: URIs and to cover timeout and clear_canvas behavior; add a Playwright or Cypress E2E test (referencing the flow in tests/websocket/test_canvas_interaction.py: render_canvas → broadcast → canvas_interaction → resolve_interaction) that verifies inline rendering, button click sends canvas_interaction over WebSocket and the agent resumes; add integration tests for cross-CLI MCP calls to ensure render_canvas from a terminal session is displayed and interactions propagate back; and add tests for maximum canvas/payload size limits, concurrent interactions, session lifecycle/clear_canvas cleanup, rate limiting of interactions, and behavior when the WebSocket is dropped during a blocking wait.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 15, Replace the hardcoded line-range reference "chat_session.py:387-424" in docs/plans/a2ui-canvas.md with a reference to the function/method name (AskUserQuestion) or a stable relative link to the source; update the sentence to read something like "Same asyncio.Event pattern as AskUserQuestion and pipeline approvals" (or link AskUserQuestion to the file path in the repo viewer) so the doc points to the behavior by symbol rather than brittle line numbers.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 44 - 119, Add production-grade resource limits and abuse protections around the new canvas registry: in create_canvas_registry and its render_canvas, update_canvas, clear_canvas and resolve_interaction logic enforce a max content size (e.g., MAX_CANVAS_BYTES), per-conversation and per-user rate limits (token-bucket or leaky-bucket keyed by conversation_id/user_id) and a max concurrent pending canvases limit (e.g., MAX_PENDING_PER_CONVERSATION) by checking and rejecting new blocking renders when limits exceeded; add a background sweeper tied to the registry that periodically expires and cleans up abandoned CanvasState entries from_pending_canvases (and triggers pending_event.set with a timeout reason) and ensure clear_canvas/session termination calls remove entries; instrument key hooks (render_canvas, update_canvas, resolve_interaction, sweeper) to emit metrics (render_count, interaction_latency, timeout_rate, sanitization_failures) and surface rejection reasons in responses so callers can handle limits; make the limits configurable constants passed into create_canvas_registry so they can be tuned at deployment.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md around lines 111 - 113, The code currently uses getattr(self, "_canvas_registry", None) making the canvas registry an implicit fragile dependency; update the WebSocketServer (or relevant class) to accept a canvas_registry parameter (or set it explicitly during initialization like workflow_handler) and replace the getattr call with a direct reference (e.g., self.canvas_registry) so resolve_interaction(canvas_id, action, payload, form_data) is invoked on the injected registry; ensure the constructor/signature and any places that instantiate WebSocketServer are updated to wire the registry during HTTP server lifespan as documented.

- Verify each finding against the current code and only fix it if needed.

In @docs/plans/a2ui-canvas.md at line 62, Make server-side HTML sanitization mandatory in render_canvas by adding a sanitization step (e.g., using bleach) that cleans the content before creating/storing CanvasState and before broadcasting canvas_event with event:"rendered"; add the chosen sanitization library to backend dependencies, run the sanitizer on the incoming content parameter inside render_canvas (both blocking and non-blocking flows) and then store/broadcast the sanitized value instead of the raw input.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/agents/spawn.py around lines 164 - 169, The code currently accesses the private attribute session_manager._storage to call update_terminal_pickup_metadata, breaking encapsulation; add a public method on ChildSessionManager (e.g., def update_terminal_pickup_metadata(self, session_id: str, agent_run_id: str, workflow_name: str | None) -> None) that delegates to self._storage.update_terminal_pickup_metadata, then replace the direct call in spawn.py to use session_manager.update_terminal_pickup_metadata(session_id=child_session.id, agent_run_id=agent_run_id, workflow_name=workflow_name) so all lifecycle/transaction logic in SessionManager/ChildSessionManager is preserved.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/install.py around lines 331 - 340, The try/except around importing and calling configure_ide_terminal_title uses a bare except; change it to catch specific exceptions (e.g., ImportError for the import and OSError, PermissionError, ValueError for file/config operations) so only expected failures are handled. Replace "except Exception as e" with a tuple of specific exceptions (e.g., except (ImportError, OSError, PermissionError, ValueError) as e), keep the existing click.echo warning behavior, and ensure the error variable 'e' is preserved in the message; target the import and the call to configure_ide_terminal_title in this block when making the change.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/memory.py around lines 546 - 554, The rebuild-graph command block currently assumes the HTTP call and JSON payload will succeed and contain keys; update the code around params, client.call_http_api(...), response.json(), and the click.echo to add defensive checks: verify response.ok and if not, surface a useful error via click.echo/process exit; wrap response.json() in try/except (catch ValueError/JSONDecodeError) and handle missing keys by using dict.get with sensible defaults for 'memories_extracted', 'memories_processed', and 'errors'; ensure any exceptions from client.call_http_api are caught and reported so the command fails gracefully instead of crashing.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/cli/memory.py around lines 514 - 522, Check the HTTP response from client.call_http_api before using response.json() and the expected keys: verify response.status_code (or response.ok) and, on non-success, read response.text or response.json() safely and surface a clear error via click.echo/process exit; when parsing, wrap response.json() in try/except (JSONDecodeError) and access data fields using .get('memories_processed')/.get('crossrefs_created') with fallback values or explicitly raise a user-friendly error so the code around params, client.call_http_api(... "/memories/crossrefs/rebuild"), response, data, and click.echo handles HTTP errors and malformed JSON gracefully.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/event_handlers/_session.py around lines 96 - 99, The code constructs std_path as an f-string (std_path = f"{tempfile.gettempdir()}/gobby-cursor-{session_id}.ndjson") and then unnecessarily wraps it in str() when returning; update the return in the event handler so it returns std_path directly (remove str(std_path)) while leaving the Path(...).exists() check and the self.logger.debug call unchanged to preserve behavior.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/hooks/hook_manager.py around lines 672 - 677, HookManager currently reaches through private attributes (self._session_manager._storage.db) to build a LocalProjectManager and call ensure_exists; add a public accessor on SessionManager (e.g., a db property that returns self._storage.db) or change the factory to pass the database into HookManager so HookManager uses session_manager.db (or the injected database) instead of touching_storage; update the code that constructs LocalProjectManager and calls LocalProjectManager.ensure_exists to use the public session_manager.db (or the injected database) and remove direct references to _storage and its db.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/llm/gemini.py around lines 194 - 196, generate_text raises RuntimeError when LiteLLM isn't initialized but generate_summary and describe_image return error strings; make error handling consistent by changing generate_summary and describe_image to raise RuntimeError (or a more specific custom exception) instead of returning strings, include the original exception context using "from e" where an underlying exception is caught, and ensure callers of generate_summary and describe_image expect exceptions just like generate_text; reference generate_text, generate_summary, and describe_image to locate and update the methods.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/llm/sdk_compat.py around lines 34 - 38, The current patch unconditionally monkey-patches private SDK internals (_internal_client.parse_message and _message_parser.parse_message) which is fragile; change it to check for the attribute before assignment (use hasattr on_internal_client and_message_parser) and only set them to_tolerant_parse_message when present, otherwise emit a warning via the module logger (e.g., logger.warning or processLogger) that the internal structure changed and the tolerance patch was not applied; also leave a short comment next to the assignments referencing the public API alternative (query/ClaudeSDKClient) or that the SDK should be pinned if compatibility is required.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/memory.py around lines 550 - 590, The rebuild_knowledge_graph tool currently hardcodes list_memories(limit=500) and uses an unstructured logger.warning; change rebuild_knowledge_graph to accept a configurable limit parameter (e.g., limit: int | None = 500) and pass that to memory_manager.list_memories(project_id=project_id, limit=limit), update the docstring accordingly, and improve failure logging from logger.warning(f"KG extraction failed for {memory.id}: {e}") to structured logging that includes memory.id and the exception details as separate fields (e.g., logger.warning(..., extra={"memory_id": memory.id, "error": str(e)}) or equivalent) so extraction failures are searchable and the batch size is configurable.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/pipelines/_execution.py around lines 119 - 135, The done-callback _log_exception is misleading because _execute_pipeline_background already catches/handles its exceptions, so t.exception() will usually be None; remove the_log_exception function and the task.add_done_callback(_log_exception) call and instead rely on the existing error handling inside_execute_pipeline_background (or, if you want a guard, change the callback to only log unexpected cancellations by checking t.cancelled()). Update references to _log_exception and task.add_done_callback accordingly so the background task creation uses only asyncio.create_task(...) with the given name.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent.py around lines 596 - 598, The hard-coded 0.5s delay before calling _check_tmux_session_alive can accumulate; make it configurable by introducing a named parameter or module-level constant (e.g., tmux_health_check_delay) and use that instead of the literal 0.5 in the spawn flow where spawn_result.terminal_type == "tmux"; for example add an optional argument to the spawning function (or read from an env/config value) and replace await asyncio.sleep(0.5) with await asyncio.sleep(tmux_health_check_delay) so callers can adjust the wait without changing the code.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/mcp_proxy/tools/spawn_agent.py around lines 51 - 52, Replace the broad "except Exception" around the check in spawn_agent.py with specific exception types (e.g., except (OSError, asyncio.TimeoutError):) to avoid swallowing unrelated errors; ensure asyncio is imported at the top if not already and only return True for those expected failure modes from the check (adjust to include other concrete exceptions like subprocess.CalledProcessError if the check uses subprocess calls).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/runner.py around lines 616 - 640, The except clause in _cleanup_stale_tmux_sessions is too broad; replace "except Exception as e" with targeted handlers for likely tmux-related failures (e.g., except subprocess.SubprocessError as e, except OSError as e) and any specific exceptions exposed by TmuxSessionManager (import them from gobby.agents.tmux.session_manager if available), log the error in each handler, and let truly unexpected exceptions propagate (or re-raise after logging) so they are not silently swallowed by the cleanup routine.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/chat_session.py around lines 478 - 513, The rejection branch in_wait_for_tool_approval currently returns PermissionResultAllow(updated_input={... "_rejected": True}) which incorrectly signals approval; change the function to return the proper deny type (PermissionResultDeny(message="User rejected tool call" or include tool_name/timeout context) when decision == "reject" or on timeout, and only return PermissionResultAllow(updated_input=input_data) for approvals (and add tool_name to_approved_tools on "approve_always"). Also update the function return annotation from PermissionResultAllow to the appropriate union/base type used by the SDK (e.g., PermissionResult or PermissionResultAllow | PermissionResultDeny) so the deny return is type-correct; keep use of _pending_approval_decision,_pending_approval_event, and _approved_tools as-is.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/memory.py around lines 227 - 259, The rebuild_knowledge_graph endpoint currently processes up to 500 memories synchronously which can time out; update the rebuild_knowledge_graph function to accept a configurable limit query param (e.g., limit: int = Query(500, description="Max memories to process")) and pass it into server.memory_manager.list_memories, and convert the synchronous loop into an asynchronous background job (use FastAPI BackgroundTasks or a queued worker) that enqueues the work calling kg.add_to_graph for each memory; expose progress via a job id and a status endpoint or WebSocket so clients can poll progress instead of waiting for the request to complete, and ensure errors are recorded per-memory (using the existing logger) and aggregated in the job status rather than forcing the HTTP response to wait.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/sessions.py around lines 622 - 626, The title extraction can be simplified and made slightly more robust: after calling provider.generate_text(llm_prompt) (via provider = server.llm_service.get_default_provider(); title = await provider.generate_text(llm_prompt)), normalize the result by ensuring it's a string, trimming surrounding whitespace and both quote characters in one call (e.g., title = str(title).strip().strip('"\'')) and then keep the existing fallback check (if not title: title = "Untitled Session") to cover empty or quote-only responses.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/source_control.py around lines 163 - 164, The bare "except Exception: pass" in source_control.py should not silently swallow errors; replace it with catching specific exceptions if known (e.g., KeyError, ValueError) or at minimum capture the exception as "except Exception as e:" and log it (e.g., logger.exception("Failed in <function_name>:", exc_info=e) or logging.exception(...)); optionally re-raise if the error must propagate. Locate the try/except block around the failing code (the current bare except) and modify it to use specific exception types or "except Exception as e:" plus a logger.exception/logging.exception call instead of pass.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/routes/source_control.py at line 385, The patch string is being silently truncated with a magic number ([:100000]) when constructing the response ("patch": patch_r.stdout[:100000] if patch_r.returncode == 0 else ""); replace this inline slice with a named constant (e.g., PATCH_MAX_BYTES or PATCH_TRUNCATE_LIMIT) and/or add a clear comment explaining why 100000 bytes is chosen, then use that constant in the construction so readers can find and adjust the limit later and the intent is documented; update references around patch_r and the "patch" dict entry in source_control.py accordingly.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/servers/websocket/voice.py around lines 108 - 130, The on_audio callback currently has an untyped/too-generic parameter; update the signature of async def on_audio(chunk: ...) in voice.py to use a concrete type instead of Any (e.g., the ElevenLabs SDK audio chunk type or a local Protocol/TypedDict that exposes audio_base64 and is_final) so linters/typecheckers can validate accesses to chunk.audio_base64 and chunk.is_final; ensure the chosen type is imported or defined in the module and update any related imports or type aliases used by on_audio and the surrounding TTS handling (references: on_audio, chunk.audio_base64, chunk.is_final, _tts_websockets).

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/config_store.py around lines 177 - 185, clear_secret currently deletes the DB record before removing the secret which can leave orphaned secrets on partial failure; change the logic in clear_secret to call secret_store.delete(secret_name) first (using config_key_to_secret_name(key)), handle a "not found" case as non-fatal, and only after successful deletion remove the config row via self.db.execute("DELETE FROM config_store WHERE key = ?", (key,)); ideally perform the DB delete inside a transaction or commit after secret deletion so that if secret_store.delete raises any error (e.g., encryption issue) the DB row is not removed—log failures from secret_store.delete and re-raise or return an error as appropriate.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/projects.py around lines 159 - 165, The INSERT OR IGNORE into the projects table is executed directly via self.db.execute; wrap this database write (and any immediately related read) in a connection transaction context by using the connection as a context manager (e.g., with self.db: self.db.execute(...)) so the insert is performed within a transaction and committed/rolled back atomically; update the code around the INSERT OR IGNORE (the block that calls self.db.execute for projects insertion) to use the context manager and keep any subsequent read that expects the row inside the same with self.db: scope if needed.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/storage/projects.py around lines 171 - 180, The fallback in the upsert path currently logs a warning and returns a locally-constructed Project when self.get(project_id) returns None, producing a non-persisted phantom object; instead modify the upsert/insert logic (the block that calls self.get(project_id) and currently returns Project(...)) to raise an explicit exception (e.g., ProjectNotFoundError or RuntimeError) with context including project_id and name, so callers cannot assume persistence; keep the logger.warning for diagnostic purposes but do not return a fake Project—raise the error to surface the inconsistent DB state and force callers to handle it.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/sync/memories.py around lines 204 - 226, The current import routine reads memories_file twice and calls self.memory_manager.list_memories(limit=10000) to get db_count, which is inefficient for large datasets; change it to stream the JSONL once and/or compute file_count while preparing batches for_import_memories_sync (avoid a separate full read), and replace the full-memory load in memory_manager.list_memories with a lightweight count query or an existing count method (e.g., implement or call memory_manager.count_memories or a direct SELECT COUNT(*) via self.db.fetchone) to obtain db_count without loading all records; update the logic around memories_file, _import_memories_sync, and memory_manager.list_memories to use these streaming and counting approaches so the file is not read twice and the DB is not fully materialized.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/voice/stt.py around lines 80 - 85, The MIME-type check for WAV only matches "audio/wav", causing valid "audio/x-wav" to be treated as non-WAV; update the condition that sets min_size (the mime_type.startswith("audio/wav") check) to also recognize "audio/x-wav" and ignore any MIME params—e.g., normalize mime_type = mime_type.split[";",1](0).strip() then use mime_type in ("audio/wav","audio/x-wav") or mime_type.startswith("audio/wav") or mime_type.startswith("audio/x-wav") before assigning min_size and performing the length check.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/voice/tts.py around lines 153 - 172, send_text currently drops text silently when not connected (checks self._connected and self._ws) — change it to return a success boolean (or raise a ConnectionError) so callers can detect dropped text: update send_text signature/type hint to return bool, when not connected log at warning and return False, otherwise perform the send and return True; ensure callers of send_text (search for send_text usages) handle the boolean result (or catch the ConnectionError) and adjust any tests/types accordingly.

- Verify each finding against the current code and only fix it if needed.

In @src/gobby/workflows/engine.py around lines 163 - 169, The current except block in the template rendering loop sets state.variables[variable] = None on failure, which can break downstream logic; instead, either (a) skip assigning the variable when rendering fails so existing values remain unchanged, or (b) assign a clear sentinel/raw value (e.g., the original template string or a constant like "<TEMPLATE_RENDER_ERROR>") so consumers can detect the failure; update the except handling around the render call that logs via logger.warning (including state.session_id and handler_type) to implement one of these two options and ensure downstream code can detect and handle the sentinel if chosen.

- Verify each finding against the current code and only fix it if needed.

In @tests/memory/test_manager.py at line 123, Replace the bare call uuid.UUID(memory.id) used to validate the ID in the test with an explicit assertion that provides a clear failure message (e.g., assert is_valid_uuid, "memory.id is not a valid UUID: {memory.id}") or wrap the uuid.UUID(...) call in a try/except and raise an AssertionError with a descriptive message; update the check located where uuid.UUID(memory.id) is invoked in tests/memory/test_manager.py so failures clearly state the UUID validation intent.

- Verify each finding against the current code and only fix it if needed.

In @web/package.json at line 12, The postinstall script in package.json uses the Unix-only "cp" which will fail on Windows; update the "postinstall" entry to use a cross-platform copy solution (e.g., install devDependency "shx" and use "shx cp ...", or use "cpy-cli"/"cpx2", or replace with a small Node.js script) and ensure the target directory exists before copying (create "public/" if missing or use the copy tool's mkdir option). Modify package.json's "postinstall" and add the chosen devDependency so npm install works across platforms.

- Verify each finding against the current code and only fix it if needed.

In @web/src/App.tsx around lines 68 - 69, Replace the inline fetch that builds baseUrl and calls fetch(`${baseUrl}/sessions/${currentSession.id}/synthesize-title`, { method: 'POST' }) with the shared API client used elsewhere (e.g., apiClient.post or api.post) so it uses the centralized base URL, headers, interceptors, and error handling; locate the call in App.tsx that references import.meta.env.VITE_API_BASE_URL, baseUrl, and currentSession.id and change it to call the common API utility for POST to `/sessions/${currentSession.id}/synthesize-title`, and ensure you propagate/handle errors and response parsing consistent with other calls.

- Verify each finding against the current code and only fix it if needed.

In @web/src/App.tsx around lines 47 - 79, The effect depends on a non-stable sessionsHook reference which can trigger spurious runs; fix by extracting stable values before the useEffect (e.g., const { sessions, refresh } = sessionsHook or memoize sessionsHook) and update the effect to use sessions and refresh instead of sessionsHook, then change the dependency array to [isStreaming, conversationId, sessions, refresh]; keep the existing refs (wasStreamingRef, titleSynthesisCountRef) and the same synthesize logic inside useEffect but reference sessions and refresh for lookup and refresh calls.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/GitHubPage.tsx around lines 95 - 148, The current render in GitHubPage builds all tab components inside an object literal ({ overview: <SourceControlOverview ... />, branches: <BranchesView ... />, ... }[activeTab]) so SourceControlOverview, BranchesView, PullRequestsView, WorktreesView, ClonesView and CICDView are all instantiated every render; change the rendering to only instantiate the active component (e.g., use a switch(activeTab) or if/else or a small renderActiveTab() function that returns a single JSX node) so only the matched component is created and passed props (keep using sc.status, sc.prs, sc.worktrees, sc.branches, sc.ciRuns and methods like sc.fetchCommits, sc.fetchDiff, sc.fetchPrs, sc.fetchPrDetail, sc.deleteWorktree, sc.syncWorktree, sc.cleanupWorktrees, sc.deleteClone, sc.syncClone), ensuring the activeTab state controls which component is returned.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/MemoryGraph.tsx around lines 109 - 117, The 500ms timeout and 400ms zoom duration are magic numbers; extract them as named constants (e.g., const ZOOM_DELAY_MS = 500 and const ZOOM_ANIMATION_MS = 400) and use those constants in the useEffect where hasZoomedRef is set and fgRef.current?.zoomToFit(ZOOM_ANIMATION_MS, 40) is called, and replace the setTimeout delay with ZOOM_DELAY_MS; update any references to the numeric values (including the fgRef.zoomToFit call signature) and ensure names are defined near the top of the MemoryGraph component for clarity.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ChatInput.tsx around lines 328 - 337, The textarea currently rendered in ChatInput (refs: textareaRef, value=input, onChange -> handleChange, onKeyDown -> handleKeyDown, props disabled/isStreaming/voiceMode) has no accessible name; add an accessible label by either adding an id to the textarea and rendering a visually-hidden <label htmlFor="..."> (or visible label) or by adding an explanatory aria-label/aria-labelledby that changes with state (e.g., "Message input", "Message input — voice mode on", or "Message input — connecting...") so screen readers receive context; ensure the chosen attribute is updated alongside disabled/isStreaming/voiceMode states.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ChatInput.tsx around lines 99 - 113, handleFilesSelected currently uses FileReader.readAsDataURL without any onerror handling, so failures are silently ignored; add a reader.onerror handler inside handleFilesSelected that logs or surfaces the error (e.g., via console.error or a user-facing notification) and ensures the file is not queued. If a previewUrl was created with URL.createObjectURL, revoke it on error using URL.revokeObjectURL(previewUrl). Keep the existing reader.onload path intact and only call setQueuedFiles on success; reference the handleFilesSelected callback, reader, setQueuedFiles, URL.createObjectURL and reader.readAsDataURL when making the change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/Markdown.tsx around lines 18 - 27, The current key `${id}-${i}` on MemoizedBlock causes unstable reconciliation when blocks shift; change to a stable content-based key by hashing each block string (the entries in blocks produced by useMemo which uses marked.lexer(content)) or by using the block text itself if safe; update the map to use that hash (or block) as the key instead of the index and ensure the hashing logic is implemented near the blocks creation so MemoizedBlock receives a stable key tied to block content rather than its index.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/MessageItem.tsx around lines 36 - 38, The assistant avatar currently gets hidden on load error in MessageItem.tsx (the img element rendered when message.role === 'assistant'); instead, change the onError handler on that img so it replaces the broken src with a fallback image (e.g., '/fallback-icon.png') and ensure it only runs once to avoid infinite loops (check currentTarget.src before replacing or use a flag). Keep the alt and class names unchanged so the visual indicator remains consistent when the primary logo fails to load.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ToolCallCard.tsx around lines 287 - 299, Update the option buttons in ToolCallCard.tsx to include accessible attributes: add aria-pressed={isSelected} to communicate toggle state, set a descriptive aria-label using the option label (e.g., `aria-label={`Select ${opt.label}`}`) so screen readers can identify the action, and also include aria-disabled={submitted} alongside the existing disabled prop to expose that state to assistive tech; adjust the JSX for the button that calls handleOptionClick and references isSelected, opt.label, opt.description, and submitted.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ToolCallCard.tsx around lines 333 - 365, The StatusIcon component returns decorative SVGs without accessible names; update the StatusIcon function so each returned SVG includes an accessible name (either add role="img" plus a title element or add an aria-label) that describes the status (e.g., "calling", "completed", "error", "pending approval"); ensure unique or consistent labeling for each branch (the SVGs inside StatusIcon for statuses 'calling', 'completed', 'error', 'pending_approval') and apply the same approach to any other status SVGs elsewhere so screen readers can announce the icon meaning.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactContext.tsx around lines 9 - 18, The fallback object returned by useArtifactContext (when ArtifactContext is missing) is recreated each call causing dependent components to rerender; change useArtifactContext to memoize a stable no-op fallback (e.g., store a single fallback object via useMemo or a module-level constant and return that instead) so openCodeAsArtifact is referentially stable when no provider exists; update the function that currently returns { openCodeAsArtifact: () => {} } to return the memoized/stableFallback object.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactImageView.tsx around lines 20 - 29, In ArtifactImageView, the current validation using /^(https?:|data:image\/|\/|\.\/)/ on the content prop is too permissive and allows e.g. "./" relative paths and may miss protocol-relative URLs; update the validation logic around the content variable used in the img src check to either (a) use a stricter regex such as /^(https?:\/\/|\/\/|data:image\/[a-z]+;base64,)/ to explicitly allow absolute HTTP(S), protocol-relative, and base64 data URIs, or (b) implement an explicit whitelist/sanitizer for allowed path formats before rendering in the <img> to prevent unexpected local path access; change only the test expression in the ArtifactImageView render branch that decides whether to show the <img> or the "Invalid image source" fallback.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactPanel.tsx around lines 32 - 42, The download anchor created in handleDownload (ArtifactPanel.tsx) is never appended to the DOM, which can prevent downloads in some browsers; modify handleDownload to append the created <a> element to document.body before calling a.click(), then remove the anchor from the DOM after triggering the click (and still call URL.revokeObjectURL(url) afterward) so the download works cross-browser and cleans up resources.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactSheetView.tsx at line 39, ArtifactSheetView currently does const headers = rows[0] which will be undefined when rows is empty; after moving the hooks you must add a guard before using headers (or compute a safe default) and perform an early return when rows.length === 0 after hooks run but before any rendering that reads headers/rows. Update the component (ArtifactSheetView) to check rows.length and either return null/placeholder or set headers = []/undefined safely, and ensure any downstream use of headers (e.g., table rendering) handles that case.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ArtifactSheetView.tsx around lines 32 - 50, Move all React hook calls so they are always executed in the same order: keep the useMemo that computes rows and the useState calls (sortCol, setSortCol, sortAsc, setSortAsc) at the top of ArtifactSheetView before any early return, then compute headers, data and sorted after those hooks; place the early return (rows.length === 0) after the hooks but before using headers/data in the UI. Also make the headers/data computation robust for empty rows (e.g., treat headers = rows[0] || [] and data = rows.slice(1)) so the memoized sorted (useMemo) can still run safely when rows is empty.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/artifacts/ResizeHandle.tsx around lines 16 - 43, The drag handler can close over a stale onResize; create a ref (e.g., onResizeRef) and update it whenever onResize changes, then inside startDrag/handleMove call onResizeRef.current(newWidth) instead of onResize so the latest callback is used mid-drag, and remove onResize from the startDrag dependency if you choose to stabilize it (or keep it but ensure only the ref is used inside handleMove); reference the startDrag, handleMove, isDragging, and onResize symbols when making this change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/chat/ui/ScrollArea.tsx around lines 11 - 17, The ScrollArea component uses WebKit-only scrollbar pseudo-elements (seen in the className passed to cn) so Firefox shows default scrollbars; update ScrollArea.tsx to add cross-browser scrollbar styles by either enabling the tailwind-scrollbar plugin and adding its utility classes (e.g., scrollbar, scrollbar-thumb, scrollbar-track) to the cn call or by adding standard CSS scrollbar properties (scrollbar-color, scrollbar-width) in a CSS/utility file and referencing those classes in the same className list so Firefox users get consistent styling.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/dashboard/SystemHealthCard.tsx around lines 17 - 49, SystemHealthCard accesses background_tasks.active without a null check which can throw when background_tasks is undefined; update the JSX in SystemHealthCard to safely handle missing background_tasks (similar to the existing checks for process) by rendering background_tasks.active only when background_tasks is truthy and falling back to a placeholder like '—' otherwise (e.g., conditionally render background_tasks.active or '—' where background_tasks.active is currently used).

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/BranchDetail.tsx around lines 35 - 48, handleViewDiff currently performs an async fetchDiff without any loading state, causing no visual feedback and allowing repeated clicks; add a local boolean state (e.g., isFetchingDiff) and set it true before calling fetchDiff and false in a finally block, update the UI controls that trigger handleViewDiff (the view-diff button/toggle) to be disabled while isFetchingDiff is true and render a small spinner or "Loading..." indicator next to the control while fetching; make sure to still call setDiff(result) and setShowDiff(true) on success and leave existing error handling (console.error) intact so behavior of fetchDiff, setDiff, and setShowDiff remains unchanged.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/BranchDetail.tsx around lines 19 - 33, Add proper error state handling and an unmount/cancellation guard inside the existing useEffect: introduce an error state (e.g., error, setError) and set it in the .catch block instead of only logging, clear it at the start of the effect, and ensure the UI renders this error when present; also add a mounted/aborted flag inside useEffect (e.g., let mounted = true; return () => { mounted = false }) and only call setLoading, setDiff, setShowDiff, setCommits, or setError if mounted is true to avoid stale closure/unmounted updates; finally, document that fetchCommits should be memoized by the parent with useCallback to prevent unnecessary re-fetches when its identity changes.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/BranchesView.tsx around lines 73 - 93, The remote branches table (rendering remoteBranches in BranchesView.tsx) lacks a <thead>, causing semantic and accessibility inconsistency with the local table; add a <thead> above the <tbody> that includes the same column headers used by the local branches table (e.g., Name, Type, <empty/placeholder> columns, Date) and apply the project’s visually-hidden utility class (or an equivalent sr-only CSS class) to the header cells so the headers are available to screen readers but not visually disruptive; ensure this change is applied alongside the existing row rendering logic that uses selectedBranch, setSelectedBranch, and b.last_commit_date.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/ClonesView.tsx around lines 50 - 63, The status counts are recomputed on every render by calling clones.filter(...) inside the map over statuses; to fix, compute a memoized map of status->count using React.useMemo (referencing clones and statuses) and then use that memoized counts map when rendering the buttons (keep usage of statuses, clones, statusFilter, setStatusFilter, and aria-pressed the same); this avoids repeated O(n) filtering per status and ensures counts update when clones or statuses change.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/GitHubUnavailable.tsx around lines 1 - 16, The GitHubUnavailable component lacks an explicit return type; update the function signature for GitHubUnavailable to include a proper JSX return type (e.g., declare it as function GitHubUnavailable(): JSX.Element) so the component's contract is explicit and TypeScript can catch accidental changes—if JSX.Element isn't available, ensure appropriate React types are imported or the project JSX types are enabled.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/PullRequestDetail.tsx around lines 16 - 28, The effect using useEffect with fetchDetail can set stale state when prNumber changes rapidly; modify the effect in PullRequestDetail.tsx to track and ignore out-of-date responses by introducing a local cancelled/active flag or an AbortController, call fetchDetail with the controller if supported, and only call setDetail and setLoading(false) when the response corresponds to the current prNumber (i.e., if !cancelled); ensure cleanup returns a function that flips the flag or aborts the controller so in-flight promises do not update state for older prNumber values (update references to useEffect, fetchDetail, setDetail, setLoading, and prNumber).

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/PullRequestDetail.tsx around lines 22 - 24, Add an error state to the PullRequestDetail component (e.g., const [error, setError] = useState<Error | string | null>(null)), update the fetchDetail catch handler to setError(e) instead of only console.error, and clear/set the error appropriately when retrying or starting a new fetch; finally render a visible error UI (message and optional retry button) inside PullRequestDetail when error is non-null so users see the failure instead of only a console log.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/SourceControlOverview.tsx around lines 18 - 24, The effect inside useEffect referencing fetchCommits can cause infinite re-renders if fetchCommits is not stable; update the component to either require a memoized fetchCommits (document that parent must wrap fetchCommits in useCallback) or make fetchCommits stable locally by storing it in a ref and calling ref.current(branch, 5) inside the effect (keep setRecentCommits and status?.current_branch as dependencies). Target the useEffect block and the fetchCommits usage so the effect no longer re-runs on every render when the function reference changes.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/WorktreesView.tsx around lines 25 - 52, The handlers handleDelete, handleSync and handleCleanup swallow errors because they use try/finally without catching results or exceptions; update each to catch errors and surface failure to the user (e.g., via a toast/notification or by setting an error state) and also handle the parent's boolean/return value from onDelete/onSync/onCleanup to show success/failure messages; ensure you still clear loading and confirmation states with setActionLoading, setConfirmDelete and setConfirmCleanup in both success and error paths so UI remains consistent.

- Verify each finding against the current code and only fix it if needed.

In @web/src/components/source-control/WorktreesView.tsx around lines 64 - 76, The rendering currently calls worktrees.filter(...) for each STATUSES entry causing O(N*M) work on every render; replace that by computing a status -> count map once (e.g. in a useMemo keyed on worktrees) and then reference the precomputed counts when rendering the chips (use STATUSES and statusFilter as before and keep setStatusFilter usage unchanged); implement the memoized computation by iterating once (reduce or loop) over worktrees to populate counts and use those counts in the map to avoid repeated filtering.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useDashboard.ts around lines 57 - 61, The effect creating the interval re-runs when the callbacks change (refresh and fetchStatus), causing a potential interval leak; make the interval use a stable callback instead — e.g., store the latest fetchStatus in a ref and call ref.current from inside the interval (or memoize fetchStatus with useCallback so refresh is stable), then change the useEffect dependency array to only include truly stable values (or use an empty array if using the ref approach); update references to the functions named refresh and fetchStatus in useEffect so the interval is created once and cleared correctly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSourceControl.ts around lines 401 - 417, The polling effects for local and GitHub refs currently run only on mount, so when projectId changes the refs update but polling and immediate fetches do not; update the two useEffect blocks that set up polling (the ones using fetchLocalRef.current, localPollRef, LOCAL_POLL_MS and fetchGitHubRef.current, githubPollRef, GITHUB_POLL_MS) to depend on projectId (add projectId to their dependency arrays), and inside each effect clear any existing interval (using clearInterval on localPollRef/githubPollRef), call the corresponding fetch function immediately (fetchLocalRef.current()/fetchGitHubRef.current()), then recreate the interval and return a cleanup that clears it; this ensures immediate refetch and interval reset whenever projectId changes.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSourceControl.ts around lines 274 - 291, The deleteWorktree function currently calls fetchWorktrees() and fetchStatus() fire-and-forget which can produce race conditions and stale UI; update deleteWorktree to await the refreshes (either await fetchWorktrees(); await fetchStatus(); or use await Promise.all([fetchWorktrees(), fetchStatus()])) and handle any errors so the function only returns true once refreshes complete, referencing the deleteWorktree, fetchWorktrees, and fetchStatus symbols so the UI state is reliably updated after the DELETE.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useSourceControl.ts around lines 99 - 101, getBaseUrl currently always returns an empty string; replace it with a constant to improve clarity and avoid unnecessary function calls: add a top-level constant named BASE_URL = '' (or the intended base value) and update all usages of getBaseUrl() to reference BASE_URL; remove the getBaseUrl function definition to eliminate dead code and ensure imports/exports (if any) are adjusted accordingly.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useTerminal.ts around lines 64 - 84, Extract the inline showModes array into a shared constant (e.g., SHOW_MODES) so both the fetch('/api/agents/running') block and the usage at line 119 reference the same array; update the filter in the fetch callback that calls setAgents (and the other location that checks modes) to import/use SHOW_MODES instead of recreating ['embedded','tmux','terminal'] locally, keeping the existing filter/map logic intact.

- Verify each finding against the current code and only fix it if needed.

In @web/src/hooks/useVoice.ts around lines 134 - 152, The current useEffect polls playbackQueueRef.current.isPlaying every 200ms to toggle isSpeaking and start/pause vadRef, which is inefficient; instead subscribe to the AudioPlaybackQueue end/start events (e.g., add an onended/onplay or equivalent listener on playbackQueueRef.current or its AudioPlaybackQueue instance) inside the hook: replace the setInterval logic in useEffect with event listeners that call setIsSpeaking, setIsListening and vadRef.current.start()/pause() accordingly, and cleanup the listeners on unmount; reference playbackQueueRef, vadRef, setIsSpeaking and setIsListening when wiring the event handlers.

- Verify each finding against the current code and only fix it if needed.

In @web/src/styles/index.css around lines 12658 - 13573, The .sc-*source-control styles block (e.g., .sc-page, .sc-page__toolbar, .sc-table, .sc-card, .sc-detail-panel, .sc-diff__line, .sc-unavailable, etc.) should be moved into a dedicated stylesheet (e.g., source-control.css): extract all selectors that start with the .sc- prefix from the large CSS blob and paste them into the new file, then remove them from the original index.css; finally update the app's stylesheet imports to include the new source-control stylesheet (or update the build/entry CSS import) so components using .sc-* classes still receive the styles. Ensure you keep comments and any dependent custom properties or variable references intact when moving the rules.

- Verify each finding against the current code and only fix it if needed.

In @web/tailwind.config.ts around lines 1 - 19, The Tailwind config currently exports a plain object and uses corePlugins.preflight (unsupported in Tailwind v4); update the file by adding a type annotation (e.g., export default tailwindConfig as satisfying Config or use "satisfies Config") to get type-safety for the config object (refer to the exported object and the content/colors keys) and remove or migrate corePlugins.preflight: false depending on your target: if you stay on v3 keep corePlugins and add the satisfies Config type, if you target v4 remove corePlugins.preflight and implement base resets via CSS (e.g., @layer base in your CSS entry and add @config "./tailwind.config.ts"; to that entry).
