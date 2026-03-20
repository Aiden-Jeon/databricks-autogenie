"""
Sequential Enhancer

Orchestrates the sequential fix application loop:
1. Analyze failures and generate fixes
2. Apply fixes one at a time
3. Evaluate each fix
4. Keep or rollback based on score improvement

Supports two analysis modes:
- Legacy: Per-question analysis (N failures × 3 categories = 3N LLM calls)
- Category-based: Batch analysis (9 LLM calls total, regardless of failure count)
"""

import json
import time
import logging
import uuid
from typing import Dict, List, Callable, Optional

from enhancer.enhancement.enhancer import EnhancementPlanner
from enhancer.enhancement.category_enhancer import CategoryEnhancer
from enhancer.enhancement.applier import BatchApplier

logger = logging.getLogger(__name__)


class SequentialEnhancer:
    """
    Orchestrates sequential enhancement with real-time evaluation.

    Applies fixes one at a time, evaluating after each:
    - If score improves: keep fix, update dev-best
    - If score drops: rollback from dev-best
    - If score unchanged: keep fix (no harm)
    """

    # Legacy fix order (DEPRECATED: metric_view removed)
    LEGACY_FIX_ORDER = ["metadata", "sample_query", "instruction"]

    # Category-based fix order (9 categories)
    CATEGORY_FIX_ORDER = [
        "instruction_fix",
        "join_specs_delete",
        "join_specs_add",
        "sql_snippets_delete",
        "sql_snippets_add",
        "metadata_delete",
        "metadata_add",
        "sample_queries_delete",
        "sample_queries_add",
    ]

    def __init__(
        self,
        llm_client,
        space_cloner,
        scorer,
        sql_executor=None,
        progress_callback: Callable[[str, str], None] = None,
        use_category_mode: bool = True
    ):
        """
        Initialize sequential enhancer.

        Args:
            llm_client: LLM client for generating fixes
            space_cloner: SpaceCloner for managing three-space architecture
            scorer: BenchmarkScorer for evaluating changes
            sql_executor: SQLExecutor for metric view creation (optional)
            progress_callback: Optional callback(message, level) for progress updates
            use_category_mode: If True, use category-based analysis (9 LLM calls).
                               If False, use legacy per-question analysis.
        """
        self.llm_client = llm_client
        self.space_cloner = space_cloner
        self.scorer = scorer
        self.sql_executor = sql_executor
        self.progress_callback = progress_callback or (lambda m, l: None)
        self.use_category_mode = use_category_mode

        # Initialize planners
        self.legacy_planner = EnhancementPlanner(llm_client)
        self.category_planner = CategoryEnhancer(llm_client)

        # Initialize applier
        self.applier = BatchApplier(
            space_api=space_cloner,
            sql_executor=sql_executor
        )

    @property
    def FIX_ORDER(self):
        """Return the appropriate fix order based on mode."""
        return self.CATEGORY_FIX_ORDER if self.use_category_mode else self.LEGACY_FIX_ORDER

    @property
    def planner(self):
        """Return the appropriate planner based on mode."""
        return self.category_planner if self.use_category_mode else self.legacy_planner

    def _log(self, message: str, level: str = "info"):
        """Log message and call progress callback."""
        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        else:
            logger.info(message)
        self.progress_callback(message, level)

    def analyze_all_failures(
        self,
        benchmark_results: Dict,
        space_config: Dict,
        parallel_workers: int = 4
    ) -> Dict[str, List[Dict]]:
        """
        Analyze all failures and generate grouped fixes.

        Args:
            benchmark_results: Results from BenchmarkScorer.score()
            space_config: Current Genie Space configuration
            parallel_workers: Number of parallel LLM calls

        Returns:
            Grouped fixes by category.

            Category mode (9 categories):
            {
                "instruction_fix": [...],
                "sample_queries_delete": [...],
                "sample_queries_add": [...],
                "metadata_delete": [...],
                "metadata_add": [...],
                "sql_snippets_delete": [...],
                "sql_snippets_add": [...],
                "join_specs_delete": [...],
                "join_specs_add": [...]
            }

            Legacy mode (4 categories):
            {
                "metric_view": [...],
                "metadata": [...],
                "sample_query": [...],
                "instruction": [...]
            }
        """
        mode_name = "Category-based" if self.use_category_mode else "Legacy per-question"
        self._log(f"Analyzing failures ({mode_name} mode)...")

        # Extract failed benchmarks
        failed_benchmarks = [
            r for r in benchmark_results.get("results", [])
            if not r.get("passed")
        ]

        if not failed_benchmarks:
            self._log("No failures to analyze", "warning")
            return {cat: [] for cat in self.FIX_ORDER}

        self._log(f"Found {len(failed_benchmarks)} failures to analyze")

        if self.use_category_mode:
            # Category-based: 9 LLM calls total (constant)
            self._log(f"Using category-based analysis: 9 LLM calls")
        else:
            # Legacy: N failures × 3 categories LLM calls
            total_calls = len(failed_benchmarks) * 3
            self._log(f"Using legacy analysis: {total_calls} LLM calls ({len(failed_benchmarks)} × 3)")

        # Generate fix plan
        grouped_fixes = self.planner.generate_plan(
            failed_benchmarks=failed_benchmarks,
            space_config=space_config,
            parallel_workers=parallel_workers
        )

        # Summary
        total = sum(len(fixes) for fixes in grouped_fixes.values())
        self._log(f"Generated {total} fixes across {len(self.FIX_ORDER)} categories")

        return grouped_fixes

    def run_sequential_loop(
        self,
        benchmarks: List[Dict],
        grouped_fixes: Dict[str, List[Dict]],
        indexing_wait_time: int = 60,
        target_score: float = 1.0,
        max_iterations: Optional[int] = None
    ) -> Dict:
        """
        Run the sequential fix application loop.

        Args:
            benchmarks: List of benchmark questions
            grouped_fixes: Fixes grouped by category
            indexing_wait_time: Seconds to wait for Genie indexing after each change
            target_score: Target score to stop early (default 1.0)
            max_iterations: Maximum number of fixes to try (default: all)

        Returns:
            {
                "initial_score": float,
                "final_score": float,
                "fixes_applied": List[Dict],
                "fixes_rejected": List[Dict],
                "iterations": int,
                "duration_seconds": float
            }
        """
        import time
        start_time = time.time()

        self._log("=" * 60)
        self._log("Starting Sequential Enhancement Loop")
        self._log("=" * 60)

        # Initial score
        self._log("Running initial benchmark...")
        initial_results = self.scorer.score(benchmarks)
        initial_score = initial_results["score"]
        current_score = initial_score
        best_score = initial_score

        self._log(f"Initial score: {initial_score:.1%}")

        # Track results
        fixes_applied = []
        fixes_rejected = []
        iteration = 0

        # Flatten fixes in order
        all_fixes = []
        for category in self.FIX_ORDER:
            for fix in grouped_fixes.get(category, []):
                fix["_category"] = category
                all_fixes.append(fix)

        total_fixes = len(all_fixes)
        if max_iterations:
            total_fixes = min(total_fixes, max_iterations)

        self._log(f"Total fixes to try: {total_fixes}")

        # Process each fix
        for fix in all_fixes[:total_fixes]:
            iteration += 1
            category = fix.get("_category", "unknown")
            fix_type = fix.get("type", "unknown")

            self._log(f"\n[{iteration}/{total_fixes}] Applying {category}/{fix_type}...")

            # Get current config
            try:
                current_config = self.space_cloner.get_dev_working_config()
            except Exception as e:
                self._log(f"Error getting config: {e}", "error")
                fix["rejection_reason"] = f"Config error: {e}"
                fixes_rejected.append(fix)
                continue

            # Apply fix
            try:
                updated_config = self._apply_single_fix(current_config, fix)
                self.space_cloner.update_dev_working_config(updated_config)
            except Exception as e:
                self._log(f"Error applying fix: {e}", "error")
                fix["rejection_reason"] = f"Apply error: {e}"
                fixes_rejected.append(fix)
                continue

            # Wait for indexing
            self._log(f"Waiting {indexing_wait_time}s for Genie indexing...")
            time.sleep(indexing_wait_time)

            # Evaluate
            self._log("Evaluating...")
            try:
                eval_results = self.scorer.score(benchmarks)
                new_score = eval_results["score"]
            except Exception as e:
                self._log(f"Evaluation error: {e}", "error")
                # Rollback on error
                self.space_cloner.rollback_dev_working()
                fix["rejection_reason"] = f"Eval error: {e}"
                fixes_rejected.append(fix)
                continue

            # Decision
            score_delta = new_score - current_score

            if new_score > current_score:
                # Improvement - keep and update dev-best
                self._log(f"IMPROVED: {current_score:.1%} -> {new_score:.1%} (+{score_delta:.1%})")
                current_score = new_score
                if new_score > best_score:
                    best_score = new_score
                    self.space_cloner.update_dev_best()
                fixes_applied.append(fix)

            elif new_score < current_score:
                # Regression - rollback
                self._log(f"REGRESSED: {current_score:.1%} -> {new_score:.1%} ({score_delta:.1%})")
                self.space_cloner.rollback_dev_working()
                fix["rejection_reason"] = f"Score dropped from {current_score:.1%} to {new_score:.1%}"
                fixes_rejected.append(fix)

            else:
                # No change - keep (no harm)
                self._log(f"UNCHANGED: {current_score:.1%}")
                fixes_applied.append(fix)

            # Check target
            if current_score >= target_score:
                self._log(f"Target score {target_score:.1%} reached!")
                break

        duration = time.time() - start_time

        # Summary
        self._log("\n" + "=" * 60)
        self._log("Sequential Enhancement Complete")
        self._log("=" * 60)
        self._log(f"Initial score: {initial_score:.1%}")
        self._log(f"Final score: {current_score:.1%}")
        self._log(f"Improvement: {current_score - initial_score:+.1%}")
        self._log(f"Fixes applied: {len(fixes_applied)}")
        self._log(f"Fixes rejected: {len(fixes_rejected)}")
        self._log(f"Duration: {duration:.1f}s")

        return {
            "initial_score": initial_score,
            "final_score": current_score,
            "best_score": best_score,
            "fixes_applied": fixes_applied,
            "fixes_rejected": fixes_rejected,
            "iterations": iteration,
            "duration_seconds": duration
        }

    def _apply_single_fix(self, config: Dict, fix: Dict) -> Dict:
        """
        Apply a single fix to the configuration.

        Args:
            config: Current space configuration
            fix: Fix to apply

        Returns:
            Updated configuration
        """
        import copy
        config = copy.deepcopy(config)

        fix_type = fix.get("type", "")

        # Metadata fixes
        if fix_type == "add_synonym":
            config = self._add_synonym(config, fix)
        elif fix_type == "delete_synonym":
            config = self._delete_synonym(config, fix)
        elif fix_type == "add_column_description":
            config = self._add_column_description(config, fix)
        elif fix_type == "add_table_description":
            config = self._add_table_description(config, fix)

        # Sample query fixes
        elif fix_type == "add_example_query":
            config = self._add_example_query(config, fix)
        elif fix_type == "delete_example_query":
            config = self._delete_example_query(config, fix)

        # Instruction fixes
        elif fix_type == "update_text_instruction":
            config = self._update_text_instruction(config, fix)

        # Metric view fixes (DEPRECATED - removed from CategoryEnhancer)
        # elif fix_type == "create_metric_view":
        #     config = self._create_metric_view(config, fix)
        # elif fix_type == "delete_metric_view":
        #     config = self._delete_metric_view(config, fix)

        # SQL snippet fixes
        elif fix_type == "add_filter":
            config = self._add_sql_snippet(config, fix, "filters")
        elif fix_type == "delete_filter":
            config = self._delete_sql_snippet(config, fix, "filters")
        elif fix_type == "add_expression":
            config = self._add_sql_snippet(config, fix, "expressions")
        elif fix_type == "delete_expression":
            config = self._delete_sql_snippet(config, fix, "expressions")
        elif fix_type == "add_measure":
            config = self._add_sql_snippet(config, fix, "measures")
        elif fix_type == "delete_measure":
            config = self._delete_sql_snippet(config, fix, "measures")

        # Join spec fixes
        elif fix_type == "add_join_spec":
            config = self._add_join_spec(config, fix)
        elif fix_type == "delete_join_spec":
            config = self._delete_join_spec(config, fix)

        else:
            logger.warning(f"Unknown fix type: {fix_type}")

        return config

    def _add_synonym(self, config: Dict, fix: Dict) -> Dict:
        """Add synonym to a column."""
        table_name = fix.get("table")
        column_name = fix.get("column")
        synonym = fix.get("synonym")

        if not all([table_name, column_name, synonym]):
            return config

        data_sources = config.get("data_sources", {})
        tables = data_sources.get("tables", [])

        for table in tables:
            if table.get("table_name") == table_name:
                columns = table.get("column_configs", [])
                found = False
                for col in columns:
                    if col.get("column_name") == column_name:
                        synonyms = col.get("synonyms", [])
                        if synonym not in synonyms:
                            synonyms.append(synonym)
                            col["synonyms"] = synonyms
                        found = True
                        break
                if not found:
                    columns.append({
                        "column_name": column_name,
                        "synonyms": [synonym]
                    })
                    table["column_configs"] = columns
                break

        return config

    def _delete_synonym(self, config: Dict, fix: Dict) -> Dict:
        """Remove synonym from a column."""
        table_name = fix.get("table")
        column_name = fix.get("column")
        synonym = fix.get("synonym")

        if not all([table_name, column_name, synonym]):
            return config

        data_sources = config.get("data_sources", {})
        tables = data_sources.get("tables", [])

        for table in tables:
            if table.get("table_name") == table_name:
                columns = table.get("column_configs", [])
                for col in columns:
                    if col.get("column_name") == column_name:
                        synonyms = col.get("synonyms", [])
                        if synonym in synonyms:
                            synonyms.remove(synonym)
                            col["synonyms"] = synonyms
                        break
                break

        return config

    def _add_column_description(self, config: Dict, fix: Dict) -> Dict:
        """Add description to a column."""
        table_name = fix.get("table")
        column_name = fix.get("column")
        description = fix.get("description")

        if not all([table_name, column_name, description]):
            return config

        data_sources = config.get("data_sources", {})
        tables = data_sources.get("tables", [])

        for table in tables:
            if table.get("table_name") == table_name:
                columns = table.get("column_configs", [])
                found = False
                for col in columns:
                    if col.get("column_name") == column_name:
                        col["description"] = description
                        found = True
                        break
                if not found:
                    columns.append({
                        "column_name": column_name,
                        "description": description
                    })
                    table["column_configs"] = columns
                break

        return config

    def _add_table_description(self, config: Dict, fix: Dict) -> Dict:
        """Add description to a table."""
        table_name = fix.get("table")
        description = fix.get("description")

        if not all([table_name, description]):
            return config

        data_sources = config.get("data_sources", {})
        tables = data_sources.get("tables", [])

        for table in tables:
            if table.get("table_name") == table_name:
                table["description"] = description
                break

        return config

    def _add_example_query(self, config: Dict, fix: Dict) -> Dict:
        """Add example query."""
        import uuid

        pattern_name = fix.get("pattern_name")
        question = fix.get("question")
        sql = fix.get("sql")

        if not all([question, sql]):
            return config

        instructions = config.setdefault("instructions", {})
        examples = instructions.setdefault("example_question_sqls", [])

        examples.append({
            "id": str(uuid.uuid4()),
            "pattern_name": pattern_name or "Custom Query",
            "question": question,
            "sql": sql
        })

        return config

    def _delete_example_query(self, config: Dict, fix: Dict) -> Dict:
        """Remove example query by pattern name or ID."""
        pattern_name = fix.get("pattern_name")
        query_id = fix.get("id")

        if not pattern_name and not query_id:
            return config

        instructions = config.get("instructions", {})
        examples = instructions.get("example_question_sqls", [])

        filtered = [
            ex for ex in examples
            if not (
                (pattern_name and ex.get("pattern_name") == pattern_name) or
                (query_id and ex.get("id") == query_id)
            )
        ]

        instructions["example_question_sqls"] = filtered

        return config

    def _update_text_instruction(self, config: Dict, fix: Dict) -> Dict:
        """Update text instructions."""
        # Support both legacy "instruction_text" and new "content" format
        instruction_text = fix.get("instruction_text") or fix.get("content")

        if not instruction_text:
            return config

        # If content is a list, join with newlines
        if isinstance(instruction_text, list):
            instruction_text = "\n".join(instruction_text)

        instructions = config.setdefault("instructions", {})
        instructions["instruction_text"] = instruction_text

        return config

    # DEPRECATED: Metric view methods removed from CategoryEnhancer
    # def _create_metric_view(self, config: Dict, fix: Dict) -> Dict:
    #     """Create metric view in Unity Catalog and add to space."""
    #     if not self.sql_executor:
    #         logger.warning("SQL executor not available for metric view creation")
    #         return config
    #
    #     catalog = fix.get("catalog")
    #     schema = fix.get("schema")
    #     view_name = fix.get("metric_view_name")
    #     sql = fix.get("sql")
    #
    #     if not all([catalog, schema, view_name, sql]):
    #         return config
    #
    #     full_name = f"{catalog}.{schema}.{view_name}"
    #
    #     # Create the view in Unity Catalog
    #     try:
    #         create_sql = f"CREATE OR REPLACE VIEW {full_name} AS {sql}"
    #         self.sql_executor.execute(create_sql)
    #         logger.info(f"Created metric view: {full_name}")
    #     except Exception as e:
    #         logger.error(f"Failed to create metric view {full_name}: {e}")
    #         raise
    #
    #     # Add view to space configuration
    #     data_sources = config.setdefault("data_sources", {})
    #     tables = data_sources.setdefault("tables", [])
    #
    #     # Check if already exists
    #     exists = any(
    #         t.get("catalog") == catalog and
    #         t.get("schema") == schema and
    #         t.get("table_name") == view_name
    #         for t in tables
    #     )
    #
    #     if not exists:
    #         tables.append({
    #             "catalog": catalog,
    #             "schema": schema,
    #             "table_name": view_name,
    #             "description": fix.get("description", f"Metric view: {view_name}")
    #         })
    #
    #     return config
    #
    # def _delete_metric_view(self, config: Dict, fix: Dict) -> Dict:
    #     """Remove metric view from space (optionally drop from UC)."""
    #     catalog = fix.get("catalog")
    #     schema = fix.get("schema")
    #     view_name = fix.get("metric_view_name")
    #     drop_from_uc = fix.get("drop_from_uc", False)
    #
    #     if not view_name:
    #         return config
    #
    #     # Remove from space config
    #     data_sources = config.get("data_sources", {})
    #     tables = data_sources.get("tables", [])
    #
    #     filtered = [
    #         t for t in tables
    #         if not (
    #             t.get("table_name") == view_name and
    #             (not catalog or t.get("catalog") == catalog) and
    #             (not schema or t.get("schema") == schema)
    #         )
    #     ]
    #
    #     data_sources["tables"] = filtered
    #
    #     # Optionally drop from Unity Catalog
    #     if drop_from_uc and self.sql_executor and catalog and schema:
    #         try:
    #             full_name = f"{catalog}.{schema}.{view_name}"
    #             drop_sql = f"DROP VIEW IF EXISTS {full_name}"
    #             self.sql_executor.execute(drop_sql)
    #             logger.info(f"Dropped metric view: {full_name}")
    #         except Exception as e:
    #             logger.warning(f"Failed to drop metric view: {e}")
    #
    #     return config

    # =========================================================================
    # SQL Snippet Methods (filters, expressions, measures)
    # =========================================================================

    def _add_sql_snippet(self, config: Dict, fix: Dict, snippet_type: str) -> Dict:
        """
        Add SQL snippet (filter, expression, or measure).

        Args:
            config: Space configuration
            fix: Fix dict with sql, display_name, synonyms, alias (for expr/measure)
            snippet_type: "filters", "expressions", or "measures"
        """
        sql = fix.get("sql")
        display_name = fix.get("display_name")

        if not sql:
            return config

        instructions = config.setdefault("instructions", {})
        snippets = instructions.setdefault("sql_snippets", {})
        snippet_list = snippets.setdefault(snippet_type, [])

        # Generate UUID for id
        snippet_id = str(uuid.uuid4()).replace("-", "")[:32]

        new_snippet = {
            "id": snippet_id,
            "sql": sql if isinstance(sql, list) else [sql],
            "display_name": display_name or f"Snippet {snippet_id[:8]}",
        }

        # Add synonyms if provided
        if fix.get("synonyms"):
            new_snippet["synonyms"] = fix["synonyms"]

        # Add alias for expressions and measures
        if snippet_type in ("expressions", "measures"):
            alias = fix.get("alias")
            if alias:
                new_snippet["alias"] = alias

        snippet_list.append(new_snippet)
        logger.info(f"Added {snippet_type[:-1]}: {display_name or snippet_id[:8]}")

        return config

    def _delete_sql_snippet(self, config: Dict, fix: Dict, snippet_type: str) -> Dict:
        """
        Delete SQL snippet by id, alias, or display_name.

        Args:
            config: Space configuration
            fix: Fix dict with id, alias, or display_name
            snippet_type: "filters", "expressions", or "measures"
        """
        snippet_id = fix.get("id")
        alias = fix.get("alias")
        display_name = fix.get("display_name")

        if not any([snippet_id, alias, display_name]):
            return config

        instructions = config.get("instructions", {})
        snippets = instructions.get("sql_snippets", {})
        snippet_list = snippets.get(snippet_type, [])

        filtered = [
            s for s in snippet_list
            if not (
                (snippet_id and s.get("id") == snippet_id) or
                (alias and s.get("alias") == alias) or
                (display_name and s.get("display_name") == display_name)
            )
        ]

        if len(filtered) < len(snippet_list):
            snippets[snippet_type] = filtered
            logger.info(f"Deleted {snippet_type[:-1]}: {snippet_id or alias or display_name}")

        return config

    # =========================================================================
    # Join Spec Methods
    # =========================================================================

    def _add_join_spec(self, config: Dict, fix: Dict) -> Dict:
        """
        Add join specification.

        Args:
            config: Space configuration
            fix: Fix dict with left_table, right_table, sql, comment
        """
        left_table = fix.get("left_table")
        right_table = fix.get("right_table")
        sql = fix.get("sql")

        if not all([left_table, right_table, sql]):
            return config

        instructions = config.setdefault("instructions", {})
        join_specs = instructions.setdefault("join_specs", [])

        # Generate UUID for id
        join_id = str(uuid.uuid4()).replace("-", "")[:32]

        new_join = {
            "id": join_id,
            "left_table": left_table,
            "right_table": right_table,
            "sql": sql if isinstance(sql, list) else [sql],
        }

        # Add comment if provided
        if fix.get("comment"):
            new_join["comment"] = fix["comment"] if isinstance(fix["comment"], list) else [fix["comment"]]

        join_specs.append(new_join)
        logger.info(f"Added join_spec: {left_table} <-> {right_table}")

        return config

    def _delete_join_spec(self, config: Dict, fix: Dict) -> Dict:
        """
        Delete join specification by id or table pair.

        Args:
            config: Space configuration
            fix: Fix dict with id, or left_table and right_table
        """
        join_id = fix.get("id")
        left_table = fix.get("left_table")
        right_table = fix.get("right_table")

        if not join_id and not (left_table and right_table):
            return config

        instructions = config.get("instructions", {})
        join_specs = instructions.get("join_specs", [])

        filtered = [
            j for j in join_specs
            if not (
                (join_id and j.get("id") == join_id) or
                (left_table and right_table and
                 j.get("left_table") == left_table and
                 j.get("right_table") == right_table)
            )
        ]

        if len(filtered) < len(join_specs):
            instructions["join_specs"] = filtered
            logger.info(f"Deleted join_spec: {join_id or f'{left_table} <-> {right_table}'}")

        return config
