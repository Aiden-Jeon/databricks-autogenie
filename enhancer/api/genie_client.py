"""
Genie Conversational API Client

Wrapper for Databricks Genie Conversational API to ask questions
and retrieve SQL/results.
"""

import requests
import time
import logging
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GenieConversationalClient:
    """Client for interacting with Genie Conversational API."""

    def __init__(self, host: str, token: str, space_id: str, verbose: bool = False):
        """
        Initialize Genie client.

        Args:
            host: Databricks workspace host (e.g., "company.cloud.databricks.com")
            token: Personal access token
            space_id: Genie Space ID
            verbose: If True, print debug info (useful for notebooks)
        """
        self.host = host.replace("https://", "").replace("http://", "").rstrip("/")
        self.base_url = f"https://{self.host}/api/2.0/genie/spaces/{space_id}"
        self.messages_base_url = f"https://{self.host}/api/2.0/genie/messages"
        # Track which API version this workspace supports (auto-detected on first call)
        self._use_legacy_api = None  # None = unknown, True = old, False = new
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        self.space_id = space_id
        self.verbose = verbose

    def _log(self, msg: str):
        """Print if verbose mode, otherwise log."""
        if self.verbose:
            print(msg)
        else:
            logger.info(msg)

    def _parse_start_response(self, raw: Dict) -> Dict:
        """Parse start-conversation response into a flat dict.

        Handles both old format (flat {conversation_id, message_id})
        and new format (nested {conversation: {...}, message: {...}}).
        """
        # New API: nested under conversation/message keys
        conversation = raw.get("conversation", {})
        message = raw.get("message", {})

        conv_id = (
            raw.get("conversation_id")
            or conversation.get("conversation_id")
            or conversation.get("id")
        )
        msg_id = (
            raw.get("message_id")
            or message.get("message_id")
            or message.get("id")
        )

        return {
            "conversation_id": conv_id,
            "message_id": msg_id,
            "status": message.get("status") or raw.get("status"),
        }

    def start_conversation(self, question: str, retry_count: int = 5) -> Dict:
        """
        Start a new conversation with a question.

        Tries the new endpoint first (POST /conversations), falls back to
        legacy (POST /start-conversation) if 404. Caches which one works.

        Args:
            question: Natural language question to ask Genie
            retry_count: Number of retries for rate limiting

        Returns:
            {
                "conversation_id": str,
                "message_id": str,
                ...
            }
        """
        payload = {"content": question}
        self._log(f"Starting conversation: {question[:100]}...")

        # Build URL list based on what we know
        if self._use_legacy_api is True:
            urls = [f"{self.base_url}/start-conversation"]
        elif self._use_legacy_api is False:
            urls = [f"{self.base_url}/conversations"]
        else:
            # Unknown — try new first, then legacy
            urls = [f"{self.base_url}/conversations", f"{self.base_url}/start-conversation"]

        for attempt in range(retry_count):
            for url in urls:
                try:
                    response = requests.post(url, headers=self.headers, json=payload)
                    if self.verbose:
                        print(f"  POST {url} -> {response.status_code}")

                    # 404 means this endpoint doesn't exist — try the other
                    if response.status_code == 404 and len(urls) > 1:
                        is_legacy = "/start-conversation" in url
                        self._log(f"{'Legacy' if is_legacy else 'New'} endpoint returned 404, trying other...")
                        continue

                    response.raise_for_status()
                    raw = response.json()
                    result = self._parse_start_response(raw)

                    # Cache which endpoint worked
                    self._use_legacy_api = "/start-conversation" in url
                    if self._use_legacy_api:
                        self._log("Using legacy Genie API (start-conversation)")
                    else:
                        self._log("Using new Genie API (conversations)")

                    self._log(f"Conversation started: {result.get('conversation_id')}")
                    return result

                except requests.exceptions.RequestException as e:
                    status_code = None
                    if hasattr(e, 'response') and e.response is not None:
                        status_code = e.response.status_code
                        if self.verbose:
                            print(f"  ERROR Response: {e.response.text[:500]}")

                    if status_code in [429, 500, 502, 503, 504]:
                        if attempt < retry_count - 1:
                            wait_time = (2 ** attempt) * 5
                            self._log(f"Error {status_code}, waiting {wait_time}s before retry...")
                            time.sleep(wait_time)
                            break  # Break url loop, retry from outer loop
                    self._log(f"Failed to start conversation: {e}")
                    raise
            else:
                # All URLs tried for this attempt, none worked with 404
                # This only happens when both return 404 — give up
                continue

    def get_message(self, conversation_id: str, message_id: str) -> Dict:
        """
        Get a message result.

        Tries new endpoint (GET /genie/messages/{mid}) first, falls back to
        legacy (GET /spaces/{sid}/conversations/{cid}/messages/{mid}).

        Args:
            conversation_id: Conversation ID (needed for legacy API)
            message_id: Message ID to retrieve

        Returns:
            Message result with status, SQL, and query results
        """
        if self._use_legacy_api is True:
            urls = [f"{self.base_url}/conversations/{conversation_id}/messages/{message_id}"]
        elif self._use_legacy_api is False:
            urls = [f"{self.messages_base_url}/{message_id}"]
        else:
            urls = [
                f"{self.messages_base_url}/{message_id}",
                f"{self.base_url}/conversations/{conversation_id}/messages/{message_id}",
            ]

        last_error = None
        for url in urls:
            try:
                response = requests.get(url, headers=self.headers)
                if response.status_code == 404 and len(urls) > 1:
                    continue
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                last_error = e
                if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
                    continue
                raise

        logger.error(f"Failed to get message: {last_error}")
        raise last_error

    def wait_for_completion(
        self,
        conversation_id: str,
        message_id: str,
        timeout: int = 300,
        poll_interval: int = 3
    ) -> Dict:
        """
        Poll until message is completed or timeout.

        Args:
            conversation_id: Conversation ID
            message_id: Message ID to poll
            timeout: Maximum seconds to wait
            poll_interval: Seconds between polls

        Returns:
            Completed message result

        Raises:
            TimeoutError: If message doesn't complete within timeout
        """
        start_time = time.time()
        poll_count = 0

        while time.time() - start_time < timeout:
            poll_count += 1
            result = self.get_message(conversation_id, message_id)
            status = result.get("status")

            if self.verbose:
                print(f"  Poll #{poll_count}: status={status}")

            if status == "COMPLETED":
                self._log(f"Message completed successfully")
                # Log EVERYTHING in the response
                self._log(f"Response keys: {list(result.keys())}")

                # Check attachments
                attachments = result.get("attachments") or []
                self._log(f"Attachments count: {len(attachments)}")
                for i, att in enumerate(attachments):
                    self._log(f"  Attachment {i}: keys={list(att.keys())}")
                    if att.get("query"):
                        self._log(f"    query keys: {list(att['query'].keys()) if isinstance(att['query'], dict) else 'not a dict'}")
                    if att.get("text"):
                        text = att.get("text")
                        if isinstance(text, dict):
                            self._log(f"    text keys: {list(text.keys())}")
                        else:
                            self._log(f"    text: {str(text)[:100]}")
                    if att.get("attachment_id"):
                        self._log(f"    attachment_id: {att.get('attachment_id')}")

                # Check query_result
                if result.get("query_result"):
                    self._log(f"Has query_result: keys={list(result['query_result'].keys()) if isinstance(result['query_result'], dict) else 'not a dict'}")

                # Check content/description
                if result.get("content"):
                    self._log(f"Content: {str(result.get('content'))[:200]}")
                if result.get("description"):
                    self._log(f"Description: {str(result.get('description'))[:200]}")

                return result
            elif status == "FAILED":
                self._log(f"Message failed: {result.get('error')}")
                if self.verbose:
                    import json
                    print(f"  FAILED response: {json.dumps(result, indent=2, default=str)[:1000]}")
                return result
            elif status in (
                "EXECUTING", "PENDING",
                "FETCHING_METADATA", "EXECUTING_QUERY", "QUERY_RESULT_EXPIRED",
                "ASKING_AI", "FILTERING_CONTEXT", "PENDING_WAREHOUSE", "SUBMITTED",
                "COMPILING", "RUNNING"
            ):
                # FETCHING_METADATA: Genie is fetching schema information
                # EXECUTING_QUERY: Query is being executed
                # ASKING_AI: Genie LLM is generating SQL
                # FILTERING_CONTEXT: Genie is filtering relevant context
                # PENDING_WAREHOUSE: Waiting for SQL warehouse
                # SUBMITTED/COMPILING/RUNNING: Query execution states
                if self.verbose and poll_count % 5 == 0:
                    print(f"  Still waiting... ({int(time.time() - start_time)}s elapsed)")
                time.sleep(poll_interval)
            elif status == "CANCELLED":
                self._log(f"Message was cancelled")
                return result
            else:
                self._log(f"Unknown status: {status}, treating as in-progress...")
                time.sleep(poll_interval)

        raise TimeoutError(
            f"Message {message_id} did not complete within {timeout}s"
        )

    def ask(
        self,
        question: str,
        timeout: int = 180
    ) -> Dict:
        """
        Complete flow: ask question and wait for answer.

        Flow:
        1. POST /conversations with question → get conversation_id, message_id
        2. Poll GET /genie/messages/{message_id} until status == COMPLETED
        3. Extract SQL and results from response

        Args:
            question: Natural language question
            timeout: Maximum seconds to wait for response

        Returns:
            {
                "question": str,
                "conversation_id": str,
                "message_id": str,
                "status": "COMPLETED" | "FAILED",
                "sql": str or None,
                "result": dict or None,
                "error": str or None,
                "response_time": float (seconds)
            }
        """
        start_time = time.time()

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"ASK: {question[:80]}...")
            print(f"{'='*60}")

        # Step 1: Start conversation with question
        start_result = self.start_conversation(question)
        conversation_id = start_result.get("conversation_id")
        message_id = start_result.get("message_id")

        # Wait for completion
        try:
            result = self.wait_for_completion(conversation_id, message_id, timeout)
        except TimeoutError as e:
            self._log(f"Timeout waiting for answer: {e}")
            return {
                "question": question,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "status": "TIMEOUT",
                "sql": None,
                "result": None,
                "error": str(e),
                "response_time": time.time() - start_time
            }

        # Extract relevant info
        sql = self._extract_sql(result)
        query_result = self._extract_result(result)
        error = self._extract_error(result)

        if self.verbose:
            print(f"\n--- EXTRACTION RESULTS ---")
            print(f"Status: {result.get('status')}")
            print(f"SQL found: {'Yes' if sql else 'No'}")
            if sql:
                print(f"SQL: {sql[:200]}...")
            print(f"Result found: {'Yes' if query_result else 'No'}")
            print(f"Error: {error}")
            print(f"Response time: {time.time() - start_time:.1f}s")
            print(f"{'='*60}\n")

        return {
            "question": question,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "status": result.get("status"),
            "sql": sql,
            "result": query_result,
            "error": error,
            "response_time": time.time() - start_time
        }

    def _extract_sql(self, result: Dict, verbose: bool = None) -> Optional[str]:
        """
        Extract SQL from message response.

        Looks in:
        1. attachments[].query.query (Genie API format)
        2. attachments[].query.body
        3. attachments[].query.statement
        4. query_result.statement_response
        5. Root level query/sql fields

        Args:
            result: Message result
            verbose: Override verbose setting

        Returns:
            SQL query string or None
        """
        _verbose = verbose if verbose is not None else self.verbose

        # Method 1: Check attachments
        attachments = result.get("attachments") or []

        if attachments and _verbose:
            print(f"  _extract_sql: checking {len(attachments)} attachments")

        for i, attachment in enumerate(attachments):
            # Check query field
            query = attachment.get("query")
            if query:
                if isinstance(query, dict):
                    if _verbose:
                        print(f"    Attachment {i} query keys: {list(query.keys())}")
                    # Try multiple possible keys where SQL might be stored
                    sql = (
                        query.get("query") or  # Genie API returns SQL in 'query' field
                        query.get("body") or
                        query.get("sql") or
                        query.get("statement")
                    )
                    if sql:
                        if _verbose:
                            print(f"    Found SQL in attachment {i}!")
                        if isinstance(sql, list):
                            return "".join(sql)
                        return sql
                elif isinstance(query, str):
                    return query

            # Check direct sql field
            if attachment.get("sql"):
                sql = attachment.get("sql")
                if isinstance(sql, list):
                    return "".join(sql)
                return sql

        # Method 2: Check query_result at root level
        query_result = result.get("query_result")
        if query_result:
            # query_result might contain the SQL directly or in nested fields
            if isinstance(query_result, dict):
                statement_response = query_result.get("statement_response", {})
                manifest = statement_response.get("manifest", {})
                if manifest.get("sql"):
                    return manifest.get("sql")
                # Check for SQL in statement
                statement = statement_response.get("statement", {})
                if statement.get("sql"):
                    return statement.get("sql")

        # Method 3: Check root level fields
        if result.get("sql"):
            return result.get("sql")

        if result.get("query"):
            query = result.get("query")
            if isinstance(query, dict):
                return query.get("body") or query.get("sql") or query.get("statement")
            return query

        return None

    def _extract_result(self, result: Dict) -> Optional[Dict]:
        """
        Extract query result from message attachments.

        Args:
            result: Message result

        Returns:
            Query result data or None
        """
        # Method 1: Check root level query_result
        root_result = result.get("query_result")
        if root_result and isinstance(root_result, dict):
            # If it has actual data (not just metadata)
            if root_result.get("data") or root_result.get("rows"):
                return root_result
            # Return metadata if that's all we have
            if root_result.get("row_count") is not None:
                return root_result

        # Method 2: Check attachments
        for attachment in result.get("attachments", []):
            # Check for QUERY_RESULT type
            if attachment.get("type") == "QUERY_RESULT":
                return attachment.get("data")

            # Check for query_result_metadata in query attachment
            query = attachment.get("query")
            if query and isinstance(query, dict):
                metadata = query.get("query_result_metadata")
                if metadata:
                    return metadata

        return None

    def _extract_error(self, result: Dict) -> Optional[str]:
        """
        Extract error message if present.

        Args:
            result: Message result

        Returns:
            Error message or None
        """
        if result.get("status") == "FAILED":
            error = result.get("error", {})
            if isinstance(error, dict):
                return error.get("message") or error.get("error") or str(error)
            return str(error) if error else "Unknown error"
        return None

    def ask_debug(self, question: str, timeout: int = 180) -> Dict:
        """
        Ask a question and return the FULL raw response for debugging.

        Args:
            question: Natural language question
            timeout: Maximum seconds to wait

        Returns:
            Full raw response dictionary
        """
        start_time = time.time()

        # Step 1: Start conversation with question
        start_result = self.start_conversation(question)
        conversation_id = start_result.get("conversation_id")
        message_id = start_result.get("message_id")

        logger.info(f"Debug: conv_id={conversation_id}, msg_id={message_id}")

        # Step 2: Wait for completion
        try:
            result = self.wait_for_completion(conversation_id, message_id, timeout)
        except TimeoutError as e:
            return {"error": str(e), "status": "TIMEOUT"}

        # Return full result for debugging
        attachments = result.get("attachments") or []
        result["_debug"] = {
            "question": question,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "response_time": time.time() - start_time,
            "start_result": start_result,
            "attachments_count": len(attachments),
            "attachments_summary": [
                {"keys": list(a.keys()), "has_query": "query" in a, "has_sql": "sql" in a}
                for a in attachments
            ]
        }

        return result


