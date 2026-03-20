"""
Enhancement Planner - Context-Informed Fix Generation

Analyzes benchmark failures and generates fixes using:
1. The specific failure (what went wrong)
2. ALL benchmarks (domain context)
3. Best practices (how to fix properly)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class EnhancementPlanner:
    """
    Analyzes failures and generates context-informed fixes.

    Key difference from before: Each analysis includes ALL benchmarks
    as context, so fixes are informed by the full domain.

    Three fix categories:
    1. Metadata (table/column descriptions, synonyms)
    2. Sample Queries (parameterized templates)
    3. Instructions (text instructions)
    """

    FIX_CATEGORIES = ["metadata", "sample_query", "instruction"]

    def __init__(self, llm_client, prompts_dir: Path = None, all_benchmarks: List[Dict] = None):
        """
        Initialize enhancement planner.

        Args:
            llm_client: LLM client for generating fixes
            prompts_dir: Directory containing prompt templates
            all_benchmarks: ALL benchmarks for domain context
        """
        self.llm_client = llm_client
        self.all_benchmarks = all_benchmarks or []

        # Load prompts
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent.parent / "prompts"

        self.prompts = {}
        prompt_files = {
            "metadata": "metadata_analysis.txt",
            "sample_query": "sample_query_analysis.txt",
            "instruction": "instruction_analysis.txt"
        }

        for category, filename in prompt_files.items():
            prompt_file = prompts_dir / filename
            if prompt_file.exists():
                self.prompts[category] = prompt_file.read_text()
            else:
                logger.warning(f"Prompt file not found: {prompt_file}")
                self.prompts[category] = ""

    def set_all_benchmarks(self, benchmarks: List[Dict]) -> None:
        """Set all benchmarks for domain context."""
        self.all_benchmarks = benchmarks
        logger.info(f"Set {len(benchmarks)} benchmarks as domain context")

    def _format_benchmarks_context(self) -> str:
        """Format all benchmarks as context string."""
        if not self.all_benchmarks:
            return "No benchmarks provided."

        context_items = []
        for i, b in enumerate(self.all_benchmarks, 1):
            context_items.append(f"""
