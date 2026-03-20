"""Combined FastAPI backend for AutoGenie.

Unifies Genie Lamp (create new spaces) and Genie Enhancer (improve existing spaces)
into a single tabbed application.
"""

import logging
import os
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from backend.services.session_store import SQLiteSessionStore
from backend.services.job_manager import JobManager
from backend.services.file_storage import LocalFileStorageService
from backend.middleware.auth import get_current_user

# Import route modules
from backend.lamp.routes import router as lamp_router, init_services as init_lamp_services
from backend.enhancer.routes import router as enhancer_router, init_services as init_enhancer_services


# Initialize FastAPI app
app = FastAPI(
    title="AutoGenie API",
    description="Unified platform for creating and enhancing Databricks Genie Spaces",
    version="1.0.0"
)


# Exception handler for JSON error responses
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Ensure all HTTP exceptions return JSON, not HTML."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code}
    )


# CORS middleware for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Serve Next.js static export
frontend_export_dir = os.getenv("FRONTEND_EXPORT_DIR", "frontend/out")
frontend_export_path = Path(frontend_export_dir)

logger.info(f"Frontend export dir: {frontend_export_dir}")
logger.info(f"Frontend path exists: {frontend_export_path.exists()}")
logger.info(f"Frontend path absolute: {frontend_export_path.absolute()}")

if frontend_export_path.exists():
    logger.info(f"Mounting frontend static assets from {frontend_export_path}")
    if (frontend_export_path / "_next").exists():
        app.mount("/_next", StaticFiles(directory=str(frontend_export_path / "_next")), name="next_static")
        logger.info("Mounted /_next static files")
else:
    logger.warning(f"Frontend export directory not found at {frontend_export_path.absolute()}")


# Initialize services
session_store = SQLiteSessionStore()
job_manager = JobManager(session_store)
file_storage = LocalFileStorageService()

# Initialize services in route modules
init_lamp_services(session_store, job_manager, file_storage)
init_enhancer_services(session_store, job_manager, file_storage)


# Mount route modules
app.include_router(lamp_router, prefix="/api/lamp")
app.include_router(enhancer_router, prefix="/api/enhancer")


# ========== Request/Response Models ==========

class CreateSessionRequest(BaseModel):
    user_id: str = "default"
    name: str = None
    workflow_type: str = "lamp"  # 'lamp' or 'enhancer'
    target_score: float = 0.90
    max_iterations: int = 3


class UpdateSessionNameRequest(BaseModel):
    name: str


# ========== Health Check ==========

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "autogenie", "version": "1.0.0"}


@app.get("/api/health")
async def api_health_check():
    """API health check endpoint."""
    return {"status": "healthy", "service": "autogenie", "version": "1.0.0"}


# ========== Shared Session Management ==========

@app.get("/api/sessions")
async def list_sessions(
    user_id: str = None,
    workflow_type: str = None,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user)
):
    """List all sessions with pagination.

    Returns sessions ordered by updated_at DESC (most recent first).
    Optionally filter by workflow_type ('lamp' or 'enhancer').
    """
    sessions, total_count = session_store.list_sessions(
        user_id=user_id,
        workflow_type=workflow_type,
        limit=limit,
        offset=offset
    )

    sessions_with_step = []
    for session in sessions:
        jobs = session_store.get_jobs_for_session(session["session_id"])
        completed_types = {job.type for job in jobs if job.status == "completed"}
        current_step = len(completed_types) + 1

        sessions_with_step.append({
            "session_id": session["session_id"],
            "name": session["name"],
            "workflow_type": session.get("workflow_type", "lamp"),
            "created_at": session["created_at"].isoformat() if isinstance(session["created_at"], datetime) else session["created_at"],
            "updated_at": session["updated_at"].isoformat() if isinstance(session["updated_at"], datetime) else session["updated_at"],
            "job_count": session["job_count"],
            "current_step": current_step
        })

    return {
        "sessions": sessions_with_step,
        "total_count": total_count
    }


