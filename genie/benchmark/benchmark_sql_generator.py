"""Benchmark SQL generation module for two-pass approach.

This module handles the second pass of config generation: generating SQL
queries for benchmark questions that don't have SQL in the requirements.
"""

import json
from typing import Dict, List, Any, Iterator, Optional
from pathlib import Path

from genie.models import BenchmarkSQLResponse
from genie.llm.databricks_llm import DatabricksLLMClient


def generate_benchmark_sql_for_config(
    config: Dict[str, Any],
    llm_client: DatabricksLLMClient,
    max_tokens: int = 4000,
    temperature: float = 0.1,
    batch_size: int = 10,
    verbose: bool = False
) -> Dict[str, Any]:
    """Generate SQL for benchmarks that don't have expected_sql.

    Args:
        config: The configuration dictionary with benchmark_questions
        llm_client: LLM client for generating SQL
        max_tokens: Maximum tokens for LLM response
        temperature: Temperature for LLM generation
        batch_size: Number of benchmarks to process per LLM call
        verbose: Print progress messages

    Returns:
        Updated config with all benchmark SQL filled

    Raises:
        ValueError: If config structure is invalid
        RuntimeError: If LLM generation fails
    """
    # Extract benchmarks from config
    genie_config = config.get("genie_space_config", {})
    benchmarks = genie_config.get("benchmark_questions", [])

    # Filter benchmarks needing SQL
    benchmarks_needing_sql = [
        bm for bm in benchmarks
        if bm.get("expected_sql") is None
    ]

    if not benchmarks_needing_sql:
        if verbose:
            print("   No benchmarks need SQL generation")
        return config

    if verbose:
        print(f"   Generating SQL for {len(benchmarks_needing_sql)} benchmarks in batches of {batch_size}")

    # Extract table and join info once
    tables = genie_config.get("tables", [])
    join_specs = genie_config.get("join_specifications", [])

    # Process in batches
    all_generated_sql = []
    for batch_num, batch in enumerate(_batch_benchmarks(benchmarks_needing_sql, batch_size), start=1):
        if verbose:
            print(f"   Processing batch {batch_num} ({len(batch)} questions)...")

        # Build prompt for this batch
        prompt = build_benchmark_sql_prompt(
            tables=tables,
            join_specs=join_specs,
            benchmark_questions=batch
        )

        # Call LLM
        try:
            response = llm_client.generate_structured(
                prompt=prompt,
                response_model=BenchmarkSQLResponse,
                max_tokens=max_tokens,
                temperature=temperature
            )

            # Parse response
            batch_results = parse_benchmark_sql_response(response)
            all_generated_sql.extend(batch_results)

            if verbose:
                print(f"      Generated {len(batch_results)} SQL queries")

        except Exception as e:
            raise RuntimeError(f"Failed to generate SQL for batch {batch_num}: {str(e)}")

    # Update config with generated SQL
    # Create a mapping of question -> sql for quick lookup
    sql_map = {result["question"]: result["sql"] for result in all_generated_sql}

    # Update benchmarks in place
    for benchmark in benchmarks:
        if benchmark.get("expected_sql") is None:
            question = benchmark["question"]
            if question in sql_map:
                benchmark["expected_sql"] = sql_map[question]
            else:
                # Shouldn't happen, but handle gracefully
                if verbose:
                    print(f"   WARNING: No SQL generated for question: {question}")

    return config


def build_benchmark_sql_prompt(
    tables: List[Dict[str, Any]],
    join_specs: List[Dict[str, Any]],
    benchmark_questions: List[Dict[str, Any]]
) -> str:
    """Build prompt for benchmark SQL generation.

    Args:
        tables: List of table definitions
        join_specs: List of join specifications
        benchmark_questions: List of benchmark questions needing SQL

    Returns:
        Formatted prompt string
    """
    # Load template
    template_path = Path(__file__).parent.parent / "prompt" / "templates" / "benchmark_sql_prompt.md"
    with open(template_path, "r") as f:
        template = f.read()

    # Format table schemas
    table_schemas = []
    for table in tables:
        fqn = f"{table['catalog_name']}.{table['schema_name']}.{table['table_name']}"
        desc = table.get("description", "")
        table_schemas.append(f"- **{fqn}**: {desc}")
    table_schemas_str = "\n".join(table_schemas)

    # Format join specs
    join_specs_str = ""
    if join_specs:
        join_items = []
        for join in join_specs:
            left = join["left_table"]
            right = join["right_table"]
            join_type = join["join_type"]
            condition = join["join_condition"]
            desc = join.get("description", "")
            join_items.append(f"- **{left}** {join_type} **{right}** ON {condition}")
            if desc:
                join_items.append(f"  - {desc}")
        join_specs_str = "\n".join(join_items)
    else:
        join_specs_str = "(No explicit join specifications provided)"

    # Format benchmark questions
    question_items = []
    for i, bm in enumerate(benchmark_questions, start=1):
        question_items.append(f"{i}. {bm['question']}")
    questions_str = "\n".join(question_items)

    # Fill template
    prompt = template.format(
        table_schemas=table_schemas_str,
        join_specs=join_specs_str,
        benchmark_questions=questions_str
    )

    return prompt


def parse_benchmark_sql_response(response: BenchmarkSQLResponse) -> List[Dict[str, Any]]:
    """Parse LLM response into list of benchmark SQL results.

    Args:
        response: BenchmarkSQLResponse from LLM

    Returns:
        List of dicts with keys: question, sql, reasoning

    Raises:
        ValueError: If response is invalid or incomplete
    """
    results = []

    for bm_sql in response.benchmark_sqls:
        # Validate SQL completeness
        sql = bm_sql.sql.strip()
        if not sql:
            raise ValueError(f"Empty SQL for question: {bm_sql.question}")

        if not sql.endswith(";"):
            # Auto-fix: add missing semicolon
            sql = sql + ";"

        results.append({
            "question": bm_sql.question,
            "sql": sql,
            "reasoning": bm_sql.reasoning
        })

    return results


def _batch_benchmarks(
    benchmarks: List[Dict[str, Any]],
    batch_size: int
) -> Iterator[List[Dict[str, Any]]]:
    """Split benchmarks into batches.

    Args:
        benchmarks: List of benchmark dictionaries
        batch_size: Number of benchmarks per batch

    Yields:
        Batches of benchmarks
    """
    for i in range(0, len(benchmarks), batch_size):
        yield benchmarks[i:i + batch_size]
