"""Background job task wrappers for Lamp pipeline functions."""

import asyncio
import os
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

# Import from genie package
from genie.pipeline.parser import parse_documents_async, parse_documents_async_with_progress
from genie.pipeline.generator import generate_config
from genie.pipeline.validator import validate_config
from genie.pipeline.deployer import deploy_space
from genie.utils.page_cache import PageCacheManager
from genie import update_config_catalog_schema_table, update_config_catalog_schema, remove_table_from_config

# Global reference to session store
_global_session_store = None


def set_session_store(store):
    """Set global session store reference for job tasks."""
    global _global_session_store
    _global_session_store = store


def _update_job_progress(job_id: str, progress_data: dict):
    """Update job progress in global session store."""
    if _global_session_store is None:
        return

    job = _global_session_store.get_job(job_id)
    if job:
        job.progress = progress_data
        _global_session_store.update_job(job)


def run_parse_job(
    file_paths: List[str],
    use_llm: bool,
    output_path: str,
    user_token: Optional[str] = None,
    job_id: str = None
) -> Dict:
    """Run parsing job on uploaded files with progress tracking.

    Uses app OAuth token for LLM operations (serving endpoints require specific permissions).
    Falls back to user token if app OAuth is not available.
    """
    input_dir = os.path.dirname(file_paths[0])
    databricks_host = os.getenv("DATABRICKS_HOST")

    # Try app OAuth for LLM (serving endpoints often require explicit permissions)
    # Fall back to user token if app OAuth fails
    try:
        from genie.auth.oauth_helper import get_app_oauth_token
        databricks_token = get_app_oauth_token()
        logger.info("Using app OAuth token for parsing (LLM operations)")
    except Exception as e:
        logger.warning(f"App OAuth not available ({e}), falling back to user token")
        if not user_token:
            raise ValueError("Neither app OAuth nor user token available for parsing")
        databricks_token = user_token
        logger.info("Using user token for parsing (fallback)")

    original_cwd = os.getcwd()

    try:
        os.chdir(project_root)

        if job_id is not None and _global_session_store is not None:
            from datetime import datetime

            progress_data = {
                "total_files": len(file_paths),
                "completed_files": 0,
                "files": [],
                "last_update": datetime.now().isoformat()
            }

            file_names = [os.path.basename(fp) for fp in file_paths]

            for file_name in file_names:
                is_pdf = file_name.lower().endswith('.pdf')
                progress_data["files"].append({
                    "name": file_name,
                    "status": "queued",
                    "pages_total": 1 if not is_pdf else None,
                    "pages_completed": 0
                })

            _update_job_progress(job_id, progress_data)

            page_cache_manager = PageCacheManager()

            def progress_callback(file_name: str, page_num: int, total_pages: int, is_cache_hit: bool, status: str, extracted_summary: dict = None):
                from datetime import datetime

                for file_entry in progress_data["files"]:
                    if file_entry["name"] == file_name:
                        file_entry["status"] = status
                        file_entry["pages_total"] = total_pages
                        file_entry["pages_completed"] = page_num
                        file_entry["cache_hit"] = is_cache_hit

                        if extracted_summary:
                            file_entry["extracted"] = extracted_summary

                        if status == "completed":
                            progress_data["completed_files"] += 1
                            progress_data["current_file"] = None
                        elif status == "processing":
                            progress_data["current_file"] = file_name
                            file_entry["current_page"] = page_num

                        break

                progress_data["last_update"] = datetime.now().isoformat()
                _update_job_progress(job_id, progress_data)

            def enrichment_progress_callback(stage: str, details: str):
                from datetime import datetime

                if "enrichment_progress" not in progress_data:
                    progress_data["enrichment_progress"] = []

                progress_data["enrichment_progress"].append({
                    "stage": stage,
                    "details": details,
                    "timestamp": datetime.now().isoformat()
                })
                progress_data["last_update"] = datetime.now().isoformat()
                _update_job_progress(job_id, progress_data)

            result = asyncio.run(parse_documents_async_with_progress(
                input_dir=input_dir,
                output_path=output_path,
                use_llm=use_llm,
                databricks_host=databricks_host,
                databricks_token=databricks_token,
                verbose=False,
                progress_callback=progress_callback,
                enrichment_progress_callback=enrichment_progress_callback,
                page_cache_manager=page_cache_manager
            ))
        else:
            result = asyncio.run(parse_documents_async(
                input_dir=input_dir,
                output_path=output_path,
                use_llm=use_llm,
                databricks_host=databricks_host,
                databricks_token=databricks_token,
                verbose=False
            ))

        file_stats = {}
        if os.path.exists(output_path):
            stats = os.stat(output_path)
            with open(output_path, 'r', encoding='utf-8') as f:
                content = f.read()
            file_stats = {
                "size_bytes": stats.st_size,
                "line_count": len(content.splitlines()),
                "char_count": len(content)
            }

        return {
            "output_path": output_path,
            "tables_found": result.get("tables_count", 0),
            "files_parsed": len(file_paths),
            "cache_stats": result.get("cache_stats", {}),
            "enrichment_reasoning": result.get("enrichment_reasoning"),
            "parsed_file_stats": file_stats
        }
    finally:
        os.chdir(original_cwd)


