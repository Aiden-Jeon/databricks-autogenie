"""Background tasks for Enhancer workflow."""

import logging
from typing import Dict, Any, Optional
from pathlib import Path

from enhancer.api.genie_client import GenieConversationalClient
from enhancer.scoring.batch_scorer import BatchBenchmarkScorer
from enhancer.enhancement.category_enhancer import CategoryEnhancer
from enhancer.enhancement.applier import BatchApplier
from enhancer.llm.llm import DatabricksLLMClient
from enhancer.utils.sql import SQLExecutor
from enhancer.api.space_api import SpaceUpdater

logger = logging.getLogger(__name__)

# Global references
_session_store = None
_job_manager = None


def _get_app_token_or_fallback(user_token: str) -> str:
    """Get app OAuth token for operations that need broader scopes.

    Falls back to user token if app OAuth is unavailable.
    Used for LLM calls, SQL execution, and other operations where
    the user's OBO token may have insufficient scopes.
    """
    try:
        from backend.middleware.auth import get_app_oauth_token
        token = get_app_oauth_token()
        logger.info("App SP OAuth token available for operations")
        return token
    except Exception as e:
        logger.warning(f"App OAuth not available ({e}), using user token")
        return user_token


def set_session_store(store):
    """Set the global session store reference."""
    global _session_store
    _session_store = store


def set_job_manager(manager):
    """Set the global job manager reference for cancellation checks."""
    global _job_manager
    _job_manager = manager


class JobCancelledException(Exception):
    """Raised when a job is cancelled."""
    pass


def check_cancelled(job_id: str):
    """Check if job is cancelled and raise if so."""
    if _job_manager and job_id and _job_manager.is_cancelled(job_id):
        logger.info(f"Job {job_id} was cancelled")
        raise JobCancelledException(f"Job {job_id} was cancelled")


def update_job_progress(job_id: str, progress: Dict[str, Any]):
    """Update job progress in session store (thread-safe atomic operation)."""
    if _session_store:
        logger.info(f"[Progress] Appending event to job {job_id}: {progress.get('event_type')}")
        _session_store.append_job_progress(job_id, progress)


def run_score_job(
    session_id: str,
    space_id: str,
    databricks_host: str,
    databricks_token: str,
    warehouse_id: str,
    benchmarks: list,
    llm_endpoint: str = "databricks-gpt-5-2",
    job_id: Optional[str] = None,
    iteration_id: Optional[str] = None
) -> Dict[str, Any]:
    """Score benchmarks against Genie Space."""
    logger.info(f"Starting score job for session {session_id} (iteration: {iteration_id})")

    # App SP token for LLM/SQL (broader scopes), user token for Genie APIs (requires user permissions)
    app_token = _get_app_token_or_fallback(databricks_token)

    genie_client = GenieConversationalClient(databricks_host, databricks_token, space_id)
    llm_client = DatabricksLLMClient(databricks_host, app_token, llm_endpoint)
    sql_executor = SQLExecutor(databricks_host, app_token, warehouse_id)

    def progress_handler(*args, **kwargs):
        """Handle both old (4-arg) and new (1-dict) callback signatures."""
        if not job_id:
            return

        if len(args) == 1 and isinstance(args[0], dict):
            event = args[0]
            update_job_progress(job_id, event)
        elif len(args) >= 4:
            phase, current, total, message = args[0], args[1], args[2], args[3]
            update_job_progress(job_id, {
                "event_type": "progress",
                "phase": phase,
                "index": current,
                "total": total,
                "message": message
            })

    scorer = BatchBenchmarkScorer(
        genie_client,
        llm_client,
        sql_executor,
        progress_callback=progress_handler
    )

    results = scorer.score(benchmarks)

    logger.info(f"Score job completed: {results['score']:.1%}")

    if iteration_id and _session_store:
        try:
            iteration = _session_store.get_iteration(iteration_id)
            if iteration:
                iteration["score_before"] = results['score']
                iteration["score_job_id"] = job_id
                iteration["status"] = "planning"
                _session_store.update_iteration(iteration)
        except Exception as e:
            logger.error(f"Failed to update iteration: {e}", exc_info=True)

    return {
        "score": results["score"],
        "passed": results["passed"],
        "failed": results["failed"],
        "total": results["total"],
        "results": results["results"]
    }


