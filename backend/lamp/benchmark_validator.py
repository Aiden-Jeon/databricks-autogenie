"""Benchmark query validation service.

Validates that benchmark SQL queries execute successfully against Unity Catalog.
"""

import time
import re
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from databricks import sql


def validate_benchmark_queries(
    benchmarks: List[Dict[str, Any]],
    databricks_server_hostname: str,
    databricks_http_path: str,
    databricks_token: str,
    limit_rows: int = 10,
    query_timeout: int = 30
) -> Dict[str, Any]:
    """Validate benchmark SQL queries by executing them against Unity Catalog.

    Args:
        benchmarks: List of benchmark dictionaries with 'question' and 'expected_sql' fields
        databricks_server_hostname: Databricks SQL warehouse hostname
        databricks_http_path: SQL warehouse HTTP path
        databricks_token: Databricks access token
        limit_rows: Maximum rows to fetch per query (default: 10)
        query_timeout: Timeout per query in seconds (default: 30)

    Returns:
        Dictionary with validation results
    """

    def add_limit_to_query(sql_query: str, limit: int) -> str:
        """Add LIMIT clause to SQL query if not already present."""
        sql_query = sql_query.rstrip().rstrip(';').rstrip()

        if re.search(r'\bLIMIT\s+\d+', sql_query, re.IGNORECASE):
            return sql_query

        if re.search(r'\b(ORDER BY|GROUP BY|HAVING)\b', sql_query, re.IGNORECASE):
            return f"SELECT * FROM ({sql_query}) AS subquery LIMIT {limit}"
        else:
            return f"{sql_query} LIMIT {limit}"

    def validate_single_query(connection, idx: int, benchmark: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a single benchmark query."""
        question = benchmark.get('question', benchmark.get('korean_question', ''))
        expected_sql = benchmark.get('expected_sql', '')

        if not expected_sql:
            return {
                "index": idx,
                "question": question,
                "sql": expected_sql,
                "status": "failed",
                "error": "No SQL query provided",
                "row_count": None,
                "execution_time_ms": None
            }

        limited_sql = add_limit_to_query(expected_sql, limit_rows)

        try:
            cursor = connection.cursor()
            start_time = time.time()

            cursor.execute(limited_sql)
            rows = cursor.fetchmany(limit_rows)
            execution_time = (time.time() - start_time) * 1000

            cursor.close()

            return {
                "index": idx,
                "question": question,
                "sql": expected_sql,
                "status": "passed",
                "error": None,
                "row_count": len(rows),
                "execution_time_ms": round(execution_time, 2)
            }

        except Exception as e:
            return {
                "index": idx,
                "question": question,
                "sql": expected_sql,
                "status": "failed",
                "error": str(e),
                "row_count": None,
                "execution_time_ms": None
            }

    results = []
    passed_count = 0
    failed_count = 0

    try:
        connection = sql.connect(
            server_hostname=databricks_server_hostname,
            http_path=databricks_http_path,
            access_token=databricks_token
        )

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for idx, benchmark in enumerate(benchmarks):
                future = executor.submit(validate_single_query, connection, idx, benchmark)
                futures.append(future)

            for future in futures:
                try:
                    result = future.result(timeout=query_timeout)
                    results.append(result)
                    if result["status"] == "passed":
                        passed_count += 1
                    else:
                        failed_count += 1
                except FuturesTimeoutError:
                    idx = len(results)
                    benchmark = benchmarks[idx] if idx < len(benchmarks) else {}
                    question = benchmark.get('question', benchmark.get('korean_question', ''))
                    expected_sql = benchmark.get('expected_sql', '')
                    results.append({
                        "index": idx,
                        "question": question,
                        "sql": expected_sql,
                        "status": "failed",
                        "error": f"Query timeout after {query_timeout} seconds",
                        "row_count": None,
                        "execution_time_ms": None
                    })
                    failed_count += 1

        connection.close()

    except Exception as e:
        for idx, benchmark in enumerate(benchmarks):
            question = benchmark.get('question', benchmark.get('korean_question', ''))
            expected_sql = benchmark.get('expected_sql', '')
            results.append({
                "index": idx,
                "question": question,
                "sql": expected_sql,
                "status": "failed",
                "error": f"Database connection error: {str(e)}",
                "row_count": None,
                "execution_time_ms": None
            })
        failed_count = len(benchmarks)

    results.sort(key=lambda x: x["index"])

    return {
        "has_errors": failed_count > 0,
        "total_benchmarks": len(benchmarks),
        "passed": passed_count,
        "failed": failed_count,
        "results": results
    }
