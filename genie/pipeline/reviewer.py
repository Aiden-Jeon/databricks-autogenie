"""
Configuration review agent for automated quality checks.

This module provides automated review of generated Genie configurations:
- SQL syntax and schema validation
- Instruction quality assessment
- Join specification completeness
- Example query coverage
- Benchmark question coverage
"""

import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path

from genie.validation import SQLValidator, InstructionQualityScorer
from genie.validation.sql_validator import validate_join_specifications
from genie.models import GenieSpaceTable


@dataclass
class ReviewIssue:
    """Represents an issue found during review."""
    severity: str  # "critical", "high", "medium", "low", "info"
    category: str  # "sql", "instructions", "joins", "coverage", "structure"
    message: str
    suggestion: Optional[str] = None
    affected_item: Optional[str] = None


@dataclass
class ConfigReviewReport:
    """Complete review report for a configuration."""
    config_name: str
    overall_score: float  # 0-100
    passed: bool
    issues: List[ReviewIssue] = field(default_factory=list)

    sql_validation_score: float = 0.0
    instruction_quality_score: float = 0.0
    join_completeness_score: float = 0.0
    coverage_score: float = 0.0

    total_sql_queries: int = 0
    valid_sql_queries: int = 0
    total_instructions: int = 0
    high_quality_instructions: int = 0
    total_joins: int = 0
    documented_joins: int = 0

    def add_issue(self, issue: ReviewIssue):
        """Add an issue to the report."""
        self.issues.append(issue)
        if issue.severity in ["critical", "high"]:
            self.passed = False

    def get_issues_by_severity(self, severity: str) -> List[ReviewIssue]:
        """Get all issues of a specific severity."""
        return [i for i in self.issues if i.severity == severity]

    def summary(self) -> str:
        """Get human-readable summary."""
        status = "✅ PASSED" if self.passed else "❌ FAILED"
        critical = len(self.get_issues_by_severity("critical"))
        high = len(self.get_issues_by_severity("high"))
        medium = len(self.get_issues_by_severity("medium"))
        low = len(self.get_issues_by_severity("low"))

        return f"""
Configuration Review Report: {self.config_name}
{'=' * 60}
Overall Status: {status}
Overall Score: {self.overall_score:.1f}/100

Component Scores:
  - SQL Validation: {self.sql_validation_score:.1f}/100
  - Instruction Quality: {self.instruction_quality_score:.1f}/100
  - Join Completeness: {self.join_completeness_score:.1f}/100
  - Coverage: {self.coverage_score:.1f}/100

Issues Found:
  - Critical: {critical}
  - High: {high}
  - Medium: {medium}
  - Low: {low}

Metrics:
  - SQL Queries: {self.valid_sql_queries}/{self.total_sql_queries} valid
  - Instructions: {self.high_quality_instructions}/{self.total_instructions} high quality
  - Joins: {self.documented_joins}/{self.total_joins} documented
"""