### Benchmark {i}: {b.get('id', 'unknown')[:8]}
**Korean Question:** {b.get('korean_question', '')}
**Expected SQL:**
```sql
{b.get('expected_sql', '')}
```
""")
        return "\n".join(context_items)

    def generate_plan(
        self,
        failed_benchmarks: List[Dict],
        space_config: Dict,
        parallel_workers: int = 1
    ) -> Dict[str, List[Dict]]:
        """
        Generate fixes for failed benchmarks with full domain context.

        Args:
            failed_benchmarks: List of failed benchmark results
            space_config: Current Genie Space configuration
            parallel_workers: Number of parallel LLM calls

        Returns:
            {
                "metadata": [fix1, fix2, ...],
                "sample_query": [fix1, fix2, ...],
                "instruction": [fix1, fix2, ...]
            }
        """
        logger.info("=" * 80)
        logger.info("Generating Context-Informed Enhancement Plan")
        logger.info("=" * 80)

        grouped_fixes = {category: [] for category in self.FIX_CATEGORIES}
        total_tasks = len(failed_benchmarks) * len(self.FIX_CATEGORIES)

        logger.info(f"Analyzing {len(failed_benchmarks)} failures")
        logger.info(f"Domain context: {len(self.all_benchmarks)} total benchmarks")
        logger.info(f"Total LLM calls: {total_tasks} ({parallel_workers} parallel)")

        # Pre-format benchmarks context (used in all prompts)
        benchmarks_context = self._format_benchmarks_context()

        # Build task list
        tasks = []
        for i, failure in enumerate(failed_benchmarks):
            for category in self.FIX_CATEGORIES:
                tasks.append((i, failure, category, benchmarks_context))

        # Run analysis in parallel
        def analyze_task(task):
            idx, failure, category, ctx = task
            try:
                fixes = self._analyze_failure(failure, space_config, category, ctx)
                return category, fixes or [], failure
            except Exception as e:
                logger.error(f"Error analyzing {category}: {e}")
                return category, [], failure

        completed = 0
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            futures = {executor.submit(analyze_task, task): task for task in tasks}

            for future in as_completed(futures):
                category, fixes, failure = future.result()
                completed += 1

                if fixes:
                    for fix in fixes:
                        fix["source_failure"] = {
                            "benchmark_id": failure.get("benchmark_id"),
                            "question": failure.get("question"),
                            "korean_question": failure.get("korean_question"),
                            "failure_category": failure.get("failure_category")
                        }
                    grouped_fixes[category].extend(fixes)

                if completed % 10 == 0:
                    logger.info(f"Progress: {completed}/{total_tasks}")

        # Deduplicate
        for category in self.FIX_CATEGORIES:
            grouped_fixes[category] = self._deduplicate_fixes(grouped_fixes[category])

        # Summary
        logger.info("=" * 80)
        logger.info("Enhancement Plan Complete")
        logger.info("=" * 80)
        total = 0
        for category, fixes in grouped_fixes.items():
            count = len(fixes)
            total += count
            if count > 0:
                logger.info(f"  {category}: {count} fixes")
        logger.info(f"  TOTAL: {total} fixes")

        return grouped_fixes

    def _analyze_failure(
        self,
        failure: Dict,
        space_config: Dict,
        category: str,
        benchmarks_context: str
    ) -> List[Dict]:
        """Analyze a single failure with full domain context."""
        prompt_template = self.prompts.get(category, "")
        if not prompt_template:
            return []

        # Use korean_question if available, fallback to question
        question = failure.get("korean_question") or failure.get("question", "")

        prompt = prompt_template.format(
            all_benchmarks=benchmarks_context,
            question=question,
            expected_sql=failure.get("expected_sql", ""),
            genie_sql=failure.get("genie_sql") or "None (Genie did not generate SQL)",
            space_config=json.dumps(space_config, indent=2, ensure_ascii=False)
        )

        try:
            response = self.llm_client.generate(
                prompt=prompt,
                temperature=0.1,
                max_tokens=4000
            )
            analysis = self._parse_llm_response(response)
            return analysis.get("recommended_fixes", [])
        except Exception as e:
            logger.error(f"LLM error: {e}")
            return []

    def _parse_llm_response(self, response: str) -> Dict:
        """Parse LLM JSON response."""
        try:
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            return json.loads(response)
        except json.JSONDecodeError:
            return {"recommended_fixes": []}

    def _deduplicate_fixes(self, fixes: List[Dict]) -> List[Dict]:
        """Remove duplicate fixes."""
        seen = set()
        unique = []

        for fix in fixes:
            fix_type = fix.get("type", "")

            # Metadata fixes
            if fix_type == "add_synonym":
                key = (fix_type, fix.get("table"), fix.get("column"), fix.get("synonym"))
            elif fix_type == "delete_synonym":
                key = (fix_type, fix.get("table"), fix.get("column"), fix.get("synonym"))
            elif fix_type == "add_column_description":
                key = (fix_type, fix.get("table"), fix.get("column"))
            elif fix_type == "add_table_description":
                key = (fix_type, fix.get("table"))

            # Sample query fixes
            elif fix_type == "add_example_query":
                key = (fix_type, fix.get("pattern_name"))
            elif fix_type == "delete_example_query":
                key = (fix_type, fix.get("pattern_name"), fix.get("id"))

            # Instruction fixes
            elif fix_type == "update_text_instruction":
                key = (fix_type,)

            # SQL snippet fixes
            elif fix_type == "add_filter":
                key = (fix_type, fix.get("display_name"), fix.get("sql_expression"))
            elif fix_type == "delete_filter":
                key = (fix_type, fix.get("display_name"), fix.get("id"))
            elif fix_type == "add_expression":
                key = (fix_type, fix.get("alias"), fix.get("sql_expression"))
            elif fix_type == "delete_expression":
                key = (fix_type, fix.get("alias"), fix.get("id"))
            elif fix_type == "add_measure":
                key = (fix_type, fix.get("alias"), fix.get("sql_expression"))
            elif fix_type == "delete_measure":
                key = (fix_type, fix.get("alias"), fix.get("id"))

            # Join spec fixes
            elif fix_type == "add_join_spec":
                key = (fix_type, fix.get("left_table"), fix.get("right_table"), fix.get("on_clause"))
            elif fix_type == "delete_join_spec":
                key = (fix_type, fix.get("left_table"), fix.get("right_table"))

            else:
                key = json.dumps(fix, sort_keys=True)

            if key not in seen:
                seen.add(key)
                unique.append(fix)

        return unique
