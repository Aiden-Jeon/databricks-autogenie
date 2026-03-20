"""
Category-Based Enhancement Planner

Instead of analyzing each failure individually (N × categories LLM calls),
this module analyzes ALL failures together by fix category (9 LLM calls total).

Categories:
1. instruction_fix - Update text_instructions
2. sample_queries_delete - Remove bad/duplicate example queries
3. sample_queries_add - Add new pattern templates
4. metadata_delete - Remove wrong synonyms
5. metadata_add - Add synonyms/descriptions
6. sql_snippets_delete - Remove bad filters/measures
7. sql_snippets_add - Add filters/expressions/measures
8. join_specs_delete - Remove incorrect join specifications
9. join_specs_add - Add join specifications
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class CategoryEnhancer:
    """
    Category-based enhancement planner.

    Analyzes ALL failures together, generating fixes by category.
    This reduces LLM calls from N×3 to just 9 (constant).
    """

    # Fix categories - order matters for application
    FIX_CATEGORIES = [
        "instruction_fix",
        "sample_queries_delete",
        "sample_queries_add",
        "metadata_delete",
        "metadata_add",
        "sql_snippets_delete",
        "sql_snippets_add",
        "join_specs_delete",
        "join_specs_add",
    ]

    # Map categories to output fix types for validation
    CATEGORY_FIX_TYPES = {
        "instruction_fix": ["update_text_instruction"],
        "sample_queries_delete": ["delete_example_query"],
        "sample_queries_add": ["add_example_query"],
        "metadata_delete": ["delete_synonym"],
        "metadata_add": ["add_synonym", "add_column_description", "add_table_description"],
        "sql_snippets_delete": ["delete_filter", "delete_expression", "delete_measure"],
        "sql_snippets_add": ["add_filter", "add_expression", "add_measure"],
        "join_specs_delete": ["delete_join_spec"],
        "join_specs_add": ["add_join_spec"],
    }

    def __init__(
        self,
        llm_client,
        prompts_dir: Path = None,
        all_benchmarks: List[Dict] = None
    ):
        """
        Initialize category-based enhancement planner.

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
        self.prompts_dir = prompts_dir

        self.prompts = {}
        self._load_prompts()

    def _load_prompts(self) -> None:
        """Load all category prompts."""
        for category in self.FIX_CATEGORIES:
            prompt_file = self.prompts_dir / f"category_{category}.txt"
            if prompt_file.exists():
                self.prompts[category] = prompt_file.read_text(encoding='utf-8')
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

    def _format_failures_context(self, failed_benchmarks: List[Dict]) -> str:
        """Format all failures as context string."""
        if not failed_benchmarks:
            return "No failures to analyze."

        failure_items = []
        for i, f in enumerate(failed_benchmarks, 1):
            question = f.get('korean_question') or f.get('question', '')
            failure_items.append(f"""
### Failure {i}: {f.get('benchmark_id', 'unknown')[:8]}
**Korean Question:** {question}
**Expected SQL:**
```sql
{f.get('expected_sql', '')}
```
**Genie's SQL:**
```sql
{f.get('genie_sql') or 'None (Genie did not generate SQL)'}
```
**Failure Category:** {f.get('failure_category', 'unknown')}
""")
        return "\n".join(failure_items)

    def _extract_category_configs(self, space_config: Dict) -> Dict[str, Dict]:
        """
        Extract only relevant config parts for each category.

        This dramatically reduces token usage by not sending the entire
        space config to every category analysis.
        """
        # Get parsed config
        parsed = space_config.get("serialized_space_parsed", space_config)
        instructions = parsed.get("instructions", {})
        data_sources = parsed.get("data_sources", {})

        # Extract full table info
        tables_full = data_sources.get("tables", [])

        # Table identifiers only (for categories that just need table names)
        table_identifiers = [{"identifier": t.get("identifier", "")} for t in tables_full]

        return {
            "instruction_fix": {
                "text_instructions": instructions.get("text_instructions", [])
            },
            "sample_queries_delete": {
                "example_question_sqls": instructions.get("example_question_sqls", [])
            },
            "sample_queries_add": {
                "example_question_sqls": instructions.get("example_question_sqls", []),
                "tables": table_identifiers
            },
            "metadata_delete": {
                "tables": tables_full
            },
            "metadata_add": {
                "tables": tables_full
            },
            "sql_snippets_delete": {
                "sql_snippets": instructions.get("sql_snippets", {})
            },
            "sql_snippets_add": {
                "sql_snippets": instructions.get("sql_snippets", {}),
                "tables": table_identifiers
            },
            "join_specs_delete": {
                "join_specs": instructions.get("join_specs", [])
            },
            "join_specs_add": {
                "join_specs": instructions.get("join_specs", []),
                "tables": table_identifiers
            }
        }

    def generate_plan(
        self,
        failed_benchmarks: List[Dict],
        space_config: Dict,
        parallel_workers: int = 3
    ) -> Dict[str, List[Dict]]:
        """
        Generate fixes for all failed benchmarks by category.

        Args:
            failed_benchmarks: List of failed benchmark results
            space_config: Current Genie Space configuration
            parallel_workers: Number of parallel LLM calls (max 9)

        Returns:
            {
                "instruction_fix": [fix1, fix2, ...],
                "sample_queries_delete": [...],
                "sample_queries_add": [...],
                "metadata_delete": [...],
                "metadata_add": [...],
                "sql_snippets_delete": [...],
                "sql_snippets_add": [...],
                "join_specs_delete": [...],
                "join_specs_add": [...]
            }
        """
        logger.info("=" * 80)
        logger.info("Category-Based Enhancement Plan")
        logger.info("=" * 80)

        grouped_fixes = {category: [] for category in self.FIX_CATEGORIES}

        if not failed_benchmarks:
            logger.warning("No failures to analyze")
            return grouped_fixes

        logger.info(f"Analyzing {len(failed_benchmarks)} failures across {len(self.FIX_CATEGORIES)} categories")
        logger.info(f"Domain context: {len(self.all_benchmarks)} total benchmarks")
        logger.info(f"Total LLM calls: {len(self.FIX_CATEGORIES)} (parallel: {parallel_workers})")

        # Pre-format contexts (used in all prompts)
        benchmarks_context = self._format_benchmarks_context()
        failures_context = self._format_failures_context(failed_benchmarks)

        # Extract relevant config parts for each category (to reduce token usage)
        category_configs = self._extract_category_configs(space_config)

        # Run analysis for each category
        def analyze_category(category: str) -> tuple:
            try:
                # Use only relevant config for this category
                relevant_config = category_configs.get(category, {})
                space_config_str = json.dumps(relevant_config, indent=2, ensure_ascii=False)

                fixes = self._analyze_category(
                    category=category,
                    benchmarks_context=benchmarks_context,
                    failures_context=failures_context,
                    space_config_str=space_config_str,
                    failure_count=len(failed_benchmarks)
                )
                return category, fixes or []
            except Exception as e:
                logger.error(f"Error analyzing {category}: {e}")
                return category, []

        # Execute in parallel
        completed = 0
        with ThreadPoolExecutor(max_workers=min(parallel_workers, len(self.FIX_CATEGORIES))) as executor:
            futures = {
                executor.submit(analyze_category, cat): cat
                for cat in self.FIX_CATEGORIES
            }

            for future in as_completed(futures):
                category, fixes = future.result()
                completed += 1

                if fixes:
                    # Validate fix types
                    valid_types = self.CATEGORY_FIX_TYPES.get(category, [])
                    validated_fixes = []
                    for fix in fixes:
                        fix_type = fix.get("type", "")
                        if fix_type in valid_types or not valid_types:
                            validated_fixes.append(fix)
                        else:
                            logger.warning(f"Invalid fix type '{fix_type}' for category '{category}'")

                    grouped_fixes[category].extend(validated_fixes)

                logger.info(f"Progress: {completed}/{len(self.FIX_CATEGORIES)} categories")

        # Summary
        logger.info("=" * 80)
        logger.info("Category-Based Enhancement Plan Complete")
        logger.info("=" * 80)
        total = 0
        for category, fixes in grouped_fixes.items():
            count = len(fixes)
            total += count
            if count > 0:
                logger.info(f"  {category}: {count} fixes")
        logger.info(f"  TOTAL: {total} fixes")

        return grouped_fixes

    def _analyze_category(
        self,
        category: str,
        benchmarks_context: str,
        failures_context: str,
        space_config_str: str,
        failure_count: int
    ) -> List[Dict]:
        """
        Analyze all failures for a specific fix category.

        Args:
            category: Fix category to analyze
            benchmarks_context: Formatted all benchmarks
            failures_context: Formatted all failures
            space_config_str: Current space config as JSON string
            failure_count: Number of failures

        Returns:
            List of fixes for this category
        """
        prompt_template = self.prompts.get(category, "")
        if not prompt_template:
            logger.warning(f"No prompt template for category: {category}")
            return []

        prompt = prompt_template.format(
            all_benchmarks=benchmarks_context,
            all_failures=failures_context,
            failure_count=failure_count,
            space_config=space_config_str
        )

        try:
            response = self.llm_client.generate(
                prompt=prompt,
                temperature=0.1,
                max_tokens=8000  # Larger for batch analysis
            )
            analysis = self._parse_llm_response(response)
            return analysis.get("recommended_fixes", [])
        except Exception as e:
            logger.error(f"LLM error for {category}: {e}")
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
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return {"recommended_fixes": []}


# Convenience function for migration
def create_category_enhancer(llm_client, prompts_dir: Path = None) -> CategoryEnhancer:
    """Factory function to create CategoryEnhancer."""
    return CategoryEnhancer(llm_client=llm_client, prompts_dir=prompts_dir)
