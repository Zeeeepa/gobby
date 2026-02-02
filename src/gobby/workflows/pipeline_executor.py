"""Pipeline executor for running typed pipeline workflows."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from gobby.workflows.pipeline_state import ExecutionStatus, PipelineExecution, StepStatus

if TYPE_CHECKING:
    from gobby.storage.database import DatabaseProtocol
    from gobby.storage.pipelines import LocalPipelineExecutionManager
    from gobby.workflows.definitions import PipelineDefinition
    from gobby.workflows.templates import TemplateEngine

logger = logging.getLogger(__name__)


class PipelineExecutor:
    """Executor for pipeline workflows with typed data flow between steps.

    Handles:
    - Creating and tracking execution records
    - Iterating through steps in order
    - Building context with inputs and step outputs
    - Executing exec commands, prompts, and nested pipelines
    - Webhook notifications
    """

    def __init__(
        self,
        db: DatabaseProtocol,
        execution_manager: LocalPipelineExecutionManager,
        llm_service: Any,
        template_engine: TemplateEngine | None = None,
        webhook_notifier: Any | None = None,
    ):
        """Initialize the pipeline executor.

        Args:
            db: Database connection for transactions
            execution_manager: Manager for pipeline execution records
            llm_service: LLM service for prompt steps
            template_engine: Optional template engine for variable substitution
            webhook_notifier: Optional notifier for webhook callbacks
        """
        self.db = db
        self.execution_manager = execution_manager
        self.llm_service = llm_service
        self.template_engine = template_engine
        self.webhook_notifier = webhook_notifier

    async def execute(
        self,
        pipeline: PipelineDefinition,
        inputs: dict[str, Any],
        project_id: str,
        execution_id: str | None = None,
        session_id: str | None = None,
    ) -> PipelineExecution:
        """Execute a pipeline workflow.

        Args:
            pipeline: The pipeline definition to execute
            inputs: Input values for the pipeline
            project_id: Project context for the execution
            execution_id: Optional existing execution ID (for resuming)
            session_id: Optional session that triggered the execution

        Returns:
            The completed PipelineExecution record
        """
        # 1. Create or load execution record
        if execution_id:
            execution = self.execution_manager.get_execution(execution_id)
            if not execution:
                raise ValueError(f"Execution {execution_id} not found")
        else:
            execution = self.execution_manager.create_execution(
                pipeline_name=pipeline.name,
                inputs_json=json.dumps(inputs),
                session_id=session_id,
            )

        # 2. Update status to RUNNING
        updated = self.execution_manager.update_execution_status(
            execution_id=execution.id,
            status=ExecutionStatus.RUNNING,
        )
        if updated:
            execution = updated

        # 3. Build execution context
        context: dict[str, Any] = {
            "inputs": inputs,
            "steps": {},  # Will hold step outputs as they complete
        }

        try:
            # 4. Iterate through steps in order
            for step in pipeline.steps:
                step_execution = self.execution_manager.create_step_execution(
                    execution_id=execution.id,
                    step_id=step.id,
                    input_json=json.dumps(context) if context else None,
                )

                # Update step status to RUNNING
                self.execution_manager.update_step_execution(
                    step_execution_id=step_execution.id,
                    status=StepStatus.RUNNING,
                )

                # Execute the step
                step_output = await self._execute_step(step, context, project_id)

                # Store step output in context for subsequent steps
                context["steps"][step.id] = {"output": step_output}

                # Update step with output and mark completed
                self.execution_manager.update_step_execution(
                    step_execution_id=step_execution.id,
                    status=StepStatus.COMPLETED,
                    output_json=json.dumps(step_output) if step_output else None,
                )

            # 5. Mark execution as completed
            completed = self.execution_manager.update_execution_status(
                execution_id=execution.id,
                status=ExecutionStatus.COMPLETED,
                outputs_json=json.dumps(self._build_outputs(pipeline, context)),
            )
            if completed:
                execution = completed

        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}", exc_info=True)
            failed = self.execution_manager.update_execution_status(
                execution_id=execution.id,
                status=ExecutionStatus.FAILED,
            )
            if failed:
                execution = failed
            raise

        return execution

    async def _execute_step(
        self,
        step: Any,  # PipelineStep
        context: dict[str, Any],
        project_id: str,
    ) -> Any:
        """Execute a single pipeline step.

        Args:
            step: The step to execute
            context: Current execution context with inputs and step outputs
            project_id: Project context

        Returns:
            The step's output value
        """
        # Render any template variables in the step
        rendered_step = self._render_step(step, context)

        if step.exec:
            # Execute shell command
            return await self._execute_exec_step(rendered_step.exec, context)
        elif step.prompt:
            # Execute LLM prompt
            return await self._execute_prompt_step(rendered_step.prompt, context)
        elif step.invoke_pipeline:
            # Execute nested pipeline
            return await self._execute_nested_pipeline(
                rendered_step.invoke_pipeline, context, project_id
            )
        else:
            logger.warning(f"Step {step.id} has no action defined")
            return None

    def _render_step(self, step: Any, context: dict[str, Any]) -> Any:
        """Render template variables in step fields.

        Args:
            step: The step to render
            context: Context with variables for substitution

        Returns:
            Step with rendered fields
        """
        if not self.template_engine:
            return step

        # For now, return step as-is - template rendering will be added later
        return step

    async def _execute_exec_step(self, command: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a shell command step.

        Args:
            command: The command to execute
            context: Execution context

        Returns:
            Dict with stdout, stderr, exit_code
        """
        # Placeholder - actual subprocess execution will be added
        logger.info(f"Executing command: {command}")
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
        }

    async def _execute_prompt_step(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute an LLM prompt step.

        Args:
            prompt: The prompt to send to the LLM
            context: Execution context

        Returns:
            Dict with response text
        """
        logger.info("Executing prompt step")
        response = await self.llm_service.generate(prompt)
        return {
            "response": response,
        }

    async def _execute_nested_pipeline(
        self,
        pipeline_name: str,
        context: dict[str, Any],
        project_id: str,
    ) -> dict[str, Any]:
        """Execute a nested pipeline.

        Args:
            pipeline_name: Name of the pipeline to invoke
            context: Execution context (used as inputs)
            project_id: Project context

        Returns:
            Dict with nested pipeline outputs
        """
        # Placeholder - nested pipeline execution will be added
        logger.info(f"Invoking nested pipeline: {pipeline_name}")
        return {
            "pipeline": pipeline_name,
            "status": "not_implemented",
        }

    def _build_outputs(self, pipeline: Any, context: dict[str, Any]) -> dict[str, Any]:
        """Build pipeline outputs from context.

        Args:
            pipeline: The pipeline definition
            context: Final execution context

        Returns:
            Dict of output name -> value
        """
        outputs: dict[str, Any] = {}

        for name, expr in pipeline.outputs.items():
            if isinstance(expr, str) and expr.startswith("$"):
                # Resolve $step.output reference
                value = self._resolve_reference(expr, context)
                outputs[name] = value
            else:
                outputs[name] = expr

        return outputs

    def _resolve_reference(self, ref: str, context: dict[str, Any]) -> Any:
        """Resolve a $step.output reference from context.

        Args:
            ref: Reference string like "$step1.output" or "$step1.output.field"
            context: Execution context

        Returns:
            The resolved value
        """
        import re

        # Parse reference: $step_id.output[.field]
        match = re.match(r"\$([a-zA-Z_][a-zA-Z0-9_]*)\.output(?:\.(.+))?", ref)
        if not match:
            return ref

        step_id = match.group(1)
        field_path = match.group(2)

        # Get step output from context
        step_data = context.get("steps", {}).get(step_id, {})
        output = step_data.get("output")

        if field_path and isinstance(output, dict):
            # Navigate nested field path
            for part in field_path.split("."):
                if isinstance(output, dict):
                    output = output.get(part)
                else:
                    break

        return output
