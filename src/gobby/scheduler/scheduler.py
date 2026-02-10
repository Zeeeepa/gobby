"""Cron scheduler - background task that checks for and dispatches due jobs."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from gobby.config.cron import CronConfig
from gobby.scheduler.executor import CronExecutor
from gobby.storage.cron import CronJobStorage, compute_next_run

logger = logging.getLogger(__name__)


class CronScheduler:
    """Background scheduler that polls for due cron jobs and dispatches them.

    Follows the SessionLifecycleManager dual-loop pattern:
    - _check_loop: polls for due jobs every check_interval_seconds
    - _cleanup_loop: deletes old run history every 6 hours
    """

    def __init__(
        self,
        storage: CronJobStorage,
        executor: CronExecutor,
        config: CronConfig,
    ):
        self.storage = storage
        self.executor = executor
        self.config = config
        self._running = False
        self._check_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the scheduler loops."""
        if self._running:
            return
        if not self.config.enabled:
            logger.info("Cron scheduler disabled by config")
            return

        self._running = True
        self._check_task = asyncio.create_task(
            self._check_loop(),
            name="cron-scheduler-check",
        )
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(),
            name="cron-scheduler-cleanup",
        )
        logger.info(
            f"Cron scheduler started (interval={self.config.check_interval_seconds}s, "
            f"max_concurrent={self.config.max_concurrent_jobs})"
        )

    async def stop(self) -> None:
        """Stop the scheduler loops gracefully."""
        self._running = False
        tasks = [t for t in [self._check_task, self._cleanup_task] if t]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Cron scheduler stopped")

    async def _check_loop(self) -> None:
        """Poll for due jobs and dispatch them."""
        while self._running:
            try:
                await self._check_due_jobs()
            except Exception as e:
                logger.error(f"Cron check loop error: {e}", exc_info=True)
            try:
                await asyncio.sleep(self.config.check_interval_seconds)
            except asyncio.CancelledError:
                break

    async def _cleanup_loop(self) -> None:
        """Periodically clean up old run history."""
        cleanup_interval = 6 * 3600  # 6 hours
        while self._running:
            try:
                await asyncio.sleep(cleanup_interval)
            except asyncio.CancelledError:
                break
            try:
                deleted = self.storage.cleanup_old_runs(self.config.cleanup_after_days)
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} old cron runs")
            except Exception as e:
                logger.error(f"Cron cleanup error: {e}", exc_info=True)

    async def _check_due_jobs(self) -> None:
        """Check for due jobs and dispatch them."""
        due_jobs = self.storage.get_due_jobs()
        if not due_jobs:
            return

        # Respect max concurrent limit
        running_count = self.storage.count_running()
        available_slots = self.config.max_concurrent_jobs - running_count

        if available_slots <= 0:
            logger.debug(
                f"Skipping {len(due_jobs)} due jobs: "
                f"{running_count}/{self.config.max_concurrent_jobs} slots used"
            )
            return

        for job in due_jobs[:available_slots]:
            # Check backoff for consecutive failures
            if job.consecutive_failures > 0:
                backoff = self._get_backoff_seconds(job.consecutive_failures)
                if job.last_run_at:
                    last = datetime.fromisoformat(job.last_run_at)
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=UTC)
                    elapsed = (datetime.now(UTC) - last).total_seconds()
                    if elapsed < backoff:
                        logger.debug(
                            f"Skipping job {job.id} ({job.name}): "
                            f"backoff {backoff}s, elapsed {elapsed:.0f}s"
                        )
                        continue

            # Create run and dispatch
            run = self.storage.create_run(job.id)
            logger.info(f"Dispatching cron job {job.id} ({job.name}), run {run.id}")

            # Fire and forget - let it run in the background
            asyncio.create_task(
                self._execute_and_update(job, run),
                name=f"cron-run-{run.id}",
            )

    async def _execute_and_update(self, job: CronJob, run: CronRun) -> None:
        """Execute a job and update its status afterward."""
        try:
            result = await self.executor.execute(job, run)

            # Update job status
            now = datetime.now(UTC).isoformat()
            if result.status == "completed":
                # Reset failure counter and compute next run
                next_run = compute_next_run(job)
                self.storage.update_job(
                    job.id,
                    last_run_at=now,
                    last_status="completed",
                    consecutive_failures=0,
                    next_run_at=next_run.isoformat() if next_run else None,
                )
            else:
                # Increment failure counter
                failures = job.consecutive_failures + 1
                next_run = compute_next_run(job)
                self.storage.update_job(
                    job.id,
                    last_run_at=now,
                    last_status="failed",
                    consecutive_failures=failures,
                    next_run_at=next_run.isoformat() if next_run else None,
                )
                logger.warning(
                    f"Cron job {job.id} ({job.name}) failed "
                    f"({failures} consecutive failures)"
                )

        except Exception as e:
            logger.error(f"Unexpected error executing cron job {job.id}: {e}", exc_info=True)

    def _get_backoff_seconds(self, consecutive_failures: int) -> int:
        """Get backoff delay based on number of consecutive failures."""
        delays = self.config.backoff_delays
        if not delays:
            return 0
        idx = min(consecutive_failures - 1, len(delays) - 1)
        return delays[idx]

    async def run_now(self, job_id: str) -> CronRun | None:
        """Trigger immediate execution of a job (bypasses schedule)."""
        job = self.storage.get_job(job_id)
        if not job:
            return None

        run = self.storage.create_run(job.id)
        logger.info(f"Manual trigger: cron job {job.id} ({job.name}), run {run.id}")

        # Execute in background
        asyncio.create_task(
            self._execute_and_update(job, run),
            name=f"cron-run-manual-{run.id}",
        )

        return run
