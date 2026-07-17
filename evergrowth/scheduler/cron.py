"""Cron scheduler for Evergrowth — natural language automations."""

import json
import logging
import time
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("evergrowth.scheduler")


class CronScheduler:
    """
    Natural language cron scheduler.

    Supports:
    - Interval-based scheduling (every N minutes/hours)
    - Cron expressions (e.g., "0 9 * * *" for daily at 9am)
    - One-shot timers
    - DI-managed schedules (DI creates its own)
    """

    def __init__(self, config):
        self.config = config
        self.scheduler = AsyncIOScheduler()
        self.jobs_file = config.resolve_data_dir() / "scheduled_jobs.json"
        self._jobs: list[dict] = []

    async def initialize(self):
        """Initialize the scheduler and load saved jobs."""
        self.scheduler.start()
        self._load_jobs()
        logger.info(f"Cron scheduler initialized: {len(self._jobs)} jobs loaded")

    async def shutdown(self):
        """Shutdown the scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Cron scheduler shut down")

    def _load_jobs(self):
        """Load scheduled jobs from disk."""
        if self.jobs_file.exists():
            try:
                with open(self.jobs_file, encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, list):
                    raise ValueError("scheduled jobs file must contain a list")
                self._jobs = []
                for job in loaded:
                    if not isinstance(job, dict) or not isinstance(job.get("id"), str):
                        logger.warning("Skipping malformed scheduled job entry: %r", job)
                        continue
                    self._jobs.append(job)
                    if job.get("enabled", True):
                        self._register_job(job)
            except Exception as e:
                logger.warning(f"Failed to load scheduled jobs: {e}")

    def _save_jobs(self):
        """Save scheduled jobs to disk."""
        try:
            temporary = self.jobs_file.with_suffix(self.jobs_file.suffix + ".tmp")
            temporary.write_text(
                json.dumps(self._jobs, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            temporary.replace(self.jobs_file)
        except Exception as e:
            logger.error(f"Failed to save scheduled jobs: {e}")

    def _register_job(self, job: dict):
        """Register a job with APScheduler."""
        try:
            job_type = job.get("type", "interval")
            job_id = job["id"]

            if job_type == "interval":
                trigger = IntervalTrigger(
                    minutes=job.get("interval_minutes", 60),
                )
            elif job_type == "cron":
                trigger = CronTrigger.from_crontab(job.get("cron_expression", "0 * * * *"))
            elif job_type == "once":
                # One-shot jobs must use a non-repeating date trigger.
                run_at = job.get("run_at", time.time())
                trigger = DateTrigger(run_date=datetime.fromtimestamp(run_at))
            else:
                return

            self.scheduler.add_job(
                self._execute_job,
                trigger=trigger,
                id=job_id,
                kwargs={"job": job},
                replace_existing=True,
            )
        except Exception as e:
            logger.error(f"Failed to register job {job.get('name', '?')}: {e}")

    async def _execute_job(self, job: dict):
        """Execute a scheduled job."""
        job_name = job.get("name", "unnamed")
        logger.info(f"Executing scheduled job: {job_name}")

        # In a full implementation, this would:
        # 1. Build a prompt for the DI
        # 2. Send it via MCP or heartbeat
        # 3. Log the result

        # For now, log it
        action = job.get("action", "No action defined")
        logger.info(f"Job {job_name}: {action}")

        if job.get("type") == "once":
            self._jobs = [item for item in self._jobs if item.get("id") != job.get("id")]
            self._save_jobs()

    def add_interval_job(
        self,
        name: str,
        action: str,
        interval_minutes: int,
        enabled: bool = True,
    ) -> str:
        """Add an interval-based job."""
        import hashlib
        job_id = f"job_{hashlib.sha256(f'{name}:{time.time()}'.encode()).hexdigest()[:8]}"

        job = {
            "id": job_id,
            "name": name,
            "type": "interval",
            "action": action,
            "interval_minutes": interval_minutes,
            "enabled": enabled,
            "created_at": time.time(),
        }

        self._jobs.append(job)
        if enabled:
            self._register_job(job)
        self._save_jobs()

        logger.info(f"Added interval job: {name} (every {interval_minutes} min)")
        return job_id

    def add_cron_job(
        self,
        name: str,
        action: str,
        cron_expression: str,
        enabled: bool = True,
    ) -> str:
        """Add a cron-based job."""
        import hashlib
        job_id = f"job_{hashlib.sha256(f'{name}:{time.time()}'.encode()).hexdigest()[:8]}"

        job = {
            "id": job_id,
            "name": name,
            "type": "cron",
            "action": action,
            "cron_expression": cron_expression,
            "enabled": enabled,
            "created_at": time.time(),
        }

        self._jobs.append(job)
        if enabled:
            self._register_job(job)
        self._save_jobs()

        logger.info(f"Added cron job: {name} ({cron_expression})")
        return job_id

    def add_once_job(
        self,
        name: str,
        action: str,
        run_at: float,
    ) -> str:
        """Add a one-shot job."""
        import hashlib
        job_id = f"job_{hashlib.sha256(f'{name}:{time.time()}'.encode()).hexdigest()[:8]}"

        job = {
            "id": job_id,
            "name": name,
            "type": "once",
            "action": action,
            "run_at": run_at,
            "enabled": True,
            "created_at": time.time(),
        }

        self._jobs.append(job)
        self._register_job(job)
        self._save_jobs()

        logger.info(f"Added one-shot job: {name} (at {time.ctime(run_at)})")
        return job_id

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job."""
        try:
            self.scheduler.remove_job(job_id)
        except Exception:
            pass

        self._jobs = [j for j in self._jobs if j["id"] != job_id]
        self._save_jobs()
        logger.info(f"Removed job: {job_id}")
        return True

    def list_jobs(self) -> list[dict]:
        """List all scheduled jobs."""
        return [
            {
                "id": j["id"],
                "name": j.get("name", "unnamed"),
                "type": j.get("type", "interval"),
                "action": j.get("action", ""),
                "enabled": j.get("enabled", True),
            }
            for j in self._jobs
        ]