class ConfigReviewAgent:
    """
    Automated configuration review agent.

    Performs comprehensive quality checks on generated Genie configurations:
    1. SQL validation (syntax, tables, joins, quality)
    2. Instruction quality (specificity, structure, clarity)
    3. Join specification completeness
    4. Example query coverage
    5. Benchmark question coverage

    Usage:
        agent = ConfigReviewAgent(available_tables=tables)
        report = agent.review_config(config)
        if report.passed:
            print("✅ Configuration ready for deployment")
        else:
            for issue in report.get_issues_by_severity("critical"):
                print(f"❌ {issue.message}")
    """

    def __init__(
        self,
        available_tables: Optional[List[GenieSpaceTable]] = None,
        min_sql_score: float = 70.0,
        min_instruction_score: float = 70.0,
        min_join_coverage: float = 80.0,
        strict_mode: bool = False
    ):
        """
        Initialize the review agent.

        Args:
            available_tables: List of tables available in the Genie space
            min_sql_score: Minimum SQL validation score (0-100)
            min_instruction_score: Minimum instruction quality score (0-100)
            min_join_coverage: Minimum join documentation coverage (0-100)
            strict_mode: If True, warnings become errors
        """
        self.available_tables = available_tables or []
        self.min_sql_score = min_sql_score
        self.min_instruction_score = min_instruction_score
        self.min_join_coverage = min_join_coverage
        self.strict_mode = strict_mode

        self.sql_validator = SQLValidator(available_tables=self.available_tables)
        self.instruction_scorer = InstructionQualityScorer()

    def review_config(self, config: Dict[str, Any], config_name: str = "Genie Space") -> ConfigReviewReport:
        """
        Review a complete Genie space configuration.

        Args:
            config: Configuration dictionary
            config_name: Name of the configuration

        Returns:
            ConfigReviewReport with detailed findings
        """
        report = ConfigReviewReport(
            config_name=config_name,
            overall_score=0.0,
            passed=True
        )

        # 1. Validate SQL
        self._review_sql(config, report)

        # 2. Review instructions
        self._review_instructions(config, report)

        # 3. Check join specifications
        self._review_joins(config, report)

        # 4. Check coverage
        self._review_coverage(config, report)

        # 5. Check structure
        self._review_structure(config, report)

        # Calculate overall score
        report.overall_score = (
            report.sql_validation_score * 0.35 +
            report.instruction_quality_score * 0.25 +
            report.join_completeness_score * 0.20 +
            report.coverage_score * 0.20
        )

        # Determine pass/fail
        if report.overall_score < 60:
            report.passed = False
            report.add_issue(ReviewIssue(
                severity="high",
                category="overall",
                message=f"Overall score {report.overall_score:.1f} is below minimum threshold (60)",
                suggestion="Address critical and high severity issues to improve score"
            ))

        return report

    def _review_sql(self, config: Dict[str, Any], report: ConfigReviewReport):
        """Review SQL queries in the configuration."""
        sql_results = self.sql_validator.validate_config_sql(config)

        report.total_sql_queries = sql_results["summary"]["total_queries"]
        report.valid_sql_queries = sql_results["summary"]["valid_queries"]

        # Calculate SQL score
        if report.total_sql_queries > 0:
            validity_ratio = report.valid_sql_queries / report.total_sql_queries
            error_count = sql_results["summary"]["queries_with_errors"]
            warning_count = sql_results["summary"]["queries_with_warnings"]

            # Score: 100 if all valid, penalize for errors more than warnings
            report.sql_validation_score = validity_ratio * 100
            report.sql_validation_score -= (error_count * 10)  # -10 per error
            report.sql_validation_score -= (warning_count * 2)   # -2 per warning
            report.sql_validation_score = max(0, report.sql_validation_score)

        # Add issues for SQL errors
        all_reports = sql_results["example_queries"]
        # Add SQL snippets reports (filters, expressions, measures)
        if "sql_snippets" in sql_results:
            all_reports.extend(sql_results["sql_snippets"].get("filters", []))
            all_reports.extend(sql_results["sql_snippets"].get("expressions", []))
            all_reports.extend(sql_results["sql_snippets"].get("measures", []))
        
        for i, sql_report in enumerate(all_reports):
            if not sql_report.is_valid:
                for error in sql_report.get_errors():
                    report.add_issue(ReviewIssue(
                        severity="high" if not self.strict_mode else "critical",
                        category="sql",
                        message=f"SQL error: {error.message}",
                        suggestion=error.suggestion,
                        affected_item=f"Query #{i+1}"
                    ))

            # Add warnings in strict mode
            if self.strict_mode:
                for warning in sql_report.get_warnings():
                    report.add_issue(ReviewIssue(
                        severity="medium",
                        category="sql",
                        message=f"SQL warning: {warning.message}",
                        suggestion=warning.suggestion,
                        affected_item=f"Query #{i+1}"
                    ))

        # Check if SQL score meets minimum
        if report.sql_validation_score < self.min_sql_score:
            report.add_issue(ReviewIssue(
                severity="high",
                category="sql",
                message=f"SQL validation score {report.sql_validation_score:.1f} below minimum {self.min_sql_score}",
                suggestion="Fix SQL errors and warnings to improve score"
            ))

    def _review_instructions(self, config: Dict[str, Any], report: ConfigReviewReport):
        """Review instruction quality."""
        quality_report = self.instruction_scorer.score_config_instructions(config)

        report.total_instructions = quality_report.total_instructions
        report.high_quality_instructions = quality_report.high_quality_count
        report.instruction_quality_score = quality_report.average_score

        # Add issues for low-quality instructions
        for i, score in enumerate(quality_report.instruction_scores):
            if score.total_score < 60:
                report.add_issue(ReviewIssue(
                    severity="medium",
                    category="instructions",
                    message=f"Instruction #{i+1} has low quality score: {score.total_score:.1f}/100",
                    suggestion="; ".join(score.suggestions[:2]) if score.suggestions else None,
                    affected_item=f"Instruction #{i+1}"
                ))

            # Critical priority instructions must be high quality
            instructions = config.get("instructions", [])
            if i < len(instructions):
                priority = instructions[i].get("priority")
                if priority == 1 and score.total_score < 80:
                    report.add_issue(ReviewIssue(
                        severity="high",
                        category="instructions",
                        message=f"Critical instruction #{i+1} (priority 1) has score {score.total_score:.1f}, should be ≥80",
                        suggestion="Improve specificity, structure, and clarity",
                        affected_item=f"Instruction #{i+1}"
                    ))

        # Check if instruction score meets minimum
        if report.instruction_quality_score < self.min_instruction_score:
            report.add_issue(ReviewIssue(
                severity="medium",
                category="instructions",
                message=f"Instruction quality score {report.instruction_quality_score:.1f} below minimum {self.min_instruction_score}",
                suggestion="Improve instruction specificity, structure, and clarity"
            ))

    def _review_joins(self, config: Dict[str, Any], report: ConfigReviewReport):
        """Review join specifications."""
        tables = config.get("tables", [])
        join_specs = config.get("join_specifications", [])

        # Validate join specifications
        tables_objs = [GenieSpaceTable(**t) for t in tables]
        join_issues = validate_join_specifications(join_specs, tables_objs)

        for issue in join_issues:
            severity = "critical" if issue.severity == "error" else "medium"
            report.add_issue(ReviewIssue(
                severity=severity,
                category="joins",
                message=issue.message,
                suggestion=issue.suggestion
            ))

        # Check join coverage
        # Estimate expected joins: for N tables, we might expect N-1 to N*(N-1)/2 joins
        num_tables = len(tables)
        if num_tables > 1:
            min_expected_joins = num_tables - 1  # Minimum spanning tree
            report.total_joins = min_expected_joins
            report.documented_joins = len(join_specs)

            if report.total_joins > 0:
                coverage_ratio = report.documented_joins / report.total_joins
                report.join_completeness_score = min(100, coverage_ratio * 100)
            else:
                report.join_completeness_score = 100

            # Warn if join coverage is low
            if report.join_completeness_score < self.min_join_coverage:
                report.add_issue(ReviewIssue(
                    severity="high",
                    category="joins",
                    message=f"Join coverage {report.join_completeness_score:.1f}% below minimum {self.min_join_coverage}%",
                    suggestion=f"Document join relationships for {report.total_joins - report.documented_joins} additional table pairs"
                ))

            # Warn if no joins documented but multiple tables
            if len(join_specs) == 0 and num_tables > 1:
                report.add_issue(ReviewIssue(
                    severity="critical",
                    category="joins",
                    message=f"No join specifications found for {num_tables} tables",
                    suggestion="Document how tables should be joined together"
                ))
        else:
            report.join_completeness_score = 100  # Single table, no joins needed

    def _review_coverage(self, config: Dict[str, Any], report: ConfigReviewReport):
        """Review example and benchmark coverage."""
        tables = config.get("tables", [])
        example_queries = config.get("example_sql_queries", [])
        benchmarks = config.get("benchmark_questions", [])
        
        # Count SQL snippets (filters, expressions, measures)
        sql_snippets = config.get("sql_snippets", {})
        num_sql_snippets = (
            len(sql_snippets.get("filters", [])) +
            len(sql_snippets.get("expressions", [])) +
            len(sql_snippets.get("measures", []))
        )

        num_tables = len(tables)

        # Check minimum examples per table
        examples_per_table = len(example_queries) / max(1, num_tables)

        if examples_per_table < 2:
            report.add_issue(ReviewIssue(
                severity="medium",
                category="coverage",
                message=f"Only {len(example_queries)} example queries for {num_tables} tables (avg {examples_per_table:.1f} per table)",
                suggestion="Add at least 2-3 example queries per table"
            ))

        # Check for benchmarks
        if len(benchmarks) < 5:
            report.add_issue(ReviewIssue(
                severity="low",
                category="coverage",
                message=f"Only {len(benchmarks)} benchmark questions",
                suggestion="Add more benchmark questions for testing (aim for 10-20)"
            ))

        # Check for SQL snippets (filters/expressions/measures)
        if num_sql_snippets == 0:
            report.add_issue(ReviewIssue(
                severity="info",
                category="coverage",
                message="No SQL snippets (filters/expressions/measures) defined",
                suggestion="Consider defining common filters, dimensions, and metrics as SQL snippets"
            ))

        # Calculate coverage score
        example_score = min(100, (len(example_queries) / max(1, num_tables * 2)) * 100)
        benchmark_score = min(100, (len(benchmarks) / 10) * 100)
        expression_score = min(100, (num_sql_snippets / 5) * 100)

        report.coverage_score = (example_score * 0.5 + benchmark_score * 0.3 + expression_score * 0.2)

    def _review_structure(self, config: Dict[str, Any], report: ConfigReviewReport):
        """Review overall configuration structure."""
        # Check required fields
        required_fields = ["space_name", "description", "purpose", "tables"]
        for field in required_fields:
            if field not in config or not config[field]:
                report.add_issue(ReviewIssue(
                    severity="critical",
                    category="structure",
                    message=f"Missing required field: {field}",
                    suggestion=f"Provide a value for {field}"
                ))

        # Check field quality
        if len(config.get("description", "")) < 20:
            report.add_issue(ReviewIssue(
                severity="low",
                category="structure",
                message="Description is too short",
                suggestion="Provide a more detailed description (at least 20 characters)"
            ))

        if len(config.get("purpose", "")) < 20:
            report.add_issue(ReviewIssue(
                severity="low",
                category="structure",
                message="Purpose is too short",
                suggestion="Provide a more detailed purpose statement"
            ))

        # Check for empty tables list
        if not config.get("tables"):
            report.add_issue(ReviewIssue(
                severity="critical",
                category="structure",
                message="No tables defined",
                suggestion="Add at least one table to the configuration"
            ))


