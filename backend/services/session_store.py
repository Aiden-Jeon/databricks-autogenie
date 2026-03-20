"""Unified session and job persistence using SQLite.

Supports both Lamp and Enhancer workflows with shared session storage.
"""

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from backend.services.session_store_base import SessionStoreBase, Job

logger = logging.getLogger(__name__)


class SQLiteSessionStore(SessionStoreBase):
    """Manages session and job state using SQLite.

    Unified storage for both Lamp and Enhancer workflows.
    """

    def __init__(self, db_path: str = "storage/sessions.db", **kwargs):
        """Initialize SQLite session storage.

        Args:
            db_path: Path to SQLite database file
            **kwargs: Additional configuration options (ignored)
        """
        self.db_path = db_path
        logger.info(f"Using SQLite local storage: {db_path}")
        self.sqlite_conn = None
        self._lock = Lock()
        self._init_sqlite()
        self.setup_schema()
        self.migrate_schema()

    def _init_sqlite(self):
        """Initialize SQLite database for local storage."""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self.sqlite_conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.sqlite_conn.row_factory = sqlite3.Row

        # Enable WAL mode for better concurrent read/write performance
        self.sqlite_conn.execute("PRAGMA journal_mode=WAL")
        self.sqlite_conn.execute("PRAGMA synchronous=NORMAL")

        logger.info(f"SQLite database initialized at: {os.path.abspath(self.db_path)}")

    def setup_schema(self) -> None:
        """Set up database schema."""
        cursor = self.sqlite_conn.cursor()

        # Unified sessions table (supports both Lamp and Enhancer)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS autogenie_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                name TEXT,
                workflow_type TEXT DEFAULT 'lamp',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                workspace_config TEXT,
                target_score REAL DEFAULT 0.90,
                max_iterations INTEGER DEFAULT 3,
                current_iteration INTEGER DEFAULT 0,
                initial_score REAL,
                latest_score REAL,
                loop_status TEXT DEFAULT 'not_started',
                deployed_space_id TEXT,
                deployed_space_url TEXT
            )
        """)

        # Unified jobs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS autogenie_jobs (
                job_id TEXT PRIMARY KEY,
                session_id TEXT,
                type TEXT,
                status TEXT,
                inputs TEXT,
                result TEXT,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                progress TEXT,
                FOREIGN KEY (session_id) REFERENCES autogenie_sessions(session_id)
            )
        """)

        # Iterations table (for Enhancer workflow)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS autogenie_iterations (
                iteration_id TEXT PRIMARY KEY,
                session_id TEXT,
                iteration_number INTEGER,
                status TEXT DEFAULT 'scoring',
                score_before REAL,
                score_after REAL,
                fixes_proposed TEXT,
                fixes_applied TEXT,
                score_job_id TEXT,
                plan_job_id TEXT,
                apply_job_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES autogenie_sessions(session_id)
            )
        """)

        self.sqlite_conn.commit()
        cursor.close()

    def migrate_schema(self) -> None:
        """Run schema migrations."""
        cursor = self.sqlite_conn.cursor()

        # Check existing columns in sessions table
        cursor.execute("PRAGMA table_info(autogenie_sessions)")
        columns = {col[1] for col in cursor.fetchall()}

        migrations = []

        # Add any missing columns
        if 'workflow_type' not in columns:
            migrations.append("ALTER TABLE autogenie_sessions ADD COLUMN workflow_type TEXT DEFAULT 'lamp'")
        if 'deployed_space_id' not in columns:
            migrations.append("ALTER TABLE autogenie_sessions ADD COLUMN deployed_space_id TEXT")
        if 'deployed_space_url' not in columns:
            migrations.append("ALTER TABLE autogenie_sessions ADD COLUMN deployed_space_url TEXT")

        if migrations:
            logger.info(f"Running {len(migrations)} SQLite migrations...")
            for migration in migrations:
                try:
                    cursor.execute(migration)
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        raise
            self.sqlite_conn.commit()
            logger.info("SQLite migrations completed")

        cursor.close()

    def close(self) -> None:
        """Close database connections."""
        if self.sqlite_conn:
            self.sqlite_conn.close()
            self.sqlite_conn = None

    # ========== Session CRUD Operations ==========

    def create_session(
        self,
        user_id: str,
        name: Optional[str] = None,
        workflow_type: str = "lamp",
        target_score: float = 0.90,
        max_iterations: int = 3
    ) -> str:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        if name is None:
            name = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor = self.sqlite_conn.cursor()
        cursor.execute("""
            INSERT INTO autogenie_sessions (
                session_id, user_id, name, workflow_type, created_at, updated_at,
                target_score, max_iterations, current_iteration, loop_status
            ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, ?, 0, 'not_started')
        """, (session_id, user_id, name, workflow_type, target_score, max_iterations))
        self.sqlite_conn.commit()
        cursor.close()
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session by ID with all metadata."""
        cursor = self.sqlite_conn.cursor()
        cursor.execute("SELECT * FROM autogenie_sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        def safe_get(row, key, default=None):
            try:
                return row[key]
            except (KeyError, IndexError):
                return default

        return {
            "session_id": row["session_id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "workflow_type": safe_get(row, "workflow_type", "lamp"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "workspace_config": json.loads(row["workspace_config"]) if row["workspace_config"] else None,
            "target_score": safe_get(row, "target_score", 0.90),
            "max_iterations": safe_get(row, "max_iterations", 3),
            "current_iteration": safe_get(row, "current_iteration", 0),
            "initial_score": safe_get(row, "initial_score"),
            "latest_score": safe_get(row, "latest_score"),
            "loop_status": safe_get(row, "loop_status", "not_started"),
            "deployed_space_id": safe_get(row, "deployed_space_id"),
            "deployed_space_url": safe_get(row, "deployed_space_url"),
        }

    def get_session_with_stats(self, session_id: str) -> Optional[dict]:
        """Get session details with job count."""
        cursor = self.sqlite_conn.cursor()
        cursor.execute("""
            SELECT
                s.session_id,
                s.user_id,
                s.name,
                s.workflow_type,
                s.created_at,
                s.updated_at,
                COUNT(j.job_id) as job_count
            FROM autogenie_sessions s
            LEFT JOIN autogenie_jobs j ON s.session_id = j.session_id
            WHERE s.session_id = ?
            GROUP BY s.session_id
        """, (session_id,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        return {
            "session_id": row["session_id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "workflow_type": row["workflow_type"] or "lamp",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "job_count": row["job_count"],
        }

    def list_sessions(
        self,
        user_id: str = None,
        workflow_type: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[dict], int]:
        """List sessions with pagination."""
        cursor = self.sqlite_conn.cursor()

        # Build query with optional filters
        conditions = []
        params = []

        if user_id:
            conditions.append("s.user_id = ?")
            params.append(user_id)

        if workflow_type:
            conditions.append("s.workflow_type = ?")
            params.append(workflow_type)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT
                s.session_id,
                s.user_id,
                s.name,
                s.workflow_type,
                s.created_at,
                s.updated_at,
                COUNT(j.job_id) as job_count
            FROM autogenie_sessions s
            LEFT JOIN autogenie_jobs j ON s.session_id = j.session_id
            {where_clause}
            GROUP BY s.session_id
            ORDER BY s.updated_at DESC
            LIMIT ? OFFSET ?
        """

        params.extend([limit, offset])
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        # Get total count
        count_query = f"SELECT COUNT(*) FROM autogenie_sessions s {where_clause}"
        count_params = params[:-2]  # Remove limit and offset
        cursor.execute(count_query, tuple(count_params))
        total = cursor.fetchone()[0]

        cursor.close()

        sessions = [
            {
                "session_id": row["session_id"],
                "user_id": row["user_id"],
                "name": row["name"],
                "workflow_type": row["workflow_type"] or "lamp",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "job_count": row["job_count"],
            }
            for row in rows
        ]

        return sessions, total

    def update_session_name(self, session_id: str, name: str) -> None:
        """Update session name and updated_at timestamp."""
        cursor = self.sqlite_conn.cursor()
        cursor.execute(
            "UPDATE autogenie_sessions SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
            (name, session_id)
        )
        self.sqlite_conn.commit()
        cursor.close()

    def update_session_activity(self, session_id: str) -> None:
        """Update session updated_at timestamp."""
        cursor = self.sqlite_conn.cursor()
        cursor.execute(
            "UPDATE autogenie_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
            (session_id,)
        )
        self.sqlite_conn.commit()
        cursor.close()

    def delete_session(self, session_id: str) -> None:
        """Delete session and all associated jobs (cascade)."""
        cursor = self.sqlite_conn.cursor()
        # Delete iterations first
        cursor.execute("DELETE FROM autogenie_iterations WHERE session_id = ?", (session_id,))
        # Delete jobs
        cursor.execute("DELETE FROM autogenie_jobs WHERE session_id = ?", (session_id,))
        # Delete session
        cursor.execute("DELETE FROM autogenie_sessions WHERE session_id = ?", (session_id,))
        self.sqlite_conn.commit()
        cursor.close()

    def update_deployed_space(self, session_id: str, space_id: str, space_url: str) -> None:
        """Update session with deployed space information."""
        cursor = self.sqlite_conn.cursor()
        cursor.execute(
            "UPDATE autogenie_sessions SET deployed_space_id = ?, deployed_space_url = ?, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
            (space_id, space_url, session_id)
        )
        self.sqlite_conn.commit()
        cursor.close()

    # ========== Job CRUD Operations ==========

    def save_job(self, job: Job) -> None:
        """Save a new job record."""
        cursor = self.sqlite_conn.cursor()
        cursor.execute(
            """INSERT INTO autogenie_jobs
               (job_id, session_id, type, status, inputs, progress, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (job.job_id, job.session_id, job.type, job.status,
             json.dumps(job.inputs),
             json.dumps(job.progress) if job.progress else None,
             job.created_at or datetime.now())
        )
        self.sqlite_conn.commit()
        cursor.close()

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve job by ID."""
        cursor = self.sqlite_conn.cursor()
        cursor.execute("SELECT * FROM autogenie_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        return Job(
            job_id=row["job_id"],
            session_id=row["session_id"],
            type=row["type"],
            status=row["status"],
            inputs=json.loads(row["inputs"]) if row["inputs"] else {},
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            progress=json.loads(row["progress"]) if row["progress"] else None
        )

    def update_job(self, job: Job) -> None:
        """Update job status, result, error."""
        with self._lock:
            cursor = self.sqlite_conn.cursor()
            cursor.execute(
                """UPDATE autogenie_jobs
                   SET status = ?, result = ?, error = ?, completed_at = ?
                   WHERE job_id = ?""",
                (
                    job.status,
                    json.dumps(job.result) if job.result else None,
                    job.error,
                    job.completed_at,
                    job.job_id
                )
            )
            self.sqlite_conn.commit()
            cursor.close()

    def get_jobs_for_session(self, session_id: str) -> List[Job]:
        """Get all jobs for a session."""
        cursor = self.sqlite_conn.cursor()
        cursor.execute(
            "SELECT * FROM autogenie_jobs WHERE session_id = ? ORDER BY created_at",
            (session_id,)
        )
        rows = cursor.fetchall()
        cursor.close()

        return [
            Job(
                job_id=row["job_id"],
                session_id=row["session_id"],
                type=row["type"],
                status=row["status"],
                inputs=json.loads(row["inputs"]) if row["inputs"] else {},
                result=json.loads(row["result"]) if row["result"] else None,
                error=row["error"],
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
                progress=json.loads(row["progress"]) if row["progress"] else None
            )
            for row in rows
        ]

    def get_session_jobs(self, session_id: str) -> List[Job]:
        """Alias for get_jobs_for_session (backward compatibility)."""
        return self.get_jobs_for_session(session_id)

    def delete_job(self, job_id: str) -> bool:
        """Delete a job by ID."""
        cursor = self.sqlite_conn.cursor()
        cursor.execute("DELETE FROM autogenie_jobs WHERE job_id = ?", (job_id,))
        deleted = cursor.rowcount > 0
        self.sqlite_conn.commit()
        cursor.close()
        return deleted

    # ========== Enhancer-Specific Operations ==========

    def update_loop_status(
        self,
        session_id: str,
        loop_status: str,
        current_iteration: Optional[int] = None,
        initial_score: Optional[float] = None,
        latest_score: Optional[float] = None
    ) -> None:
        """Update session loop status for enhancer workflow."""
        cursor = self.sqlite_conn.cursor()

        updates = ["loop_status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [loop_status]

        if current_iteration is not None:
            updates.append("current_iteration = ?")
            params.append(current_iteration)

        if initial_score is not None:
            updates.append("initial_score = ?")
            params.append(initial_score)

        if latest_score is not None:
            updates.append("latest_score = ?")
            params.append(latest_score)

        params.append(session_id)

        cursor.execute(
            f"UPDATE autogenie_sessions SET {', '.join(updates)} WHERE session_id = ?",
            tuple(params)
        )
        self.sqlite_conn.commit()
        cursor.close()

    def append_job_progress(self, job_id: str, event: Dict[str, Any]) -> None:
        """Atomically append a progress event to a job (thread-safe)."""
        with self._lock:
            cursor = self.sqlite_conn.cursor()
            cursor.execute("SELECT progress FROM autogenie_jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()

            if not row:
                cursor.close()
                return

            progress = json.loads(row["progress"]) if row["progress"] else {"events": []}
            if "events" not in progress:
                progress["events"] = []

            progress["events"].append(event)

            # Keep only last 100 events
            if len(progress["events"]) > 100:
                progress["events"] = progress["events"][-100:]

            progress["current"] = event

            cursor.execute(
                "UPDATE autogenie_jobs SET progress = ? WHERE job_id = ?",
                (json.dumps(progress), job_id)
            )
            self.sqlite_conn.commit()
            cursor.close()

    # ========== Iteration Management (Enhancer) ==========

    def create_iteration(self, session_id: str, iteration_number: int) -> Dict[str, Any]:
        """Create a new iteration for enhancer workflow."""
        iteration_id = str(uuid.uuid4())

        cursor = self.sqlite_conn.cursor()
        cursor.execute("""
            INSERT INTO autogenie_iterations (
                iteration_id, session_id, iteration_number, status, created_at
            ) VALUES (?, ?, ?, 'scoring', CURRENT_TIMESTAMP)
        """, (iteration_id, session_id, iteration_number))
        self.sqlite_conn.commit()
        cursor.close()

        return {
            "iteration_id": iteration_id,
            "session_id": session_id,
            "iteration_number": iteration_number,
            "status": "scoring"
        }

    def get_iteration(self, iteration_id: str) -> Optional[Dict[str, Any]]:
        """Get iteration by ID."""
        cursor = self.sqlite_conn.cursor()
        cursor.execute("SELECT * FROM autogenie_iterations WHERE iteration_id = ?", (iteration_id,))
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        return {
            "iteration_id": row["iteration_id"],
            "session_id": row["session_id"],
            "iteration_number": row["iteration_number"],
            "status": row["status"],
            "score_before": row["score_before"],
            "score_after": row["score_after"],
            "fixes_proposed": json.loads(row["fixes_proposed"]) if row["fixes_proposed"] else None,
            "fixes_applied": json.loads(row["fixes_applied"]) if row["fixes_applied"] else None,
            "score_job_id": row["score_job_id"],
            "plan_job_id": row["plan_job_id"],
            "apply_job_id": row["apply_job_id"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }

    def update_iteration(self, iteration: Dict[str, Any]) -> None:
        """Update an iteration."""
        cursor = self.sqlite_conn.cursor()
        cursor.execute("""
            UPDATE autogenie_iterations SET
                status = ?,
                score_before = ?,
                score_after = ?,
                fixes_proposed = ?,
                fixes_applied = ?,
                score_job_id = ?,
                plan_job_id = ?,
                apply_job_id = ?,
                completed_at = ?
            WHERE iteration_id = ?
        """, (
            iteration.get("status"),
            iteration.get("score_before"),
            iteration.get("score_after"),
            json.dumps(iteration.get("fixes_proposed")) if iteration.get("fixes_proposed") else None,
            json.dumps(iteration.get("fixes_applied")) if iteration.get("fixes_applied") else None,
            iteration.get("score_job_id"),
            iteration.get("plan_job_id"),
            iteration.get("apply_job_id"),
            iteration.get("completed_at"),
            iteration["iteration_id"]
        ))
        self.sqlite_conn.commit()
        cursor.close()

    def list_iterations(self, session_id: str) -> List[Dict[str, Any]]:
        """List iterations for a session."""
        cursor = self.sqlite_conn.cursor()
        cursor.execute(
            "SELECT * FROM autogenie_iterations WHERE session_id = ? ORDER BY iteration_number",
            (session_id,)
        )
        rows = cursor.fetchall()
        cursor.close()

        return [
            {
                "iteration_id": row["iteration_id"],
                "session_id": row["session_id"],
                "iteration_number": row["iteration_number"],
                "status": row["status"],
                "score_before": row["score_before"],
                "score_after": row["score_after"],
                "fixes_proposed": json.loads(row["fixes_proposed"]) if row["fixes_proposed"] else None,
                "fixes_applied": json.loads(row["fixes_applied"]) if row["fixes_applied"] else None,
                "created_at": row["created_at"],
                "completed_at": row["completed_at"],
            }
            for row in rows
        ]
