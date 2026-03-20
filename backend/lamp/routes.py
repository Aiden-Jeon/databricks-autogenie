"""Lamp API routes - Generate Genie Spaces from requirements.

All routes are prefixed with /api/lamp when mounted.
"""

import os
import json
from datetime import datetime
from typing import List

from fastapi import APIRouter, File, UploadFile, BackgroundTasks, Depends, Form, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.middleware.auth import get_current_user
from backend.lamp.tasks import (
    run_parse_job,
    run_generate_job,
    run_validate_job,
    run_deploy_job,
    apply_validation_fixes,
    set_session_store as set_lamp_session_store,
)

router = APIRouter(tags=["Lamp"])

# These will be set by main.py
_session_store = None
_job_manager = None
_file_storage = None


def init_services(session_store, job_manager, file_storage):
    """Initialize services for Lamp routes."""
    global _session_store, _job_manager, _file_storage
    _session_store = session_store
    _job_manager = job_manager
    _file_storage = file_storage
    set_lamp_session_store(session_store)


# ========== Request/Response Models ==========

class GenerateRequest(BaseModel):
    session_id: str
    requirements_path: str
    model: str = "databricks-gpt-5-2"


class ValidateRequest(BaseModel):
    session_id: str
    config_path: str


class ValidationFix(BaseModel):
    old_catalog: str
    old_schema: str
    old_table: str
    new_catalog: str
    new_schema: str
    new_table: str


class FixValidationRequest(BaseModel):
    session_id: str
    config_path: str
    replacements: List[ValidationFix] = []
    bulk_catalog: str = None
    bulk_schema: str = None
    exclude_tables: List[str] = []


class DeployRequest(BaseModel):
    session_id: str
    config_path: str
    parent_path: str = None
    space_name: str = None


class ValidateBenchmarkRequest(BaseModel):
    session_id: str
    benchmarks: List[dict]


# ========== Parse Endpoint ==========

@router.post("/parse")
async def parse_files(
    session_id: str = Form(...),
    use_llm: bool = Form(True),
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: dict = Depends(get_current_user)
):
    """Parse uploaded requirement documents.

    Saves files to storage and starts async parsing job.
    """
    user_token = current_user["token"]

    file_paths = await _file_storage.save_uploads(files, session_id)

    session_dir = _file_storage.get_session_dir(session_id)
    output_path = f"{session_dir}/parsed_requirements.md"

    job = _job_manager.create_job("parse", session_id, {
        "file_paths": file_paths,
        "use_llm": use_llm,
        "output_path": output_path
    })

    background_tasks.add_task(
        _job_manager.run_job,
        job.job_id,
        run_parse_job,
        file_paths,
        use_llm,
        output_path,
        user_token
    )

    return {
        "job_id": job.job_id,
        "status": "running",
        "message": f"Parsing {len(files)} files"
    }


# ========== Generate Endpoint ==========

