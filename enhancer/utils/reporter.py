"""
Progress Reporter

Reports enhancement progress to Delta tables or other destinations.
"""

import logging
from typing import Dict, List
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProgressReporter:
    """Report enhancement progress to various destinations."""

    def __init__(self, config: Dict = None):
        """
        Initialize reporter.

        Args:
            config: Reporter configuration
                {
                    "report_to": "delta_table" | "console" | "mlflow",
                    "table_name": "catalog.schema.enhancement_progress",
                    "mlflow_experiment": "/path/to/experiment",
                    "mlflow_run_id": "run_id"
                }
        """
        self.config = config or {}
        self.report_to = self.config.get("report_to", "console")

    def report(self, iteration_data: Dict):
        """
        Report iteration results.

        Args:
            iteration_data: {
                "iteration": int,
                "timestamp": str,
                "score": float,
                "score_delta": float,
                "total_benchmarks": int,
                "passed": int,
                "failed": int,
                "changes_made": List[Dict],
                "failures_by_category": Dict[str, int],
                "duration_seconds": float,
                "space_id": str,
                "config": Dict  # Job configuration
            }
        """
        logger.info(f"Reporting iteration {iteration_data['iteration']} results...")

        if self.report_to == "delta_table":
            self._report_to_delta_table(iteration_data)
        elif self.report_to == "mlflow":
            self._report_to_mlflow(iteration_data)
        elif self.report_to == "console":
            self._report_to_console(iteration_data)
        else:
            logger.warning(f"Unknown report_to: {self.report_to}, using console")
            self._report_to_console(iteration_data)

    def _report_to_console(self, data: Dict):
        """Report to console (pretty print)."""
        print("\n" + "=" * 80)
        print(f"Iteration {data['iteration']} Report")
        print("=" * 80)
        print(f"Timestamp: {data['timestamp']}")
        print(f"Space ID: {data.get('space_id', 'N/A')}")
        print(f"\nScore: {data['score']:.2%} ({data['passed']}/{data['total_benchmarks']})")
        print(f"Score Change: {data['score_delta']:+.2%}")
        print(f"Duration: {data['duration_seconds']:.1f}s")

        if data.get('changes_made'):
            print(f"\nChanges Made: {len(data['changes_made'])}")
            by_type = {}
            for change in data['changes_made']:
                change_type = change.get('type', 'unknown')
                by_type[change_type] = by_type.get(change_type, 0) + 1

            for change_type, count in sorted(by_type.items()):
                print(f"  - {change_type}: {count}")

        if data.get('failures_by_category'):
            print(f"\nFailures by Category:")
            for category, count in sorted(data['failures_by_category'].items()):
                print(f"  - {category}: {count}")

        print("=" * 80 + "\n")

    def _report_to_delta_table(self, data: Dict):
        """Report to Delta table."""
        try:
            from pyspark.sql import SparkSession
            import json

            table_name = self.config.get("table_name")
            if not table_name:
                logger.error("table_name not specified in config")
                self._report_to_console(data)
                return

            spark = SparkSession.builder.getOrCreate()

            # Flatten data for table
            row_data = {
                "iteration": data["iteration"],
                "timestamp": data["timestamp"],
                "space_id": data.get("space_id"),
                "score": data["score"],
                "score_delta": data["score_delta"],
                "total_benchmarks": data["total_benchmarks"],
                "passed": data["passed"],
                "failed": data["failed"],
                "num_changes": len(data.get("changes_made", [])),
                "changes_json": json.dumps(data.get("changes_made", [])),
                "failures_by_category_json": json.dumps(data.get("failures_by_category", {})),
                "duration_seconds": data["duration_seconds"],
                "config_json": json.dumps(data.get("config", {}))
            }

            # Create DataFrame
            df = spark.createDataFrame([row_data])

            # Write to table (append mode)
            df.write.mode("append").saveAsTable(table_name)

            logger.info(f"✅ Reported to Delta table: {table_name}")

        except Exception as e:
            logger.error(f"Failed to write to Delta table: {e}")
            logger.info("Falling back to console reporting")
            self._report_to_console(data)

    def _report_to_mlflow(self, data: Dict):
        """Report to MLflow."""
        try:
            import mlflow

            run_id = self.config.get("mlflow_run_id")
            experiment = self.config.get("mlflow_experiment")

            if not run_id and experiment:
                # Start a new run if not provided
                mlflow.set_experiment(experiment)
                mlflow.start_run()
                run_id = mlflow.active_run().info.run_id

            if not run_id:
                logger.error("mlflow_run_id not specified in config")
                self._report_to_console(data)
                return

            # Log metrics
            iteration = data["iteration"]
            mlflow.log_metrics({
                "score": data["score"],
                "score_delta": data["score_delta"],
                "passed": data["passed"],
                "failed": data["failed"],
                "num_changes": len(data.get("changes_made", [])),
                "duration_seconds": data["duration_seconds"]
            }, step=iteration)

            # Log parameters (first iteration only)
            if iteration == 1:
                config = data.get("config", {})
                mlflow.log_params({
                    "space_id": data.get("space_id"),
                    "target_score": config.get("target_score"),
                    "max_iterations": config.get("max_iterations")
                })

            logger.info(f"✅ Reported to MLflow run: {run_id}")

        except Exception as e:
            logger.error(f"Failed to write to MLflow: {e}")
            logger.info("Falling back to console reporting")
            self._report_to_console(data)

    def report_final(self, final_data: Dict):
        """
        Report final results.

        Args:
            final_data: {
                "success": bool,
                "final_score": float,
                "initial_score": float,
                "iterations": int,
                "total_duration": float,
                "final_status": str,
                "space_id": str
            }
        """
        print("\n" + "=" * 80)
        print("FINAL RESULTS")
        print("=" * 80)
        print(f"Space ID: {final_data.get('space_id', 'N/A')}")
        print(f"Status: {final_data['final_status']}")
        print(f"Success: {'✅ YES' if final_data['success'] else '❌ NO'}")
        print(f"\nInitial Score: {final_data['initial_score']:.2%}")
        print(f"Final Score: {final_data['final_score']:.2%}")
        print(f"Improvement: {final_data['final_score'] - final_data['initial_score']:+.2%}")
        print(f"\nIterations: {final_data['iterations']}")
        print(f"Total Duration: {final_data['total_duration']:.1f}s ({final_data['total_duration']/60:.1f} min)")
        print("=" * 80 + "\n")

        # Also write final results to table if configured
        if self.report_to == "delta_table":
            try:
                from pyspark.sql import SparkSession
                import json

                table_name = self.config.get("table_name", "").replace("_progress", "_final")
                if table_name:
                    spark = SparkSession.builder.getOrCreate()

                    row_data = {
                        "timestamp": datetime.now().isoformat(),
                        "space_id": final_data.get("space_id"),
                        "success": final_data["success"],
                        "final_status": final_data["final_status"],
                        "initial_score": final_data["initial_score"],
                        "final_score": final_data["final_score"],
                        "score_improvement": final_data["final_score"] - final_data["initial_score"],
                        "iterations": final_data["iterations"],
                        "total_duration_seconds": final_data["total_duration"]
                    }

                    df = spark.createDataFrame([row_data])
                    df.write.mode("append").saveAsTable(table_name)
                    logger.info(f"✅ Final results written to: {table_name}")

            except Exception as e:
                logger.error(f"Failed to write final results: {e}")


# Example usage
if __name__ == "__main__":
    # Test console reporting
    reporter = ProgressReporter({"report_to": "console"})

    iteration_data = {
        "iteration": 1,
        "timestamp": datetime.now().isoformat(),
        "space_id": "test-space-id",
        "score": 0.75,
        "score_delta": 0.10,
        "total_benchmarks": 20,
        "passed": 15,
        "failed": 5,
        "changes_made": [
            {"type": "add_synonym", "reasoning": "Added synonym for column"},
            {"type": "fix_join", "reasoning": "Fixed join relationship type"}
        ],
        "failures_by_category": {
            "missing_table_or_column": 3,
            "wrong_join": 2
        },
        "duration_seconds": 45.2,
        "config": {"target_score": 0.90}
    }

    reporter.report(iteration_data)

    final_data = {
        "success": True,
        "final_score": 0.92,
        "initial_score": 0.65,
        "iterations": 3,
        "total_duration": 180.5,
        "final_status": "threshold_reached",
        "space_id": "test-space-id"
    }

    reporter.report_final(final_data)