def run_generate_job(
    requirements_path: str,
    output_path: str,
    model: str,
    user_token: Optional[str] = None,
    job_id: str = None
) -> Dict:
    """Generate Genie space configuration from requirements.

    Uses app OAuth token for LLM operations (serving endpoints require specific permissions).
    Falls back to user token if app OAuth is not available.
    """
    original_cwd = os.getcwd()
    databricks_host = os.getenv("DATABRICKS_HOST")

    # Try app OAuth for LLM (serving endpoints often require explicit permissions)
    try:
        from genie.auth.oauth_helper import get_app_oauth_token
        databricks_token = get_app_oauth_token()
        logger.info("Using app OAuth token for generation (LLM operations)")
    except Exception as e:
        logger.warning(f"App OAuth not available ({e}), falling back to user token")
        if not user_token:
            raise ValueError("Neither app OAuth nor user token available for generation")
        databricks_token = user_token
        logger.info("Using user token for generation (fallback)")

    try:
        os.chdir(project_root)

        result = generate_config(
            requirements_path=requirements_path,
            output_path=output_path,
            model=model,
            databricks_host=databricks_host,
            databricks_token=databricks_token,
            validate_sql=True,
            verbose=False
        )

        reasoning = result.get("reasoning", {})
        config = result.get("genie_space_config", {})
        tables_count = len(config.get("tables", []))
        instructions_count = len(config.get("instructions", []))

        return {
            "output_path": output_path,
            "reasoning": reasoning,
            "tables_count": tables_count,
            "instructions_count": instructions_count
        }
    finally:
        os.chdir(original_cwd)


def _get_app_token() -> Optional[str]:
    """Try to get the app's service principal OAuth token for fallback auth."""
    try:
        from backend.middleware.auth import get_app_oauth_token
        return get_app_oauth_token()
    except Exception as e:
        logger.debug(f"Could not get app OAuth token for fallback: {e}")
        return None


def run_validate_job(config_path: str, user_token: str, job_id: str = None) -> Dict:
    """Validate Genie space configuration against Unity Catalog.

    Uses user's OAuth token for SQL operations (on-behalf authentication).
    Falls back to app's service principal token if user token lacks permissions.
    """
    if not user_token:
        raise ValueError("user_token is required for validation (SQL operations)")

    original_cwd = os.getcwd()
    databricks_host = os.getenv("DATABRICKS_HOST")

    # Get app SP token as fallback for when user token has stale/narrow scopes
    fallback_token = _get_app_token()
    if fallback_token:
        logger.info("App SP token available as fallback for validation")

    logger.info("Using user token for validation (SQL operations with user permissions)")

    try:
        os.chdir(project_root)

        report = validate_config(
            config_path=config_path,
            databricks_host=databricks_host,
            databricks_token=user_token,
            fallback_token=fallback_token,
            verbose=False
        )

        return {
            "has_errors": report.has_errors(),
            "tables_valid": report.tables_valid,
            "tables_invalid": report.tables_invalid,
            "issues": [
                {
                    "type": issue.type,
                    "severity": issue.severity,
                    "table": issue.table,
                    "column": issue.column,
                    "location": issue.location,
                    "message": issue.message
                }
                for issue in report.issues
            ]
        }
    finally:
        os.chdir(original_cwd)


def run_deploy_job(
    config_path: str,
    parent_path: str = None,
    user_token: Optional[str] = None,
    space_name: Optional[str] = None,
    job_id: str = None
) -> Dict:
    """Deploy Genie space to Databricks.

    Uses user's OAuth token for deployment (on-behalf authentication).
    The Genie space will be owned by the user.
    """
    if not user_token:
        raise ValueError("user_token is required for deployment (on-behalf operation)")

    original_cwd = os.getcwd()
    databricks_host = os.getenv("DATABRICKS_HOST")

    logger.info("Using user token for deployment (Genie space created on user's behalf)")

    try:
        os.chdir(project_root)

        if space_name:
            import json
            import tempfile

            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            if "genie_space_config" in config_data:
                config_data["genie_space_config"]["space_name"] = space_name
            else:
                config_data["space_name"] = space_name

            temp_fd, temp_config_path = tempfile.mkstemp(suffix='.json', prefix='genie_config_')
            os.close(temp_fd)

            with open(temp_config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            config_path = temp_config_path

        result = deploy_space(
            config_path=config_path,
            databricks_host=databricks_host,
            databricks_token=user_token,
            parent_path=parent_path,
            verbose=True
        )

        logger.info(f"Deployment successful: space_id={result.get('space_id')}")

        return {
            "space_id": result["space_id"],
            "space_url": result["space_url"]
        }
    finally:
        os.chdir(original_cwd)


def apply_validation_fixes(
    config_path: str,
    replacements: List[Dict] = None,
    bulk_catalog: str = None,
    bulk_schema: str = None,
    exclude_tables: List[str] = None
) -> None:
    """Apply table/catalog/schema replacements to config."""
    if exclude_tables:
        for table_name in exclude_tables:
            parts = table_name.split('.')
            if len(parts) == 3:
                catalog, schema, table = parts
                remove_table_from_config(
                    config_path=config_path,
                    catalog=catalog,
                    schema=schema,
                    table=table
                )

    if bulk_catalog and bulk_schema:
        import json
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        if "genie_space_config" in config:
            genie_config = config["genie_space_config"]
        else:
            genie_config = config

        catalog_schemas = set()
        for table_def in genie_config.get("tables", []):
            old_cat = table_def.get("catalog_name")
            old_sch = table_def.get("schema_name")
            if old_cat and old_sch:
                catalog_schemas.add((old_cat, old_sch))

        for old_catalog, old_schema in catalog_schemas:
            update_config_catalog_schema(
                config_path=config_path,
                old_catalog=old_catalog,
                old_schema=old_schema,
                new_catalog=bulk_catalog,
                new_schema=bulk_schema
            )

    if replacements:
        for rep in replacements:
            update_config_catalog_schema_table(
                config_path=config_path,
                old_catalog=rep["old_catalog"],
                old_schema=rep["old_schema"],
                old_table=rep["old_table"],
                new_catalog=rep["new_catalog"],
                new_schema=rep["new_schema"],
                new_table=rep["new_table"]
            )
