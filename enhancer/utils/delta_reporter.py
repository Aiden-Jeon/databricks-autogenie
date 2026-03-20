"""
Enhanced Delta Table Reporter

Writes enhancement progress to normalized Delta tables optimized for:
- Databricks Apps dashboards
- SQL queries and analytics
- Rollback capability
- Operational monitoring
"""

import uuid
import logging
from datetime import datetime
from typing import Dict, List, Any
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DeltaReporter:
    """Enhanced reporter that writes to normalized Delta tables."""

    def __init__(self, catalog: str = None, schema: str = None, spark=None):
        """
        Initialize Delta reporter.

        Args:
            catalog: Catalog name (defaults to CATALOG env var or "sandbox")
            schema: Schema name (defaults to SCHEMA env var or "genie_enhancement")
            spark: Spark session (auto-detected in Databricks)
        """
        import os
        self.catalog = catalog or os.getenv("CATALOG", "sandbox")
        self.schema = schema or os.getenv("SCHEMA", "genie_enhancement")
        self.full_name = f"{self.catalog}.{self.schema}"
        self.spark = spark or self._get_spark_session()
        self.current_run_id = None

    def _get_spark_session(self):
        """Get Spark session (works in Databricks and local PySpark)."""
        try:
            from pyspark.sql import SparkSession
            return SparkSession.builder.getOrCreate()
        except ImportError:
            logger.warning("PySpark not available - Delta reporting disabled")
            return None

    def start_run(
        self,
        space_id: str,
        space_name: str,
        config: Dict[str, Any],
        triggered_by: str = None
    ) -> str:
        """
        Start a new enhancement run.

        Args:
            space_id: Genie Space ID
            space_name: Human-readable space name
            config: Enhancement configuration
            triggered_by: User or service principal

        Returns:
            run_id (UUID)
        """
        if not self.spark:
            logger.warning("Spark not available - skipping run start")
            return str(uuid.uuid4())

        self.current_run_id = str(uuid.uuid4())
        started_at = datetime.now()

        run_data = {
            "run_id": self.current_run_id,
            "space_id": space_id,
            "space_name": space_name,
            "started_at": started_at,
            "completed_at": None,
            "status": "RUNNING",
            "target_score": config.get("target_score", 0.90),
            "max_iterations": config.get("max_iterations", 10),
            "llm_endpoint": config.get("llm_endpoint", "unknown"),
            "benchmark_source": config.get("benchmark_source", ""),
            "initial_score": None,  # Set after first scoring
            "final_score": None,
            "score_improvement": None,
            "iterations_completed": 0,
            "total_changes_applied": 0,
            "duration_seconds": None,
            "error_message": None,
            "triggered_by": triggered_by or "unknown",
            "created_at": started_at,
            "updated_at": started_at
        }

        try:
            df = self.spark.createDataFrame([run_data])
            df.write.format("delta").mode("append").saveAsTable(
                f"{self.full_name}.enhancement_runs"
            )
            logger.info(f"✅ Started run tracking: {self.current_run_id}")
        except Exception as e:
            logger.error(f"Failed to write run start: {e}")

        return self.current_run_id

    def report_iteration(
        self,
        iteration_number: int,
        benchmark_results: Dict,
        changes_made: List[Dict],
        duration_seconds: float,
        config_snapshot_path: str = None,
        llm_stats: Dict = None
    ):
        """
        Report iteration results to Delta tables.

        Args:
            iteration_number: Iteration sequence number
            benchmark_results: Results from BenchmarkScorer
            changes_made: List of changes applied
            duration_seconds: Iteration duration
            config_snapshot_path: Path to config snapshot (for rollback)
            llm_stats: LLM usage statistics
        """
        if not self.spark or not self.current_run_id:
            logger.warning("Spark not available or no run started - skipping iteration report")
            return

        started_at = datetime.now()

        # Calculate deltas and aggregations
        score = benchmark_results.get("score", 0.0)
        score_delta = self._calculate_score_delta(iteration_number, score)

        # Count changes by type
        changes_by_type = {}
        for change in changes_made:
            change_type = change.get("type", "unknown")
            changes_by_type[change_type] = changes_by_type.get(change_type, 0) + 1

        # Count failures by category
        failures_by_category = {}
        for result in benchmark_results.get("results", []):
            if not result.get("passed"):
                category = result.get("failure_category", "unknown")
                failures_by_category[category] = failures_by_category.get(category, 0) + 1

        top_failure_category = max(failures_by_category, key=failures_by_category.get) if failures_by_category else None

        # Iteration data
        iteration_data = {
            "run_id": self.current_run_id,
            "iteration_number": iteration_number,
            "started_at": started_at,
            "completed_at": datetime.now(),
            "duration_seconds": duration_seconds,
            "score": score,
            "score_delta": score_delta,
            "total_benchmarks": benchmark_results.get("total", 0),
            "passed": benchmark_results.get("passed", 0),
            "failed": benchmark_results.get("failed", 0),
            "num_changes": len(changes_made),
            "changes_by_type": changes_by_type,
            "failures_by_category": failures_by_category,
            "top_failure_category": top_failure_category,
            "llm_calls": llm_stats.get("calls", 0) if llm_stats else None,
            "llm_tokens_used": llm_stats.get("tokens", 0) if llm_stats else None,
            "llm_cost_estimate": llm_stats.get("cost_usd", 0.0) if llm_stats else None,
            "config_snapshot_path": config_snapshot_path,
            "can_rollback": config_snapshot_path is not None,
            "status": "COMPLETED",
            "error_message": None,
            "created_at": started_at
        }

        try:
            # Write iteration
            df = self.spark.createDataFrame([iteration_data])
            df.write.format("delta").mode("append").saveAsTable(
                f"{self.full_name}.enhancement_iterations"
            )

            # Write individual changes (exploded)
            if changes_made:
                self._write_changes(iteration_number, changes_made)

            # Write benchmark results
            self._write_benchmark_results(iteration_number, benchmark_results)

            logger.info(f"✅ Reported iteration {iteration_number} to Delta tables")

        except Exception as e:
            logger.error(f"Failed to write iteration {iteration_number}: {e}")

    def _write_changes(self, iteration_number: int, changes: List[Dict]):
        """Write individual changes to enhancement_changes table."""
        change_rows = []
        created_at = datetime.now()

        for change in changes:
            source_failure = change.get("source_failure", {})

            change_row = {
                "run_id": self.current_run_id,
                "iteration_number": iteration_number,
                "change_id": str(uuid.uuid4()),
                "change_type": change.get("type", "unknown"),
                "target_table": change.get("table") or change.get("left_table"),
                "target_column": change.get("column"),
                "change_value": self._extract_change_value(change),
                "change_details": self._flatten_change_details(change),
                "source_failure_benchmark_id": source_failure.get("benchmark_id"),
                "source_failure_question": source_failure.get("question"),
                "applied_successfully": True,  # If we're here, it applied
                "validation_status": "valid",
                "error_message": None,
                "created_at": created_at
            }
            change_rows.append(change_row)

        if change_rows:
            try:
                df = self.spark.createDataFrame(change_rows)
                df.write.format("delta").mode("append").saveAsTable(
                    f"{self.full_name}.enhancement_changes"
                )
            except Exception as e:
                logger.error(f"Failed to write changes: {e}")

    def _write_benchmark_results(self, iteration_number: int, benchmark_results: Dict):
        """Write per-benchmark results to enhancement_benchmarks table."""
        benchmark_rows = []
        created_at = datetime.now()

        for result in benchmark_results.get("results", []):
            benchmark_row = {
                "run_id": self.current_run_id,
                "iteration_number": iteration_number,
                "benchmark_id": result.get("benchmark_id", "unknown"),
                "question": result.get("question", ""),
                "expected_sql": result.get("expected_sql"),
                "passed": result.get("passed", False),
                "genie_sql": result.get("genie_sql"),
                "genie_status": "COMPLETED" if result.get("passed") else "FAILED",
                "failure_category": result.get("failure_category"),
                "failure_reason": result.get("failure_reason"),
                "comparison_confidence": result.get("comparison_details", {}).get("confidence"),
                "semantic_equivalence": result.get("comparison_details", {}).get("semantic_equivalence"),
                "response_time_seconds": result.get("response_time", 0.0),
                "created_at": created_at
            }
            benchmark_rows.append(benchmark_row)

        if benchmark_rows:
            try:
                df = self.spark.createDataFrame(benchmark_rows)
                df.write.format("delta").mode("append").saveAsTable(
                    f"{self.full_name}.enhancement_benchmarks"
                )
            except Exception as e:
                logger.error(f"Failed to write benchmark results: {e}")

    def complete_run(
        self,
        final_score: float,
        initial_score: float,
        iterations_completed: int,
        total_changes: int,
        status: str = "COMPLETED",
        error_message: str = None
    ):
        """
        Mark run as complete and update summary statistics.

        Args:
            final_score: Final benchmark score
            initial_score: Initial benchmark score
            iterations_completed: Number of iterations run
            total_changes: Total changes applied
            status: COMPLETED | FAILED | STOPPED
            error_message: Error details if failed
        """
        if not self.spark or not self.current_run_id:
            return

        completed_at = datetime.now()

        # Read start time from table
        try:
            run_df = self.spark.read.format("delta").table(
                f"{self.full_name}.enhancement_runs"
            ).filter(f"run_id = '{self.current_run_id}'")

            if run_df.count() == 0:
                logger.error(f"Run {self.current_run_id} not found in table")
                return

            started_at = run_df.select("started_at").first()[0]
            duration_seconds = (completed_at - started_at).total_seconds()

            # Update run record
            update_query = f"""
            MERGE INTO {self.catalog}.enhancement_runs AS target
            USING (SELECT '{self.current_run_id}' AS run_id) AS source
            ON target.run_id = source.run_id
            WHEN MATCHED THEN UPDATE SET
                completed_at = timestamp'{completed_at.isoformat()}',
                status = '{status}',
                final_score = {final_score},
                initial_score = {initial_score},
                score_improvement = {final_score - initial_score},
                iterations_completed = {iterations_completed},
                total_changes_applied = {total_changes},
                duration_seconds = {duration_seconds},
                error_message = {f"'{error_message}'" if error_message else "NULL"},
                updated_at = timestamp'{completed_at.isoformat()}'
            """

            self.spark.sql(update_query)
            logger.info(f"✅ Completed run tracking: {self.current_run_id}")

        except Exception as e:
            logger.error(f"Failed to complete run: {e}")

    def _calculate_score_delta(self, iteration_number: int, current_score: float) -> float:
        """Calculate score delta from previous iteration."""
        if iteration_number == 1:
            return 0.0

        try:
            prev_iter_df = self.spark.read.format("delta").table(
                f"{self.full_name}.enhancement_iterations"
            ).filter(
                f"run_id = '{self.current_run_id}' AND iteration_number = {iteration_number - 1}"
            )

            if prev_iter_df.count() > 0:
                prev_score = prev_iter_df.select("score").first()[0]
                return current_score - prev_score

        except Exception as e:
            logger.warning(f"Could not calculate score delta: {e}")

        return 0.0

    def _extract_change_value(self, change: Dict) -> str:
        """Extract the main change value for easy querying."""
        change_type = change.get("type")

        if change_type == "add_synonym":
            return change.get("synonym", "")
        elif change_type in ["add_column_description", "update_table_description"]:
            desc = change.get("description", "")
            return desc[0] if isinstance(desc, list) else desc
        elif change_type in ["add_join", "fix_join"]:
            return change.get("sql", "")
        elif change_type == "add_example_query":
            return change.get("question", "")
        else:
            return str(change.get("value", ""))

    def _flatten_change_details(self, change: Dict) -> Dict[str, str]:
        """Flatten change details to string key-value pairs for MAP column."""
        flattened = {}

        for key, value in change.items():
            if key in ["type", "table", "column", "source_failure"]:
                continue  # Already captured in dedicated columns

            if isinstance(value, (list, dict)):
                flattened[key] = json.dumps(value)
            else:
                flattened[key] = str(value)

        return flattened


# Example usage
if __name__ == "__main__":
    print("Delta Reporter - Example Usage")
    print("=" * 60)

    # This would be used in enhancement_job.py like:
    # reporter = DeltaReporter()  # Uses env vars CATALOG and SCHEMA
    # run_id = reporter.start_run(space_id, space_name, config)
    # ...
    # reporter.report_iteration(iteration_number, benchmark_results, changes_made, duration)
    # ...
    # reporter.complete_run(final_score, initial_score, iterations, total_changes)