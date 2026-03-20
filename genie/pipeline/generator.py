"""Configuration generation module."""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

from genie.prompt.prompt_builder import PromptBuilder
from genie.llm.databricks_llm import DatabricksFoundationModelClient, DatabricksLLMClient
from genie.extractor import (
    extract_sample_queries_as_examples,
    merge_examples_into_config_dict,
    validate_examples,
    extract_domain_knowledge,
    extract_tables_from_requirements,
    merge_llm_and_rule_based_tables
)
from genie.validation import SQLValidator, InstructionQualityScorer
from genie.benchmark import load_benchmarks_auto
from genie.pipeline.reviewer import ConfigReviewAgent


def generate_config(
    requirements_path: str,
    output_path: str = "output/genie_space_config.json",
    model: str = "databricks-gpt-5-2",
    endpoint: Optional[str] = None,
    context_doc: str = "genie/prompt/templates/curate_effective_genie.md",
    output_doc: str = "genie/prompt/templates/genie_api.md",
    max_tokens: int = 24000,
    temperature: float = 0.1,
    databricks_host: Optional[str] = None,
    databricks_token: Optional[str] = None,
    validate_sql: bool = True,
    validate_instructions: bool = True,
    validation_output: Optional[str] = None,
    extract_domain: bool = True,
    review_config: bool = True,
    review_output: Optional[str] = None,
    benchmark_batch_size: int = 10,
    skip_benchmark_sql: bool = False,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Generate Genie space configuration with direct example SQL extraction.
    
    This function:
    1. Generates the configuration using LLM (for tables, instructions, etc.)
    2. Extracts SQL examples DIRECTLY from requirements document (bypassing LLM)
    3. Replaces LLM-generated examples with extracted examples
    4. Loads benchmark_questions from benchmarks/benchmarks.json (if available)
    5. Saves the final configuration
    
    Args:
        requirements_path: Path to requirements document
        output_path: Output file path for generated config
        model: Foundation model to use (e.g., databricks-gpt-5-2)
        endpoint: Custom serving endpoint name (alternative to foundation model)
        context_doc: Path to context document (best practices)
        output_doc: Path to output format document (API docs)
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature (0.0-1.0)
        databricks_host: Databricks workspace URL
        databricks_token: Databricks personal access token
        validate_sql: Run SQL validation on generated queries
        validate_instructions: Run instruction quality scoring
        validation_output: Optional path to save validation report
        extract_domain: Extract domain knowledge from requirements
        review_config: Run comprehensive config review
        review_output: Optional path to save review report
        benchmark_batch_size: (Deprecated) No longer used
        skip_benchmark_sql: (Deprecated) No longer used
        verbose: Print progress messages
        
    Returns:
        dict: Generated configuration
        
    Raises:
        ValueError: If credentials are missing
        Exception: If generation or extraction fails
    """
    # Get credentials
    host = databricks_host or os.getenv("DATABRICKS_HOST")
    token = databricks_token or os.getenv("DATABRICKS_TOKEN")
    
    if not host or not token:
        raise ValueError(
            "DATABRICKS_HOST and DATABRICKS_TOKEN must be set. "
            "Either set environment variables or pass as arguments."
        )
    
    # Ensure output directory exists
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    # =========================================================================
    # STEP 1: Extract domain knowledge (optional, Priority 3)
    # =========================================================================
    domain_knowledge = None
    if extract_domain:
        if verbose:
            print("📚 Extracting domain knowledge...")

        try:
            domain_knowledge = extract_domain_knowledge(requirements_path, verbose=verbose)
        except Exception as e:
            if verbose:
                print(f"   ⚠️  Domain extraction failed: {e}")
                print("   Continuing without domain knowledge...")

    # =========================================================================
    # STEP 2: Generate configuration with LLM
    # =========================================================================
    if verbose:
        print("\n📝 Generating configuration with LLM...")

    # Build prompt
    builder = PromptBuilder(
        context_doc_path=context_doc,
        output_doc_path=output_doc,
        input_data_path=requirements_path
    )
    
    prompt = builder.build_prompt(domain_knowledge=domain_knowledge)
    
    if verbose:
        print(f"   Prompt: {len(prompt)} characters")
    
    # Initialize LLM client
    if endpoint:
        if verbose:
            print(f"   Using custom endpoint: {endpoint}")
        llm_client = DatabricksLLMClient(
            endpoint_name=endpoint,
            databricks_host=host,
            databricks_token=token
        )
    else:
        if verbose:
            print(f"   Using foundation model: {model}")
        llm_client = DatabricksFoundationModelClient(
            model_name=model,
            databricks_host=host,
            databricks_token=token
        )
    
    # Generate configuration
    if verbose:
        print(f"   Calling LLM (max_tokens={max_tokens}, temperature={temperature})...")
        print("   This may take 30-60 seconds...")
    
    response = llm_client.generate_genie_config(
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=temperature
    )
    
    if verbose:
        print("   ✓ Configuration generated by LLM")
    
    # Extract config
    config_data = response.model_dump()

    # Extract reasoning from response
    reasoning = {}
    if hasattr(response, 'reasoning') and response.reasoning:
        reasoning["overall_strategy"] = response.reasoning
    else:
        # Extract from config data if reasoning is part of the response
        config = config_data.get("genie_space_config", {})
        reasoning["table_selection"] = f"Selected {len(config.get('tables', []))} tables from requirements"
        reasoning["instruction_design"] = f"Created {len(config.get('instructions', []))} instructions for data context"
        reasoning["sql_examples"] = f"Generated {len(config.get('example_sql_queries', []))} example SQL queries"
        reasoning["overall_strategy"] = f"Designed Genie space '{config.get('space_name', 'Unknown')}' based on provided requirements"

    # Store reasoning in config data
    config_data["reasoning"] = reasoning

    # Show summary
    if verbose:
        config = config_data["genie_space_config"]
        print(f"\n   Space Name: {config['space_name']}")
        print(f"   Tables: {len(config['tables'])}")
        print(f"   Instructions: {len(config['instructions'])}")
        print(f"   LLM-Generated Example SQL Queries: {len(config['example_sql_queries'])}")
    
    # =========================================================================
    # STEP 2.5: Hybrid Table Merging (Rule-based + LLM)
    # =========================================================================
    if verbose:
        print("\n🔀 Hybrid table extraction (rule-based + LLM)...")
    
    # Extract tables using rule-based patterns
    rule_based_tables = extract_tables_from_requirements(
        requirements_path=requirements_path,
        default_catalog="main",
        verbose=verbose
    )
    
    # Merge LLM-selected tables with rule-based extracted tables
    llm_table_count = len(config_data["genie_space_config"]["tables"])
    
    merged_tables = merge_llm_and_rule_based_tables(
        llm_tables=config_data["genie_space_config"]["tables"],
        rule_based_tables=rule_based_tables,
        max_tables=25,  # Genie limit
        prioritize_llm=True  # LLM tables have better descriptions
    )
    
    # Update config with merged tables
    config_data["genie_space_config"]["tables"] = merged_tables
    
    if verbose:
        added_count = len(merged_tables) - llm_table_count
        print(f"   LLM selected: {llm_table_count} tables")
        print(f"   Rule-based found: {len(rule_based_tables)} tables")
        print(f"   Merged total: {len(merged_tables)} tables")
        if added_count > 0:
            print(f"   ✓ Added {added_count} tables that LLM missed")
    
    # =========================================================================
    # STEP 3: Extract SQL examples directly from requirements
    # =========================================================================
    if verbose:
        print("\n📊 Extracting SQL examples from requirements...")
    
    examples = extract_sample_queries_as_examples(requirements_path=requirements_path)
    
    if verbose:
        print(f"   ✓ Extracted {len(examples)} SQL examples from sample queries")
    
    # Validate examples
    issues = validate_examples(examples)
    if verbose:
        if issues:
            print(f"   ⚠️  {len(issues)} validation issues found")
            for issue in issues[:3]:
                print(f"       - {issue}")
        else:
            print(f"   ✓ All examples are valid")
    
    # =========================================================================
    # STEP 4: Replace LLM examples with extracted examples
    # =========================================================================
    if verbose:
        print("\n🔗 Replacing LLM-generated examples with extracted examples...")
    
    original_example_count = len(config_data["genie_space_config"].get("example_sql_queries", []))
    
    config_data = merge_examples_into_config_dict(
        config=config_data,
        examples=examples,
        replace=True  # Replace LLM-generated examples
    )
    
    if verbose:
        print(f"   ✓ Replaced {original_example_count} LLM-generated examples")
        print(f"   ✓ Added {len(examples)} extracted SQL examples")
    
    # =========================================================================
    # STEP 5: Load benchmark_questions from JSON file (if available)
    # =========================================================================
    if verbose:
        print("\n📊 Loading benchmark questions...")
    
    # Try to load benchmarks from benchmarks/benchmarks.json
    benchmarks = load_benchmarks_auto(requirements_path, verbose=verbose)
    
    if benchmarks:
        config_data["genie_space_config"]["benchmark_questions"] = benchmarks
        if verbose:
            print(f"   ✓ Loaded {len(benchmarks)} benchmark questions from JSON file")
    else:
        # No benchmarks file found, keep empty
        original_benchmark_count = len(config_data["genie_space_config"].get("benchmark_questions", []))
        config_data["genie_space_config"]["benchmark_questions"] = []
        if verbose:
            print(f"   ℹ No benchmarks file found, keeping section empty")
            if original_benchmark_count > 0:
                print(f"   ✓ Cleared {original_benchmark_count} LLM-generated benchmarks")

    # =========================================================================
    # STEP 6: Validate configuration quality (optional, Priority 2)
    # =========================================================================
    validation_results = {}

    if validate_sql or validate_instructions:
        if verbose:
            print("\n🔍 Running validation checks...")

        config = config_data["genie_space_config"]

        # SQL Validation
        if validate_sql:
            if verbose:
                print("   Running SQL validation...")

            # Get tables for validation context
            from genie.models import GenieSpaceTable
            tables = [
                GenieSpaceTable(**table) for table in config.get("tables", [])
            ]

            sql_validator = SQLValidator(available_tables=tables)
            sql_results = sql_validator.validate_config_sql(config)
            validation_results["sql_validation"] = sql_results

            if verbose:
                summary = sql_results["summary"]
                print(f"   SQL Validation Results:")
                print(f"     - Total queries: {summary['total_queries']}")
                print(f"     - Valid queries: {summary['valid_queries']}")
                print(f"     - With errors: {summary['queries_with_errors']}")
                print(f"     - With warnings: {summary['queries_with_warnings']}")

                # Show first few errors if any
                all_reports = sql_results["example_queries"]
                # Add SQL snippets reports (filters, expressions, measures)
                if "sql_snippets" in sql_results:
                    all_reports.extend(sql_results["sql_snippets"].get("filters", []))
                    all_reports.extend(sql_results["sql_snippets"].get("expressions", []))
                    all_reports.extend(sql_results["sql_snippets"].get("measures", []))
                
                errors_shown = 0
                for report in all_reports:
                    if not report.is_valid and errors_shown < 3:
                        print(f"\n   ⚠️  SQL Error in query:")
                        for error in report.get_errors()[:2]:
                            print(f"       - {error.message}")
                        errors_shown += 1

        # Instruction Quality Validation
        if validate_instructions:
            if verbose:
                print("\n   Running instruction quality scoring...")

            scorer = InstructionQualityScorer()
            quality_report = scorer.score_config_instructions(config)
            validation_results["instruction_quality"] = {
                "average_score": quality_report.average_score,
                "total_instructions": quality_report.total_instructions,
                "high_quality_count": quality_report.high_quality_count,
                "medium_quality_count": quality_report.medium_quality_count,
                "low_quality_count": quality_report.low_quality_count,
                "scores": [
                    {
                        "score": s.total_score,
                        "grade": s.grade(),
                        "specificity": s.specificity_score,
                        "structure": s.structure_score,
                        "clarity": s.clarity_score,
                        "issues": s.issues,
                        "suggestions": s.suggestions
                    }
                    for s in quality_report.instruction_scores
                ]
            }

            if verbose:
                print(f"   Instruction Quality Results:")
                print(f"     - Average score: {quality_report.average_score:.1f}/100")
                print(f"     - High quality (≥80): {quality_report.high_quality_count}")
                print(f"     - Medium quality (60-79): {quality_report.medium_quality_count}")
                print(f"     - Low quality (<60): {quality_report.low_quality_count}")

                # Show issues for low-quality instructions
                for i, score in enumerate(quality_report.instruction_scores):
                    if score.total_score < 60:
                        print(f"\n   ⚠️  Low-quality instruction #{i+1} (Score: {score.total_score:.1f}):")
                        for issue in score.issues[:2]:
                            print(f"       - {issue}")

        # Save validation report if requested
        if validation_output:
            if verbose:
                print(f"\n   Saving validation report to {validation_output}...")

            validation_path = Path(validation_output)
            validation_path.parent.mkdir(parents=True, exist_ok=True)

            with open(validation_path, 'w', encoding='utf-8') as f:
                # Convert reports to JSON-serializable format
                serializable_results = {
                    "sql_validation": {},
                    "instruction_quality": validation_results.get("instruction_quality", {})
                }

                if "sql_validation" in validation_results:
                    sql_val = validation_results["sql_validation"]
                    serializable_results["sql_validation"] = {
                        "summary": sql_val["summary"],
                        "example_queries": [
                            {
                                "is_valid": r.is_valid,
                                "tables": list(r.tables_referenced),
                                "columns": list(r.columns_referenced),
                                "has_joins": r.has_explicit_joins,
                                "errors": [{"severity": e.severity, "category": e.category, "message": e.message} for e in r.get_errors()],
                                "warnings": [{"severity": w.severity, "category": w.category, "message": w.message} for w in r.get_warnings()],
                            }
                            for r in sql_val["example_queries"]
                        ]
                    }

                json.dump(serializable_results, f, indent=2, ensure_ascii=False)

            if verbose:
                print(f"   ✓ Validation report saved")

    # =========================================================================
    # STEP 7: Comprehensive config review (optional, Priority 3)
    # =========================================================================
    review_report = None
    if review_config:
        if verbose:
            print("\n🔬 Running comprehensive configuration review...")

        try:
            # Get tables for review context
            from genie.models import GenieSpaceTable
            tables = [
                GenieSpaceTable(**table) for table in config.get("tables", [])
            ]

            reviewer = ConfigReviewAgent(available_tables=tables)
            review_report = reviewer.review_config(
                config,
                config_name=config.get("space_name", "Genie Space")
            )

            if verbose:
                status = "✅ PASSED" if review_report.passed else "❌ FAILED"
                print(f"   Review Status: {status}")
                print(f"   Overall Score: {review_report.overall_score:.1f}/100")
                print(f"   Component Scores:")
                print(f"     - SQL: {review_report.sql_validation_score:.1f}/100")
                print(f"     - Instructions: {review_report.instruction_quality_score:.1f}/100")
                print(f"     - Joins: {review_report.join_completeness_score:.1f}/100")
                print(f"     - Coverage: {review_report.coverage_score:.1f}/100")

                # Show critical/high issues
                critical = review_report.get_issues_by_severity("critical")
                high = review_report.get_issues_by_severity("high")

                if critical:
                    print(f"\n   ⚠️  {len(critical)} CRITICAL issues:")
                    for issue in critical[:3]:  # Show first 3
                        print(f"       - [{issue.category}] {issue.message}")

                if high:
                    print(f"\n   ⚠️  {len(high)} HIGH priority issues:")
                    for issue in high[:3]:  # Show first 3
                        print(f"       - [{issue.category}] {issue.message}")

            # Save review report if requested
            if review_output:
                review_data = {
                    "config_name": review_report.config_name,
                    "overall_score": review_report.overall_score,
                    "passed": review_report.passed,
                    "component_scores": {
                        "sql_validation": review_report.sql_validation_score,
                        "instruction_quality": review_report.instruction_quality_score,
                        "join_completeness": review_report.join_completeness_score,
                        "coverage": review_report.coverage_score
                    },
                    "metrics": {
                        "sql_queries": f"{review_report.valid_sql_queries}/{review_report.total_sql_queries}",
                        "instructions": f"{review_report.high_quality_instructions}/{review_report.total_instructions}",
                        "joins": f"{review_report.documented_joins}/{review_report.total_joins}"
                    },
                    "issues": [
                        {
                            "severity": issue.severity,
                            "category": issue.category,
                            "message": issue.message,
                            "suggestion": issue.suggestion,
                            "affected_item": issue.affected_item
                        }
                        for issue in review_report.issues
                    ]
                }

                review_path = Path(review_output)
                review_path.parent.mkdir(parents=True, exist_ok=True)

                with open(review_path, 'w', encoding='utf-8') as f:
                    json.dump(review_data, f, indent=2, ensure_ascii=False)

                if verbose:
                    print(f"   ✓ Review report saved to {review_output}")

        except Exception as e:
            if verbose:
                print(f"   ⚠️  Config review failed: {e}")
                print("   Continuing without review...")

    # =========================================================================
    # STEP 8: Save final configuration
    # =========================================================================
    if verbose:
        print(f"\n💾 Saving configuration to {output_path}...")

    with open(output_path_obj, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)

    if verbose:
        print(f"   ✓ Configuration saved")

    # Add validation and review results to return value
    if validation_results:
        config_data["_validation_results"] = validation_results

    if review_report:
        config_data["_review_report"] = {
            "overall_score": review_report.overall_score,
            "passed": review_report.passed,
            "component_scores": {
                "sql": review_report.sql_validation_score,
                "instructions": review_report.instruction_quality_score,
                "joins": review_report.join_completeness_score,
                "coverage": review_report.coverage_score
            }
        }

    return config_data