@router.post("/generate")
async def generate_config(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Generate Genie space configuration from requirements.

    Uses LLM to create configuration JSON from parsed requirements.
    """
    user_token = current_user["token"]

    session_dir = _file_storage.get_session_dir(request.session_id)
    output_path = f"{session_dir}/genie_space_config.json"

    job = _job_manager.create_job("generate", request.session_id, {
        "requirements_path": request.requirements_path,
        "output_path": output_path,
        "model": request.model
    })

    background_tasks.add_task(
        _job_manager.run_job,
        job.job_id,
        run_generate_job,
        request.requirements_path,
        output_path,
        request.model,
        user_token
    )

    return {
        "job_id": job.job_id,
        "status": "running",
        "message": f"Generating config with {request.model}"
    }


# ========== Validate Endpoint ==========

@router.post("/validate")
async def validate_config_endpoint(
    request: ValidateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Validate configuration against Unity Catalog.

    Requires OBO user token - validates token is a genuine user token
    before proceeding with SQL operations on the user's behalf.
    """
    user_token = current_user["token"]

    job = _job_manager.create_job("validate", request.session_id, {
        "config_path": request.config_path
    })

    background_tasks.add_task(
        _job_manager.run_job,
        job.job_id,
        run_validate_job,
        request.config_path,
        user_token
    )

    return {
        "job_id": job.job_id,
        "status": "running",
        "message": "Validating configuration"
    }


# ========== Fix Validation Endpoint ==========

@router.post("/validate/fix")
async def fix_validation(
    request: FixValidationRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Apply table/catalog/schema fixes and re-validate.

    Requires OBO user token. Updates configuration with corrected table
    references and re-runs validation with user's permissions.
    """
    user_token = current_user["token"]

    replacements_dict = [rep.dict() for rep in request.replacements] if request.replacements else []
    apply_validation_fixes(
        config_path=request.config_path,
        replacements=replacements_dict,
        bulk_catalog=request.bulk_catalog,
        bulk_schema=request.bulk_schema,
        exclude_tables=request.exclude_tables
    )

    job = _job_manager.create_job("validate", request.session_id, {
        "config_path": request.config_path
    })

    background_tasks.add_task(
        _job_manager.run_job,
        job.job_id,
        run_validate_job,
        request.config_path,
        user_token
    )

    return {
        "job_id": job.job_id,
        "status": "running",
        "message": "Applied fixes and re-validating"
    }


# ========== Deploy Endpoint ==========

@router.post("/deploy")
async def deploy_space_endpoint(
    request: DeployRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Deploy Genie space to Databricks.

    Requires OBO user token. The Genie space will be owned by the
    authenticated user.
    """
    user_token = current_user["token"]

    job = _job_manager.create_job("deploy", request.session_id, {
        "config_path": request.config_path,
        "parent_path": request.parent_path,
        "space_name": request.space_name
    })

    background_tasks.add_task(
        _job_manager.run_job,
        job.job_id,
        run_deploy_job,
        request.config_path,
        request.parent_path,
        user_token,
        request.space_name
    )

    return {
        "job_id": job.job_id,
        "status": "running",
        "message": "Deploying Genie space"
    }


# ========== Benchmark Validation Endpoint ==========

@router.post("/benchmark/validate")
async def validate_benchmarks_endpoint(
    request: ValidateBenchmarkRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Validate benchmark SQL queries against Unity Catalog.

    Requires OBO user token. Executes each benchmark's expected_sql query
    with user's permissions to verify correctness.
    """
    user_token = current_user["token"]

    from backend.lamp.benchmark_validator import validate_benchmark_queries

    job = _job_manager.create_job("benchmark_validate", request.session_id, {
        "total_benchmarks": len(request.benchmarks)
    })

    databricks_server_hostname = os.getenv("DATABRICKS_SERVER_HOSTNAME")
    databricks_http_path = os.getenv("DATABRICKS_HTTP_PATH")

    def run_benchmark_validation(**kwargs):
        return validate_benchmark_queries(
            benchmarks=request.benchmarks,
            databricks_server_hostname=databricks_server_hostname,
            databricks_http_path=databricks_http_path,
            databricks_token=user_token
        )

    background_tasks.add_task(
        _job_manager.run_job,
        job.job_id,
        run_benchmark_validation
    )

    return {
        "job_id": job.job_id,
        "status": "running",
        "message": f"Validating {len(request.benchmarks)} benchmark queries"
    }


# ========== File Content Endpoint ==========

@router.get("/files/{session_id}/{filename}/content")
async def get_file_content(
    session_id: str,
    filename: str,
    current_user: dict = Depends(get_current_user)
):
    """Get file content from session directory.

    Security: Only allows whitelisted files to prevent path traversal attacks.
    """
    allowed_files = [
        'parsed_requirements.md',
        'genie_space_config.json',
        'validation_report.json'
    ]

    if filename not in allowed_files:
        raise HTTPException(status_code=403, detail="File not allowed")

    session_dir = _file_storage.get_session_dir(session_id)
    file_path = f"{session_dir}/{filename}"

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        stats = os.stat(file_path)

        return {
            "content": content,
            "filename": filename,
            "size_bytes": stats.st_size,
            "line_count": len(content.splitlines()),
            "char_count": len(content)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")


# ========== Config Metadata Endpoint ==========

@router.get("/config/metadata")
async def get_config_metadata(
    config_path: str,
    current_user: dict = Depends(get_current_user)
):
    """Get metadata from a configuration file (space_name, description, etc.)"""
    if not config_path.startswith("storage/"):
        raise HTTPException(status_code=400, detail="Invalid config path")

    if not os.path.exists(config_path):
        raise HTTPException(status_code=404, detail="Configuration file not found")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        if "genie_space_config" in config:
            cfg = config["genie_space_config"]
        else:
            cfg = config

        return {
            "space_name": cfg.get("space_name", ""),
            "description": cfg.get("description", ""),
            "purpose": cfg.get("purpose", ""),
            "table_count": len(cfg.get("tables", [])),
            "join_count": len(cfg.get("join_specifications", []))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read config: {str(e)}")


# ========== Download Config Endpoint ==========

@router.get("/download/config/{session_id}")
async def download_config(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Download the generated Genie space configuration as JSON."""
    session_dir = _file_storage.get_session_dir(session_id)
    config_path = f"{session_dir}/genie_space_config.json"

    if not os.path.exists(config_path):
        raise HTTPException(status_code=404, detail="Configuration file not found")

    with open(config_path, 'r') as f:
        config = json.load(f)

    return JSONResponse(
        content=config,
        headers={
            "Content-Disposition": f"attachment; filename=genie_space_config_{session_id}.json"
        }
    )
