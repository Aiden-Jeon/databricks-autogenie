"""
Job State Management for 4-Stage Databricks Job

Handles state persistence between job stages using Delta tables.
Each stage reads its input and writes its output to Delta tables
for visibility and debuggability.
"""

import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class JobState:
    """
    Manages state between job stages using Delta tables.

    Tables:
    - job_runs: High-level job execution tracking
    - job_stage_results: Output from each stage
    - benchmark_results: Detailed benchmark scoring
    - enhancement_plans: Generated fixes from analysis
    - implementation_results: Applied changes
    """

    STAGE_NAMES = ["score", "plan", "apply", "validate"]

    def __init__(
        self,
        catalog: str,
        schema: str,
        spark=None
    ):
        """
        Initialize job state manager.

        Args:
            catalog: Unity Catalog name
            schema: Schema name for state tables
            spark: SparkSession (required in Databricks)
        """
        self.catalog = catalog
        self.schema = schema
        self.spark = spark
        self.table_prefix = f"{catalog}.{schema}"

    def _get_table(self, name: str) -> str:
        """Get fully qualified table name."""
        return f"{self.table_prefix}.genie_job_{name}"

    def ensure_tables_exist(self):
        """Create state tables if they don't exist."""
        if not self.spark:
            logger.warning("No SparkSession - cannot create tables")
            return

        # Job runs table
        self.spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {self._get_table('runs')} (
                run_id STRING,
                space_id STRING,
                status STRING,
                current_stage STRING,
                config STRING,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                completed_at TIMESTAMP
            )
            USING DELTA
        """)

        # Stage results table
        self.spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {self._get_table('stage_results')} (
                run_id STRING,
                stage_name STRING,
                stage_number INT,
                status STRING,
                input_json STRING,
                output_json STRING,
                error_message STRING,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                duration_seconds DOUBLE
            )
            USING DELTA
        """)

        # Benchmark results table
        self.spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {self._get_table('benchmark_results')} (
                run_id STRING,
                stage STRING,
                benchmark_id STRING,
                question STRING,
                expected_sql STRING,
                genie_sql STRING,
                passed BOOLEAN,
                failure_category STRING,
                failure_reason STRING,
                response_time DOUBLE,
                scored_at TIMESTAMP
            )
            USING DELTA
        """)

        # Enhancement plans table
        self.spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {self._get_table('enhancement_plans')} (
                run_id STRING,
                fix_category STRING,
                fix_type STRING,
                fix_details STRING,
                source_benchmark_id STRING,
                source_question STRING,
                created_at TIMESTAMP
            )
            USING DELTA
        """)

        # Implementation results table
        self.spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {self._get_table('implementation_results')} (
                run_id STRING,
                fix_category STRING,
                fix_type STRING,
                fix_details STRING,
                applied BOOLEAN,
                rejection_reason STRING,
                score_before DOUBLE,
                score_after DOUBLE,
                applied_at TIMESTAMP
            )
            USING DELTA
        """)

        logger.info(f"State tables ensured in {self.table_prefix}")

    # =========================================================================
    # Job Run Management
    # =========================================================================

    def create_run(
        self,
        space_id: str,
        config: Dict
    ) -> str:
        """
        Create a new job run.

        Args:
            space_id: Genie Space ID being enhanced
            config: Job configuration

        Returns:
            run_id: Unique identifier for this run
        """
        run_id = str(uuid.uuid4())
        now = datetime.now()

        if self.spark:
            self.spark.sql(f"""
                INSERT INTO {self._get_table('runs')}
                VALUES (
                    '{run_id}',
                    '{space_id}',
                    'RUNNING',
                    'benchmark',
                    '{json.dumps(config).replace("'", "''")}',
                    '{now.isoformat()}',
                    '{now.isoformat()}',
                    NULL
                )
            """)

        logger.info(f"Created job run: {run_id}")
        return run_id

    def get_run(self, run_id: str) -> Optional[Dict]:
        """Get job run details."""
        if not self.spark:
            return None

        df = self.spark.sql(f"""
            SELECT * FROM {self._get_table('runs')}
            WHERE run_id = '{run_id}'
        """)

        rows = df.collect()
        if not rows:
            return None

        row = rows[0]
        return {
            "run_id": row.run_id,
            "space_id": row.space_id,
            "status": row.status,
            "current_stage": row.current_stage,
            "config": json.loads(row.config) if row.config else {},
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "completed_at": row.completed_at
        }

    def update_run_stage(self, run_id: str, stage: str, status: str = "RUNNING"):
        """Update current stage of a run."""
        now = datetime.now()

        if self.spark:
            self.spark.sql(f"""
                UPDATE {self._get_table('runs')}
                SET current_stage = '{stage}',
                    status = '{status}',
                    updated_at = '{now.isoformat()}'
                WHERE run_id = '{run_id}'
            """)

    def complete_run(self, run_id: str, status: str = "COMPLETED"):
        """Mark run as completed."""
        now = datetime.now()

        if self.spark:
            self.spark.sql(f"""
                UPDATE {self._get_table('runs')}
                SET status = '{status}',
                    completed_at = '{now.isoformat()}',
                    updated_at = '{now.isoformat()}'
                WHERE run_id = '{run_id}'
            """)

    # =========================================================================
    # Stage Results Management
    # =========================================================================

    def start_stage(
        self,
        run_id: str,
        stage_name: str,
        input_data: Dict = None
    ):
        """Record stage start."""
        stage_number = self.STAGE_NAMES.index(stage_name) + 1 if stage_name in self.STAGE_NAMES else 0
        now = datetime.now()

        if self.spark:
            input_json = json.dumps(input_data or {}).replace("'", "''")
            self.spark.sql(f"""
                INSERT INTO {self._get_table('stage_results')}
                VALUES (
                    '{run_id}',
                    '{stage_name}',
                    {stage_number},
                    'RUNNING',
                    '{input_json}',
                    NULL,
                    NULL,
                    '{now.isoformat()}',
                    NULL,
                    NULL
                )
            """)

        logger.info(f"Started stage: {stage_name}")

    def complete_stage(
        self,
        run_id: str,
        stage_name: str,
        output_data: Dict,
        error: str = None
    ):
        """Record stage completion."""
        now = datetime.now()
        status = "FAILED" if error else "COMPLETED"

        if self.spark:
            output_json = json.dumps(output_data or {}).replace("'", "''")
            error_escaped = (error or "").replace("'", "''")

            self.spark.sql(f"""
                UPDATE {self._get_table('stage_results')}
                SET status = '{status}',
                    output_json = '{output_json}',
                    error_message = '{error_escaped}' if '{error_escaped}' else NULL,
                    completed_at = '{now.isoformat()}',
                    duration_seconds = TIMESTAMPDIFF(SECOND, started_at, '{now.isoformat()}')
                WHERE run_id = '{run_id}' AND stage_name = '{stage_name}'
                AND completed_at IS NULL
            """)

        logger.info(f"Completed stage: {stage_name} ({status})")

    def get_stage_output(self, run_id: str, stage_name: str) -> Optional[Dict]:
        """Get output from a previous stage."""
        if not self.spark:
            return None

        df = self.spark.sql(f"""
            SELECT output_json FROM {self._get_table('stage_results')}
            WHERE run_id = '{run_id}' AND stage_name = '{stage_name}'
            AND status = 'COMPLETED'
            ORDER BY completed_at DESC
            LIMIT 1
        """)

        rows = df.collect()
        if not rows or not rows[0].output_json:
            return None

        return json.loads(rows[0].output_json)

    # =========================================================================
    # Benchmark Results
    # =========================================================================

    def save_benchmark_results(
        self,
        run_id: str,
        stage: str,
        results: List[Dict]
    ):
        """Save detailed benchmark results."""
        if not self.spark:
            return

        now = datetime.now()

        for result in results:
            benchmark_id = result.get("benchmark_id", "")
            question = (result.get("question", "") or "").replace("'", "''")
            expected_sql = (result.get("expected_sql", "") or "").replace("'", "''")
            genie_sql = (result.get("genie_sql", "") or "").replace("'", "''")
            passed = "TRUE" if result.get("passed") else "FALSE"
            failure_category = result.get("failure_category", "") or ""
            failure_reason = (result.get("failure_reason", "") or "").replace("'", "''")
            response_time = result.get("response_time", 0) or 0

            self.spark.sql(f"""
                INSERT INTO {self._get_table('benchmark_results')}
                VALUES (
                    '{run_id}',
                    '{stage}',
                    '{benchmark_id}',
                    '{question}',
                    '{expected_sql}',
                    '{genie_sql}',
                    {passed},
                    '{failure_category}',
                    '{failure_reason}',
                    {response_time},
                    '{now.isoformat()}'
                )
            """)

    # =========================================================================
    # Enhancement Plans
    # =========================================================================

    def save_enhancement_plan(
        self,
        run_id: str,
        grouped_fixes: Dict[str, List[Dict]]
    ):
        """Save enhancement plan (grouped fixes)."""
        if not self.spark:
            return

        now = datetime.now()

        for category, fixes in grouped_fixes.items():
            for fix in fixes:
                fix_type = fix.get("type", "")
                fix_details = json.dumps(fix).replace("'", "''")
                source = fix.get("source_failure", {})
                source_id = source.get("benchmark_id", "")
                source_question = (source.get("question", "") or "").replace("'", "''")

                self.spark.sql(f"""
                    INSERT INTO {self._get_table('enhancement_plans')}
                    VALUES (
                        '{run_id}',
                        '{category}',
                        '{fix_type}',
                        '{fix_details}',
                        '{source_id}',
                        '{source_question}',
                        '{now.isoformat()}'
                    )
                """)

    def get_enhancement_plan(self, run_id: str) -> Dict[str, List[Dict]]:
        """Retrieve enhancement plan for a run."""
        if not self.spark:
            return {}

        df = self.spark.sql(f"""
            SELECT fix_category, fix_details FROM {self._get_table('enhancement_plans')}
            WHERE run_id = '{run_id}'
            ORDER BY fix_category
        """)

        grouped = {}
        for row in df.collect():
            category = row.fix_category
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(json.loads(row.fix_details))

        return grouped

    # =========================================================================
    # Implementation Results
    # =========================================================================

    def save_implementation_result(
        self,
        run_id: str,
        fix: Dict,
        applied: bool,
        rejection_reason: str = None,
        score_before: float = None,
        score_after: float = None
    ):
        """Save individual fix implementation result."""
        if not self.spark:
            return

        now = datetime.now()
        category = fix.get("_category", "")
        fix_type = fix.get("type", "")
        fix_details = json.dumps(fix).replace("'", "''")
        applied_str = "TRUE" if applied else "FALSE"
        reason = (rejection_reason or "").replace("'", "''")

        self.spark.sql(f"""
            INSERT INTO {self._get_table('implementation_results')}
            VALUES (
                '{run_id}',
                '{category}',
                '{fix_type}',
                '{fix_details}',
                {applied_str},
                '{reason}' if '{reason}' else NULL,
                {score_before if score_before is not None else 'NULL'},
                {score_after if score_after is not None else 'NULL'},
                '{now.isoformat()}'
            )
        """)

    def get_implementation_summary(self, run_id: str) -> Dict:
        """Get summary of implementation results."""
        if not self.spark:
            return {}

        df = self.spark.sql(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN applied THEN 1 ELSE 0 END) as applied,
                SUM(CASE WHEN NOT applied THEN 1 ELSE 0 END) as rejected,
                MAX(score_after) as final_score
            FROM {self._get_table('implementation_results')}
            WHERE run_id = '{run_id}'
        """)

        row = df.collect()[0]
        return {
            "total": row.total or 0,
            "applied": row.applied or 0,
            "rejected": row.rejected or 0,
            "final_score": row.final_score
        }


# Convenience function for notebook usage
def get_job_state(catalog: str = None, schema: str = None) -> JobState:
    """
    Get JobState instance with SparkSession.

    Usage in notebook:
        from pipeline.job_state import get_job_state
        state = get_job_state()
    """
    try:
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()

        # Get default catalog/schema from spark config or use defaults
        if not catalog:
            catalog = spark.conf.get("spark.databricks.catalog", "sandbox")
        if not schema:
            schema = spark.conf.get("spark.databricks.schema", "genie_enhancement")

    except Exception:
        spark = None
        catalog = catalog or "sandbox"
        schema = schema or "genie_enhancement"

    return JobState(catalog=catalog, schema=schema, spark=spark)
