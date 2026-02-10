"""Cron job executor - dispatches jobs by action type."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from gobby.storage.cron import CronJobStorage
from gobby.storage.cron_models import CronJob, CronRun

if TYPE_CHECKING:
    from gobby.workflows.pipeline_executor import PipelineExecutor

logger = logging.getLogger(__name__)


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
            logger.error(f"Cron job {job.id} ({job.name}) failed: {e}")
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

        # Load and execute pipeline
        from gobby.workflows.loader import WorkflowLoader

        loader = WorkflowLoader()
        pipeline = await loader.load_pipeline(pipeline_name)
        if not pipeline:
            raise ValueError(f"Pipeline '{pipeline_name}' not found")

        execution = await self.pipeline_executor.execute(
            pipeline=pipeline,
            inputs=inputs,
            project_id=job.project_id,
        )

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