@app.post("/api/sessions")
async def create_session(
    request: CreateSessionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new session.

    Optionally provide a custom name, otherwise defaults to timestamp.
    Specify workflow_type as 'lamp' (create new) or 'enhancer' (improve existing).
    """
    session_id = session_store.create_session(
        user_id=request.user_id,
        name=request.name,
        workflow_type=request.workflow_type,
        target_score=request.target_score,
        max_iterations=request.max_iterations
    )
    session = session_store.get_session_with_stats(session_id)

    return {
        "session_id": session_id,
        "name": session["name"],
        "workflow_type": session.get("workflow_type", "lamp"),
        "created_at": session["created_at"].isoformat() if isinstance(session["created_at"], datetime) else session["created_at"],
        "updated_at": session["updated_at"].isoformat() if isinstance(session["updated_at"], datetime) else session["updated_at"],
        "job_count": 0
    }


@app.put("/api/sessions/{session_id}")
async def update_session_name(
    session_id: str,
    request: UpdateSessionNameRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update session name."""
    session_store.update_session_name(session_id, request.name)
    session = session_store.get_session_with_stats(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "name": session["name"],
        "workflow_type": session.get("workflow_type", "lamp"),
        "created_at": session["created_at"].isoformat() if isinstance(session["created_at"], datetime) else session["created_at"],
        "updated_at": session["updated_at"].isoformat() if isinstance(session["updated_at"], datetime) else session["updated_at"],
        "job_count": session["job_count"]
    }


@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete session and all associated jobs."""
    # Cancel all running jobs for this session first
    cancelled_count = job_manager.cancel_session_jobs(session_id)

    # Clear job manager state
    job_manager.clear_state(session_id)

    # Delete session data and files
    session_store.delete_session(session_id)
    file_storage.delete_session_files(session_id)

    return {"success": True, "jobs_cancelled": cancelled_count}


@app.get("/api/sessions/{session_id}")
async def get_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get session details with all jobs for state restoration."""
    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    jobs = session_store.get_jobs_for_session(session_id)
    completed_types = {job.type for job in jobs if job.status == "completed"}
    current_step = len(completed_types) + 1

    return {
        "session_id": session_id,
        "name": session.get("name"),
        "workflow_type": session.get("workflow_type", "lamp"),
        "current_step": current_step,
        "loop_status": session.get("loop_status"),
        "target_score": session.get("target_score"),
        "initial_score": session.get("initial_score"),
        "latest_score": session.get("latest_score"),
        "deployed_space_id": session.get("deployed_space_id"),
        "deployed_space_url": session.get("deployed_space_url"),
        "jobs": [
            {
                "job_id": job.job_id,
                "type": job.type,
                "status": job.status,
                "result": job.result,
                "error": job.error,
                "progress": job.progress,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None
            }
            for job in jobs
        ]
    }


# ========== Shared Job Management ==========

@app.get("/api/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get job status and results."""
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job.job_id,
        "status": job.status,
        "type": job.type,
        "result": job.result,
        "error": job.error,
        "progress": job.progress,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None
    }


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Cancel a running job."""
    success = job_manager.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job_id": job_id}


@app.delete("/api/jobs/{job_id}")
async def delete_job(
    job_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a job record.

    Only completed, failed, or cancelled jobs can be deleted.
    """
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in ("pending", "running"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete job in '{job.status}' status. Cancel it first."
        )

    success = job_manager.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete job")

    return {"success": True, "job_id": job_id, "message": "Job deleted"}


# ========== Serve Frontend ==========

if frontend_export_path.exists():
    @app.get("/")
    async def serve_frontend_root():
        return FileResponse(str(frontend_export_path / "index.html"))

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Don't serve frontend for API routes
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")

        # Try to serve the exact file if it exists
        file_path = frontend_export_path / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))

        # Try with .html extension for clean URLs
        html_path = frontend_export_path / f"{full_path}.html"
        if html_path.exists():
            return FileResponse(str(html_path))

        # Try with index.html in directory
        dir_index = frontend_export_path / full_path / "index.html"
        if dir_index.exists():
            return FileResponse(str(dir_index))

        # Default to root index.html for client-side routing
        return FileResponse(str(frontend_export_path / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
