"""
SQL syntax and schema validation for Genie configurations.

This module validates SQL queries in Genie configurations to catch errors before deployment:
- SQL syntax validation
- Table reference extraction and validation
- Column reference extraction and validation
- Join condition validation
"""

import re
import sqlparse
from typing import Dict, List, Set, Tuple, Any, Optional
from dataclasses import dataclass, field
from genie.models import GenieSpaceTable


@dataclass
class ValidationIssue:
    """Represents a validation issue found in SQL."""
    severity: str  # "error", "warning", "info"
    category: str  # "syntax", "table", "column", "join", "best_practice"
    message: str
    sql_snippet: Optional[str] = None
    line_number: Optional[int] = None
    suggestion: Optional[str] = None


@dataclass
class SQLValidationReport:
    """Report of SQL validation results."""
    sql_query: str
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    tables_referenced: Set[str] = field(default_factory=set)
    columns_referenced: Set[str] = field(default_factory=set)
    has_explicit_joins: bool = False
    has_group_by: bool = False
    has_limit: bool = False

    def add_issue(self, issue: ValidationIssue):
        """Add a validation issue to the report."""
        self.issues.append(issue)
        if issue.severity == "error":
            self.is_valid = False

    def get_errors(self) -> List[ValidationIssue]:
        """Get all error-level issues."""
        return [i for i in self.issues if i.severity == "error"]

    def get_warnings(self) -> List[ValidationIssue]:
        """Get all warning-level issues."""
        return [i for i in self.issues if i.severity == "warning"]

    def summary(self) -> str:
        """Get a human-readable summary."""
        errors = self.get_errors()
        warnings = self.get_warnings()
        status = "✅ Valid" if self.is_valid else "❌ Invalid"
        return (
            f"{status} - {len(errors)} errors, {len(warnings)} warnings\n"
            f"Tables: {len(self.tables_referenced)}, Columns: {len(self.columns_referenced)}"
        )


