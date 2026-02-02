"""Pipeline executor for running typed pipeline workflows."""

from __future__ import annotations

import json
import logging
import secrets
from typing import TYPE_CHECKING, Any

from gobby.workflows.pipeline_state import (
    ApprovalRequired,
    ExecutionStatus,
    PipelineExecution,
    StepStatus,
)
from gobby.workflows.safe_evaluator import SafeExpressionEvaluator

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
        loader: Any | None = None,
    ):
        """Initialize the pipeline executor.

        Args:
            db: Database connection for transactions
            execution_manager: Manager for pipeline execution records
            llm_service: LLM service for prompt steps
            template_engine: Optional template engine for variable substitution
            webhook_notifier: Optional notifier for webhook callbacks
            loader: Optional workflow loader for nested pipelines
        """
        self.db = db
        self.execution_manager = execution_manager
        self.llm_service = llm_service
        self.template_engine = template_engine
        self.webhook_notifier = webhook_notifier
        self.loader = loader

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

                # Check if step should run based on condition
                if not self._should_run_step(step, context):
                    # Skip this step
                    self.execution_manager.update_step_execution(
                        step_execution_id=step_execution.id,
                        status=StepStatus.SKIPPED,
                    )
                    logger.info(f"Skipping step {step.id}: condition not met")
                    continue

                # Update step status to RUNNING
                self.execution_manager.update_step_execution(
                    step_execution_id=step_execution.id,
                    status=StepStatus.RUNNING,
                )

                # Check for approval gate
                await self._check_approval_gate(step, execution, step_execution, pipeline)

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

    def _should_run_step(self, step: Any, context: dict[str, Any]) -> bool:
        """Check if a step should run based on its condition.

        Args:
            step: The step to check
            context: Current execution context

        Returns:
            True if step should run, False if it should be skipped
        """
        # No condition means always run
        if not step.condition:
            return True

        try:
            # Evaluate the condition using safe AST-based evaluator
            # This avoids eval() security risks while supporting common expressions
            eval_context = {
                "inputs": context.get("inputs", {}),
                "steps": context.get("steps", {}),
            }
            # Allow common helper functions for conditions
            allowed_funcs: dict[str, Any] = {
                "len": len,
                "bool": bool,
                "str": str,
                "int": int,
            }
            evaluator = SafeExpressionEvaluator(eval_context, allowed_funcs)
            return evaluator.evaluate(step.condition)
        except Exception as e:
            logger.warning(f"Condition evaluation failed for step {step.id}: {e}")
            # Default to running the step if condition evaluation fails
            return True

    async def _check_approval_gate(
        self,
        step: Any,
        execution: PipelineExecution,
        step_execution: Any,
        pipeline: Any,
    ) -> None:
        """Check if a step has an approval gate and handle it.

        If the step requires approval, this method:
        1. Generates a unique approval token
        2. Updates the step and execution status to WAITING_APPROVAL
        3. Calls the webhook notifier if configured
        4. Raises ApprovalRequired to pause execution

        Args:
            step: The step to check for approval requirement
            execution: The current pipeline execution record
            step_execution: The current step execution record
            pipeline: The pipeline definition (for webhook config)

        Raises:
            ApprovalRequired: If the step requires approval
        """
        # Check if step has approval gate
        if not step.approval or not step.approval.required:
            return

        # Generate unique approval token
        token = secrets.token_urlsafe(24)

        # Get approval message
        message = step.approval.message or f"Approval required for step '{step.id}'"

        # Update step status to WAITING_APPROVAL and store token
        self.execution_manager.update_step_execution(
            step_execution_id=step_execution.id,
            status=StepStatus.WAITING_APPROVAL,
            approval_token=token,
        )

        # Update execution status to WAITING_APPROVAL
        self.execution_manager.update_execution_status(
            execution_id=execution.id,
            status=ExecutionStatus.WAITING_APPROVAL,
            resume_token=token,
        )

        # Call webhook notifier if configured
        if self.webhook_notifier:
            try:
                await self.webhook_notifier.notify_approval_pending(
                    execution_id=execution.id,
                    step_id=step.id,
                    token=token,
                    message=message,
                    pipeline=pipeline,
                )
            except Exception as e:
                logger.warning(f"Failed to send approval webhook: {e}")

        # Raise to pause execution
        raise ApprovalRequired(
            execution_id=execution.id,
            step_id=step.id,
            token=token,
            message=message,
        )

    async def approve(
        self,
        token: str,
        approved_by: str | None = None,
    ) -> PipelineExecution:
        """Approve a pipeline execution that is waiting for approval.

        Args:
            token: The approval token from the ApprovalRequired exception
            approved_by: Optional identifier of the approver

        Returns:
            The updated PipelineExecution record

        Raises:
            ValueError: If the token is invalid or not found
        """
        # Find the step by approval token
        step = self.execution_manager.get_step_by_approval_token(token)
        if not step:
            raise ValueError(f"Invalid approval token: {token}")

        # Mark step as approved
        self.execution_manager.update_step_execution(
            step_execution_id=step.id,
            status=StepStatus.COMPLETED,
            approved_by=approved_by,
        )

        # Get the execution
        execution = self.execution_manager.get_execution(step.execution_id)

        return execution

    async def reject(
        self,
        token: str,
        rejected_by: str | None = None,
    ) -> PipelineExecution:
        """Reject a pipeline execution that is waiting for approval.

        Args:
            token: The approval token from the ApprovalRequired exception
            rejected_by: Optional identifier of the rejector

        Returns:
            The updated PipelineExecution record

        Raises:
            ValueError: If the token is invalid or not found
        """
        # Find the step by approval token
        step = self.execution_manager.get_step_by_approval_token(token)
        if not step:
            raise ValueError(f"Invalid approval token: {token}")

        # Mark step as failed
        self.execution_manager.update_step_execution(
            step_execution_id=step.id,
            status=StepStatus.FAILED,
            rejected_by=rejected_by,
        )

        # Set execution status to CANCELLED
        execution = self.execution_manager.update_execution_status(
            execution_id=step.execution_id,
            status=ExecutionStatus.CANCELLED,
        )

        return execution

    async def _execute_exec_step(self, command: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a shell command step.

        Args:
            command: The command to execute
            context: Execution context

        Returns:
            Dict with stdout, stderr, exit_code
        """
        import asyncio

        logger.info(f"Executing command: {command}")

        try:
            # Run command via shell
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await proc.communicate()

            return {
                "stdout": stdout_bytes.decode("utf-8", errors="replace"),
                "stderr": stderr_bytes.decode("utf-8", errors="replace"),
                "exit_code": proc.returncode or 0,
            }

        except Exception as e:
            logger.error(f"Command execution failed: {e}", exc_info=True)
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": 1,
            }

    async def _execute_prompt_step(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute an LLM prompt step.

        Args:
            prompt: The prompt to send to the LLM
            context: Execution context

        Returns:
            Dict with response text or error
        """
        logger.info("Executing prompt step")

        try:
            response = await self.llm_service.generate(prompt)
            return {
                "response": response,
            }
        except Exception as e:
            logger.error(f"LLM prompt execution failed: {e}", exc_info=True)
            return {
                "response": "",
                "error": str(e),
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
        logger.info(f"Invoking nested pipeline: {pipeline_name}")

        # Check if loader is available
        if not self.loader:
            logger.warning("No loader configured for nested pipeline execution")
            return {
                "pipeline": pipeline_name,
                "error": "No loader configured for nested pipeline execution",
            }

        try:
            # Load the nested pipeline
            nested_pipeline = self.loader.load_pipeline(pipeline_name)

            if not nested_pipeline:
                return {
                    "pipeline": pipeline_name,
                    "error": f"Pipeline '{pipeline_name}' not found",
                }

            # Execute the nested pipeline recursively
            # Use inputs from context as the nested pipeline's inputs
            nested_inputs = context.get("inputs", {})

            result = await self.execute(
                pipeline=nested_pipeline,
                inputs=nested_inputs,
                project_id=project_id,
            )

            return {
                "pipeline": pipeline_name,
                "execution_id": result.id,
                "status": result.status.value,
            }

        except Exception as e:
            logger.error(f"Nested pipeline execution failed: {e}", exc_info=True)
            return {
                "pipeline": pipeline_name,
                "error": str(e),
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
