"""Enhancer API routes - Improve existing Genie Spaces.

All routes are prefixed with /api/enhancer when mounted.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, File, UploadFile, BackgroundTasks, Form, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.middleware.auth import get_user_token, get_workspace_host, get_app_oauth_token
from backend.enhancer.tasks import (
    run_score_job,
    run_plan_job,
    run_apply_job,
    run_validate_job,
    run_auto_loop_job,
    set_session_store as set_enhancer_session_store,
    set_job_manager as set_enhancer_job_manager,
)

router = APIRouter(tags=["Enhancer"])
logger = logging.getLogger(__name__)

# These will be set by main.py
_session_store = None
_job_manager = None
_file_storage = None
_iteration_controller = None


def init_services(session_store, job_manager, file_storage):
    """Initialize services for Enhancer routes."""
    global _session_store, _job_manager, _file_storage, _iteration_controller
    _session_store = session_store
    _job_manager = job_manager
    _file_storage = file_storage
    set_enhancer_session_store(session_store)
    set_enhancer_job_manager(job_manager)

    # Initialize iteration controller
    from backend.enhancer.iteration_controller import IterationController
    _iteration_controller = IterationController(session_store, job_manager)


# ========== Request/Response Models ==========

class WorkspaceConfig(BaseModel):
    """Databricks workspace configuration."""
    warehouse_id: str
    space_id: str
    llm_endpoint: str = "databricks-gpt-5-2"


class ScoreRequest(BaseModel):
    session_id: str
    workspace_config: WorkspaceConfig
    benchmarks: List[dict]


class PlanRequest(BaseModel):
    session_id: str
    workspace_config: WorkspaceConfig
    failed_benchmarks: List[dict]
    iteration_id: Optional[str] = None


class ApplyRequest(BaseModel):
    session_id: str
    workspace_config: WorkspaceConfig
    grouped_fixes: dict
    dry_run: bool = False


class ValidateRequest(BaseModel):
    session_id: str
    workspace_config: WorkspaceConfig
    benchmarks: List[dict]
    initial_score: float
    target_score: float = 0.90


class AutoLoopRequest(BaseModel):
    workspace_config: WorkspaceConfig
    benchmarks: list
    target_score: float = 0.90
    max_iterations: int = 5


class IterationStartRequest(BaseModel):
    workspace_config: WorkspaceConfig
    benchmarks: List[dict]


class IterationApproveRequest(BaseModel):
    approved_fixes: Dict[str, Any]


class JobResponse(BaseModel):
    job_id: str
    type: str
    status: str
    progress: Optional[dict] = None
    result: Optional[dict] = None
    error: Optional[str] = None


# ========== Workspace Configuration ==========

@router.get("/workspace/config")
async def get_workspace_config():
    """Get workspace configuration."""
    host = get_workspace_host()
    return {
        "host": host,
        "auth_mode": "oauth_with_user_token",
        "description": "User operations use X-Forwarded-Access-Token, app operations use OAuth"
    }


@router.get("/workspace/warehouses")
async def list_warehouses(request: Request):
    """List SQL Warehouses accessible to the user (OBO)."""
    try:
        from databricks.sdk import WorkspaceClient

        user_token = get_user_token(request)
        host = get_workspace_host()

        # Clear OAuth env vars to prevent conflict with PAT auth
        saved_client_id = os.environ.pop('DATABRICKS_CLIENT_ID', None)
        saved_client_secret = os.environ.pop('DATABRICKS_CLIENT_SECRET', None)

        try:
            client = WorkspaceClient(host=host, token=user_token)

            warehouses = []
            for wh in client.warehouses.list():
                warehouses.append({
                    "id": wh.id,
                    "name": wh.name,
                    "state": wh.state.value if wh.state else "UNKNOWN",
                    "cluster_size": wh.cluster_size if hasattr(wh, 'cluster_size') else None
                })

            return {"warehouses": warehouses}
        finally:
            if saved_client_id:
                os.environ['DATABRICKS_CLIENT_ID'] = saved_client_id
            if saved_client_secret:
                os.environ['DATABRICKS_CLIENT_SECRET'] = saved_client_secret
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list warehouses: {str(e)}")


@router.get("/workspace/spaces")
async def list_genie_spaces(request: Request):
    """List Genie Spaces accessible to the user (OBO)."""
    try:
        import requests as http_requests

        user_token = get_user_token(request)
        host = get_workspace_host()

        url = f"{host}/api/2.0/genie/spaces"
        headers = {
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json"
        }

        response = http_requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        spaces = []
        for space in data.get('spaces', []):
            spaces.append({
                "id": space.get('space_id'),
                "name": space.get('name') or space.get('title') or 'Unnamed Space',
                "description": space.get('description', '')
            })

        return {"spaces": spaces}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list Genie spaces: {str(e)}")


# ========== Enhancement Workflow Jobs ==========

@router.post("/jobs/score")
async def start_score_job(
    score_request: ScoreRequest,
    request: Request,
    background_tasks: BackgroundTasks
):
    """Start benchmark scoring job (OBO)."""
    user_token = get_user_token(request)
    host = get_workspace_host()

    job = _job_manager.create_job("score", score_request.session_id, {
        "workspace_config": score_request.workspace_config.dict(),
        "benchmarks": score_request.benchmarks
    })

    background_tasks.add_task(
        _job_manager.run_job,
        job.job_id,
        run_score_job,
        score_request.session_id,
        score_request.workspace_config.space_id,
        host,
        user_token,
        score_request.workspace_config.warehouse_id,
        score_request.benchmarks,
        score_request.workspace_config.llm_endpoint
    )

    return {"job_id": job.job_id, "status": "pending"}


@router.post("/jobs/plan")
async def start_plan_job(
    plan_request: PlanRequest,
    request: Request,
    background_tasks: BackgroundTasks
):
    """Start enhancement planning job (OBO)."""
    user_token = get_user_token(request)
    host = get_workspace_host()

    job = _job_manager.create_job("plan", plan_request.session_id, {
        "workspace_config": plan_request.workspace_config.dict(),
        "failed_benchmarks": plan_request.failed_benchmarks
    })

    background_tasks.add_task(
        _job_manager.run_job,
        job.job_id,
        run_plan_job,
        plan_request.session_id,
        plan_request.workspace_config.space_id,
        host,
        user_token,
        plan_request.failed_benchmarks,
        plan_request.workspace_config.llm_endpoint,
        iteration_id=plan_request.iteration_id
    )

    return {"job_id": job.job_id, "status": "pending"}


@router.post("/jobs/apply")
async def start_apply_job(
    apply_request: ApplyRequest,
    request: Request,
    background_tasks: BackgroundTasks
):
    """Start fix application job (OBO)."""
    user_token = get_user_token(request)
    host = get_workspace_host()

    job = _job_manager.create_job("apply", apply_request.session_id, {
        "workspace_config": apply_request.workspace_config.dict(),
        "grouped_fixes": apply_request.grouped_fixes,
        "dry_run": apply_request.dry_run
    })

    background_tasks.add_task(
        _job_manager.run_job,
        job.job_id,
        run_apply_job,
        apply_request.session_id,
        apply_request.workspace_config.space_id,
        host,
        user_token,
        apply_request.workspace_config.warehouse_id,
        apply_request.grouped_fixes,
        apply_request.dry_run
    )

    return {"job_id": job.job_id, "status": "pending"}


@router.post("/jobs/validate")
async def start_validate_job(
    validate_request: ValidateRequest,
    request: Request,
    background_tasks: BackgroundTasks
):
    """Start validation job (OBO)."""
    user_token = get_user_token(request)
    host = get_workspace_host()

    job = _job_manager.create_job("validate", validate_request.session_id, {
        "workspace_config": validate_request.workspace_config.dict(),
        "benchmarks": validate_request.benchmarks,
        "initial_score": validate_request.initial_score,
        "target_score": validate_request.target_score
    })

    background_tasks.add_task(
        _job_manager.run_job,
        job.job_id,
        run_validate_job,
        validate_request.session_id,
        validate_request.workspace_config.space_id,
        host,
        user_token,
        validate_request.workspace_config.warehouse_id,
        validate_request.benchmarks,
        validate_request.initial_score,
        validate_request.target_score,
        validate_request.workspace_config.llm_endpoint
    )

    return {"job_id": job.job_id, "status": "pending"}


# ========== Auto-Loop ==========

@router.post("/sessions/{session_id}/auto-loop")
async def start_auto_loop(
    session_id: str,
    request_body: AutoLoopRequest,
    request: Request,
    background_tasks: BackgroundTasks
):
    """Start automatic enhancement loop (OBO).

    Runs Score → Plan → Apply → Repeat until target score reached or max iterations.
    """
    host = get_workspace_host()
    user_token = get_user_token(request)

    _session_store.update_loop_status(
        session_id,
        loop_status="auto_running"
    )

    job = _job_manager.create_job("auto_loop", session_id, {
        "workspace_config": request_body.workspace_config.model_dump(),
        "benchmarks": request_body.benchmarks,
        "target_score": request_body.target_score,
        "max_iterations": request_body.max_iterations
    })

    background_tasks.add_task(
        _job_manager.run_job,
        job.job_id,
        run_auto_loop_job,
        session_id,
        request_body.workspace_config.space_id,
        host,
        user_token,
        request_body.workspace_config.warehouse_id,
        request_body.benchmarks,
        request_body.target_score,
        request_body.max_iterations,
        request_body.workspace_config.llm_endpoint
    )

    return {
        "job_id": job.job_id,
        "status": "auto_loop_started",
        "target_score": request_body.target_score,
        "max_iterations": request_body.max_iterations
    }


# ========== Iterations ==========

@router.post("/sessions/{session_id}/iterations/start")
async def start_iteration(
    session_id: str,
    iteration_request: IterationStartRequest,
    request: Request,
    background_tasks: BackgroundTasks
):
    """Start a new iteration (score + plan) (OBO)."""
    user_token = get_user_token(request)
    host = get_workspace_host()

    iteration_id, _, _ = _iteration_controller.start_iteration(
        session_id,
        iteration_request.workspace_config.dict(),
        iteration_request.benchmarks
    )

    score_job = _job_manager.create_job("score", session_id, {
        "iteration_id": iteration_id,
        "workspace_config": iteration_request.workspace_config.dict(),
        "benchmarks": iteration_request.benchmarks
    })

    background_tasks.add_task(
        _job_manager.run_job,
        score_job.job_id,
        run_score_job,
        session_id,
        iteration_request.workspace_config.space_id,
        host,
        user_token,
        iteration_request.workspace_config.warehouse_id,
        iteration_request.benchmarks,
        iteration_request.workspace_config.llm_endpoint,
        iteration_id=iteration_id
    )

    return {
        "iteration_id": iteration_id,
        "score_job_id": score_job.job_id,
        "status": "scoring"
    }


@router.get("/iterations/{iteration_id}")
async def get_iteration(iteration_id: str):
    """Get iteration status."""
    return _iteration_controller.get_iteration_status(iteration_id)


@router.get("/sessions/{session_id}/iterations")
async def get_session_iterations(session_id: str):
    """Get all iterations for a session."""
    return {
        "iterations": _iteration_controller.get_iteration_history(session_id)
    }


@router.post("/iterations/{iteration_id}/approve")
async def approve_fixes(
    iteration_id: str,
    approve_request: IterationApproveRequest,
    request: Request,
    background_tasks: BackgroundTasks
):
    """Approve fixes and start apply job (OBO)."""
    user_token = get_user_token(request)
    host = get_workspace_host()

    iteration = _session_store.get_iteration(iteration_id)
    if not iteration:
        raise HTTPException(status_code=404, detail="Iteration not found")

    session = _session_store.get_session(iteration["session_id"])
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    _iteration_controller.approve_and_apply(iteration_id, approve_request.approved_fixes)

    score_job = _session_store.get_job(iteration["score_job_id"])
    workspace_config_dict = score_job.inputs.get("workspace_config", {})

    apply_job = _job_manager.create_job("apply", iteration["session_id"], {
        "iteration_id": iteration_id,
        "workspace_config": workspace_config_dict,
        "grouped_fixes": approve_request.approved_fixes,
        "dry_run": False
    })

    background_tasks.add_task(
        _job_manager.run_job,
        apply_job.job_id,
        run_apply_job,
        iteration["session_id"],
        workspace_config_dict["space_id"],
        host,
        user_token,
        workspace_config_dict["warehouse_id"],
        approve_request.approved_fixes,
        False
    )

    return {
        "apply_job_id": apply_job.job_id,
        "status": "applying"
    }


@router.post("/iterations/{iteration_id}/cancel")
async def cancel_iteration(iteration_id: str):
    """Cancel current iteration and stop loop."""
    _iteration_controller.cancel_iteration(iteration_id)
    return {"success": True}


# ========== Space Operations ==========

@router.post("/sessions/{session_id}/clone-space")
async def clone_production_space(
    session_id: str,
    space_id: str = Form(...),
    request: Request = None
):
    """Clone production space for safe testing (OBO)."""
    try:
        user_token = get_user_token(request)
        host = get_workspace_host()

        from enhancer.api.space_cloner import SpaceCloner

        cloner = SpaceCloner(host, user_token)
        result = cloner.setup_three_spaces(
            production_space_id=space_id,
            working_suffix="_dev_working",
            best_suffix="_dev_best"
        )

        if result["success"]:
            return {
                "success": True,
                "production_id": result["production_id"],
                "dev_working_id": result["dev_working_id"],
                "dev_best_id": result["dev_best_id"],
                "production_name": result["production_name"]
            }
        else:
            raise HTTPException(status_code=500, detail=result["error"])

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clone space: {str(e)}")


@router.post("/sessions/{session_id}/copy-to-best")
async def copy_to_best_space(
    session_id: str,
    source_space_id: str = Form(...),
    target_space_id: str = Form(...),
    request: Request = None
):
    """Copy configuration from working space to best space (OBO)."""
    try:
        user_token = get_user_token(request)
        host = get_workspace_host()

        from enhancer.api.space_cloner import SpaceCloner

        cloner = SpaceCloner(host, user_token)
        result = cloner.copy_config(source_space_id, target_space_id)

        if result["success"]:
            return {"success": True, "message": "Configuration copied to best space"}
        else:
            raise HTTPException(status_code=500, detail=result["error"])

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to copy config: {str(e)}")


@router.post("/sessions/{session_id}/promote-to-production")
async def promote_to_production(
    session_id: str,
    source_space_id: str = Form(...),
    target_space_id: str = Form(...),
    request: Request = None
):
    """Promote best configuration to production space (OBO)."""
    try:
        user_token = get_user_token(request)
        host = get_workspace_host()

        from enhancer.api.space_cloner import SpaceCloner

        cloner = SpaceCloner(host, user_token)
        result = cloner.copy_config(source_space_id, target_space_id)

        if result["success"]:
            return {"success": True, "message": "Configuration promoted to production"}
        else:
            raise HTTPException(status_code=500, detail=result["error"])

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to promote to production: {str(e)}")


# ========== File Upload ==========

@router.post("/sessions/{session_id}/upload")
async def upload_file(
    session_id: str,
    file: UploadFile = File(...)
):
    """Upload and validate benchmark file for a session."""
    from enhancer.utils.benchmark_validator import BenchmarkValidator

    try:
        content = await file.read()

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON format: {str(e)}"
            )

        is_valid, errors, valid_benchmarks = BenchmarkValidator.validate_benchmarks(data)

        if not is_valid:
            error_message = BenchmarkValidator.format_errors(errors)
            raise HTTPException(
                status_code=400,
                detail=error_message
            )

        file_path = _file_storage.save_file(session_id, file.filename, content)

        return {
            "filename": file.filename,
            "path": file_path,
            "benchmark_count": len(valid_benchmarks),
            "benchmarks": valid_benchmarks
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process file: {str(e)}"
        )


@router.get("/benchmarks/template")
async def get_benchmark_template():
    """Get benchmark template for users."""
    from enhancer.utils.benchmark_validator import BenchmarkValidator

    return {
        "template": BenchmarkValidator.get_template(),
        "example": BenchmarkValidator.get_example_benchmark(),
        "required_fields": BenchmarkValidator.REQUIRED_FIELDS,
        "optional_fields": BenchmarkValidator.OPTIONAL_FIELDS
    }
