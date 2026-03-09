"""Cron job executor - dispatches jobs by action type."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.storage.cron import CronJobStorage
from gobby.storage.cron_models import CronJob, CronRun

if TYPE_CHECKING:
    from gobby.workflows.pipeline_executor import PipelineExecutor

logger = logging.getLogger(__name__)

# Type for registered cron handlers: async callables that receive a CronJob and return output
CronHandler = Callable[[CronJob], Awaitable[str]]


class CronExecutor:
    """Dispatches cron jobs to the appropriate execution backend."""

    def __init__(
        self,
        storage: CronJobStorage,
        agent_runner: Any | None = None,
        pipeline_executor: PipelineExecutor | None = None,
    ):
        self.storage = storage
        self.agent_runner = agent_runner
        self.pipeline_executor = pipeline_executor
        self._handlers: dict[str, CronHandler] = {}

    def register_handler(self, name: str, handler: CronHandler) -> None:
        """Register a named handler for the 'handler' action type.

        Args:
            name: Handler name (referenced in action_config["handler"])
            handler: Async callable that receives a CronJob and returns output string
        """
        self._handlers[name] = handler

    async def execute(self, job: CronJob, run: CronRun) -> CronRun:
        """Execute a cron job and update the run record.

        Args:
            job: The cron job to execute
            run: The cron run record to update

        Returns:
            Updated CronRun with status and output
        """
        now = datetime.now(UTC).isoformat()
        self.storage.update_run(run.id, status="running", started_at=now)

        try:
            if job.action_type == "agent_spawn":
                output = await self._execute_agent_spawn(job)
            elif job.action_type == "pipeline":
                output = await self._execute_pipeline(job)
            elif job.action_type == "shell":
                output = await self._execute_shell(job)
            elif job.action_type == "handler":
                output = await self._execute_handler(job)
            else:
                raise ValueError(f"Unknown action_type: {job.action_type}")

            completed_at = datetime.now(UTC).isoformat()
            updated = self.storage.update_run(
                run.id,
                status="completed",
                completed_at=completed_at,
                output=output[:10000] if output and len(output) > 10000 else output,
            )
            return updated or run

        except Exception as e:
            logger.exception("Cron job %s (%s) failed", job.id, job.name)
            completed_at = datetime.now(UTC).isoformat()
            updated = self.storage.update_run(
                run.id,
                status="failed",
                completed_at=completed_at,
                error=str(e)[:5000],
            )
            return updated or run

    async def _execute_agent_spawn(self, job: CronJob) -> str:
        """Execute an agent_spawn action."""
        if not self.agent_runner:
            raise RuntimeError("agent_runner not configured for cron executor")

        config = job.action_config
        prompt = config.get("prompt", "")
        if not prompt:
            raise ValueError("agent_spawn action requires a 'prompt' in action_config")

        provider = config.get("provider", "claude")
        timeout = config.get("timeout_seconds", 300)
        workflow = config.get("workflow")

        # Resolve agent_definition if specified
        agent_def_name = config.get("agent_definition")
        if agent_def_name:
            from gobby.workflows.agent_resolver import resolve_agent

            agent_body = resolve_agent(
                agent_def_name,
                self.storage.db,
                project_id=job.project_id,
            )
            if agent_body:
                preamble = agent_body.build_prompt_preamble()
                if preamble:
                    prompt = f"{preamble}\n\n---\n\n{prompt}"
                # Use agent definition's provider if no explicit provider in config
                if "provider" not in config and agent_body.provider != "inherit":
                    provider = agent_body.provider

        # Use the agent runner's spawn method
        result = await self.agent_runner.spawn_headless(
            prompt=prompt,
            project_id=job.project_id,
            provider=provider,
            workflow=workflow,
            timeout=timeout,
        )

        return result.get("output", "Agent completed") if isinstance(result, dict) else str(result)

    async def _execute_pipeline(self, job: CronJob) -> str:
        """Execute a pipeline action."""
        if not self.pipeline_executor:
            raise RuntimeError("pipeline_executor not configured for cron executor")

        config = job.action_config
        pipeline_name = config.get("pipeline_name")
        if not pipeline_name:
            raise ValueError("pipeline action requires 'pipeline_name' in action_config")

        inputs = config.get("inputs", {})

        # Use pipeline_executor's loader (has DB context) instead of bare WorkflowLoader()
        loader = self.pipeline_executor.loader
        if not loader:
            raise RuntimeError("pipeline_executor has no loader configured")
        pipeline = await loader.load_pipeline(pipeline_name)
        if not pipeline:
            raise ValueError(f"Pipeline '{pipeline_name}' not found")

        # Create a session for the cron-triggered pipeline so spawned agents
        # have a valid parent_session_id (required by spawn_agent).
        session_id: str | None = None
        sm = self.pipeline_executor.session_manager
        if sm:
            try:
                cron_session = sm.register(
                    external_id=f"cron-{job.id}-{pipeline_name}",
                    machine_id="cron",
                    source="cron",
                    project_id=job.project_id,
                    title=f"cron:{job.name}",
                    agent_depth=0,
                )
                session_id = cron_session.id
            except Exception:
                logger.warning("Failed to create session for cron pipeline", exc_info=True)

        # Set project context so MCP tools can resolve task refs like #9916
        # Must include project_path — spawn_agent_impl requires it.
        from gobby.utils.project_context import reset_project_context, set_project_context

        project_ctx: dict[str, Any] | None = None
        if job.project_id:
            project_ctx = {"id": job.project_id}
            # Look up repo_path from projects table
            try:
                row = self.storage.db.execute(
                    "SELECT repo_path FROM projects WHERE id = ?",
                    (job.project_id,),
                ).fetchone()
                if row and row[0]:
                    project_ctx["project_path"] = row[0]
            except Exception:
                logger.debug(
                    "Failed to resolve repo_path for project %s", job.project_id, exc_info=True
                )

        token = set_project_context(project_ctx)
        try:
            execution = await self.pipeline_executor.execute(
                pipeline=pipeline,
                inputs=inputs,
                project_id=job.project_id,
                session_id=session_id,
            )
        finally:
            reset_project_context(token)

        return f"Pipeline completed with status: {execution.status}"

    async def _execute_shell(self, job: CronJob) -> str:
        """Execute a shell command action."""
        config = job.action_config
        command = config.get("command")
        if not command:
            raise ValueError("shell action requires 'command' in action_config")

        args = config.get("args", [])
        cwd = config.get("cwd")
        timeout = config.get("timeout_seconds", 60)

        cmd = [command] + args

        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            output = stdout.decode("utf-8", errors="replace") if stdout else ""

            if process.returncode != 0:
                raise RuntimeError(
                    f"Command exited with code {process.returncode}: {output[:2000]}"
                )

            return output

        except TimeoutError as err:
            if process:
                process.terminate()
            raise RuntimeError(f"Shell command timed out after {timeout}s") from err

    async def _execute_handler(self, job: CronJob) -> str:
        """Execute a registered handler action.

        The handler name is read from action_config["handler"] and dispatched
        to a previously registered async callable.
        """
        name = job.action_config.get("handler")
        if not name:
            raise ValueError("handler action requires 'handler' in action_config")
        handler = self._handlers.get(name)
        if not handler:
            available = list(self._handlers.keys())
            raise ValueError(f"No handler registered: '{name}'. Available: {available}")
        return await handler(job)