def run_plan_job(
    session_id: str,
    space_id: str,
    databricks_host: str,
    databricks_token: str,
    failed_benchmarks: list,
    llm_endpoint: str = "databricks-gpt-5-2",
    job_id: Optional[str] = None,
    iteration_id: Optional[str] = None
) -> Dict[str, Any]:
    """Generate enhancement plan from failed benchmarks."""
    logger.info(f"Starting plan job for session {session_id} (iteration: {iteration_id})")

    app_token = _get_app_token_or_fallback(databricks_token)

    llm_client = DatabricksLLMClient(databricks_host, app_token, llm_endpoint)
    # Use user token for Space API (requires user's Genie Space permissions)
    space_api = SpaceUpdater(databricks_host, databricks_token)

    space_config = space_api.export_space(space_id)

    prompts_dir = Path(__file__).parent.parent.parent / "prompts"
    planner = CategoryEnhancer(llm_client, prompts_dir)

    grouped_fixes = planner.generate_plan(
        failed_benchmarks=failed_benchmarks,
        space_config=space_config
    )

    total_fixes = sum(len(fixes) for fixes in grouped_fixes.values())
    logger.info(f"Plan job completed: {total_fixes} fixes generated")

    if iteration_id and _session_store:
        try:
            iteration = _session_store.get_iteration(iteration_id)
            if iteration:
                iteration["fixes_proposed"] = grouped_fixes
                iteration["plan_job_id"] = job_id
                iteration["status"] = "awaiting_approval"
                _session_store.update_iteration(iteration)
        except Exception as e:
            logger.error(f"Failed to update iteration: {e}", exc_info=True)

    return {
        "total_fixes": total_fixes,
        "grouped_fixes": grouped_fixes
    }


def run_apply_job(
    session_id: str,
    space_id: str,
    databricks_host: str,
    databricks_token: str,
    warehouse_id: str,
    grouped_fixes: dict,
    dry_run: bool = False,
    job_id: Optional[str] = None
) -> Dict[str, Any]:
    """Apply enhancement fixes to Genie Space."""
    logger.info(f"Starting apply job for session {session_id} (dry_run={dry_run})")

    app_token = _get_app_token_or_fallback(databricks_token)

    # Use user token for Space API (requires user's Genie Space permissions)
    space_api = SpaceUpdater(databricks_host, databricks_token)
    sql_executor = SQLExecutor(databricks_host, app_token, warehouse_id)

    applier = BatchApplier(space_api, sql_executor)

    if dry_run:
        logger.info("Dry run mode - skipping actual application")
        return {
            "applied_count": 0,
            "dry_run": True,
            "success": True
        }

    result = applier.apply_all(space_id, grouped_fixes)

    logger.info(f"Apply job completed: {result.get('applied_count', 0)} fixes applied")

    return result


def run_validate_job(
    session_id: str,
    space_id: str,
    databricks_host: str,
    databricks_token: str,
    warehouse_id: str,
    benchmarks: list,
    initial_score: float,
    target_score: float,
    llm_endpoint: str = "databricks-gpt-5-2",
    job_id: Optional[str] = None
) -> Dict[str, Any]:
    """Validate enhancements by re-scoring benchmarks."""
    logger.info(f"Starting validate job for session {session_id}")

    score_result = run_score_job(
        session_id,
        space_id,
        databricks_host,
        databricks_token,
        warehouse_id,
        benchmarks,
        llm_endpoint,
        job_id
    )

    new_score = score_result["score"]
    improvement = new_score - initial_score
    target_reached = new_score >= target_score

    logger.info(f"Validate job completed: {new_score:.1%} (improvement: {improvement:+.1%})")

    return {
        "initial_score": initial_score,
        "new_score": new_score,
        "improvement": improvement,
        "target_score": target_score,
        "target_reached": target_reached,
        "results": score_result["results"]
    }


