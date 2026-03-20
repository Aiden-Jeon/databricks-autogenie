"""Abstract base class for session and job persistence.

This module provides the base interface for session storage backends,
supporting both Lamp (create new Genie spaces) and Enhancer (improve existing spaces) workflows.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel


class Job(BaseModel):
    """Job model for tracking async operations.

    Supports both Lamp jobs (parse, generate, validate, deploy) and
    Enhancer jobs (score, plan, apply, validate, auto_loop).
    """
    job_id: str
    session_id: str
    type: str  # Lamp: parse, generate, validate, deploy, benchmark_validate
              # Enhancer: score, plan, apply, validate, auto_loop
    status: str  # pending, running, completed, failed, cancelled
    inputs: dict = {}
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: Optional[dict] = None

    class Config:
        # Allow arbitrary types like datetime
        arbitrary_types_allowed = True


class SessionStoreBase(ABC):
    """Abstract base class for session and job persistence.

    Supports shared sessions between Lamp and Enhancer workflows,
    enabling workflow continuity (create space → enhance space).
    """

    @abstractmethod
    def __init__(self, **kwargs):
        """Initialize storage backend with backend-specific configuration."""
        pass

    # ========== Session CRUD Operations ==========

    @abstractmethod
    def create_session(
        self,
        user_id: str,
        name: Optional[str] = None,
        workflow_type: str = "lamp",
        target_score: float = 0.90,
        max_iterations: int = 3
    ) -> str:
        """Create new session.

        Args:
            user_id: User identifier
            name: Optional session name
            workflow_type: 'lamp' or 'enhancer'
            target_score: Target score for enhancer workflow
            max_iterations: Max iterations for enhancer auto-loop

        Returns:
            Generated session_id (UUID string)
        """
        pass

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session by ID with all metadata."""
        pass

    @abstractmethod
    def get_session_with_stats(self, session_id: str) -> Optional[dict]:
        """Get session details with job count."""
        pass

    @abstractmethod
    def list_sessions(
        self,
        user_id: str = None,
        workflow_type: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[dict], int]:
        """List sessions with pagination.

        Args:
            user_id: Optional filter by user_id
            workflow_type: Optional filter by 'lamp' or 'enhancer'
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            Tuple of (sessions list, total count)
        """
        pass

    @abstractmethod
    def update_session_name(self, session_id: str, name: str) -> None:
        """Update session name and updated_at timestamp."""
        pass

    @abstractmethod
    def update_session_activity(self, session_id: str) -> None:
        """Update session updated_at timestamp."""
        pass

    @abstractmethod
    def delete_session(self, session_id: str) -> None:
        """Delete session and all associated jobs (cascade)."""
        pass

    # ========== Job CRUD Operations ==========

    @abstractmethod
    def save_job(self, job: Job) -> None:
        """Save new job record."""
        pass

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve job by ID."""
        pass

    @abstractmethod
    def update_job(self, job: Job) -> None:
        """Update job status, result, error, progress."""
        pass

    @abstractmethod
    def get_jobs_for_session(self, session_id: str) -> List[Job]:
        """Get all jobs for session, ordered by created_at."""
        pass

    @abstractmethod
    def delete_job(self, job_id: str) -> bool:
        """Delete a job by ID. Returns True if deleted."""
        pass

    # ========== Enhancer-Specific Operations ==========

    @abstractmethod
    def update_loop_status(
        self,
        session_id: str,
        loop_status: str,
        current_iteration: Optional[int] = None,
        initial_score: Optional[float] = None,
        latest_score: Optional[float] = None
    ) -> None:
        """Update session loop status for enhancer workflow."""
        pass

    @abstractmethod
    def append_job_progress(self, job_id: str, event: Dict[str, Any]) -> None:
        """Atomically append a progress event to a job."""
        pass

    # ========== Iteration Management (Enhancer) ==========

    def create_iteration(self, session_id: str, iteration_number: int) -> Dict[str, Any]:
        """Create a new iteration for enhancer workflow. Override in implementation."""
        raise NotImplementedError("Iteration support not implemented")

    def get_iteration(self, iteration_id: str) -> Optional[Dict[str, Any]]:
        """Get iteration by ID. Override in implementation."""
        raise NotImplementedError("Iteration support not implemented")

    def update_iteration(self, iteration: Dict[str, Any]) -> None:
        """Update an iteration. Override in implementation."""
        raise NotImplementedError("Iteration support not implemented")

    def list_iterations(self, session_id: str) -> List[Dict[str, Any]]:
        """List iterations for a session. Override in implementation."""
        raise NotImplementedError("Iteration support not implemented")

    # ========== Hook Methods (Optional Overrides) ==========

    def setup_schema(self) -> None:
        """Set up database schema. Override for SQL databases."""
        pass

    def migrate_schema(self) -> None:
        """Run schema migrations. Override for version upgrades."""
        pass

    def health_check(self) -> bool:
        """Check storage backend health."""
        return True

    def close(self) -> None:
        """Close connections and cleanup."""
        pass
