"""
Validator for Databricks tables and columns referenced in Genie Space configurations.

This module validates that:
1. All tables referenced in the configuration exist in Unity Catalog
2. All columns referenced in SQL queries and expressions exist in their respective tables
3. All tables referenced in benchmark questions are valid
4. The user has proper access permissions to the tables

Usage:
    from genie.table_validator import TableValidator

    validator = TableValidator()
    report = validator.validate_config("output/genie_space_config.json")
    print(report.summary())
"""

import os
import re
import json
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
import requests
from pathlib import Path


@dataclass
class ValidationIssue:
    """Represents a validation issue found during table/column validation."""
    severity: str  # "error", "warning", "info"
    type: str  # "table_not_found", "column_not_found", "access_denied", etc.
    message: str
    table: Optional[str] = None
    column: Optional[str] = None
    location: Optional[str] = None  # where in config this was found


@dataclass
class ValidationReport:
    """Complete validation report for a Genie space configuration."""
    tables_checked: List[str] = field(default_factory=list)
    tables_valid: List[str] = field(default_factory=list)
    tables_invalid: List[str] = field(default_factory=list)
    columns_checked: Dict[str, List[str]] = field(default_factory=dict)
    columns_valid: Dict[str, List[str]] = field(default_factory=dict)
    columns_invalid: Dict[str, List[str]] = field(default_factory=dict)
    issues: List[ValidationIssue] = field(default_factory=list)
    
    def add_issue(self, severity: str, type: str, message: str, **kwargs):
        """Add a validation issue to the report."""
        self.issues.append(ValidationIssue(
            severity=severity,
            type=type,
            message=message,
            **kwargs
        ))
    
    def has_errors(self) -> bool:
        """Check if there are any error-level issues."""
        return any(issue.severity == "error" for issue in self.issues)
    
    def has_warnings(self) -> bool:
        """Check if there are any warning-level issues."""
        return any(issue.severity == "warning" for issue in self.issues)
    
    def summary(self) -> str:
        """Generate a human-readable summary of the validation report."""
        lines = []
        lines.append("=" * 80)
        lines.append("TABLE & COLUMN VALIDATION REPORT")
        lines.append("=" * 80)
        lines.append("")
        
        # Tables summary
        lines.append(f"Tables Checked: {len(self.tables_checked)}")
        lines.append(f"  ✓ Valid:   {len(self.tables_valid)}")
        if self.tables_invalid:
            lines.append(f"  ✗ Invalid: {len(self.tables_invalid)}")
        lines.append("")
        
        # Columns summary
        total_columns = sum(len(cols) for cols in self.columns_checked.values())
        valid_columns = sum(len(cols) for cols in self.columns_valid.values())
        invalid_columns = sum(len(cols) for cols in self.columns_invalid.values())
        
        lines.append(f"Columns Checked: {total_columns}")
        lines.append(f"  ✓ Valid:   {valid_columns}")
        if invalid_columns:
            lines.append(f"  ✗ Invalid: {invalid_columns}")
        lines.append("")
        
        # Issues breakdown
        errors = [i for i in self.issues if i.severity == "error"]
        warnings = [i for i in self.issues if i.severity == "warning"]
        infos = [i for i in self.issues if i.severity == "info"]
        
        lines.append("Issues:")
        lines.append(f"  Errors:   {len(errors)}")
        lines.append(f"  Warnings: {len(warnings)}")
        lines.append(f"  Info:     {len(infos)}")
        lines.append("")
        
        # List all issues
        if self.issues:
            lines.append("-" * 80)
            lines.append("DETAILED ISSUES")
            lines.append("-" * 80)
            lines.append("")
            
            for issue in self.issues:
                icon = "✗" if issue.severity == "error" else "⚠" if issue.severity == "warning" else "ℹ"
                lines.append(f"{icon} [{issue.severity.upper()}] {issue.type}")
                lines.append(f"  {issue.message}")
                if issue.table:
                    lines.append(f"  Table: {issue.table}")
                if issue.column:
                    lines.append(f"  Column: {issue.column}")
                if issue.location:
                    lines.append(f"  Location: {issue.location}")
                lines.append("")
        
        # Final status
        lines.append("=" * 80)
        if not self.has_errors():
            lines.append("✓ VALIDATION PASSED - All tables and columns are valid!")
        else:
            lines.append("✗ VALIDATION FAILED - Please fix the errors above")
        lines.append("=" * 80)
        
        return "\n".join(lines)


