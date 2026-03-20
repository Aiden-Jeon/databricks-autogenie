"""
SQL Executor

Executes SQL queries on Databricks using the Databricks SDK.
"""

import time
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SQLExecutor:
    """Execute SQL queries on Databricks SQL Warehouse using SDK."""

    def __init__(self, host: str, token: str, warehouse_id: str):
        """
        Initialize SQL executor with Databricks SDK.

        Args:
            host: Databricks workspace host
            token: Personal access token
            warehouse_id: SQL Warehouse ID to execute queries on
        """
        import os
        from databricks.sdk import WorkspaceClient

        self.host = host.replace("https://", "").replace("http://", "")
        self.warehouse_id = warehouse_id

        # CRITICAL: Clear OAuth env vars to prevent conflict with PAT auth
        # Databricks Apps runtime may set these, but we want to use PAT
        saved_client_id = os.environ.pop('DATABRICKS_CLIENT_ID', None)
        saved_client_secret = os.environ.pop('DATABRICKS_CLIENT_SECRET', None)

        try:
            # Initialize SDK client with PAT only
            self.client = WorkspaceClient(
                host=f"https://{self.host}",
                token=token
            )
            logger.info(f"SQLExecutor initialized with SDK (warehouse: {warehouse_id})")
        finally:
            # Restore OAuth env vars
            if saved_client_id:
                os.environ['DATABRICKS_CLIENT_ID'] = saved_client_id
            if saved_client_secret:
                os.environ['DATABRICKS_CLIENT_SECRET'] = saved_client_secret

    def execute(
        self,
        sql: str,
        timeout: int = 120,
        wait_timeout: str = "50s"  # Databricks API only accepts 5-50 seconds
    ) -> Dict[str, Any]:
        """
        Execute SQL query using Databricks SDK and return results.

        Args:
            sql: SQL query to execute
            timeout: Not used directly (SDK handles timeout)
            wait_timeout: How long to wait for query completion

        Returns:
            {
                "status": "SUCCEEDED" | "FAILED" | "TIMEOUT",
                "result": {
                    "columns": List[str],
                    "rows": List[Dict],
                    "row_count": int
                } or None,
                "error": str or None,
                "execution_time": float
            }
        """
        from databricks.sdk.service.sql import StatementState

        logger.debug(f"Executing SQL: {sql[:100]}...")
        start_time = time.time()

        try:
            # Execute statement using SDK
            response = self.client.statement_execution.execute_statement(
                warehouse_id=self.warehouse_id,
                statement=sql,
                wait_timeout=wait_timeout
            )

            execution_time = time.time() - start_time
            state = response.status.state

            logger.debug(f"Statement state: {state}")

            if state == StatementState.SUCCEEDED:
                # Extract results
                result_data = self._extract_results_sdk(response)
                logger.debug(f"Query succeeded ({result_data['row_count']} rows, {execution_time:.2f}s)")

                return {
                    "status": "SUCCEEDED",
                    "result": result_data,
                    "error": None,
                    "execution_time": execution_time
                }

            elif state in [StatementState.FAILED, StatementState.CANCELED, StatementState.CLOSED]:
                error_message = response.status.error.message if response.status.error else "Unknown error"
                logger.warning(f"Query failed: {error_message}")

                return {
                    "status": "FAILED",
                    "result": None,
                    "error": error_message,
                    "execution_time": execution_time
                }

            else:
                # Still running or pending
                logger.warning(f"Query in unexpected state: {state}")
                return {
                    "status": "TIMEOUT",
                    "result": None,
                    "error": f"Query in state: {state}",
                    "execution_time": execution_time
                }

        except Exception as e:
            logger.error(f"SQL execution failed: {e}")
            return {
                "status": "FAILED",
                "result": None,
                "error": str(e),
                "execution_time": time.time() - start_time
            }

    def _extract_results_sdk(self, response) -> Dict:
        """
        Extract query results from SDK response.

        Args:
            response: SDK StatementResponse

        Returns:
            {
                "columns": List[str],
                "rows": List[Dict],
                "row_count": int
            }
        """
        # Get column names from manifest
        columns = []
        if response.manifest and response.manifest.schema and response.manifest.schema.columns:
            columns = [col.name for col in response.manifest.schema.columns]

        # Get data
        rows = []
        if response.result and response.result.data_array:
            for row_data in response.result.data_array:
                row_dict = {}
                for i, col_name in enumerate(columns):
                    row_dict[col_name] = row_data[i] if i < len(row_data) else None
                rows.append(row_dict)

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows)
        }


# Example usage
if __name__ == "__main__":
    import os

    HOST = os.getenv("DATABRICKS_HOST")
    TOKEN = os.getenv("DATABRICKS_TOKEN")
    WAREHOUSE_ID = os.getenv("WAREHOUSE_ID")

    executor = SQLExecutor(HOST, TOKEN, WAREHOUSE_ID)

    # Test query
    sql = """
    SELECT 'Hello' as greeting, 123 as number
    UNION ALL
    SELECT 'World', 456
    """

    result = executor.execute(sql)

    print(f"Status: {result['status']}")
    print(f"Execution time: {result['execution_time']:.2f}s")

    if result['status'] == 'SUCCEEDED':
        print(f"\nColumns: {result['result']['columns']}")
        print(f"Rows: {result['result']['row_count']}")
        print(f"\nData:")
        for row in result['result']['rows']:
            print(f"  {row}")
    else:
        print(f"Error: {result['error']}")