class SQLValidator:
    """
    Validates SQL queries for syntax and schema correctness.

    Usage:
        validator = SQLValidator(available_tables)
        report = validator.validate_sql(sql_query)
        if not report.is_valid:
            for error in report.get_errors():
                print(f"Error: {error.message}")
    """

    # SQL keywords that shouldn't be counted as column names
    SQL_KEYWORDS = {
        'SELECT', 'FROM', 'WHERE', 'JOIN', 'INNER', 'LEFT', 'RIGHT', 'FULL', 'OUTER',
        'ON', 'AND', 'OR', 'NOT', 'IN', 'LIKE', 'BETWEEN', 'IS', 'NULL', 'AS',
        'GROUP', 'BY', 'HAVING', 'ORDER', 'LIMIT', 'OFFSET', 'DISTINCT', 'COUNT',
        'SUM', 'AVG', 'MIN', 'MAX', 'CAST', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
        'UNION', 'INTERSECT', 'EXCEPT', 'WITH', 'CURRENT_DATE', 'CURRENT_TIMESTAMP',
        'DATE_SUB', 'DATE_ADD', 'DATE_TRUNC', 'COALESCE', 'NULLIF', 'TRY_DIVIDE',
        'OVER', 'PARTITION', 'ROW_NUMBER', 'RANK', 'DENSE_RANK', 'LAG', 'LEAD',
        'DECIMAL', 'INTEGER', 'STRING', 'BOOLEAN', 'TIMESTAMP', 'DATE'
    }

    def __init__(self, available_tables: Optional[List[GenieSpaceTable]] = None):
        """
        Initialize SQL validator.

        Args:
            available_tables: List of tables available in the Genie space
        """
        self.available_tables = available_tables or []
        self.table_map = self._build_table_map()

    def _build_table_map(self) -> Dict[str, GenieSpaceTable]:
        """Build a lookup map of table identifiers."""
        table_map = {}
        for table in self.available_tables:
            # Full identifier: catalog.schema.table
            full_id = f"{table.catalog_name}.{table.schema_name}.{table.table_name}"
            table_map[full_id] = table

            # Schema.table identifier
            schema_table = f"{table.schema_name}.{table.table_name}"
            table_map[schema_table] = table

            # Table name only
            table_map[table.table_name] = table

        return table_map

    def validate_sql(self, sql: str, query_name: Optional[str] = None) -> SQLValidationReport:
        """
        Validate a SQL query.

        Args:
            sql: SQL query to validate
            query_name: Optional name for the query (for reporting)

        Returns:
            SQLValidationReport with validation results
        """
        report = SQLValidationReport(sql_query=sql, is_valid=True)

        # Skip empty queries
        if not sql or not sql.strip():
            report.add_issue(ValidationIssue(
                severity="error",
                category="syntax",
                message="Empty SQL query"
            ))
            return report

        # 1. Basic syntax validation
        self._validate_syntax(sql, report)

        # 2. Extract and validate table references
        self._extract_and_validate_tables(sql, report)

        # 3. Check for explicit joins
        self._check_join_patterns(sql, report)

        # 4. Check for common SQL quality issues
        self._check_sql_quality(sql, report)

        # 5. Extract column references (informational)
        self._extract_column_references(sql, report)

        return report

    def _validate_syntax(self, sql: str, report: SQLValidationReport):
        """Validate basic SQL syntax."""
        try:
            # Parse SQL using sqlparse
            parsed = sqlparse.parse(sql)

            if not parsed:
                report.add_issue(ValidationIssue(
                    severity="error",
                    category="syntax",
                    message="Failed to parse SQL query"
                ))
                return

            # Check for common syntax issues
            sql_upper = sql.upper()

            # Check for balanced parentheses
            if sql.count('(') != sql.count(')'):
                report.add_issue(ValidationIssue(
                    severity="error",
                    category="syntax",
                    message="Unbalanced parentheses in SQL",
                    suggestion="Check that all opening parentheses have matching closing ones"
                ))

            # Check for balanced quotes
            single_quotes = sql.count("'") - sql.count("\\'")
            if single_quotes % 2 != 0:
                report.add_issue(ValidationIssue(
                    severity="error",
                    category="syntax",
                    message="Unbalanced single quotes in SQL",
                    suggestion="Check that all string literals are properly quoted"
                ))

            # Check for SELECT without FROM (except for special cases)
            if 'SELECT' in sql_upper and 'FROM' not in sql_upper:
                if 'CURRENT_DATE' not in sql_upper and 'CURRENT_TIMESTAMP' not in sql_upper:
                    report.add_issue(ValidationIssue(
                        severity="warning",
                        category="syntax",
                        message="SELECT without FROM clause",
                        suggestion="Most queries should have a FROM clause"
                    ))

        except Exception as e:
            report.add_issue(ValidationIssue(
                severity="error",
                category="syntax",
                message=f"SQL parsing error: {str(e)}"
            ))

    def _extract_and_validate_tables(self, sql: str, report: SQLValidationReport):
        """Extract table references and validate they exist."""
        # Pattern to match table references in FROM and JOIN clauses
        # Matches: catalog.schema.table, schema.table, or table
        table_pattern = r'\b(?:FROM|JOIN)\s+([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)?(?:\.[a-zA-Z0-9_]+)?)\s*(?:AS\s+)?([a-zA-Z0-9_]+)?'

        matches = re.finditer(table_pattern, sql, re.IGNORECASE)

        for match in matches:
            table_ref = match.group(1)
            report.tables_referenced.add(table_ref)

            # Validate table exists if we have a table map
            if self.available_tables and table_ref not in self.table_map:
                report.add_issue(ValidationIssue(
                    severity="error",
                    category="table",
                    message=f"Table not found: {table_ref}",
                    sql_snippet=match.group(0),
                    suggestion=f"Available tables: {', '.join(self.table_map.keys())}"
                ))

    def _check_join_patterns(self, sql: str, report: SQLValidationReport):
        """Check for explicit JOIN patterns and conditions."""
        sql_upper = sql.upper()

        # Check for explicit JOIN keywords
        has_join = any(join_type in sql_upper for join_type in ['INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'FULL JOIN', 'JOIN'])
        report.has_explicit_joins = has_join

        if has_join:
            # Check that JOINs have ON clauses
            join_count = len(re.findall(r'\bJOIN\b', sql_upper))
            on_count = len(re.findall(r'\bON\b', sql_upper))

            if join_count > on_count:
                report.add_issue(ValidationIssue(
                    severity="error",
                    category="join",
                    message=f"Found {join_count} JOINs but only {on_count} ON clauses",
                    suggestion="Every JOIN should have an ON clause specifying the join condition"
                ))

        # Check for implicit joins (comma-separated tables without proper WHERE)
        from_clause_match = re.search(r'FROM\s+(.*?)(?:WHERE|GROUP|ORDER|HAVING|LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
        if from_clause_match:
            from_clause = from_clause_match.group(1)
            comma_tables = from_clause.count(',')

            if comma_tables > 0 and not has_join:
                report.add_issue(ValidationIssue(
                    severity="warning",
                    category="join",
                    message="Implicit join detected (comma-separated tables)",
                    sql_snippet=from_clause.strip(),
                    suggestion="Use explicit JOIN syntax with ON clauses instead of comma-separated tables"
                ))

    def _check_sql_quality(self, sql: str, report: SQLValidationReport):
        """Check for SQL quality best practices."""
        sql_upper = sql.upper()

        # Check for GROUP BY
        report.has_group_by = 'GROUP BY' in sql_upper

        # Check for LIMIT
        report.has_limit = 'LIMIT' in sql_upper

        # Check for SELECT *
        if re.search(r'\bSELECT\s+\*', sql, re.IGNORECASE):
            report.add_issue(ValidationIssue(
                severity="warning",
                category="best_practice",
                message="SELECT * found - consider selecting specific columns",
                suggestion="Explicitly list columns instead of using SELECT *"
            ))

        # Check for hard-coded dates
        date_patterns = [
            r"'\d{4}-\d{2}-\d{2}'",  # '2024-01-01'
            r'"\d{4}-\d{2}-\d{2}"',  # "2024-01-01"
        ]
        for pattern in date_patterns:
            if re.search(pattern, sql):
                report.add_issue(ValidationIssue(
                    severity="warning",
                    category="best_practice",
                    message="Hard-coded date found in SQL",
                    suggestion="Use dynamic date functions like CURRENT_DATE(), DATE_SUB(), etc."
                ))
                break

        # Check for aggregates without GROUP BY
        aggregates = ['COUNT', 'SUM', 'AVG', 'MIN', 'MAX']
        has_aggregate = any(agg in sql_upper for agg in aggregates)

        if has_aggregate and not report.has_group_by:
            # Check if there are column references outside aggregates
            select_clause_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
            if select_clause_match:
                select_clause = select_clause_match.group(1)
                # Check if we have non-aggregate columns mixed with aggregates
                # Look for column names that aren't inside aggregate functions
                # Simple heuristic: if we have commas and aggregates, likely mixing
                has_comma = ',' in select_clause

                if has_comma:
                    # Count aggregate function calls vs total columns
                    agg_count = sum(select_clause.upper().count(agg + '(') for agg in aggregates)
                    # If we have multiple columns and not all are aggregates, warn
                    if agg_count > 0:
                        report.add_issue(ValidationIssue(
                            severity="warning",
                            category="best_practice",
                            message="Aggregate function used without GROUP BY",
                            suggestion="When mixing aggregate and non-aggregate columns, include GROUP BY clause"
                        ))

        # Check for division without safety
        if '/' in sql and 'TRY_DIVIDE' not in sql_upper and 'NULLIF' not in sql_upper:
            report.add_issue(ValidationIssue(
                severity="info",
                category="best_practice",
                message="Division operator found without null safety",
                suggestion="Consider using try_divide() to handle division by zero/null"
            ))

        # Check for DECIMAL casting in aggregates
        if has_aggregate and 'CAST' not in sql_upper and 'DECIMAL' not in sql_upper:
            report.add_issue(ValidationIssue(
                severity="info",
                category="best_practice",
                message="Aggregate without DECIMAL casting",
                suggestion="Consider casting aggregates to DECIMAL(38,2) for consistent precision"
            ))

    def _extract_column_references(self, sql: str, report: SQLValidationReport):
        """Extract column references from SQL (informational)."""
        # Pattern to match column references (table.column or just column)
        column_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)\b'

        matches = re.finditer(column_pattern, sql)

        for match in matches:
            ref = match.group(1)
            # Skip SQL keywords
            if ref.upper() not in self.SQL_KEYWORDS and '.' in ref:
                report.columns_referenced.add(ref)

    def validate_config_sql(
        self,
        config: Dict[str, Any],
        check_examples: bool = True,
        check_expressions: bool = True
    ) -> Dict[str, List[SQLValidationReport]]:
        """
        Validate all SQL in a Genie configuration.

        Args:
            config: Genie space configuration dictionary
            check_examples: Whether to validate example SQL queries
            check_expressions: Whether to validate SQL expressions

        Returns:
            Dictionary mapping SQL type to list of validation reports
        """
        results = {
            "example_queries": [],
            "sql_snippets": {
                "filters": [],
                "expressions": [],
                "measures": []
            },
            "summary": {
                "total_queries": 0,
                "valid_queries": 0,
                "queries_with_errors": 0,
                "queries_with_warnings": 0
            }
        }

        # Validate example SQL queries
        if check_examples:
            examples = config.get("example_sql_queries", [])
            for i, example in enumerate(examples):
                sql = example.get("sql_query", "")
                question = example.get("question", f"Query #{i+1}")

                report = self.validate_sql(sql, query_name=question)
                results["example_queries"].append(report)

                results["summary"]["total_queries"] += 1
                if report.is_valid:
                    results["summary"]["valid_queries"] += 1
                else:
                    results["summary"]["queries_with_errors"] += 1
                if report.get_warnings():
                    results["summary"]["queries_with_warnings"] += 1

        # Validate SQL snippets (filters, expressions, measures)
        if check_expressions:
            sql_snippets = config.get("sql_snippets", {})
            
            # Validate filters
            filters = sql_snippets.get("filters", [])
            for i, filt in enumerate(filters):
                sql = filt.get("sql", "")
                name = filt.get("display_name", f"Filter #{i+1}")
                report = self.validate_sql(sql, query_name=name)
                results["sql_snippets"]["filters"].append(report)
                
                results["summary"]["total_queries"] += 1
                if report.is_valid:
                    results["summary"]["valid_queries"] += 1
                else:
                    results["summary"]["queries_with_errors"] += 1
                if report.get_warnings():
                    results["summary"]["queries_with_warnings"] += 1
            
            # Validate expressions
            expressions = sql_snippets.get("expressions", [])
            for i, expr in enumerate(expressions):
                sql = expr.get("sql", "")
                name = expr.get("alias", f"Expression #{i+1}")
                report = self.validate_sql(sql, query_name=name)
                results["sql_snippets"]["expressions"].append(report)
                
                results["summary"]["total_queries"] += 1
                if report.is_valid:
                    results["summary"]["valid_queries"] += 1
                else:
                    results["summary"]["queries_with_errors"] += 1
                if report.get_warnings():
                    results["summary"]["queries_with_warnings"] += 1
            
            # Validate measures
            measures = sql_snippets.get("measures", [])
            for i, measure in enumerate(measures):
                sql = measure.get("sql", "")
                name = measure.get("alias", f"Measure #{i+1}")
                report = self.validate_sql(sql, query_name=name)
                results["sql_snippets"]["measures"].append(report)
                
                results["summary"]["total_queries"] += 1
                if report.is_valid:
                    results["summary"]["valid_queries"] += 1
                else:
                    results["summary"]["queries_with_errors"] += 1
                if report.get_warnings():
                    results["summary"]["queries_with_warnings"] += 1

        return results


def validate_join_specifications(
    join_specs: List[Dict[str, Any]],
    available_tables: List[GenieSpaceTable]
) -> List[ValidationIssue]:
    """
    Validate join specifications in a configuration.

    Args:
        join_specs: List of join specification dictionaries
        available_tables: List of available tables

    Returns:
        List of validation issues
    """
    issues = []

    # Build table map with multiple identifier formats
    table_map = {}
    for t in available_tables:
        full_id = f"{t.catalog_name}.{t.schema_name}.{t.table_name}"
        schema_table = f"{t.schema_name}.{t.table_name}"

        table_map[full_id] = t
        table_map[schema_table] = t
        table_map[t.table_name] = t

    for i, join_spec in enumerate(join_specs):
        left_table = join_spec.get("left_table", "")
        right_table = join_spec.get("right_table", "")
        join_condition = join_spec.get("join_condition", "")

        # Check left table exists
        if left_table and left_table not in table_map:
            issues.append(ValidationIssue(
                severity="error",
                category="table",
                message=f"Join #{i+1}: Left table not found: {left_table}",
                suggestion=f"Available tables: {', '.join(set([f'{t.catalog_name}.{t.schema_name}.{t.table_name}' for t in available_tables]))}"
            ))

        # Check right table exists
        if right_table and right_table not in table_map:
            issues.append(ValidationIssue(
                severity="error",
                category="table",
                message=f"Join #{i+1}: Right table not found: {right_table}",
                suggestion=f"Available tables: {', '.join(set([f'{t.catalog_name}.{t.schema_name}.{t.table_name}' for t in available_tables]))}"
            ))

        # Check join condition is not empty
        if not join_condition:
            issues.append(ValidationIssue(
                severity="error",
                category="join",
                message=f"Join #{i+1}: Empty join condition",
                suggestion="Provide a join condition like 'table1.id = table2.foreign_id'"
            ))

    return issues