class TableValidator:
    """Validates tables and columns in Genie Space configurations against Unity Catalog."""
    
    def __init__(
        self,
        databricks_host: Optional[str] = None,
        databricks_token: Optional[str] = None,
        fallback_token: Optional[str] = None
    ):
        """
        Initialize the validator.

        Args:
            databricks_host: Databricks workspace URL (defaults to DATABRICKS_HOST env var)
            databricks_token: Databricks personal access token (defaults to DATABRICKS_TOKEN env var)
            fallback_token: Optional fallback token (e.g., app SP token) used when primary token
                           lacks permissions for UC API or SQL operations
        """
        self.databricks_host = databricks_host or os.getenv("DATABRICKS_HOST")
        self.databricks_token = databricks_token or os.getenv("DATABRICKS_TOKEN")
        self.fallback_token = fallback_token

        if not self.databricks_host:
            raise ValueError("databricks_host must be provided or DATABRICKS_HOST env var must be set")
        if not self.databricks_token:
            raise ValueError("databricks_token must be provided or DATABRICKS_TOKEN env var must be set")

        # Clean up host URL
        self.databricks_host = self.databricks_host.rstrip('/')
        if not self.databricks_host.startswith('http'):
            self.databricks_host = f"https://{self.databricks_host}"

        # Cache for table schemas to avoid repeated API calls
        self._table_cache: Dict[str, Dict[str, Any]] = {}
    
    def _get_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        """Get headers for API requests."""
        return {
            "Authorization": f"Bearer {token or self.databricks_token}",
            "Content-Type": "application/json"
        }

    def _resolve_warehouse_id(self) -> Optional[str]:
        """Resolve SQL warehouse ID from multiple environment sources."""
        # 1. Direct WAREHOUSE_ID env var (set by app.yaml valueFrom)
        warehouse_id = os.getenv("WAREHOUSE_ID")
        if warehouse_id:
            return warehouse_id

        # 2. Extract from DATABRICKS_HTTP_PATH (e.g., /sql/1.0/warehouses/<id>)
        http_path = os.getenv("DATABRICKS_HTTP_PATH")
        if http_path and "/warehouses/" in http_path:
            return http_path.split("/warehouses/")[-1].strip("/")

        return None
    
    def get_table_schema(self, catalog: str, schema: str, table: str) -> Optional[Dict[str, Any]]:
        """
        Get the schema of a table from Unity Catalog.

        Tries multiple methods in order:
        1. UC REST API with primary token
        2. SQL Statement API with primary token
        3. SQL connector with primary token
        4. If fallback token available: repeat steps 1-3 with fallback token

        Args:
            catalog: Catalog name
            schema: Schema name
            table: Table name

        Returns:
            Dictionary containing table metadata including columns, or None if table doesn't exist
        """
        import logging
        logger = logging.getLogger(__name__)

        full_name = f"{catalog}.{schema}.{table}"

        # Check cache first
        if full_name in self._table_cache:
            logger.debug(f"Table {full_name}: cache hit")
            return self._table_cache[full_name]

        # Try with primary token
        result = self._try_get_table(catalog, schema, table, self.databricks_token, "user")
        if result is not None:
            return result

        # Try with fallback token (e.g., app service principal)
        if self.fallback_token and self.fallback_token != self.databricks_token:
            logger.info(f"Table {full_name}: retrying with fallback (app SP) token")
            result = self._try_get_table(catalog, schema, table, self.fallback_token, "app-sp")
            if result is not None:
                return result

        logger.warning(f"Table {full_name}: all validation methods exhausted")
        self._table_cache[full_name] = None
        return None

    def _try_get_table(self, catalog: str, schema: str, table: str, token: str, label: str) -> Optional[Dict[str, Any]]:
        """Try all methods to get table schema using the given token."""
        import logging
        logger = logging.getLogger(__name__)

        full_name = f"{catalog}.{schema}.{table}"

        # 1. Try UC REST API
        result = self._check_table_via_uc_api(catalog, schema, table, token, label)
        if result is not None:
            return result

        # 2. Try SQL Statement API
        result = self._check_table_via_sql_api(catalog, schema, table, token, label)
        if result is not None:
            return result

        # 3. Try SQL connector
        result = self._check_table_via_sql_connector(catalog, schema, table, token, label)
        if result is not None:
            return result

        return None

    def _check_table_via_uc_api(self, catalog: str, schema: str, table: str, token: str, label: str) -> Optional[Dict[str, Any]]:
        """Check table existence via Unity Catalog REST API."""
        import logging
        logger = logging.getLogger(__name__)

        full_name = f"{catalog}.{schema}.{table}"

        try:
            url = f"{self.databricks_host}/api/2.1/unity-catalog/tables/{catalog}.{schema}.{table}"
            logger.info(f"Table {full_name}: trying UC API ({label})")
            response = requests.get(url, headers=self._get_headers(token), timeout=30)

            if response.status_code == 200:
                table_info = response.json()
                self._table_cache[full_name] = table_info
                logger.info(f"Table {full_name}: found via UC API ({label})")
                return table_info
            elif response.status_code == 404:
                logger.warning(f"Table {full_name}: UC API 404 ({label})")
                return None
            else:
                logger.warning(f"Table {full_name}: UC API {response.status_code} ({label}) - {response.text[:200]}")
                return None
        except Exception as e:
            logger.warning(f"Table {full_name}: UC API error ({label}) - {e}")
            return None
    
    def _get_table_schema_via_sql(self, catalog: str, schema: str, table: str) -> Optional[Dict[str, Any]]:
        """
        Fallback method to check table existence via SQL.

        Tries two approaches:
        1. SQL Statement Execution REST API (no connector needed)
        2. Databricks SQL connector (if REST API fails)

        Args:
            catalog: Catalog name
            schema: Schema name
            table: Table name

        Returns:
            Dictionary containing table metadata, or None if table doesn't exist or no access
        """
        import logging
        logger = logging.getLogger(__name__)

        full_name = f"{catalog}.{schema}.{table}"

        # Try REST-based SQL Statement API first (simpler, no connector)
        result = self._check_table_via_sql_api(catalog, schema, table)
        if result is not None:
            return result

        # Fall back to SQL connector
        result = self._check_table_via_sql_connector(catalog, schema, table)
        if result is not None:
            return result

        logger.warning(f"Table {full_name}: all validation methods failed")
        self._table_cache[full_name] = None
        return None

    def _check_table_via_sql_api(self, catalog: str, schema: str, table: str, token: Optional[str] = None, label: str = "user") -> Optional[Dict[str, Any]]:
        """Check table existence using the SQL Statement Execution REST API."""
        import logging
        import time as _time
        logger = logging.getLogger(__name__)

        full_name = f"{catalog}.{schema}.{table}"
        token = token or self.databricks_token
        warehouse_id = self._resolve_warehouse_id()

        if not warehouse_id:
            logger.warning(f"Table {full_name}: no warehouse ID for SQL API ({label})")
            return None

        logger.info(f"Table {full_name}: trying SQL Statement API ({label}, warehouse={warehouse_id})")

        try:
            # Submit SQL statement
            url = f"{self.databricks_host}/api/2.0/sql/statements/"
            payload = {
                "warehouse_id": warehouse_id,
                "statement": f"DESCRIBE TABLE {full_name}",
                "wait_timeout": "30s",
                "disposition": "INLINE"
            }
            response = requests.post(url, headers=self._get_headers(token), json=payload, timeout=60)

            if response.status_code != 200:
                logger.warning(
                    f"Table {full_name}: SQL API returned {response.status_code} ({label}) - "
                    f"{response.text[:200]}"
                )
                return None

            result = response.json()
            status = result.get("status", {}).get("state", "")

            # Handle async execution — poll until done
            statement_id = result.get("statement_id")
            poll_count = 0
            while status in ("PENDING", "RUNNING") and poll_count < 30:
                _time.sleep(1)
                poll_url = f"{self.databricks_host}/api/2.0/sql/statements/{statement_id}"
                poll_resp = requests.get(poll_url, headers=self._get_headers(token), timeout=30)
                if poll_resp.status_code != 200:
                    break
                result = poll_resp.json()
                status = result.get("status", {}).get("state", "")
                poll_count += 1

            if status == "SUCCEEDED":
                # Parse DESCRIBE TABLE result
                columns = []
                data_array = result.get("result", {}).get("data_array", [])
                for row in data_array:
                    if row and len(row) >= 2 and row[0] and not row[0].startswith("#"):
                        columns.append({
                            "name": row[0],
                            "type_text": row[1] if len(row) > 1 else "unknown",
                            "type_name": row[1] if len(row) > 1 else "unknown"
                        })

                table_info = {
                    "full_name": full_name,
                    "catalog_name": catalog,
                    "schema_name": schema,
                    "name": table,
                    "columns": columns
                }
                self._table_cache[full_name] = table_info
                logger.info(f"Table {full_name}: found via SQL API ({label}) with {len(columns)} columns")
                return table_info
            else:
                error_msg = result.get("status", {}).get("error", {}).get("message", status)
                logger.warning(f"Table {full_name}: SQL API failed ({label}) - {error_msg}")
                return None

        except Exception as e:
            logger.warning(f"Table {full_name}: SQL API error ({label}) - {e}")
            return None

    def _check_table_via_sql_connector(self, catalog: str, schema: str, table: str, token: Optional[str] = None, label: str = "user") -> Optional[Dict[str, Any]]:
        """Check table existence using the Databricks SQL connector."""
        import logging
        from io import StringIO
        from contextlib import redirect_stdout, redirect_stderr

        logger = logging.getLogger(__name__)

        full_name = f"{catalog}.{schema}.{table}"
        token = token or self.databricks_token
        warehouse_id = self._resolve_warehouse_id()

        if not warehouse_id:
            logger.warning(f"Table {full_name}: no warehouse ID for SQL connector ({label})")
            return None

        try:
            from databricks import sql as databricks_sql
        except ImportError:
            logger.warning(f"Table {full_name}: databricks-sql not installed")
            return None

        logger.info(f"Table {full_name}: trying SQL connector ({label}, warehouse={warehouse_id})")

        connection = None
        cursor = None
        columns = []
        table_info = None
        error_detail = None

        stdout_buffer = StringIO()
        stderr_buffer = StringIO()

        try:
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                server_hostname = self.databricks_host.replace("https://", "").replace("http://", "")
                http_path = f"/sql/1.0/warehouses/{warehouse_id}"

                connection = databricks_sql.connect(
                    server_hostname=server_hostname,
                    http_path=http_path,
                    access_token=token,
                    timeout=30
                )
                cursor = connection.cursor()

                cursor.execute(f"SELECT 1 FROM {full_name} LIMIT 0")
                _ = cursor.fetchall()

                cursor.execute(f"DESCRIBE TABLE {full_name}")
                rows = cursor.fetchall()

                for row in rows:
                    columns.append({
                        "name": row[0],
                        "type_text": row[1],
                        "type_name": row[1]
                    })

                table_info = {
                    "full_name": full_name,
                    "catalog_name": catalog,
                    "schema_name": schema,
                    "name": table,
                    "columns": columns
                }

        except Exception as e:
            error_detail = str(e)
            table_info = None

        finally:
            try:
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    if cursor is not None:
                        cursor.close()
            except Exception:
                pass
            try:
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    if connection is not None:
                        connection.close()
            except Exception:
                pass

        if table_info is not None:
            self._table_cache[full_name] = table_info
            logger.info(f"Table {full_name}: found via SQL connector ({label}) with {len(columns)} columns")
            return table_info
        else:
            logger.warning(f"Table {full_name}: SQL connector failed ({label}) - {error_detail}")
            return None
    
    def validate_table(self, catalog: str, schema: str, table: str) -> bool:
        """
        Validate that a table exists.
        
        Args:
            catalog: Catalog name
            schema: Schema name
            table: Table name
            
        Returns:
            True if table exists, False otherwise
        """
        return self.get_table_schema(catalog, schema, table) is not None
    
    def validate_columns(
        self,
        catalog: str,
        schema: str,
        table: str,
        columns: List[str]
    ) -> Dict[str, bool]:
        """
        Validate that columns exist in a table.
        
        Args:
            catalog: Catalog name
            schema: Schema name
            table: Table name
            columns: List of column names to validate
            
        Returns:
            Dictionary mapping column names to validation status (True/False)
        """
        table_schema = self.get_table_schema(catalog, schema, table)
        
        if not table_schema:
            return {col: False for col in columns}
        
        # Extract column names from schema (case-insensitive comparison)
        schema_columns = set()
        if "columns" in table_schema:
            for col in table_schema["columns"]:
                schema_columns.add(col["name"].lower())
        
        # Validate each column
        results = {}
        for col in columns:
            results[col] = col.lower() in schema_columns
        
        return results
    
    def extract_columns_from_sql(self, sql: str, alias_map: Dict[str, str]) -> Set[str]:
        """
        Extract column references from SQL expressions.
        
        Args:
            sql: SQL query or expression
            alias_map: Mapping of table aliases to full table names (e.g., {"t": "catalog.schema.transactions"})
            
        Returns:
            Set of fully-qualified column references (table_name.column_name)
        """
        columns = set()
        
        # Pattern to match table_alias.column_name references
        # Matches: t.customer_id, a.product_name, etc.
        pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\b'
        
        for match in re.finditer(pattern, sql):
            alias = match.group(1)
            column = match.group(2)
            
            # Skip SQL keywords and functions
            sql_keywords = {
                "current_date", "current_timestamp", "date_trunc", "date_add",
                "count", "sum", "avg", "min", "max", "try_divide"
            }
            if alias.lower() in sql_keywords or column.lower() in sql_keywords:
                continue
            
            # Resolve alias to full table name
            if alias in alias_map:
                full_table = alias_map[alias]
                columns.add(f"{full_table}.{column}")
        
        return columns
    
    def validate_tables_only(self, config_path: str) -> ValidationReport:
        """
        Simplified validation: only check if tables exist in Unity Catalog.
        Does not validate columns.

        Args:
            config_path: Path to the Genie space configuration JSON file

        Returns:
            ValidationReport containing table existence results
        """
        report = ValidationReport()

        # Load configuration
        config_file = Path(config_path)
        if not config_file.exists():
            report.add_issue(
                severity="error",
                type="config_not_found",
                message=f"Configuration file not found: {config_path}"
            )
            return report

        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # Extract genie_space_config
        if "genie_space_config" in config:
            genie_config = config["genie_space_config"]
        else:
            genie_config = config

        # Get all unique tables from the configuration
        tables_to_check = set()

        # 1. Tables from table definitions
        for table_def in genie_config.get("tables", []):
            catalog = table_def.get("catalog_name")
            schema = table_def.get("schema_name")
            table = table_def.get("table_name")
            if catalog and schema and table:
                tables_to_check.add((catalog, schema, table))

        # 2. Tables from join specifications
        for join_spec in genie_config.get("join_specifications", []):
            for table_key in ["left_table", "right_table"]:
                full_name = join_spec.get(table_key, "")
                parts = full_name.split(".")
                if len(parts) == 3:
                    tables_to_check.add(tuple(parts))

        # Validate each unique table
        for catalog, schema, table in tables_to_check:
            full_name = f"{catalog}.{schema}.{table}"
            report.tables_checked.append(full_name)

            # Check if table exists
            table_exists = self.validate_table(catalog, schema, table)

            if table_exists:
                report.tables_valid.append(full_name)
            else:
                report.tables_invalid.append(full_name)
                report.add_issue(
                    severity="error",
                    type="table_not_found",
                    message=f"Table does not exist or is not accessible: {full_name}",
                    table=full_name,
                    location="table_definitions"
                )

        return report

    def validate_config(self, config_path: str) -> ValidationReport:
        """
        Validate all tables and columns in a Genie space configuration.

        This includes validation of:
        - Table definitions in the 'tables' section
        - Tables referenced in SQL expressions
        - Tables referenced in example SQL queries
        - Tables referenced in benchmark questions

        Args:
            config_path: Path to the Genie space configuration JSON file

        Returns:
            ValidationReport containing all validation results and issues
        """
        report = ValidationReport()
        
        # Load configuration
        config_file = Path(config_path)
        if not config_file.exists():
            report.add_issue(
                severity="error",
                type="config_not_found",
                message=f"Configuration file not found: {config_path}"
            )
            return report
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Extract genie_space_config
        if "genie_space_config" in config:
            genie_config = config["genie_space_config"]
        else:
            genie_config = config
        
        # Validate tables
        tables = genie_config.get("tables", [])
        table_map = {}  # Maps catalog.schema.table to table info
        
        report.add_issue(
            severity="info",
            type="validation_start",
            message=f"Validating {len(tables)} tables from configuration"
        )
        
        for table_def in tables:
            catalog = table_def.get("catalog_name")
            schema = table_def.get("schema_name")
            table = table_def.get("table_name")
            
            if not all([catalog, schema, table]):
                report.add_issue(
                    severity="error",
                    type="incomplete_table_definition",
                    message="Table definition missing catalog_name, schema_name, or table_name",
                    location="tables"
                )
                continue
            
            full_name = f"{catalog}.{schema}.{table}"
            report.tables_checked.append(full_name)
            table_map[full_name] = table_def
            
            # Validate table exists
            if self.validate_table(catalog, schema, table):
                report.tables_valid.append(full_name)
                report.add_issue(
                    severity="info",
                    type="table_valid",
                    message=f"Table exists and is accessible",
                    table=full_name
                )
            else:
                report.tables_invalid.append(full_name)
                report.add_issue(
                    severity="error",
                    type="table_not_found",
                    message=f"Table does not exist or is not accessible",
                    table=full_name,
                    location="tables"
                )
        
        # Extract and validate columns from SQL snippets
        self._validate_sql_snippets(genie_config, table_map, report)
        self._validate_example_queries(genie_config, table_map, report)
        self._validate_benchmark_queries(genie_config, table_map, report)

        # Validate join specifications
        self._validate_join_specifications(genie_config, report)

        return report

    def _validate_join_specifications(
        self,
        genie_config: Dict[str, Any],
        report: ValidationReport
    ):
        """Validate join specifications for invalid self-joins."""
        join_specifications = genie_config.get("join_specifications", [])

        if not join_specifications:
            return

        report.add_issue(
            severity="info",
            type="validation_section",
            message=f"Validating {len(join_specifications)} join specifications"
        )

        for i, join_spec in enumerate(join_specifications):
            left_table = join_spec.get("left_table", "")
            right_table = join_spec.get("right_table", "")
            join_condition = join_spec.get("join_condition", "")

            # Check for self-joins
            if left_table == right_table:
                # Parse the join condition to check if it's invalid
                if "=" in join_condition:
                    parts = [p.strip() for p in join_condition.split("=")]

                    if len(parts) == 2:
                        left_expr = parts[0]
                        right_expr = parts[1]

                        # Check if both sides are identical (tautology)
                        if left_expr == right_expr:
                            report.add_issue(
                                severity="error",
                                type="invalid_self_join",
                                message=f"Invalid self-join with tautological condition: {join_condition}",
                                table=left_table,
                                location=f"join_specifications[{i}]"
                            )
                            continue

                        # Check if both sides reference the same column (likely invalid)
                        left_col = left_expr.split(".")[-1]
                        right_col = right_expr.split(".")[-1]

                        if left_col == right_col:
                            report.add_issue(
                                severity="warning",
                                type="suspicious_self_join",
                                message=f"Suspicious self-join on same column '{left_col}': {join_condition}. "
                                        f"Self-joins should typically compare different columns.",
                                table=left_table,
                                location=f"join_specifications[{i}]"
                            )
                else:
                    report.add_issue(
                        severity="error",
                        type="invalid_join_condition",
                        message=f"Join condition must contain '=': {join_condition}",
                        table=left_table,
                        location=f"join_specifications[{i}]"
                    )

    def _validate_sql_snippets(
        self,
        genie_config: Dict[str, Any],
        table_map: Dict[str, Any],
        report: ValidationReport
    ):
        """Validate columns referenced in sql_snippets (filters, expressions, measures)."""
        sql_snippets = genie_config.get("sql_snippets", {})
        
        if not sql_snippets:
            return
        
        # Build alias map from table definitions
        alias_map = self._build_alias_map(genie_config)
        
        # Validate filters
        filters = sql_snippets.get("filters", [])
        if filters:
            report.add_issue(
                severity="info",
                type="validation_section",
                message=f"Validating columns in {len(filters)} SQL filters"
            )
            for filt in filters:
                display_name = filt.get("display_name", "unnamed")
                sql = filt.get("sql", "")
                self._validate_sql_string(sql, display_name, "sql_snippets.filters", alias_map, table_map, report)
        
        # Validate expressions (dimensions)
        expressions = sql_snippets.get("expressions", [])
        if expressions:
            report.add_issue(
                severity="info",
                type="validation_section",
                message=f"Validating columns in {len(expressions)} SQL expressions"
            )
            for expr in expressions:
                alias = expr.get("alias", "unnamed")
                sql = expr.get("sql", "")
                self._validate_sql_string(sql, alias, "sql_snippets.expressions", alias_map, table_map, report)
        
        # Validate measures (aggregations)
        measures = sql_snippets.get("measures", [])
        if measures:
            report.add_issue(
                severity="info",
                type="validation_section",
                message=f"Validating columns in {len(measures)} SQL measures"
            )
            for measure in measures:
                alias = measure.get("alias", "unnamed")
                sql = measure.get("sql", "")
                self._validate_sql_string(sql, alias, "sql_snippets.measures", alias_map, table_map, report)
    
    def _validate_sql_string(
        self,
        sql: str,
        name: str,
        location_prefix: str,
        alias_map: Dict[str, str],
        table_map: Dict[str, Any],
        report: ValidationReport
    ):
        """Helper method to validate a SQL string."""
        if not sql:
            return
        
        # Extract column references
        columns = self.extract_columns_from_sql(sql, alias_map)
        
        for col_ref in columns:
            # Parse table.column
            if '.' in col_ref:
                parts = col_ref.rsplit('.', 1)
                full_table = parts[0]
                column = parts[1]
                
                # Parse table name
                table_parts = full_table.split('.')
                if len(table_parts) == 3:
                    catalog, schema, table = table_parts
                    
                    # Track column check
                    if full_table not in report.columns_checked:
                        report.columns_checked[full_table] = []
                    if column not in report.columns_checked[full_table]:
                        report.columns_checked[full_table].append(column)
                    
                    # Validate column
                    if full_table in report.tables_valid:
                        col_results = self.validate_columns(catalog, schema, table, [column])
                        
                        if col_results.get(column, False):
                            if full_table not in report.columns_valid:
                                report.columns_valid[full_table] = []
                            if column not in report.columns_valid[full_table]:
                                report.columns_valid[full_table].append(column)
                        else:
                            if full_table not in report.columns_invalid:
                                report.columns_invalid[full_table] = []
                            if column not in report.columns_invalid[full_table]:
                                report.columns_invalid[full_table].append(column)
                            
                            report.add_issue(
                                severity="error",
                                type="column_not_found",
                                message=f"Column not found in table",
                                table=full_table,
                                column=column,
                                location=f"{location_prefix}[{name}]"
                            )
    
    def _validate_example_queries(
        self,
        genie_config: Dict[str, Any],
        table_map: Dict[str, Any],
        report: ValidationReport
    ):
        """Validate columns referenced in example_sql_queries."""
        example_queries = genie_config.get("example_sql_queries", [])
        
        if not example_queries:
            return
        
        report.add_issue(
            severity="info",
            type="validation_section",
            message=f"Validating columns in {len(example_queries)} example queries"
        )
        
        # Note: Full SQL parsing is complex, so we'll do basic validation
        # In a production system, you might want to use a SQL parser library
        for i, query_def in enumerate(example_queries):
            question = query_def.get("question", f"Query {i+1}")
            sql_query = query_def.get("sql_query", "")
            
            # Extract table names from FROM and JOIN clauses
            tables_in_query = self._extract_tables_from_sql(sql_query)
            
            for table_ref in tables_in_query:
                if table_ref not in report.tables_valid:
                    report.add_issue(
                        severity="warning",
                        type="table_reference_invalid",
                        message=f"Query references table that failed validation",
                        table=table_ref,
                        location=f"example_sql_queries[{question[:50]}...]"
                    )
    
    def _validate_benchmark_queries(
        self,
        genie_config: Dict[str, Any],
        table_map: Dict[str, Any],
        report: ValidationReport
    ):
        """Validate tables referenced in benchmark_questions."""
        benchmark_questions = genie_config.get("benchmark_questions", [])

        if not benchmark_questions:
            return

        report.add_issue(
            severity="info",
            type="validation_section",
            message=f"Validating tables in {len(benchmark_questions)} benchmark questions"
        )

        for i, benchmark in enumerate(benchmark_questions):
            question = benchmark.get("question", f"Benchmark {i+1}")
            expected_sql = benchmark.get("expected_sql", "")

            if not expected_sql:
                continue

            # Extract table names from the SQL query
            tables_in_query = self._extract_tables_from_sql(expected_sql)

            for table_ref in tables_in_query:
                if table_ref not in report.tables_valid:
                    report.add_issue(
                        severity="warning",
                        type="table_reference_invalid",
                        message=f"Benchmark question references table that failed validation",
                        table=table_ref,
                        location=f"benchmark_questions[{question[:50]}...]"
                    )

    def _build_alias_map(self, genie_config: Dict[str, Any]) -> Dict[str, str]:
        """Build a map of common table aliases to full table names."""
        alias_map = {}
        
        tables = genie_config.get("tables", [])
        for table_def in tables:
            catalog = table_def.get("catalog_name")
            schema = table_def.get("schema_name")
            table = table_def.get("table_name")
            
            if all([catalog, schema, table]):
                full_name = f"{catalog}.{schema}.{table}"
                
                # Use first letter as alias (common convention: transactions -> t, articles -> a)
                alias = table[0].lower()
                alias_map[alias] = full_name
                
                # Also map common aliases
                if table == "transactions":
                    alias_map["t"] = full_name
                elif table == "articles":
                    alias_map["a"] = full_name
                elif table == "customers":
                    alias_map["c"] = full_name
                elif table == "customer_demographics":
                    alias_map["d"] = full_name
                elif table == "category_insights":
                    alias_map["ci"] = full_name
        
        return alias_map
    
    def _extract_tables_from_sql(self, sql: str) -> Set[str]:
        """Extract full table names from SQL query."""
        tables = set()

        # Pattern to match catalog.schema.table references with optional backticks
        # Matches: catalog.schema.table or `catalog`.`schema`.`table` or mixed
        pattern = r'`?([a-zA-Z_][a-zA-Z0-9_]*)`?\.`?([a-zA-Z_][a-zA-Z0-9_]*)`?\.`?([a-zA-Z_][a-zA-Z0-9_]*)`?'

        for match in re.finditer(pattern, sql):
            # Combine the three parts (catalog, schema, table) without backticks
            full_name = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
            tables.add(full_name)

        return tables


def main():
    """Example usage and CLI interface."""
    import sys
    from dotenv import load_dotenv
    
    # Load environment variables
    load_dotenv()
    
    # Default config path
    config_path = "output/genie_space_config.json"
    
    # Allow custom path from command line
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    
    print("=" * 80)
    print("TABLE & COLUMN VALIDATOR")
    print("=" * 80)
    print()
    print(f"Configuration: {config_path}")
    print()
    
    try:
        # Initialize validator
        validator = TableValidator()
        
        # Run validation
        print("Running validation...")
        print()
        report = validator.validate_config(config_path)
        
        # Print report
        print(report.summary())
        
        # Exit with appropriate code
        sys.exit(1 if report.has_errors() else 0)
        
    except Exception as e:
        print(f"✗ Validation failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
