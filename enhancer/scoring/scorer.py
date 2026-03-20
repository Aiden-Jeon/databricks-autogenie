"""
Benchmark Scorer

Runs benchmark questions through Genie and scores the results using LLM judge.
"""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

from enhancer.api.genie_client import GenieConversationalClient
from enhancer.utils.sql import SQLExecutor
from prompts.prompt_loader import PromptLoader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BenchmarkScorer:
    """Score Genie Space performance using benchmark Q&A pairs."""

    def __init__(
        self,
        genie_client: GenieConversationalClient,
        llm_client,  # LLM client for answer comparison
        sql_executor: SQLExecutor,  # REQUIRED: SQL executor for result comparison
        config: Dict = None
    ):
        """
        Initialize benchmark scorer.

        Args:
            genie_client: Client for asking Genie questions
            llm_client: LLM client for comparing answers
            sql_executor: SQL executor for running queries (REQUIRED - always compare actual results)
            config: Scorer configuration
                - question_timeout: Timeout for Genie questions (default 120)
                - parallel_workers: Number of parallel workers (0=sequential)
                - question_delay: Delay between questions (default 3.0)
                - error_delay: Extra delay after errors (default 5.0)
                - debug_mode: Enable verbose debug logging (default False)
                - save_debug_output: Save raw LLM responses to file (default False)
                - debug_output_path: Path for debug output files
        """
        if sql_executor is None:
            raise ValueError("sql_executor is required - result comparison is mandatory")

        self.genie_client = genie_client
        self.llm_client = llm_client
        self.sql_executor = sql_executor
        self.config = config or {}
        self.prompt_loader = PromptLoader()
        # Always use result comparison - comparing actual data values
        self.use_result_comparison = True

        # Debug mode settings
        self.debug_mode = self.config.get("debug_mode", False)
        self.save_debug_output = self.config.get("save_debug_output", False)
        self.debug_output_path = self.config.get("debug_output_path", "/tmp/scorer_debug")

        if self.debug_mode:
            logger.setLevel(logging.DEBUG)
            logger.info("🔍 Debug mode enabled")

    def score(self, benchmarks: List[Dict]) -> Dict:
        """
        Run all benchmarks and calculate score.

        Args:
            benchmarks: List of benchmark dictionaries with:
                - id: str
                - question: str
                - expected_sql: str
                - (optional) expected_result: dict

        Returns:
            {
                "score": float (0.0 to 1.0),
                "total": int,
                "passed": int,
                "failed": int,
                "results": List[Dict],
                "timestamp": str,
                "duration_seconds": float
            }
        """
        logger.info(f"Starting benchmark scoring with {len(benchmarks)} questions")
        start_time = datetime.now()

        results = []
        # Parallel workers (0 = sequential, >0 = parallel)
        parallel_workers = self.config.get("parallel_workers", 0)
        # Add delay between questions to avoid rate limiting (default 3 seconds)
        question_delay = self.config.get("question_delay", 3.0)
        # Extra delay after errors (default 5 seconds)
        error_delay = self.config.get("error_delay", 5.0)

        if parallel_workers > 0:
            # PARALLEL MODE
            logger.info(f"Running {len(benchmarks)} benchmarks in PARALLEL ({parallel_workers} workers)")
            results = self._score_parallel(benchmarks, parallel_workers)
        else:
            # SEQUENTIAL MODE (original behavior)
            for i, benchmark in enumerate(benchmarks):
                logger.info(f"[{i+1}/{len(benchmarks)}] Testing: {benchmark['question'][:80]}...")

                result = self._score_single_benchmark(benchmark)
                results.append(result)

                # Log result
                status = "✅ PASS" if result["passed"] else "❌ FAIL"
                logger.info(f"  {status} ({result.get('failure_category', 'N/A')})")

                # Delay between questions to avoid rate limiting
                if i < len(benchmarks) - 1:
                    # Longer delay after errors to let API recover
                    if result.get("failure_category") == "api_error":
                        logger.info(f"  Waiting {error_delay}s after API error...")
                        time.sleep(error_delay)
                    elif question_delay > 0:
                        time.sleep(question_delay)

        # Calculate overall score
        passed = sum(1 for r in results if r["passed"])
        failed = len(results) - passed
        score = passed / len(results) if results else 0.0

        duration = (datetime.now() - start_time).total_seconds()

        # Analyze failure categories
        failure_analysis = self._analyze_failures(results)

        summary = {
            "score": score,
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "results": results,
            "timestamp": start_time.isoformat(),
            "duration_seconds": duration,
            "failure_analysis": failure_analysis
        }

        logger.info(f"\n{'='*60}")
        logger.info(f"Benchmark Score: {score:.2%} ({passed}/{len(results)} passed)")
        logger.info(f"Duration: {duration:.1f}s")

        # Log failure breakdown
        if failure_analysis["categories"]:
            logger.info(f"\nFailure Breakdown:")
            for category, count in sorted(failure_analysis["categories"].items(), key=lambda x: -x[1]):
                pct = (count / failed * 100) if failed > 0 else 0
                logger.info(f"  {category}: {count} ({pct:.1f}%)")

        logger.info(f"{'='*60}\n")

        return summary

    def _analyze_failures(self, results: List[Dict]) -> Dict:
        """
        Analyze failure patterns across all results.

        Args:
            results: List of benchmark results

        Returns:
            {
                "categories": {category: count},
                "by_category": {category: [benchmark_ids]},
                "llm_parse_errors": int,
                "unknown_failures": int,
                "suggestions": [str]
            }
        """
        categories = {}
        by_category = {}
        llm_parse_errors = 0
        unknown_failures = 0

        for r in results:
            if r["passed"]:
                continue

            category = r.get("failure_category", "unknown_failure")
            benchmark_id = r.get("benchmark_id", "unknown")

            categories[category] = categories.get(category, 0) + 1

            if category not in by_category:
                by_category[category] = []
            by_category[category].append(benchmark_id)

            if category == "llm_parse_error":
                llm_parse_errors += 1
            elif category == "unknown_failure":
                unknown_failures += 1

            # Check comparison details for parse errors
            comparison = r.get("comparison_details", {})
            if comparison.get("_parse_error"):
                llm_parse_errors += 1

        # Generate suggestions based on failure patterns
        suggestions = []

        if llm_parse_errors > 0:
            suggestions.append(
                f"⚠️ {llm_parse_errors} LLM response parsing errors - check LLM endpoint and response format"
            )

        if unknown_failures > 0:
            suggestions.append(
                f"⚠️ {unknown_failures} unknown failures - enable debug_mode for more details"
            )

        if categories.get("wrong_aggregation", 0) > 0:
            suggestions.append(
                "💡 Aggregation errors detected - consider adding more sample queries with aggregations"
            )

        if categories.get("wrong_join", 0) > 0:
            suggestions.append(
                "💡 Join errors detected - review table relationships in Genie Space"
            )

        if categories.get("wrong_filter", 0) > 0:
            suggestions.append(
                "💡 Filter errors detected - check date handling and column descriptions"
            )

        if categories.get("api_error", 0) > 0:
            suggestions.append(
                "⚠️ API errors detected - check Genie Space availability and credentials"
            )

        return {
            "categories": categories,
            "by_category": by_category,
            "llm_parse_errors": llm_parse_errors,
            "unknown_failures": unknown_failures,
            "suggestions": suggestions
        }

    def _score_parallel(self, benchmarks: List[Dict], max_workers: int) -> List[Dict]:
        """
        Score benchmarks in parallel using ThreadPoolExecutor.

        Args:
            benchmarks: List of benchmark dictionaries
            max_workers: Maximum number of parallel workers

        Returns:
            List of result dictionaries (in original order)
        """
        results = [None] * len(benchmarks)  # Preserve order

        def score_with_index(idx_benchmark):
            idx, benchmark = idx_benchmark
            try:
                result = self._score_single_benchmark(benchmark)
                status = "✅" if result["passed"] else "❌"
                logger.info(f"  [{idx+1}] {status} {benchmark['question'][:50]}...")
                return idx, result
            except Exception as e:
                logger.error(f"  [{idx+1}] Error: {e}")
                return idx, {
                    "benchmark_id": benchmark.get("id"),
                    "question": benchmark["question"],
                    "expected_sql": benchmark["expected_sql"],
                    "genie_sql": None,
                    "passed": False,
                    "failure_reason": str(e),
                    "failure_category": "parallel_error",
                    "response_time": 0
                }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(score_with_index, (i, b)): i
                for i, b in enumerate(benchmarks)
            }

            completed = 0
            for future in as_completed(futures):
                idx, result = future.result()
                results[idx] = result
                completed += 1
                logger.info(f"  Progress: {completed}/{len(benchmarks)} completed")

        return results

    def _score_single_benchmark(self, benchmark: Dict) -> Dict:
        """
        Score a single benchmark question.

        Args:
            benchmark: Benchmark dictionary

        Returns:
            {
                "benchmark_id": str,
                "question": str,
                "expected_sql": str,
                "genie_sql": str or None,
                "expected_result": dict or None,
                "genie_result": dict or None,
                "passed": bool,
                "failure_reason": str or None,
                "failure_category": str or None,
                "comparison_details": dict,
                "response_time": float,
                "_debug": dict (if debug_mode enabled)
            }
        """
        question = benchmark["question"]
        expected_sql = benchmark["expected_sql"]
        benchmark_id = benchmark.get("id", "unknown")

        debug_info = {
            "benchmark_id": benchmark_id,
            "stages": [],
            "timestamps": {}
        }

        if self.debug_mode:
            debug_info["timestamps"]["start"] = datetime.now().isoformat()
            logger.info(f"  🔍 DEBUG: Starting benchmark {benchmark_id}")

        # Ask Genie
        try:
            if self.debug_mode:
                debug_info["timestamps"]["genie_start"] = datetime.now().isoformat()

            genie_response = self.genie_client.ask(
                question,
                timeout=self.config.get("question_timeout", 120)
            )

            if self.debug_mode:
                debug_info["timestamps"]["genie_end"] = datetime.now().isoformat()
                debug_info["genie_status"] = genie_response.get("status")
                debug_info["genie_has_sql"] = genie_response.get("sql") is not None
                debug_info["genie_has_result"] = genie_response.get("result") is not None
                debug_info["stages"].append("genie_completed")

        except Exception as e:
            logger.error(f"Error asking Genie: {e}")
            if self.debug_mode:
                debug_info["genie_error"] = str(e)
                debug_info["stages"].append("genie_failed")

            result = {
                "benchmark_id": benchmark_id,
                "question": question,
                "expected_sql": expected_sql,
                "genie_sql": None,
                "expected_result": None,
                "genie_result": None,
                "passed": False,
                "failure_reason": f"Genie API error: {str(e)}",
                "failure_category": "api_error",
                "comparison_details": {},
                "response_time": 0
            }
            if self.debug_mode:
                result["_debug"] = debug_info
            return result

        # Extract Genie's SQL and result
        genie_sql = genie_response.get("sql")
        genie_result = genie_response.get("result")

        if self.debug_mode:
            if genie_sql:
                debug_info["genie_sql_preview"] = genie_sql[:300]
            if genie_result:
                debug_info["genie_result_type"] = type(genie_result).__name__

        # Execute expected SQL to get actual results (REQUIRED for result comparison)
        expected_result = None
        expected_execution_error = None
        if expected_sql:
            logger.info(f"  Executing expected SQL for result comparison...")
            try:
                if self.debug_mode:
                    debug_info["timestamps"]["expected_sql_start"] = datetime.now().isoformat()

                expected_execution = self.sql_executor.execute(expected_sql, timeout=60)
                if expected_execution["status"] == "SUCCEEDED":
                    expected_result = expected_execution["result"]
                    logger.info(f"  Expected query returned {expected_result.get('row_count', 'N/A')} rows")
                    if self.debug_mode:
                        debug_info["expected_result_rows"] = expected_result.get("row_count")
                        debug_info["stages"].append("expected_sql_executed")
                else:
                    expected_execution_error = expected_execution.get("error", "Unknown error")
                    logger.warning(f"  Expected SQL execution failed: {expected_execution_error}")
                    if self.debug_mode:
                        debug_info["expected_sql_error"] = expected_execution_error

                if self.debug_mode:
                    debug_info["timestamps"]["expected_sql_end"] = datetime.now().isoformat()

            except Exception as e:
                expected_execution_error = str(e)
                logger.warning(f"  Could not execute expected SQL: {e}")
                if self.debug_mode:
                    debug_info["expected_sql_exception"] = str(e)

        # Check if Genie generated SQL
        if genie_response["status"] != "COMPLETED":
            failure_category = self._categorize_failure(genie_response, None)
            if self.debug_mode:
                debug_info["failure_category"] = failure_category
                debug_info["stages"].append(f"genie_not_completed:{genie_response['status']}")

            result = {
                "benchmark_id": benchmark_id,
                "question": question,
                "expected_sql": expected_sql,
                "genie_sql": genie_sql,
                "expected_result": None,
                "genie_result": None,
                "passed": False,
                "failure_reason": genie_response.get("error", "No SQL generated"),
                "failure_category": failure_category,
                "comparison_details": {},
                "response_time": genie_response.get("response_time", 0)
            }
            if self.debug_mode:
                result["_debug"] = debug_info
            return result

        # Compare answers using LLM judge (with executed results if available)
        if self.debug_mode:
            debug_info["timestamps"]["comparison_start"] = datetime.now().isoformat()
            debug_info["stages"].append("starting_llm_comparison")

        comparison = self._compare_answers(
            question=question,
            expected_sql=expected_sql,
            genie_sql=genie_sql,
            expected_result=expected_result or benchmark.get("expected_result"),
            genie_result=genie_result
        )

        if self.debug_mode:
            debug_info["timestamps"]["comparison_end"] = datetime.now().isoformat()
            debug_info["comparison_passed"] = comparison.get("passed")
            debug_info["comparison_confidence"] = comparison.get("confidence")
            debug_info["comparison_had_parse_error"] = comparison.get("_parse_error", False)
            if comparison.get("_raw_response"):
                debug_info["llm_raw_response_preview"] = comparison.get("_raw_response")[:500]
            debug_info["stages"].append("llm_comparison_completed")

        # Save debug output if enabled
        if self.save_debug_output:
            self._save_debug_output(benchmark_id, debug_info, comparison)

        failure_category = None
        if not comparison["passed"]:
            failure_category = self._categorize_failure(genie_response, comparison)
            if self.debug_mode:
                debug_info["failure_category"] = failure_category
                logger.info(f"  🔍 DEBUG: Categorized as '{failure_category}'")

        result = {
            "benchmark_id": benchmark_id,
            "question": question,
            "expected_sql": expected_sql,
            "genie_sql": genie_sql,
            "expected_result": expected_result or benchmark.get("expected_result"),
            "genie_result": genie_result,
            "passed": comparison["passed"],
            "failure_reason": comparison.get("reasoning") if not comparison["passed"] else None,
            "failure_category": failure_category,
            "comparison_details": comparison,
            "response_time": genie_response.get("response_time", 0)
        }

        if self.debug_mode:
            debug_info["timestamps"]["end"] = datetime.now().isoformat()
            result["_debug"] = debug_info

        return result

    def _save_debug_output(self, benchmark_id: str, debug_info: Dict, comparison: Dict):
        """
        Save debug output to file for analysis.

        Args:
            benchmark_id: Benchmark ID
            debug_info: Debug information dictionary
            comparison: Comparison result dictionary
        """
        try:
            import os
            os.makedirs(self.debug_output_path, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.debug_output_path}/debug_{benchmark_id}_{timestamp}.json"

            output = {
                "benchmark_id": benchmark_id,
                "debug_info": debug_info,
                "comparison": comparison
            }

            with open(filename, 'w') as f:
                json.dump(output, f, indent=2, default=str)

            logger.debug(f"Debug output saved to: {filename}")

        except Exception as e:
            logger.warning(f"Failed to save debug output: {e}")

    def _compare_answers(
        self,
        question: str,
        expected_sql: str,
        genie_sql: str,
        expected_result: Dict = None,
        genie_result: Dict = None
    ) -> Dict:
        """
        Compare expected vs actual answer using LLM judge.

        PRIORITY: Always compare actual data results when available.
        Fallback to SQL comparison only if result execution failed.

        Args:
            question: The question
            expected_sql: Expected SQL
            genie_sql: Genie's SQL
            expected_result: Expected query result (from executing expected_sql)
            genie_result: Genie's query result (from Genie response)

        Returns:
            {
                "passed": bool,
                "confidence": "high" | "medium" | "low",
                "reasoning": str,
                "differences": List[str],
                "semantic_equivalence": str,
                "comparison_type": "results" | "sql"
            }
        """
        # PRIORITY: Compare actual results when available
        # This catches cases where different SQL produces same results (should pass)
        # And where similar SQL produces different results (should fail)
        if expected_result and genie_result:
            comparing_type = "results"
            expected = expected_result
            actual = genie_result
            logger.info(f"  Comparing actual data RESULTS (expected: {expected_result.get('row_count', '?')} rows, genie: {genie_result.get('row_count', '?')} rows)")
        else:
            # Fallback to SQL comparison if results not available
            comparing_type = "sql"
            expected = expected_sql
            actual = genie_sql
            if not expected_result:
                logger.warning(f"  ⚠️ Expected result not available - falling back to SQL comparison")
            if not genie_result:
                logger.warning(f"  ⚠️ Genie result not available - falling back to SQL comparison")
            logger.info(f"  Comparing SQL structure (fallback)...")

        logger.debug(f"  Expected: {str(expected)[:200]}...")
        logger.debug(f"  Genie: {str(actual)[:200]}...")

        # Use LLM judge with fat prompt
        prompt = self.prompt_loader.format_answer_comparison_prompt(
            question=question,
            expected_result=expected,
            genie_result=actual
        )

        # Log prompt length for debugging
        logger.debug(f"  Prompt length: {len(prompt)} chars")

        try:
            response = self.llm_client.generate(
                prompt=prompt,
                temperature=0.1,  # Low temperature for consistent judging
                max_tokens=100000
            )

            # Log raw response for debugging
            logger.debug(f"  Raw LLM response length: {len(response)} chars")
            if self.config.get("debug_mode"):
                logger.info(f"  === LLM RAW RESPONSE START ===")
                logger.info(response[:2000])
                logger.info(f"  === LLM RAW RESPONSE END ===")

            # Parse JSON response
            comparison_result = self._parse_comparison_result(response)

            # Add comparison type to result
            comparison_result["comparison_type"] = comparing_type

            # Enhanced logging
            logger.info(f"  LLM verdict: passed={comparison_result.get('passed')}, confidence={comparison_result.get('confidence')}, type={comparing_type}")
            if comparison_result.get('_parse_error'):
                logger.warning(f"  ⚠️ LLM response parsing had issues")
            if not comparison_result.get('passed'):
                logger.info(f"  Reason: {comparison_result.get('reasoning', 'N/A')[:200]}")
                differences = comparison_result.get('differences', [])
                if differences:
                    logger.info(f"  Differences ({len(differences)}): {differences[:3]}")
                semantic = comparison_result.get('semantic_equivalence', '')
                if semantic:
                    logger.info(f"  Semantic: {semantic[:150]}")

            return comparison_result

        except Exception as e:
            logger.error(f"Error in LLM comparison: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Fallback: simple SQL comparison
            fallback_result = self._simple_sql_comparison(expected_sql, genie_sql)
            fallback_result["_llm_error"] = str(e)
            return fallback_result

    def _parse_comparison_result(self, response: str) -> Dict:
        """
        Parse LLM comparison response with robust JSON extraction.

        Args:
            response: LLM response (should be JSON)

        Returns:
            Parsed comparison dictionary
        """
        import re

        original_response = response
        logger.debug(f"Raw LLM response ({len(response)} chars): {response[:500]}...")

        # Try multiple JSON extraction methods
        extraction_methods = [
            ("markdown_json", self._extract_json_from_markdown),
            ("find_json_object", self._extract_json_object),
            ("direct_parse", lambda r: json.loads(r)),
            ("relaxed_parse", self._relaxed_json_parse),
        ]

        for method_name, extractor in extraction_methods:
            try:
                result = extractor(response)
                if result and isinstance(result, dict):
                    # Validate required fields
                    if "passed" in result:
                        logger.debug(f"JSON extracted using method: {method_name}")
                        # Ensure all expected fields exist
                        result.setdefault("confidence", "medium")
                        result.setdefault("reasoning", "")
                        result.setdefault("differences", [])
                        result.setdefault("semantic_equivalence", "")
                        return result
            except Exception as e:
                logger.debug(f"Method {method_name} failed: {e}")
                continue

        # All methods failed - log full response for debugging
        logger.error(f"Failed to parse LLM response with all methods")
        logger.error(f"Full response:\n{original_response}")

        # Try to infer pass/fail from response text
        response_lower = response.lower()
        inferred_pass = None
        if '"passed": true' in response_lower or '"passed":true' in response_lower:
            inferred_pass = True
        elif '"passed": false' in response_lower or '"passed":false' in response_lower:
            inferred_pass = False
        elif 'pass' in response_lower and 'fail' not in response_lower:
            inferred_pass = True
        elif 'fail' in response_lower or 'incorrect' in response_lower or 'wrong' in response_lower:
            inferred_pass = False

        return {
            "passed": inferred_pass if inferred_pass is not None else False,
            "confidence": "low",
            "reasoning": f"Failed to parse LLM response - inferred from text",
            "differences": ["LLM response parsing error"],
            "semantic_equivalence": "Unknown",
            "_raw_response": original_response[:1000],
            "_parse_error": True
        }

    def _extract_json_from_markdown(self, response: str) -> Dict:
        """Extract JSON from markdown code blocks."""
        import re

        # Try ```json ... ``` first
        match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if match:
            return json.loads(match.group(1).strip())

        # Try ``` ... ``` (no language specified)
        match = re.search(r'```\s*([\s\S]*?)\s*```', response)
        if match:
            content = match.group(1).strip()
            # Skip if it looks like SQL or other code
            if content.startswith('{'):
                return json.loads(content)

        raise ValueError("No markdown JSON block found")

    def _extract_json_object(self, response: str) -> Dict:
        """Find and extract a JSON object from anywhere in the response."""
        import re

        # Find the first { and try to match to closing }
        start = response.find('{')
        if start == -1:
            raise ValueError("No JSON object found")

        # Track brace depth to find matching closing brace
        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(response[start:], start):
            if escape_next:
                escape_next = False
                continue
            if char == '\\' and in_string:
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    json_str = response[start:i+1]
                    return json.loads(json_str)

        raise ValueError("Unbalanced braces in JSON")

    def _relaxed_json_parse(self, response: str) -> Dict:
        """Try to parse JSON with some relaxations."""
        import re

        # Remove any leading/trailing non-JSON content
        response = response.strip()

        # Remove common prefixes
        prefixes_to_remove = [
            "Here is the comparison:",
            "Here's my analysis:",
            "Based on my analysis:",
            "Result:",
            "Output:",
        ]
        for prefix in prefixes_to_remove:
            if response.lower().startswith(prefix.lower()):
                response = response[len(prefix):].strip()

        # Try direct parse
        return json.loads(response)

    def _simple_sql_comparison(self, expected_sql: str, genie_sql: str) -> Dict:
        """
        Simple SQL comparison fallback.

        Args:
            expected_sql: Expected SQL
            genie_sql: Genie's SQL

        Returns:
            Comparison result
        """
        # Handle None cases
        if not genie_sql:
            return {
                "passed": False,
                "confidence": "high",
                "reasoning": "Genie did not generate any SQL",
                "differences": ["No SQL generated"],
                "semantic_equivalence": "No output"
            }

        if not expected_sql:
            return {
                "passed": False,
                "confidence": "low",
                "reasoning": "No expected SQL to compare against",
                "differences": ["Missing expected SQL"],
                "semantic_equivalence": "Unknown"
            }

        # Normalize both SQLs
        expected_normalized = self._normalize_sql(expected_sql)
        genie_normalized = self._normalize_sql(genie_sql)

        passed = expected_normalized == genie_normalized

        return {
            "passed": passed,
            "confidence": "medium" if passed else "low",
            "reasoning": "Simple SQL string comparison (LLM judge failed)",
            "differences": [] if passed else ["SQLs differ after normalization"],
            "semantic_equivalence": "Exact match" if passed else "Different"
        }

    def _normalize_sql(self, sql: str) -> str:
        """
        Normalize SQL for comparison.

        Args:
            sql: SQL query string

        Returns:
            Normalized SQL
        """
        if not sql:
            return ""

        import re
        # Convert to uppercase
        sql = sql.upper()
        # Remove extra whitespace
        sql = re.sub(r'\s+', ' ', sql)
        # Remove trailing semicolon
        sql = sql.rstrip(';')
        # Strip
        sql = sql.strip()
        return sql

    def _categorize_failure(self, genie_response: Dict, comparison: Dict = None) -> str:
        """
        Categorize failure type for targeted fixes.

        Analyzes multiple fields from the comparison result to determine
        the most specific failure category possible.

        Args:
            genie_response: Genie's response
            comparison: Comparison result (if available)

        Returns:
            Failure category string
        """
        status = genie_response.get("status")

        if status == "FAILED":
            error = genie_response.get("error", "")
            # Handle case where error is a dict or None
            if isinstance(error, dict):
                error = error.get("message", "")
            if not error:
                error = ""
            error_lower = error.lower()

            if "not found" in error_lower or "does not exist" in error_lower:
                return "missing_table_or_column"
            elif "syntax" in error_lower:
                return "sql_syntax_error"
            elif "permission" in error_lower:
                return "permission_denied"
            elif "timeout" in error_lower or "timed out" in error_lower:
                return "query_timeout"
            elif "ambiguous" in error_lower:
                return "ambiguous_reference"
            else:
                return "execution_failed"

        elif status == "TIMEOUT":
            return "timeout"

        elif status == "COMPLETED":
            if not genie_response.get("sql"):
                return "no_sql_generated"

            if comparison:
                # Check if it was a parse error
                if comparison.get("_parse_error"):
                    return "llm_parse_error"

                # Collect all text to analyze from multiple fields
                reasoning = comparison.get("reasoning", "").lower()
                semantic = comparison.get("semantic_equivalence", "").lower()
                differences = comparison.get("differences", [])
                differences_text = " ".join(str(d).lower() for d in differences)

                # Combine all text for analysis
                all_text = f"{reasoning} {semantic} {differences_text}"

                # Categorize based on comprehensive keyword analysis
                category = self._analyze_failure_keywords(all_text)
                if category:
                    return category

                # If we have differences but couldn't categorize, try to be more specific
                if differences:
                    return self._categorize_from_differences(differences)

                # Generic semantic difference if comparison failed but no specific category
                return "semantic_difference"

        return "unknown_failure"

    def _analyze_failure_keywords(self, text: str) -> str:
        """
        Analyze text for failure category keywords.

        Args:
            text: Combined text from reasoning, semantic_equivalence, and differences

        Returns:
            Failure category or None if no match
        """
        # Define keyword patterns for each category (order matters - more specific first)
        category_patterns = [
            # Aggregation issues
            ("wrong_aggregation", [
                "sum instead of count", "count instead of sum",
                "avg instead of", "instead of avg",
                "wrong aggregation", "different aggregation",
                "sum vs count", "count vs sum",
                "aggregation function", "aggregate function",
                "sum(", "count(", "avg(", "max(", "min(",
            ]),
            # Join issues
            ("wrong_join", [
                "wrong join", "missing join", "extra join",
                "join type", "inner vs left", "left vs inner",
                "join condition", "cartesian", "cross join",
                "should join", "didn't join", "not joined",
            ]),
            # Filter/WHERE clause issues
            ("wrong_filter", [
                "wrong filter", "missing filter", "extra filter",
                "where clause", "missing where", "wrong where",
                "filter condition", "wrong condition",
                "included.*should.*excluded", "excluded.*should.*included",
                "wrong date", "date range", "wrong predicate",
            ]),
            # Column issues
            ("wrong_column", [
                "wrong column", "missing column", "extra column",
                "different column", "column name", "wrong field",
                "selecting wrong", "wrong attribute",
            ]),
            # Table issues
            ("wrong_table", [
                "wrong table", "different table", "missing table",
                "should query", "querying wrong",
            ]),
            # Grouping issues
            ("wrong_grouping", [
                "group by", "grouping", "wrong group",
                "missing group", "different grouping level",
            ]),
            # Ordering issues
            ("wrong_ordering", [
                "wrong order", "order by", "sorting",
                "ascending", "descending", "top n", "bottom n",
            ]),
            # Data/result issues
            ("result_mismatch", [
                "missing row", "extra row", "missing data",
                "different value", "wrong value", "value mismatch",
                "row count", "different result", "wrong result",
            ]),
            # Semantic/logic issues
            ("semantic_difference", [
                "semantically different", "different meaning",
                "misunderstood", "different interpretation",
                "wrong logic", "logic error",
            ]),
        ]

        for category, keywords in category_patterns:
            for keyword in keywords:
                if keyword in text:
                    logger.debug(f"Categorized as '{category}' due to keyword: '{keyword}'")
                    return category

        return None

    def _categorize_from_differences(self, differences: list) -> str:
        """
        Try to categorize based on the differences list.

        Args:
            differences: List of difference strings

        Returns:
            Failure category
        """
        if not differences:
            return "semantic_difference"

        # Analyze the structure of differences
        diff_text = " ".join(str(d).lower() for d in differences)

        # Check for specific patterns in differences
        if any(x in diff_text for x in ["expected sql:", "genie sql:"]):
            return "sql_mismatch"
        if any(x in diff_text for x in ["expected:", "actual:", "genie:"]):
            return "result_mismatch"
        if "row" in diff_text:
            return "row_count_mismatch"

        return "semantic_difference"


# Example usage
if __name__ == "__main__":
    import os
    from lib.benchmark_parser import BenchmarkLoader

    # Configuration
    HOST = os.getenv("DATABRICKS_HOST")
    TOKEN = os.getenv("DATABRICKS_TOKEN")
    SPACE_ID = os.getenv("GENIE_SPACE_ID")

    # Mock LLM client for testing
    class MockLLMClient:
        def generate(self, prompt, temperature=0.1, max_tokens=1000):
            # Return mock comparison result
            return json.dumps({
                "passed": True,
                "confidence": "high",
                "reasoning": "Mock comparison - always passes",
                "differences": [],
                "semantic_equivalence": "Mock result"
            })

    # Create clients
    genie_client = GenieConversationalClient(HOST, TOKEN, SPACE_ID)
    llm_client = MockLLMClient()

    # Load benchmarks
    loader = BenchmarkLoader("benchmarks/benchmarks.json")
    benchmarks = loader.load()

    # Create scorer
    scorer = BenchmarkScorer(genie_client, llm_client)

    # Run scoring
    results = scorer.score(benchmarks)

    print(json.dumps(results, indent=2))
