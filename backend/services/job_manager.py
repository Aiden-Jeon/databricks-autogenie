"""Job manager for background task orchestration.

Unified job manager supporting both Lamp and Enhancer workflows.
"""

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock
from typing import Callable, Set

from backend.services.session_store_base import SessionStoreBase, Job


class JobManager:
    """Manages background job execution with thread pool.

    Supports both Lamp jobs (parse, generate, validate, deploy) and
    Enhancer jobs (score, plan, apply, validate, auto_loop).
    """

    def __init__(self, session_store: SessionStoreBase, max_workers: int = 4):
        """Initialize job manager.

        Args:
            session_store: Store for persisting job state
            max_workers: Maximum concurrent jobs
        """
        self.store = session_store
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        # Track cancelled jobs (jobs check this to exit early)
        self._cancelled_jobs: Set[str] = set()
        self._cancel_lock = Lock()

    def create_job(self, job_type: str, session_id: str, inputs: dict) -> Job:
        """Create a new job record.

        Args:
            job_type: Type of job
                      Lamp: parse, generate, validate, deploy, benchmark_validate
                      Enhancer: score, plan, apply, validate, auto_loop
            session_id: Session identifier
            inputs: Job input parameters

        Returns:
            Created Job object
        """
        job = Job(
            job_id=str(uuid.uuid4()),
            type=job_type,
            session_id=session_id,
            status="pending",
            inputs=inputs,
            created_at=datetime.now()
        )
        self.store.save_job(job)
        self.store.update_session_activity(session_id)

        return job

    async def run_job(self, job_id: str, task_func: Callable, *args, **kwargs) -> None:
        """Execute a job in the background.

        Args:
            job_id: Job identifier
            task_func: Function to execute
            *args: Positional arguments for task_func
            **kwargs: Keyword arguments for task_func
        """
        job = self.store.get_job(job_id)
        if not job:
            return

        job.status = "running"
        self.store.update_job(job)

        try:
            if 'job_id' not in kwargs:
                kwargs['job_id'] = job_id

            loop = asyncio.get_event_loop()

            def run_with_kwargs():
                return task_func(*args, **kwargs)

            result = await loop.run_in_executor(
                self.executor,
                run_with_kwargs
            )

            # Reload job to get latest progress updates from background thread
            job = self.store.get_job(job_id)
            if not job:
                return

            job.status = "completed"
            job.result = result
            job.completed_at = datetime.now()

        except Exception as e:
            # Reload job to preserve progress from background thread
            job = self.store.get_job(job_id)
            if job:
                # Safely extract error message
                try:
                    error_msg = str(e)
                except:
                    try:
                        error_type = type(e).__name__
                        error_msg = f"{error_type}: Error occurred during job execution"
                    except:
                        error_msg = "Error occurred during job execution (details unavailable)"

                job.status = "failed"
                job.error = error_msg
                job.completed_at = datetime.now()

        finally:
            if job:
                self.store.update_job(job)

    def get_job(self, job_id: str) -> Job:
        """Get job status."""
        return self.store.get_job(job_id)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job.

        Jobs must periodically check is_cancelled() to respect this.
        """
        job = self.store.get_job(job_id)
        if not job:
            return False

        with self._cancel_lock:
            self._cancelled_jobs.add(job_id)

        job.status = "cancelled"
        job.completed_at = datetime.now()
        self.store.update_job(job)

        return True

    def is_cancelled(self, job_id: str) -> bool:
        """Check if a job has been cancelled."""
        with self._cancel_lock:
            return job_id in self._cancelled_jobs

    def cancel_session_jobs(self, session_id: str) -> int:
        """Cancel all running jobs for a session."""
        jobs = self.store.get_jobs_for_session(session_id)
        cancelled_count = 0

        for job in jobs:
            if job.status in ("pending", "running"):
                self.cancel_job(job.job_id)
                cancelled_count += 1

        return cancelled_count

    def clear_state(self, session_id: str = None):
        """Clear cancelled job tracking state."""
        with self._cancel_lock:
            if session_id:
                jobs = self.store.get_jobs_for_session(session_id)
                job_ids = {j.job_id for j in jobs}
                self._cancelled_jobs -= job_ids
            else:
                self._cancelled_jobs.clear()

    def delete_job(self, job_id: str) -> bool:
        """Delete a job from the store.

        Jobs must be completed, failed, or cancelled before deletion.
        """
        job = self.store.get_job(job_id)
        if not job:
            return False

        if job.status in ("pending", "running"):
            return False

        with self._cancel_lock:
            self._cancelled_jobs.discard(job_id)

        return self.store.delete_job(job_id)
