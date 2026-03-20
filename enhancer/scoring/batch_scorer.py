"""
Batch Benchmark Scorer

Three-phase batch scoring with safety measures:
1. Batch Genie queries (with rate limiting, retry, circuit breaker)
2. Batch SQL execution (concurrent with error handling)
3. Batch LLM evaluation (chunked for token limits)
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from enhancer.api.batch_genie_client import BatchGenieClient
from enhancer.utils.sql import SQLExecutor
from prompts.prompt_loader import PromptLoader

logger = logging.getLogger(__name__)


class BatchBenchmarkScorer:
    """
    Batch benchmark scorer with three-phase execution.

    Much faster than sequential scoring:
    - Sequential: ~7 minutes for 20 benchmarks
    - Parallel (current): ~1.5 minutes
    - Batch (this): ~30-40 seconds
    """

    def __init__(
        self,
        genie_client,
        llm_client,
        sql_executor: SQLExecutor,
        config: Optional[Dict] = None,
        progress_callback=None
    ):
        """
        Initialize batch scorer.

        Args:
            genie_client: Base Genie client
            llm_client: LLM client for evaluation
            sql_executor: SQL executor
            config: Configuration dict:
                # Genie batch config
            progress_callback: Optional callback(phase, current, total, message)
                - genie_max_concurrent: Max concurrent Genie calls (default: 3)
                - genie_retry_attempts: Retry attempts per query (default: 2)
                - genie_timeout: Timeout per query (default: 120)
                - genie_circuit_threshold: Failures before circuit opens (default: 5)

                # SQL batch config
                - sql_max_concurrent: Max concurrent SQL queries (default: 10)
                - sql_timeout: Timeout per SQL query (default: 60)

                # Evaluation config
                - eval_chunk_size: Results per LLM evaluation call (default: 10)
                - eval_timeout: Timeout per evaluation call (default: 30)
        """
        self.genie_client = genie_client
        self.llm_client = llm_client
        self.sql_executor = sql_executor
        self.config = config or {}
        self.prompt_loader = PromptLoader()
        self.progress_callback = progress_callback

        # Check if verbose mode is enabled
        self.verbose = getattr(genie_client, 'verbose', False)

        # Initialize batch Genie client with safety measures
        genie_config = {
            "max_concurrent": self.config.get("genie_max_concurrent", 3),
            "retry_attempts": self.config.get("genie_retry_attempts", 2),
            "query_timeout": self.config.get("genie_timeout", 120),
            "circuit_breaker_threshold": self.config.get("genie_circuit_threshold", 5),
            "fallback_to_sequential": True
        }
        # Pass progress callback to batch client for real-time updates
        self.batch_genie = BatchGenieClient(genie_client, genie_config, progress_callback)

        # SQL execution config
        self.sql_max_concurrent = self.config.get("sql_max_concurrent", 10)
        self.sql_timeout = self.config.get("sql_timeout", 60)

        # Evaluation config - smaller chunks = faster individual responses
        self.eval_chunk_size = self.config.get("eval_chunk_size", 5)
        self.eval_timeout = self.config.get("eval_timeout", 30)

        logger.info(f"BatchBenchmarkScorer initialized: "
                   f"genie_concurrent={genie_config['max_concurrent']}, "
                   f"sql_concurrent={self.sql_max_concurrent}, "
                   f"eval_chunk_size={self.eval_chunk_size}")

    def score(self, benchmarks: List[Dict]) -> Dict:
        """
        Score benchmarks using three-phase batch execution.

        Args:
            benchmarks: List of benchmark dicts

        Returns:
            Score summary dict
        """
        logger.info(f"Starting BATCH scoring for {len(benchmarks)} benchmarks")
        start_time = time.time()

        # Run async batch scoring
        results = asyncio.run(self._score_async(benchmarks))

        # Calculate metrics
        passed = sum(1 for r in results if r["passed"])
        failed = len(results) - passed
        score = passed / len(results) if results else 0.0
        duration = time.time() - start_time

        summary = {
            "score": score,
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "results": results,
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": duration,
            "scoring_method": "batch"
        }

        logger.info(f"\n{'='*60}")
        logger.info(f"Batch Score: {score:.2%} ({passed}/{len(results)} passed)")
        logger.info(f"Duration: {duration:.1f}s ({duration/len(results):.1f}s per benchmark)")
        logger.info(f"{'='*60}\n")

        return summary

    async def _score_async(self, benchmarks: List[Dict]) -> List[Dict]:
        """Three-phase async batch scoring."""
        total = len(benchmarks)
        start_time = time.time()

        # Phase 1: Batch Genie Queries (progress emitted by BatchGenieClient)
        logger.info(f"Phase 1: Batch Genie Queries ({total} questions)")
        genie_responses = await self.batch_genie.batch_ask(benchmarks)
        genie_success = sum(1 for r in genie_responses if r["success"])
        logger.info(f"Phase 1 complete: {genie_success}/{total} succeeded")

        # Phase 2: Batch SQL Execution
        logger.info(f"Phase 2: SQL Execution")
        self._emit_progress({"event_type": "progress", "phase": "sql", "completed": 0, "total": total, "message": "Executing SQL..."})
        sql_results = await self._batch_execute_sql(benchmarks, genie_responses)
        sql_success = sum(1 for r in sql_results if r.get("expected_success") and r.get("genie_success"))
        logger.info(f"Phase 2 complete: {sql_success}/{total} succeeded")
        self._emit_progress({"event_type": "progress", "phase": "sql", "completed": total, "total": total, "message": "SQL complete"})

        # Phase 3: Batch LLM Evaluation
        logger.info(f"Phase 3: LLM Evaluation")
        self._emit_progress({"event_type": "progress", "phase": "eval", "completed": 0, "total": total, "message": "Evaluating results..."})
        evaluations = await self._batch_evaluate(sql_results)
        eval_success = sum(1 for e in evaluations if e["passed"])
        logger.info(f"Phase 3 complete: {eval_success}/{total} passed")

        # Final progress
        duration = time.time() - start_time
        self._emit_progress({
            "event_type": "progress",
            "phase": "complete",
            "completed": total,
            "total": total,
            "passed": eval_success,
            "score": eval_success / total if total > 0 else 0,
            "message": f"Done: {eval_success}/{total} passed ({eval_success/total*100:.0f}%)"
        })

        return evaluations

    def _emit_progress(self, event: Dict):
        """Emit a progress event with consistent structure."""
        if self.progress_callback:
            from datetime import datetime
            event["timestamp"] = datetime.now().isoformat()
            self.progress_callback(event)

    async def _batch_execute_sql(
        self,
        benchmarks: List[Dict],
        genie_responses: List[Dict]
    ) -> List[Dict]:
        """
        Execute all SQL queries in batch (concurrent).

        Args:
            benchmarks: Original benchmarks
            genie_responses: Genie responses from Phase 1

        Returns:
            List of SQL result dicts
        """
        tasks = []

        for benchmark, genie_resp in zip(benchmarks, genie_responses):
            tasks.append(
                self._execute_sql_pair(benchmark, genie_resp)
            )

        # Execute concurrently with semaphore
        semaphore = asyncio.Semaphore(self.sql_max_concurrent)

        async def execute_with_limit(task):
            async with semaphore:
                return await task

        results = await asyncio.gather(
            *[execute_with_limit(task) for task in tasks],
            return_exceptions=True
        )

        # Handle exceptions
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"SQL execution error [{i}]: {result}")
                processed.append({
                    "benchmark_id": benchmarks[i].get("id"),
                    "expected_success": False,
                    "genie_success": False,
                    "error": str(result)
                })
            else:
                processed.append(result)

        return processed

    async def _execute_sql_pair(
        self,
        benchmark: Dict,
        genie_response: Dict
    ) -> Dict:
        """
        Execute expected SQL and Genie SQL for one benchmark.

        Args:
            benchmark: Benchmark dict
            genie_response: Genie response from Phase 1

        Returns:
            SQL result dict
        """
        benchmark_id = benchmark.get("id", "unknown")
        expected_sql = benchmark["expected_sql"]

        result = {
            "benchmark_id": benchmark_id,
            "question": benchmark["question"],
            "expected_sql": expected_sql,
            "genie_response": genie_response
        }

        # Execute expected SQL
        try:
            expected_exec = await self._execute_sql_async(expected_sql)
            result["expected_success"] = expected_exec["status"] == "SUCCEEDED"
            result["expected_result"] = expected_exec.get("result")
            result["expected_error"] = expected_exec.get("error")
        except Exception as e:
            logger.error(f"Expected SQL error [{benchmark_id}]: {e}")
            result["expected_success"] = False
            result["expected_error"] = str(e)

        # Execute Genie SQL (if available)
        if genie_response["success"] and genie_response["response"]:
            genie_sql = genie_response["response"].get("sql")
            genie_result_from_api = genie_response["response"].get("result")

            result["genie_sql"] = genie_sql

            # Option 1: Use result from Genie API if available
            if genie_result_from_api:
                result["genie_success"] = True
                result["genie_result"] = genie_result_from_api
            # Option 2: Execute Genie SQL ourselves
            elif genie_sql:
                try:
                    genie_exec = await self._execute_sql_async(genie_sql)
                    result["genie_success"] = genie_exec["status"] == "SUCCEEDED"
                    result["genie_result"] = genie_exec.get("result")
                    result["genie_error"] = genie_exec.get("error")
                except Exception as e:
                    logger.error(f"Genie SQL error [{benchmark_id}]: {e}")
                    result["genie_success"] = False
                    result["genie_error"] = str(e)
            else:
                result["genie_success"] = False
                result["genie_error"] = "No SQL generated"
        else:
            result["genie_success"] = False
            result["genie_sql"] = None
            result["genie_error"] = genie_response.get("error", "Genie call failed")

        return result

    async def _execute_sql_async(self, sql: str) -> Dict:
        """
        Async wrapper for SQL execution.

        Args:
            sql: SQL query

        Returns:
            Execution result dict
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.sql_executor.execute(sql, timeout=self.sql_timeout)
        )

    async def _batch_evaluate(self, sql_results: List[Dict]) -> List[Dict]:
        """
        Evaluate all results in batches using LLM.

        Args:
            sql_results: SQL results from Phase 2

        Returns:
            List of evaluation result dicts
        """
        # Split into chunks for token limits
        chunks = [
            sql_results[i:i + self.eval_chunk_size]
            for i in range(0, len(sql_results), self.eval_chunk_size)
        ]

        logger.info(f"Evaluating in {len(chunks)} chunks of {self.eval_chunk_size} (PARALLEL)")

        # Evaluate all chunks in parallel
        chunk_tasks = [
            self._evaluate_chunk(chunk)
            for chunk in chunks
        ]

        # Run all chunk evaluations concurrently
        chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)

        # Flatten results
        all_evaluations = []
        for i, result in enumerate(chunk_results):
            if isinstance(result, Exception):
                logger.error(f"Chunk {i+1} evaluation error: {result}")
                # Fallback: mark all as failed
                all_evaluations.extend([
                    {
                        "benchmark_id": r.get("benchmark_id"),
                        "question": r.get("question"),
                        "passed": False,
                        "reason": f"Evaluation error: {str(result)}"
                    }
                    for r in chunks[i]
                ])
            else:
                all_evaluations.extend(result)

        return all_evaluations

    async def _evaluate_chunk(self, chunk: List[Dict]) -> List[Dict]:
        """
        Evaluate a chunk of results using LLM.

        Args:
            chunk: Chunk of SQL results

        Returns:
            List of evaluation dicts
        """
        # Build batch evaluation prompt
        prompt = self._build_batch_eval_prompt(chunk)

        # Call LLM
        try:
            loop = asyncio.get_event_loop()
            llm_response = await loop.run_in_executor(
                None,
                lambda: self.llm_client.generate(prompt, max_tokens=4000)
            )

            # Parse LLM response (expects JSON array)
            evaluations = self._parse_batch_eval_response(llm_response, chunk)

        except Exception as e:
            logger.error(f"Batch evaluation error: {e}")
            # Fallback: all failed
            evaluations = [
                {
                    "benchmark_id": r["benchmark_id"],
                    "question": r["question"],
                    "passed": False,
                    "failure_reason": f"Evaluation error: {str(e)}",
                    "failure_category": "eval_error"
                }
                for r in chunk
            ]

        return evaluations

    def _build_batch_eval_prompt(self, chunk: List[Dict]) -> str:
        """Build prompt for batch evaluation."""
        # Load base prompt
        base_prompt = self.prompt_loader.load("answer_comparison")

        # Format each result
        result_blocks = []
        for i, r in enumerate(chunk):
            block = f"""
## Result {i + 1}

**Benchmark ID:** {r['benchmark_id']}

**Question:** {r['question']}

**Expected SQL:**
```sql
{r.get('expected_sql', 'N/A')}
```

**Genie SQL:**
```sql
{r.get('genie_sql', 'N/A')}
```

**Expected Result:**
{json.dumps(r.get('expected_result'), indent=2) if r.get('expected_result') else 'N/A'}

**Genie Result:**
{json.dumps(r.get('genie_result'), indent=2) if r.get('genie_result') else 'N/A'}

---
"""
            result_blocks.append(block)

        # Build final prompt - override the base prompt format for batch processing
        prompt = f"""
You are evaluating Genie Space answers in BATCH mode.

For each result, compare the expected answer with Genie's answer using these rules:
- Focus on DATA RESULTS when available (preferred)
- Fall back to SQL comparison only if data execution failed
- Be lenient - PASS if semantically equivalent
- Row count differences are OK if core data matches

**Results to Evaluate:**

{"".join(result_blocks)}

Return a JSON array with {len(chunk)} evaluation objects, one per result IN THE SAME ORDER:

```json
[
  {{
    "benchmark_id": "bench_1",
    "passed": true,
    "failure_reason": "Brief explanation if failed, or null if passed",
    "failure_category": "wrong_table" | "wrong_calculation" | "missing_synonym" | "missing_pattern" | "wrong_filter" | null
  }},
  {{
    "benchmark_id": "bench_2",
    "passed": false,
    "failure_reason": "Specific reason why it failed",
    "failure_category": "wrong_calculation"
  }}
]
```

**Failure Categories:**
- `wrong_table`: Used incorrect table
- `wrong_calculation`: Wrong aggregation (SUM vs COUNT, etc.)
- `missing_synonym`: Term not recognized
- `missing_pattern`: Query pattern not understood
- `wrong_filter`: Incorrect WHERE/date filtering

**IMPORTANT:**
- Use `failure_reason` (not `reasoning`)
- Include `benchmark_id` to match results
- Return ONLY the JSON array, no other text
- Order must match the input order
"""
        return prompt

    def _parse_batch_eval_response(
        self,
        llm_response: str,
        chunk: List[Dict]
    ) -> List[Dict]:
        """Parse LLM batch evaluation response."""
        try:
            # Extract JSON from response
            json_str = llm_response
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]

            evals = json.loads(json_str.strip())

            # Merge with original data
            results = []
            for eval_data, original in zip(evals, chunk):
                results.append({
                    **original,
                    "passed": eval_data.get("passed", False),
                    "failure_reason": eval_data.get("failure_reason"),
                    "failure_category": eval_data.get("failure_category")
                })

            return results

        except Exception as e:
            logger.error(f"Failed to parse batch evaluation response: {e}")
            # Fallback
            return [
                {
                    **r,
                    "passed": False,
                    "failure_reason": "Failed to parse evaluation",
                    "failure_category": "eval_parse_error"
                }
                for r in chunk
            ]