def run_auto_loop_job(
    session_id: str,
    space_id: str,
    databricks_host: str,
    databricks_token: str,
    warehouse_id: str,
    benchmarks: list,
    target_score: float = 0.90,
    max_iterations: int = 5,
    llm_endpoint: str = "databricks-gpt-5-2",
    job_id: Optional[str] = None
) -> Dict[str, Any]:
    """Run full auto-loop: Score → Plan → Apply → Repeat until target reached."""
    logger.info(f"Starting AUTO-LOOP for session {session_id}")
    logger.info(f"  Target: {target_score:.0%}, Max iterations: {max_iterations}")

    iterations_completed = []
    current_score = 0.0
    initial_score = None

    try:
        for iteration_num in range(1, max_iterations + 1):
            check_cancelled(job_id)

            logger.info(f"\n{'='*60}")
            logger.info(f"AUTO-LOOP: Iteration {iteration_num}/{max_iterations}")
            logger.info(f"{'='*60}")

            if job_id:
                update_job_progress(job_id, {
                    "event_type": "progress",
                    "phase": "auto_loop",
                    "iteration": iteration_num,
                    "max_iterations": max_iterations,
                    "current_score": current_score,
                    "target_score": target_score,
                    "message": f"Iteration {iteration_num}: Scoring..."
                })

            # Step 1: Score
            check_cancelled(job_id)
            score_result = run_score_job(
                session_id, space_id, databricks_host, databricks_token,
                warehouse_id, benchmarks, llm_endpoint
            )

            current_score = score_result["score"]
            if initial_score is None:
                initial_score = current_score

            logger.info(f"[Iteration {iteration_num}] Score: {current_score:.1%}")

            if current_score >= target_score:
                logger.info(f"Target score reached! {current_score:.1%} >= {target_score:.1%}")
                iterations_completed.append({
                    "iteration": iteration_num,
                    "score": current_score,
                    "status": "target_reached"
                })
                break

            failed_benchmarks = [r for r in score_result["results"] if not r.get("passed")]
            if not failed_benchmarks:
                logger.info("All benchmarks passed but score below target - stopping")
                iterations_completed.append({
                    "iteration": iteration_num,
                    "score": current_score,
                    "status": "no_failures"
                })
                break

            if job_id:
                update_job_progress(job_id, {
                    "event_type": "progress",
                    "phase": "auto_loop",
                    "iteration": iteration_num,
                    "current_score": current_score,
                    "message": f"Iteration {iteration_num}: Planning fixes for {len(failed_benchmarks)} failures..."
                })

            # Step 2: Plan
            check_cancelled(job_id)
            plan_result = run_plan_job(
                session_id, space_id, databricks_host, databricks_token,
                failed_benchmarks, llm_endpoint
            )

            grouped_fixes = plan_result["grouped_fixes"]
            total_fixes = plan_result["total_fixes"]

            if total_fixes == 0:
                logger.info("No fixes generated - stopping")
                iterations_completed.append({
                    "iteration": iteration_num,
                    "score": current_score,
                    "status": "no_fixes"
                })
                break

            logger.info(f"[Iteration {iteration_num}] Generated {total_fixes} fixes")

            if job_id:
                update_job_progress(job_id, {
                    "event_type": "progress",
                    "phase": "auto_loop",
                    "iteration": iteration_num,
                    "current_score": current_score,
                    "message": f"Iteration {iteration_num}: Applying {total_fixes} fixes..."
                })

            # Step 3: Apply ALL fixes
            check_cancelled(job_id)
            apply_result = run_apply_job(
                session_id, space_id, databricks_host, databricks_token,
                warehouse_id, grouped_fixes, dry_run=False
            )

            logger.info(f"[Iteration {iteration_num}] Applied {apply_result.get('applied_count', 0)} fixes")

            iterations_completed.append({
                "iteration": iteration_num,
                "score_before": current_score,
                "fixes_applied": total_fixes,
                "status": "completed"
            })

    except JobCancelledException:
        logger.info(f"AUTO-LOOP CANCELLED after {len(iterations_completed)} iterations")
        if _session_store:
            _session_store.update_loop_status(session_id, loop_status="cancelled")
        return {
            "initial_score": initial_score,
            "final_score": current_score,
            "improvement": (current_score - initial_score) if initial_score else 0,
            "target_score": target_score,
            "target_reached": False,
            "iterations_completed": len(iterations_completed),
            "iterations": iterations_completed,
            "cancelled": True
        }

    final_score = current_score
    improvement = final_score - initial_score if initial_score else 0
    target_reached = final_score >= target_score

    logger.info(f"\n{'='*60}")
    logger.info(f"AUTO-LOOP COMPLETE")
    logger.info(f"  Initial Score: {initial_score:.1%}")
    logger.info(f"  Final Score: {final_score:.1%}")
    logger.info(f"  Improvement: {improvement:+.1%}")
    logger.info(f"  Target Reached: {target_reached}")
    logger.info(f"  Iterations: {len(iterations_completed)}")
    logger.info(f"{'='*60}\n")

    if _session_store:
        _session_store.update_loop_status(
            session_id,
            loop_status="target_reached" if target_reached else "max_iterations",
            initial_score=initial_score,
            latest_score=final_score
        )

    return {
        "initial_score": initial_score,
        "final_score": final_score,
        "improvement": improvement,
        "target_score": target_score,
        "target_reached": target_reached,
        "iterations_completed": len(iterations_completed),
        "iterations": iterations_completed
    }
