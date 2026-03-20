"""Iteration controller for managing enhancement loops."""

import logging
from datetime import datetime
from typing import Dict, Any, Tuple

from backend.services.session_store_base import SessionStoreBase
from backend.services.job_manager import JobManager

logger = logging.getLogger(__name__)


class IterationController:
    """Controls the iterative enhancement loop.

    Responsibilities:
    - Start new iterations
    - Track iteration progress
    - Determine if loop should continue
    - Update session loop status
    """

    def __init__(
        self,
        session_store: SessionStoreBase,
        job_manager: JobManager
    ):
        """Initialize iteration controller."""
        self.session_store = session_store
        self.job_manager = job_manager

    def start_iteration(
        self,
        session_id: str,
        workspace_config: Dict[str, Any],
        benchmarks: list
    ) -> Tuple[str, str, str]:
        """Start a new iteration (score + plan).

        Args:
            session_id: Session ID
            workspace_config: Workspace configuration
            benchmarks: List of benchmarks

        Returns:
            Tuple of (iteration_id, score_job_id, plan_job_id)
        """
        session = self.session_store.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        existing_iterations = self.session_store.list_iterations(session_id)
        iteration_number = len(existing_iterations) + 1

        logger.info(f"Starting iteration {iteration_number} for session {session_id}")

        iteration = self.session_store.create_iteration(session_id, iteration_number)

        self.session_store.update_loop_status(
            session_id,
            loop_status="running",
            current_iteration=iteration_number
        )

        return iteration["iteration_id"], None, None

    def update_iteration_score(
        self,
        iteration_id: str,
        score: float,
        score_job_id: str
    ):
        """Update iteration with scoring results."""
        iteration = self.session_store.get_iteration(iteration_id)
        if not iteration:
            raise ValueError(f"Iteration not found: {iteration_id}")

        iteration["score_before"] = score
        iteration["score_job_id"] = score_job_id
        iteration["status"] = "planning"

        self.session_store.update_iteration(iteration)

        if iteration["iteration_number"] == 1:
            self.session_store.update_loop_status(
                iteration["session_id"],
                loop_status="running",
                initial_score=score,
                latest_score=score
            )

        logger.info(f"Iteration {iteration_id} scored: {score:.1%}")

    def update_iteration_plan(
        self,
        iteration_id: str,
        fixes_proposed: Dict[str, Any],
        plan_job_id: str
    ):
        """Update iteration with planning results."""
        iteration = self.session_store.get_iteration(iteration_id)
        if not iteration:
            raise ValueError(f"Iteration not found: {iteration_id}")

        iteration["fixes_proposed"] = fixes_proposed
        iteration["plan_job_id"] = plan_job_id
        iteration["status"] = "awaiting_approval"

        self.session_store.update_iteration(iteration)

        logger.info(f"Iteration {iteration_id} planned: {len(fixes_proposed)} fix categories")

    def approve_and_apply(
        self,
        iteration_id: str,
        approved_fixes: Dict[str, Any]
    ) -> str:
        """Approve fixes and start apply job.

        Args:
            iteration_id: Iteration ID
            approved_fixes: User-approved fixes (subset of proposed)

        Returns:
            Apply job ID
        """
        iteration = self.session_store.get_iteration(iteration_id)
        if not iteration:
            raise ValueError(f"Iteration not found: {iteration_id}")

        if iteration["status"] not in ("awaiting_approval", "applying"):
            status = iteration["status"]
            raise ValueError(f"Iteration {iteration_id} is not awaiting approval (status: {status})")

        iteration["fixes_approved"] = approved_fixes
        iteration["status"] = "applying"
        self.session_store.update_iteration(iteration)

        logger.info(f"Iteration {iteration_id} approved: {len(approved_fixes)} fix categories")

        return iteration_id

    def update_iteration_apply(
        self,
        iteration_id: str,
        fixes_applied: Dict[str, Any],
        apply_job_id: str
    ):
        """Update iteration with apply results."""
        iteration = self.session_store.get_iteration(iteration_id)
        if not iteration:
            raise ValueError(f"Iteration not found: {iteration_id}")

        iteration["fixes_applied"] = fixes_applied
        iteration["apply_job_id"] = apply_job_id
        iteration["status"] = "validating"

        self.session_store.update_iteration(iteration)

        logger.info(f"Iteration {iteration_id} applied: {len(fixes_applied)} fixes")

    def update_iteration_validate(
        self,
        iteration_id: str,
        score_after: float,
        validate_job_id: str
    ):
        """Update iteration with validation results."""
        iteration = self.session_store.get_iteration(iteration_id)
        if not iteration:
            raise ValueError(f"Iteration not found: {iteration_id}")

        iteration["score_after"] = score_after
        iteration["validate_job_id"] = validate_job_id
        iteration["status"] = "completed"
        iteration["completed_at"] = datetime.now()

        self.session_store.update_iteration(iteration)

        self.session_store.update_loop_status(
            iteration["session_id"],
            loop_status="running",
            latest_score=score_after
        )

        logger.info(f"Iteration {iteration_id} validated: {score_after:.1%}")

    def should_continue(self, session_id: str) -> Tuple[bool, str]:
        """Determine if loop should continue.

        Args:
            session_id: Session ID

        Returns:
            Tuple of (should_continue, reason)
        """
        session = self.session_store.get_session(session_id)
        if not session:
            return False, "Session not found"

        latest_score = session.get("latest_score")
        target_score = session.get("target_score", 0.90)
        current_iteration = session.get("current_iteration", 0)
        max_iterations = session.get("max_iterations", 3)

        if latest_score is not None and latest_score >= target_score:
            self.session_store.update_loop_status(
                session_id,
                loop_status="target_reached"
            )
            return False, f"Target score ({target_score:.1%}) reached: {latest_score:.1%}"

        if current_iteration >= max_iterations:
            self.session_store.update_loop_status(
                session_id,
                loop_status="max_iterations"
            )
            return False, f"Max iterations ({max_iterations}) reached"

        return True, "Loop conditions not met, continuing"

    def get_iteration_status(self, iteration_id: str) -> Dict[str, Any]:
        """Get current iteration status."""
        iteration = self.session_store.get_iteration(iteration_id)
        if not iteration:
            return {"error": "Iteration not found"}
        return iteration

    def get_iteration_history(self, session_id: str) -> list:
        """Get all iterations for a session."""
        return self.session_store.list_iterations(session_id)

    def cancel_iteration(self, iteration_id: str):
        """Cancel current iteration and stop loop."""
        iteration = self.session_store.get_iteration(iteration_id)
        if not iteration:
            raise ValueError(f"Iteration not found: {iteration_id}")

        iteration["status"] = "failed"
        iteration["completed_at"] = datetime.now()
        self.session_store.update_iteration(iteration)

        self.session_store.update_loop_status(
            iteration["session_id"],
            loop_status="cancelled"
        )

        logger.info(f"Iteration {iteration_id} cancelled")