def review_config_file(
    config_path: str,
    available_tables: Optional[List[GenieSpaceTable]] = None,
    output_path: Optional[str] = None,
    strict_mode: bool = False,
    verbose: bool = True
) -> ConfigReviewReport:
    """
    Convenience function to review a configuration file.

    Args:
        config_path: Path to configuration JSON file
        available_tables: List of available tables (optional)
        output_path: Path to save review report (optional)
        strict_mode: If True, warnings become errors
        verbose: Print review results

    Returns:
        ConfigReviewReport with review findings
    """
    # Load configuration
    with open(config_path, 'r', encoding='utf-8') as f:
        full_config = json.load(f)

    # Extract genie_space_config if wrapped
    if "genie_space_config" in full_config:
        config = full_config["genie_space_config"]
    else:
        config = full_config

    # Get tables from config if not provided
    if not available_tables and "tables" in config:
        available_tables = [GenieSpaceTable(**t) for t in config["tables"]]

    # Create review agent
    agent = ConfigReviewAgent(
        available_tables=available_tables,
        strict_mode=strict_mode
    )

    # Review configuration
    config_name = config.get("space_name", Path(config_path).stem)
    report = agent.review_config(config, config_name=config_name)

    # Print results
    if verbose:
        print(report.summary())

        # Print issues by severity
        for severity in ["critical", "high", "medium", "low"]:
            issues = report.get_issues_by_severity(severity)
            if issues:
                print(f"\n{severity.upper()} Issues:")
                for issue in issues:
                    affected = f" ({issue.affected_item})" if issue.affected_item else ""
                    print(f"  - [{issue.category}] {issue.message}{affected}")
                    if issue.suggestion:
                        print(f"    💡 {issue.suggestion}")

    # Save report if requested
    if output_path:
        report_data = {
            "config_name": report.config_name,
            "overall_score": report.overall_score,
            "passed": report.passed,
            "component_scores": {
                "sql_validation": report.sql_validation_score,
                "instruction_quality": report.instruction_quality_score,
                "join_completeness": report.join_completeness_score,
                "coverage": report.coverage_score
            },
            "metrics": {
                "sql_queries": f"{report.valid_sql_queries}/{report.total_sql_queries}",
                "instructions": f"{report.high_quality_instructions}/{report.total_instructions}",
                "joins": f"{report.documented_joins}/{report.total_joins}"
            },
            "issues": [
                {
                    "severity": issue.severity,
                    "category": issue.category,
                    "message": issue.message,
                    "suggestion": issue.suggestion,
                    "affected_item": issue.affected_item
                }
                for issue in report.issues
            ]
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        if verbose:
            print(f"\n📄 Review report saved to {output_path}")

    return report
