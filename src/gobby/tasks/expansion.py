"""
Task expansion module.

Handles breaking down high-level tasks into smaller, actionable subtasks
using LLM providers with structured JSON output.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from gobby.config.app import ProjectVerificationConfig, TaskExpansionConfig
from gobby.llm import LLMService
from gobby.storage.task_dependencies import TaskDependencyManager
from gobby.storage.tasks import LocalTaskManager, Task
from gobby.tasks.context import ExpansionContext, ExpansionContextGatherer
from gobby.tasks.criteria import PatternCriteriaInjector
from gobby.tasks.prompts.expand import ExpansionPromptBuilder
from gobby.utils.json_helpers import extract_json_from_text
from gobby.utils.project_context import get_verification_config

logger = logging.getLogger(__name__)


@dataclass
class SubtaskSpec:
    """Parsed subtask specification from LLM output."""

    title: str
    description: str | None = None
    priority: int = 2
    task_type: str = "task"
    test_strategy: str | None = None
    depends_on: list[int] | None = None


class TaskExpander:
    """Expands tasks into subtasks using LLM and context."""

    def __init__(
        self,
        config: TaskExpansionConfig,
        llm_service: LLMService,
        task_manager: LocalTaskManager,
        mcp_manager: Any | None = None,
        verification_config: ProjectVerificationConfig | None = None,
    ):
        self.config = config
        self.llm_service = llm_service
        self.task_manager = task_manager
        self.mcp_manager = mcp_manager
        self.context_gatherer = ExpansionContextGatherer(
            task_manager=task_manager,
            llm_service=llm_service,
            config=config,
            mcp_manager=mcp_manager,
        )
        self.prompt_builder = ExpansionPromptBuilder(config)

        # Initialize pattern criteria injector
        # Try to get verification config from project if not provided
        if verification_config is None:
            verification_config = get_verification_config()
        self.criteria_injector = PatternCriteriaInjector(
            pattern_config=config.pattern_criteria,
            verification_config=verification_config,
        )

    async def expand_task(
        self,
        task_id: str,
        title: str,
        description: str | None = None,
        context: str | None = None,
        enable_web_research: bool = False,
        enable_code_context: bool = True,
        tdd_mode: bool | None = None,
    ) -> dict[str, Any]:
        """
        Expand a task into subtasks using structured JSON output.

        The LLM returns a JSON object with subtask specifications, which are
        then parsed and created as tasks with proper dependency wiring.

        Args:
            task_id: ID of the task to expand
            title: Task title
            description: Task description
            context: Additional context for expansion
            enable_web_research: Whether to enable web research (default: False)
            enable_code_context: Whether to enable code context gathering (default: True)
            tdd_mode: Override TDD mode setting. If None, uses config default.

        Returns:
            Dictionary with:
            - subtask_ids: List of created subtask IDs
            - subtask_count: Number of subtasks created
            - raw_response: The raw LLM response (for debugging)
        """
        if not self.config.enabled:
            logger.info("Task expansion disabled, skipping")
            return {
                "subtask_ids": [],
                "subtask_count": 0,
                "raw_response": "Expansion disabled",
            }

        logger.info(f"Expanding task {task_id}: {title}")

        # Apply overall timeout for entire expansion
        timeout_seconds = self.config.timeout
        try:
            async with asyncio.timeout(timeout_seconds):
                return await self._expand_task_impl(
                    task_id=task_id,
                    title=title,
                    description=description,
                    context=context,
                    enable_web_research=enable_web_research,
                    enable_code_context=enable_code_context,
                    tdd_mode=tdd_mode,
                )
        except TimeoutError:
            error_msg = (
                f"Task expansion timed out after {timeout_seconds} seconds. "
                f"Consider increasing task_expansion.timeout in config or simplifying the task."
            )
            logger.error(f"Expansion timeout for {task_id}: {error_msg}")
            return {
                "error": error_msg,
                "subtask_ids": [],
                "subtask_count": 0,
                "timeout": True,
            }

    async def _expand_task_impl(
        self,
        task_id: str,
        title: str,
        description: str | None = None,
        context: str | None = None,
        enable_web_research: bool = False,
        enable_code_context: bool = True,
        tdd_mode: bool | None = None,
    ) -> dict[str, Any]:
        """Internal implementation of expand_task (called within timeout context)."""
        # Gather enhanced context
        task_obj = self.task_manager.get_task(task_id)
        if not task_obj:
            logger.warning(
                f"Task {task_id} not found for context gathering, using basic info"
            )
            task_obj = Task(
                id=task_id,
                project_id="unknown",
                title=title,
                status="open",
                priority=2,
                task_type="task",
                created_at="",
                updated_at="",
                description=description,
            )

        expansion_ctx = await self.context_gatherer.gather_context(
            task_obj,
            enable_web_research=enable_web_research,
            enable_code_context=enable_code_context,
        )

        # Inject pattern-specific criteria based on task labels and description
        pattern_criteria = self.criteria_injector.inject(
            task=task_obj,
            context=expansion_ctx,
        )

        # Combine user context with pattern criteria if detected
        combined_instructions = context or ""
        if pattern_criteria:
            logger.info(
                f"Detected patterns for {task_id}, adding pattern-specific criteria"
            )
            if combined_instructions:
                combined_instructions += f"\n\n{pattern_criteria}"
            else:
                combined_instructions = pattern_criteria

        # Build prompt using builder
        prompt = self.prompt_builder.build_user_prompt(
            task=task_obj,
            context=expansion_ctx,
            user_instructions=combined_instructions if combined_instructions else None,
        )

        try:
            # Get provider and generate text response
            provider = self.llm_service.get_provider(self.config.provider)

            # Disable TDD mode for epics - epics are container tasks whose
            # closing condition is "all children closed", not test verification.
            # Use passed tdd_mode if provided, otherwise fall back to config.
            effective_tdd = tdd_mode if tdd_mode is not None else self.config.tdd_mode
            tdd_for_prompt = effective_tdd and task_obj.task_type != "epic"

            response = await provider.generate_text(
                prompt=prompt,
                system_prompt=self.prompt_builder.get_system_prompt(
                    tdd_mode=tdd_for_prompt
                ),
                model=self.config.model,
            )

            logger.debug(f"LLM response (first 500 chars): {response[:500]}")

            # Parse JSON from response
            subtask_specs = self._parse_subtasks(response)
            logger.debug(f"Parsed {len(subtask_specs)} subtask specs")

            if not subtask_specs:
                logger.warning(f"No subtasks parsed from response for {task_id}")
                return {
                    "subtask_ids": [],
                    "subtask_count": 0,
                    "raw_response": response,
                    "error": "No subtasks found in response",
                }

            # Create tasks with dependency wiring and precise criteria
            subtask_ids = await self._create_subtasks(
                parent_task_id=task_id,
                project_id=task_obj.project_id,
                subtask_specs=subtask_specs,
                expansion_context=expansion_ctx,
                parent_labels=task_obj.labels or [],
                tdd_mode=tdd_for_prompt,
            )

            # Save expansion context to the parent task for audit/reuse
            self._save_expansion_context(task_id, expansion_ctx)

            logger.info(
                f"Expansion complete for {task_id}: created {len(subtask_ids)} subtasks"
            )

            return {
                "subtask_ids": subtask_ids,
                "subtask_count": len(subtask_ids),
                "raw_response": response,
            }

        except Exception as e:
            error_msg = str(e) or f"{type(e).__name__}: (no message)"
            logger.error(f"Failed to expand task {task_id}: {error_msg}", exc_info=True)
            return {"error": error_msg, "subtask_ids": [], "subtask_count": 0}

    def _parse_subtasks(self, response: str) -> list[SubtaskSpec]:
        """
        Parse subtask specifications from LLM JSON response.

        Args:
            response: Raw LLM response text (should be JSON)

        Returns:
            List of SubtaskSpec objects parsed from the response
        """
        # Try to extract JSON from the response
        json_str = self._extract_json(response)
        if not json_str:
            logger.warning("No JSON found in response")
            return []

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return []

        # Extract subtasks array
        subtasks_data = data.get("subtasks", [])
        if not isinstance(subtasks_data, list):
            logger.warning(
                f"Expected 'subtasks' to be a list, got {type(subtasks_data)}"
            )
            return []

        # Parse each subtask
        subtask_specs = []
        for i, item in enumerate(subtasks_data):
            if not isinstance(item, dict):
                logger.warning(f"Subtask {i} is not a dict, skipping")
                continue

            if "title" not in item:
                logger.warning(f"Subtask {i} missing title, skipping")
                continue

            spec = SubtaskSpec(
                title=item["title"],
                description=item.get("description"),
                priority=item.get("priority", 2),
                task_type=item.get("task_type", "task"),
                test_strategy=item.get("test_strategy"),
                depends_on=item.get("depends_on"),
            )
            subtask_specs.append(spec)

        return subtask_specs

    def _extract_json(self, text: str) -> str | None:
        """Extract JSON from text. Delegates to shared utility."""
        return extract_json_from_text(text)

    async def _create_subtasks(
        self,
        parent_task_id: str,
        project_id: str,
        subtask_specs: list[SubtaskSpec],
        expansion_context: ExpansionContext | None = None,
        parent_labels: list[str] | None = None,
        tdd_mode: bool = False,
    ) -> list[str]:
        """
        Create tasks from parsed subtask specifications.

        Handles dependency wiring by mapping depends_on indices to task IDs.
        Generates precise validation criteria using expansion context.
        Implements TDD fallback: converts single tasks to triplets if tests are missing.

        Args:
            parent_task_id: ID of the parent task
            project_id: Project ID for the new tasks
            subtask_specs: List of parsed subtask specifications
            expansion_context: Context gathered during expansion (for criteria generation)
            parent_labels: Labels from the parent task (for pattern detection)
            tdd_mode: Whether TDD mode is enabled

        Returns:
            List of created task IDs
        """
        created_ids: list[str] = []
        dep_manager = TaskDependencyManager(self.task_manager.db)

        # Map subtask_spec index to the "final" task ID (Refactor or single task)
        # This ensures dependents waiting on spec[i] wait on the completion of the entire triplet
        spec_index_to_id: dict[int, str] = {}

        # Track overall created index for depends_on calculation within created_ids list
        # We can't use simple indexing anymore because 1 spec might = 3 tasks

        for i, spec in enumerate(subtask_specs):
            # Check TDD fallback:
            # If TDD mode is on, and this is a coding task, and it's not a test,
            # and it doesn't depend on a test... expand to triplet.
            is_test = "test" in spec.title.lower() or spec.title.lower().startswith(
                "write tests"
            )
            # Assume tasks without type are 'task' (coding) unless specified otherwise
            is_coding = spec.task_type in ("task", "feature", "bug", "chore")

            has_test_dependency = False
            if spec.depends_on:
                for dep_idx in spec.depends_on:
                    if 0 <= dep_idx < len(subtask_specs):
                        dep_title = subtask_specs[dep_idx].title.lower()
                        if "test" in dep_title or dep_title.startswith("write tests"):
                            has_test_dependency = True
                            break

            should_expand_triplet = (
                tdd_mode and is_coding and not is_test and not has_test_dependency
            )

            if should_expand_triplet:
                logger.info(f"Applying TDD fallback (triplet) for: {spec.title}")
                # Create Triplet

                # 1. Test Task (Red)
                test_title = f"Write tests for: {spec.title}"
                test_desc = f"Write failing tests for: {spec.title}\n\nTest strategy: Tests should fail initially (red phase)"

                test_task = self.task_manager.create_task(
                    title=test_title,
                    description=test_desc,
                    project_id=project_id,
                    priority=spec.priority,
                    task_type="task",
                    parent_task_id=parent_task_id,
                )
                created_ids.append(test_task.id)

                # Wire dependencies from original spec to Test task
                if spec.depends_on:
                    for dep_idx in spec.depends_on:
                        if dep_idx in spec_index_to_id:
                            blocker_id = spec_index_to_id[dep_idx]
                            try:
                                dep_manager.add_dependency(
                                    test_task.id, blocker_id, "blocks"
                                )
                            except Exception as e:
                                logger.warning(f"Failed to add dependency: {e}")

                # 2. Impl Task (Green)
                impl_title = f"Implement: {spec.title}"
                impl_desc = spec.description or ""
                if impl_desc:
                    impl_desc += "\n\n"
                impl_desc += "Test strategy: All tests from previous subtask should pass (green phase)"

                # Generate criteria for implementation
                if expansion_context:
                    extra_criteria = await self._generate_precise_criteria(
                        spec=spec,
                        context=expansion_context,
                        parent_labels=parent_labels or [],
                    )
                    if extra_criteria:
                        impl_desc += f"\n\n{extra_criteria}"

                impl_task = self.task_manager.create_task(
                    title=impl_title,
                    description=impl_desc,
                    project_id=project_id,
                    priority=spec.priority,
                    task_type="task",
                    parent_task_id=parent_task_id,
                    test_strategy=spec.test_strategy,
                )
                created_ids.append(impl_task.id)

                # Impl depends on Test
                dep_manager.add_dependency(impl_task.id, test_task.id, "blocks")

                # 3. Refactor Task (Blue)
                refactor_title = f"Refactor: {spec.title}"
                refactor_desc = f"Refactor the implementation of: {spec.title}\n\nTest strategy: All tests must continue to pass after refactoring"

                refactor_task = self.task_manager.create_task(
                    title=refactor_title,
                    description=refactor_desc,
                    project_id=project_id,
                    priority=spec.priority,
                    task_type="task",
                    parent_task_id=parent_task_id,
                )
                created_ids.append(refactor_task.id)

                # Refactor depends on Impl
                dep_manager.add_dependency(refactor_task.id, impl_task.id, "blocks")

                # Map original index to Refactor task
                spec_index_to_id[i] = refactor_task.id

            else:
                # Normal creation
                # Build description with test strategy if present
                description = spec.description or ""
                if spec.test_strategy:
                    if description:
                        description += f"\n\n**Test Strategy:** {spec.test_strategy}"
                    else:
                        description = f"**Test Strategy:** {spec.test_strategy}"

                # Generate precise validation criteria if context is available
                if expansion_context:
                    precise_criteria = await self._generate_precise_criteria(
                        spec=spec,
                        context=expansion_context,
                        parent_labels=parent_labels or [],
                    )
                    if precise_criteria:
                        if description:
                            description += f"\n\n{precise_criteria}"
                        else:
                            description = precise_criteria

                # Create the task
                task = self.task_manager.create_task(
                    title=spec.title,
                    description=description if description else None,
                    project_id=project_id,
                    priority=spec.priority,
                    task_type=spec.task_type,
                    parent_task_id=parent_task_id,
                    test_strategy=spec.test_strategy,
                )

                created_ids.append(task.id)
                logger.debug(f"Created subtask {task.id}: {spec.title}")

                spec_index_to_id[i] = task.id

                # Add dependencies
                if spec.depends_on:
                    for dep_idx in spec.depends_on:
                        if dep_idx in spec_index_to_id:
                            blocker_id = spec_index_to_id[dep_idx]
                            try:
                                dep_manager.add_dependency(
                                    task.id, blocker_id, "blocks"
                                )
                                logger.debug(
                                    f"Added dependency: {task.id} blocked by {blocker_id}"
                                )
                            except Exception as e:
                                logger.warning(f"Failed to add dependency: {e}")
                        else:
                            logger.warning(
                                f"Subtask {i} references invalid or forward index {dep_idx}, skipping dependency"
                            )

        return created_ids

    def _save_expansion_context(
        self,
        task_id: str,
        context: "ExpansionContext",
    ) -> None:
        """
        Save expansion context to the task for audit and reuse.

        Stores web research results and other context in the task's
        expansion_context field as JSON.

        Args:
            task_id: ID of the task to update
            context: The expansion context to save
        """
        try:
            # Build a slim context dict focused on web research
            context_data: dict[str, Any] = {}

            if context.web_research:
                context_data["web_research"] = context.web_research

            if context.agent_findings:
                context_data["agent_findings"] = context.agent_findings

            if context.relevant_files:
                context_data["relevant_files"] = context.relevant_files

            if not context_data:
                logger.debug(f"No expansion context to save for {task_id}")
                return

            # Serialize and update the task
            context_json = json.dumps(context_data)
            self.task_manager.update_task(task_id, expansion_context=context_json)
            logger.info(
                f"Saved expansion context for {task_id} ({len(context_json)} bytes)"
            )

        except Exception as e:
            logger.warning(f"Failed to save expansion context for {task_id}: {e}")

    async def _generate_precise_criteria(
        self,
        spec: SubtaskSpec,
        context: ExpansionContext,
        parent_labels: list[str],
    ) -> str:
        """
        Generate precise validation criteria for a subtask using full expansion context.

        Args:
            spec: The subtask specification
            context: Full expansion context with verification commands, signatures, etc.
            parent_labels: Labels from the parent task (for pattern detection)

        Returns:
            Markdown-formatted validation criteria string
        """
        criteria_parts: list[str] = []

        # 1. Start with pattern-specific criteria from parent labels
        pattern_criteria = self.criteria_injector.inject_for_labels(
            labels=parent_labels,
            extra_placeholders=context.verification_commands,
        )
        if pattern_criteria:
            criteria_parts.append(pattern_criteria)

        # 2. Add base criteria from test_strategy if present
        if spec.test_strategy:
            # Substitute verification commands into test_strategy
            strategy = spec.test_strategy
            if context.verification_commands:
                for name, cmd in context.verification_commands.items():
                    strategy = strategy.replace(f"{{{name}}}", f"`{cmd}`")
            criteria_parts.append(f"## Test Strategy\n\n- [ ] {strategy}")

        # 3. Add file-specific criteria if relevant files are mentioned
        if context.relevant_files and spec.description:
            relevant_for_subtask = [
                f
                for f in context.relevant_files
                if f.lower() in (spec.title + (spec.description or "")).lower()
            ]
            if relevant_for_subtask:
                file_criteria = ["## File Requirements", ""]
                for f in relevant_for_subtask:
                    file_criteria.append(f"- [ ] `{f}` is correctly modified/created")
                criteria_parts.append("\n".join(file_criteria))

        # 4. Add function signature criteria if applicable
        if context.function_signatures and spec.description:
            desc_lower = (spec.description or "").lower()
            for _file_path, signatures in context.function_signatures.items():
                for sig in signatures:
                    if not sig:
                        continue
                    # Extract function name robustly using regex
                    # Handles: "def func_name(", "async def func_name(", "func_name("
                    func_name = None
                    # Try regex patterns first
                    match = re.search(r"(?:async\s+)?def\s+(\w+)", sig)
                    if match:
                        func_name = match.group(1)
                    else:
                        # Fallback: try to get name before first paren
                        match = re.search(r"(\w+)\s*\(", sig)
                        if match:
                            func_name = match.group(1)
                        else:
                            # Last resort: use existing split logic
                            try:
                                func_name = (
                                    sig.split("(")[0].split()[-1]
                                    if "(" in sig
                                    else sig.split()[-1]
                                )
                            except (IndexError, AttributeError):
                                continue

                    if func_name and func_name.lower() in desc_lower:
                        criteria_parts.append(
                            f"## Function Integrity\n\n"
                            f"- [ ] `{func_name}` signature preserved or updated as intended"
                        )
                        break

        # 5. Add verification command criteria
        if context.verification_commands:
            verification_criteria = ["## Verification", ""]
            for name, cmd in context.verification_commands.items():
                if name in ["unit_tests", "type_check", "lint"]:
                    verification_criteria.append(f"- [ ] `{cmd}` passes")
            if len(verification_criteria) > 2:  # Has items beyond header
                criteria_parts.append("\n".join(verification_criteria))

        return "\n\n".join(criteria_parts) if criteria_parts else ""
