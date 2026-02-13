"""Pipeline executor for running typed pipeline workflows."""

from __future__ import annotations

import json
import logging
import secrets
import shlex
from typing import TYPE_CHECKING, Any

from gobby.workflows.pipeline_state import (
    ApprovalRequired,
    ExecutionStatus,
    PipelineExecution,
    StepStatus,
)
from gobby.workflows.safe_evaluator import SafeExpressionEvaluator

if TYPE_CHECKING:
    from gobby.agents.tmux.spawner import TmuxSpawner
    from gobby.storage.database import DatabaseProtocol
    from gobby.storage.pipelines import LocalPipelineExecutionManager
    from gobby.storage.sessions import LocalSessionManager
    from gobby.workflows.definitions import PipelineDefinition
    from gobby.workflows.templates import TemplateEngine

logger = logging.getLogger(__name__)


# Type alias for event callback
PipelineEventCallback = Any  # Callable[[str, str, dict], Awaitable[None]]


class PipelineExecutor:
    """Executor for pipeline workflows with typed data flow between steps.

    Handles:
    - Creating and tracking execution records
    - Iterating through steps in order
    - Building context with inputs and step outputs
    - Executing exec commands, prompts, and nested pipelines
    - Webhook notifications
    - WebSocket event broadcasting for real-time updates
    """

    def __init__(
        self,
        db: DatabaseProtocol,
        execution_manager: LocalPipelineExecutionManager,
        llm_service: Any,
        template_engine: TemplateEngine | None = None,
        webhook_notifier: Any | None = None,
        loader: Any | None = None,
        event_callback: PipelineEventCallback | None = None,
        tool_proxy_getter: Any | None = None,
        spawner: "TmuxSpawner | None" = None,
        session_manager: "LocalSessionManager | None" = None,
    ):
        """Initialize the pipeline executor.

        Args:
            db: Database connection for transactions
            execution_manager: Manager for pipeline execution records
            llm_service: LLM service for prompt steps
            template_engine: Optional template engine for variable substitution
            webhook_notifier: Optional notifier for webhook callbacks
            loader: Optional workflow loader for nested pipelines
            event_callback: Optional async callback for broadcasting events.
                           Signature: async def callback(event: str, execution_id: str, **kwargs)
            tool_proxy_getter: Optional callable returning ToolProxyService for MCP steps
            spawner: Optional TmuxSpawner for spawn_session steps
            session_manager: Optional LocalSessionManager for session creation
        """
        self.db = db
        self.execution_manager = execution_manager
        self.llm_service = llm_service
        self.template_engine = template_engine
        self.webhook_notifier = webhook_notifier
        self.loader = loader
        self.event_callback = event_callback
        self.tool_proxy_getter = tool_proxy_getter
        self.spawner = spawner
        self.session_manager = session_manager

    async def _emit_event(self, event: str, execution_id: str, **kwargs: Any) -> None:
        """Emit a pipeline event via the callback if configured.

        Args:
            event: Event type (pipeline_started, step_completed, etc.)
            execution_id: Pipeline execution ID
            **kwargs: Additional event data
        """
        if self.event_callback:
            try:
                await self.event_callback(event, execution_id, **kwargs)
            except Exception as e:
                logger.warning(f"Failed to emit pipeline event {event}: {e}")

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

        # Emit pipeline_started event
        await self._emit_event(
            "pipeline_started",
            execution.id,
            pipeline_name=pipeline.name,
            inputs=inputs,
            step_count=len(pipeline.steps),
        )

        # 3. Build execution context
        context: dict[str, Any] = {
            "inputs": inputs,
            "steps": {},  # Will hold step outputs as they complete
        }

        # Fetch existing steps if resuming
        existing_steps = {}
        if execution_id:
            steps = self.execution_manager.get_steps_for_execution(execution_id)
            existing_steps = {s.step_id: s for s in steps}

        try:
            # 4. Iterate through steps in order
            for step in pipeline.steps:
                # Check for existing execution
                step_execution = existing_steps.get(step.id)

                if step_execution:
                    # If completed, load output into context and skip
                    if step_execution.status == StepStatus.COMPLETED:
                        logger.info(f"Skipping completed step {step.id}")
                        output = None
                        if step_execution.output_json:
                            try:
                                output = json.loads(step_execution.output_json)
                            except json.JSONDecodeError:
                                output = step_execution.output_json
                        context["steps"][step.id] = {"output": output}
                        continue

                    # If skipped, just skip
                    if step_execution.status == StepStatus.SKIPPED:
                        logger.info(f"Skipping previously skipped step {step.id}")
                        continue

                    # If waiting approval, check if we should check gate again
                    # If we are resuming, it might have been approved
                    if step_execution.status == StepStatus.WAITING_APPROVAL:
                        # If the step is still marked as waiting approval in DB,
                        # checking the gate will just re-raise ApprovalRequired.
                        # If it was approved, status should be COMPLETED.
                        # So we can just proceed to check/execute.
                        pass

                # Create new step execution if not exists
                if not step_execution:
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

                    # Emit step_skipped event
                    await self._emit_event(
                        "step_skipped",
                        execution.id,
                        step_id=step.id,
                        step_name=getattr(step, "name", step.id),
                        reason="condition not met",
                    )
                    continue

                # Update step status to RUNNING
                self.execution_manager.update_step_execution(
                    step_execution_id=step_execution.id,
                    status=StepStatus.RUNNING,
                )

                # Emit step_started event
                await self._emit_event(
                    "step_started",
                    execution.id,
                    step_id=step.id,
                    step_name=getattr(step, "name", step.id),
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

                # Emit step_completed event
                await self._emit_event(
                    "step_completed",
                    execution.id,
                    step_id=step.id,
                    step_name=getattr(step, "name", step.id),
                    output=step_output,
                )

            # 5. Mark execution as completed
            outputs = self._build_outputs(pipeline, context)
            completed = self.execution_manager.update_execution_status(
                execution_id=execution.id,
                status=ExecutionStatus.COMPLETED,
                outputs_json=json.dumps(outputs),
            )
            if completed:
                execution = completed

            # Emit pipeline_completed event
            await self._emit_event(
                "pipeline_completed",
                execution.id,
                pipeline_name=pipeline.name,
                outputs=outputs,
            )

        except ApprovalRequired:
            # Don't treat approval as an error - just re-raise
            raise

        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}", exc_info=True)
            failed = self.execution_manager.update_execution_status(
                execution_id=execution.id,
                status=ExecutionStatus.FAILED,
            )
            if failed:
                execution = failed

            # Emit pipeline_failed event
            await self._emit_event(
                "pipeline_failed",
                execution.id,
                pipeline_name=pipeline.name,
                error=str(e),
            )
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
        elif step.mcp:
            # Execute MCP tool call
            return await self._execute_mcp_step(rendered_step, context)
        elif step.spawn_session:
            # Spawn a CLI session via tmux
            return await self._execute_spawn_session_step(rendered_step, context, project_id)
        elif step.activate_workflow:
            # Activate a workflow on a session
            return await self._execute_activate_workflow_step(rendered_step, context)
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

        template_engine = self.template_engine

        import os
        import re

        # Build render context
        render_context = {
            "inputs": context.get("inputs", {}),
            "steps": context.get("steps", {}),
            "env": os.environ,
        }

        def render_string(s: str) -> str:
            if not s:
                return s
            # Replace ${{ ... }} with {{ ... }} for Jinja2
            # Use dotall to allow multi-line expressions
            jinja_template = re.sub(r"\$\{\{(.*?)\}\}", r"{{\1}}", s, flags=re.DOTALL)

            # If no changes (no ${{ }}), we might still want to run it through jinja
            # if we wanted to support direct {{ }} syntax too.
            # But the requirement highlights ${{ }}.
            # If the user provides {{ }}, it will also be rendered by Jinja.

            return template_engine.render(jinja_template, render_context)

        def _coerce_value(value: str) -> Any:
            """Auto-coerce rendered string values to native types.

            After template rendering, values like "${{ inputs.timeout }}" become "600" (string).
            MCP tools expect native types, so coerce: "600" → 600, "true" → True, etc.
            """
            if not isinstance(value, str):
                return value
            # Boolean
            if value.lower() == "true":
                return True
            if value.lower() == "false":
                return False
            # Null
            if value.lower() in ("null", "none"):
                return None
            # Integer
            try:
                return int(value)
            except ValueError:
                pass
            # Float
            try:
                return float(value)
            except ValueError:
                pass
            return value

        def render_mcp_arguments(args: dict[str, Any]) -> dict[str, Any]:
            """Render template variables in MCP arguments and coerce types."""
            rendered: dict[str, Any] = {}
            for key, value in args.items():
                if isinstance(value, str):
                    rendered_val = render_string(value)
                    rendered[key] = _coerce_value(rendered_val)
                elif isinstance(value, dict):
                    rendered[key] = render_mcp_arguments(value)
                elif isinstance(value, list):
                    rendered[key] = [
                        _coerce_value(render_string(v)) if isinstance(v, str) else v for v in value
                    ]
                else:
                    rendered[key] = value
            return rendered

        # Create a copy of the step to avoid modifying the definition
        rendered_step = step.model_copy(deep=True)

        try:
            if rendered_step.exec:
                rendered_step.exec = render_string(rendered_step.exec)

            if rendered_step.prompt:
                rendered_step.prompt = render_string(rendered_step.prompt)

            if rendered_step.mcp and rendered_step.mcp.arguments:
                rendered_step.mcp.arguments = render_mcp_arguments(rendered_step.mcp.arguments)

        except Exception as e:
            raise ValueError(f"Failed to render step {step.id}: {e}") from e

        return rendered_step

    async def _execute_mcp_step(self, rendered_step: Any, context: dict[str, Any]) -> Any:
        """Execute an MCP tool call step.

        Args:
            rendered_step: The rendered step with MCP config
            context: Execution context

        Returns:
            The MCP tool result (structured JSON)

        Raises:
            RuntimeError: If tool_proxy_getter is not configured or MCP call fails
        """
        mcp_config = rendered_step.mcp

        logger.info(f"Executing MCP step: {mcp_config.server}:{mcp_config.tool}")

        if not self.tool_proxy_getter:
            raise RuntimeError(
                f"MCP step {rendered_step.id} requires tool_proxy_getter but none configured"
            )

        tool_proxy = self.tool_proxy_getter()
        if not tool_proxy:
            raise RuntimeError("tool_proxy_getter returned None")

        result = await tool_proxy.call_tool(
            mcp_config.server,
            mcp_config.tool,
            mcp_config.arguments or {},
        )

        # Check for MCP-level failure
        if isinstance(result, dict) and result.get("success") is False:
            error_msg = result.get("error", "Unknown MCP tool error")
            raise RuntimeError(
                f"MCP step {rendered_step.id} failed: "
                f"{mcp_config.server}:{mcp_config.tool} returned error: {error_msg}"
            )

        return result

    async def _execute_spawn_session_step(
        self, rendered_step: Any, context: dict[str, Any], project_id: str
    ) -> dict[str, Any]:
        """Execute a spawn_session step — spawn a CLI session via tmux.

        Args:
            rendered_step: The rendered step with spawn_session config
            context: Execution context
            project_id: Project ID for the session

        Returns:
            Dict with session_id and tmux_session_name
        """
        config = rendered_step.spawn_session
        if not self.spawner:
            raise RuntimeError(
                f"spawn_session step {rendered_step.id} requires a tmux spawner but none configured"
            )

        if not self.session_manager:
            raise RuntimeError(
                f"spawn_session step {rendered_step.id} requires session_manager but none configured"
            )

        cli = config.get("cli", "claude")
        prompt = config.get("prompt")
        cwd = config.get("cwd")
        workflow_name = config.get("workflow_name")
        agent_depth = config.get("agent_depth", 1)

        # Create a gobby session record
        session = self.session_manager.create_session(
            platform=cli,
            project_id=project_id,
        )
        session_id = session.id if hasattr(session, "id") else str(session)

        try:
            result = self.spawner.spawn_agent(
                cli=cli,
                cwd=cwd or ".",
                session_id=session_id,
                parent_session_id="",
                agent_run_id=session_id,
                project_id=project_id,
                workflow_name=workflow_name,
                agent_depth=agent_depth,
                prompt=prompt,
            )
            return {
                "session_id": session_id,
                "tmux_session_name": getattr(result, "tmux_session_name", ""),
            }
        except Exception as e:
            raise RuntimeError(f"spawn_session step {rendered_step.id} failed: {e}") from e

    async def _execute_activate_workflow_step(
        self, rendered_step: Any, context: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute an activate_workflow step — activate a workflow on a session.

        Args:
            rendered_step: The rendered step with activate_workflow config
            context: Execution context

        Returns:
            Dict with workflow activation result
        """
        config = rendered_step.activate_workflow
        if not self.loader:
            raise RuntimeError(
                f"activate_workflow step {rendered_step.id} requires workflow loader but none configured"
            )

        workflow_name = config.get("name")
        session_id = config.get("session_id")
        variables = config.get("variables") or {}

        if not workflow_name:
            raise RuntimeError(
                f"activate_workflow step {rendered_step.id} requires 'name' field"
            )
        if not session_id:
            raise RuntimeError(
                f"activate_workflow step {rendered_step.id} requires 'session_id' field"
            )
        if not self.session_manager:
            raise RuntimeError(
                f"activate_workflow step {rendered_step.id} requires session_manager but none configured"
            )

        try:
            from gobby.mcp_proxy.tools.workflows._lifecycle import activate_workflow
            from gobby.workflows.state_manager import WorkflowStateManager

            state_manager = WorkflowStateManager(self.db)

            result = await activate_workflow(
                loader=self.loader,
                state_manager=state_manager,
                session_manager=self.session_manager,
                db=self.db,
                name=workflow_name,
                session_id=session_id,
                variables=variables,
            )
            return result
        except Exception as e:
            raise RuntimeError(
                f"activate_workflow step {rendered_step.id} failed: {e}"
            ) from e

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

        # Emit approval_required event
        await self._emit_event(
            "approval_required",
            execution.id,
            step_id=step.id,
            step_name=getattr(step, "name", step.id),
            message=message,
            token=token,
        )

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
        if not execution:
            raise ValueError(f"Execution {step.execution_id} not found")

        # Resume execution
        if self.loader:
            try:
                pipeline = await self.loader.load_pipeline(execution.pipeline_name)
                if pipeline:
                    inputs = {}
                    if execution.inputs_json:
                        try:
                            inputs = json.loads(execution.inputs_json)
                        except json.JSONDecodeError:
                            pass

                    # Execute (resume)
                    execution = await self.execute(
                        pipeline=pipeline,
                        inputs=inputs,
                        project_id=execution.project_id,
                        execution_id=execution.id,
                    )
            except ApprovalRequired:
                # Pipeline paused again for another approval - this is expected
                # Refresh execution to get latest status
                execution = self.execution_manager.get_execution(execution.id)
                if not execution:
                    raise ValueError(
                        f"Execution {step.execution_id} not found after resume"
                    ) from None
            except Exception as e:
                logger.error(f"Failed to resume execution after approval: {e}", exc_info=True)
                # Don't fail the approval if resume fails, but log it
        else:
            logger.warning("No loader configured, cannot resume execution automatically")

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
        error_msg = "Rejected"
        if rejected_by:
            error_msg += f" by {rejected_by}"

        self.execution_manager.update_step_execution(
            step_execution_id=step.id,
            status=StepStatus.FAILED,
            error=error_msg,
        )

        # Set execution status to CANCELLED
        execution = self.execution_manager.update_execution_status(
            execution_id=step.execution_id,
            status=ExecutionStatus.CANCELLED,
        )

        if not execution:
            raise ValueError(f"Execution {step.execution_id} not found")

        return execution

    async def _execute_exec_step(self, command: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a shell command step.

        Commands are parsed using shlex.split and executed via create_subprocess_exec
        to avoid shell injection vulnerabilities. The command string is treated as a
        space-separated list of arguments, not a shell script.

        Note: Pipeline commands are defined by the pipeline author, not end users.
        This is a defense-in-depth measure.

        Args:
            command: The command to execute (space-separated arguments)
            context: Execution context

        Returns:
            Dict with stdout, stderr, exit_code
        """
        import asyncio

        logger.info(f"Executing command: {command}")

        try:
            # Parse command into arguments to avoid shell injection
            args = shlex.split(command)
            if not args:
                return {
                    "stdout": "",
                    "stderr": "Empty command",
                    "exit_code": 1,
                }

            # Run command without shell
            proc = await asyncio.create_subprocess_exec(
                *args,
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
            nested_pipeline = await self.loader.load_pipeline(pipeline_name)

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