# Example usage
if __name__ == "__main__":
    import os
    import json

    print("=" * 60)
    print("GENIE API DEBUG - Step by Step")
    print("=" * 60)

    # Configuration
    HOST = os.getenv("DATABRICKS_HOST", "")
    TOKEN = os.getenv("DATABRICKS_TOKEN", "")
    SPACE_ID = os.getenv("GENIE_SPACE_ID", "")

    print("\n[1] CREDENTIALS CHECK")
    print(f"  HOST: {HOST[:30]}..." if HOST else "  HOST: NOT SET!")
    print(f"  TOKEN: {TOKEN[:10]}..." if TOKEN else "  TOKEN: NOT SET!")
    print(f"  SPACE_ID: {SPACE_ID}" if SPACE_ID else "  SPACE_ID: NOT SET!")

    if not all([HOST, TOKEN, SPACE_ID]):
        print("\nMissing credentials! Set environment variables:")
        print("  export DATABRICKS_HOST=your-workspace.cloud.databricks.com")
        print("  export DATABRICKS_TOKEN=your-token")
        print("  export GENIE_SPACE_ID=your-space-id")
        exit(1)

    # Create client
    client = GenieConversationalClient(HOST, TOKEN, SPACE_ID)
    print(f"\n  Base URL: {client.base_url}")

    # Step 1: Start conversation
    print("\n[2] STARTING CONVERSATION")
    question = "What are top 10 sales?"
    print(f"  Question: {question}")
    print(f"  POST {client.base_url}/conversations")

    try:
        start_result = client.start_conversation(question)
        print(f"\n  Raw start_result:")
        print(json.dumps(start_result, indent=4, default=str))

        conversation_id = start_result.get("conversation_id")
        message_id = start_result.get("message_id")
        print(f"\n  conversation_id: {conversation_id}")
        print(f"  message_id: {message_id}")

    except Exception as e:
        print(f"\n  ERROR: {type(e).__name__}: {e}")
        exit(1)

    # Step 2: Poll for completion
    print("\n[3] POLLING FOR COMPLETION")
    print(f"  GET {client.messages_base_url}/{message_id}")

    try:
        result = client.wait_for_completion(conversation_id, message_id, timeout=180)
        status = result.get("status")
        print(f"\n  Final status: {status}")

    except TimeoutError as e:
        print(f"\n  TIMEOUT: {e}")
        exit(1)
    except Exception as e:
        print(f"\n  ERROR: {type(e).__name__}: {e}")
        exit(1)

    # Step 3: Full response dump
    print("\n[4] FULL RESPONSE")
    print(json.dumps(result, indent=4, default=str))

    # Step 4: Parse key fields
    print("\n[5] KEY FIELDS ANALYSIS")
    print(f"  Top-level keys: {list(result.keys())}")

    attachments = result.get("attachments") or []
    print(f"  Attachments count: {len(attachments)}")

    for i, att in enumerate(attachments):
        print(f"\n  Attachment [{i}]:")
        print(f"    Keys: {list(att.keys())}")

        if "query" in att:
            query = att["query"]
            print(f"    query type: {type(query).__name__}")
            if isinstance(query, dict):
                print(f"    query keys: {list(query.keys())}")
                for k in ["body", "sql", "statement", "query"]:
                    if k in query:
                        val = query[k]
                        if val:
                            print(f"    query.{k}: {str(val)[:200]}...")

        if "query_result" in att:
            qr = att["query_result"]
            print(f"    query_result type: {type(qr).__name__}")
            if isinstance(qr, dict):
                print(f"    query_result keys: {list(qr.keys())}")

        if "text" in att:
            print(f"    text: {str(att['text'])[:200]}...")

    # Step 5: SQL extraction
    print("\n[6] SQL EXTRACTION")
    sql = client._extract_sql(result)
    if sql:
        print(f"  Found SQL:\n{sql}")
    else:
        print("  No SQL found!")

    # Step 6: Result extraction
    print("\n[7] RESULT EXTRACTION")
    query_result = client._extract_result(result)
    if query_result:
        print(f"  Found result: {json.dumps(query_result, indent=4, default=str)[:500]}...")
    else:
        print("  No result found!")

    print("\n" + "=" * 60)
    print("DEBUG COMPLETE")
    print("=" * 60)
