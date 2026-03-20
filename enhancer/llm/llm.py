"""
Databricks LLM Client

Wrapper for Databricks Foundation Models API for LLM inference.
"""

import requests
import logging
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabricksLLMClient:
    """Client for Databricks Foundation Models API."""

    def __init__(
        self,
        host: str,
        token: str,
        endpoint_name: str = "databricks-gpt-5-2",
        request_delay: float = 5.0,
        rate_limit_base_delay: float = 60.0
    ):
        """
        Initialize Databricks LLM client.

        Args:
            host: Databricks workspace host
            token: Personal access token or service principal token
            endpoint_name: Name of the serving endpoint
                Common options:
                - databricks-gpt-5-2 (recommended)
                - databricks-meta-llama-3-1-70b-instruct
                - databricks-meta-llama-3-1-405b-instruct
            request_delay: Delay in seconds between requests (default 5s)
            rate_limit_base_delay: Base delay for rate limit retries (default 60s)
        """
        self.host = host.replace("https://", "").replace("http://", "")
        self.endpoint_name = endpoint_name
        self.base_url = f"https://{self.host}/serving-endpoints/{endpoint_name}/invocations"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        self.request_delay = request_delay
        self.rate_limit_base_delay = rate_limit_base_delay
        self._last_request_time = 0

    def generate(
        self,
        prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 4000,
        top_p: float = 0.95,
        retry_count: int = 5
    ) -> str:
        """
        Generate text using Databricks Foundation Model.

        Args:
            prompt: Input prompt
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            retry_count: Number of retries on failure (default 5 for rate limits)

        Returns:
            Generated text
        """
        import time

        # Throttle requests - wait if needed since last request
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_delay and self._last_request_time > 0:
            wait_time = self.request_delay - elapsed
            logger.debug(f"Throttling: waiting {wait_time:.1f}s before request")
            time.sleep(wait_time)

        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p
        }

        last_error = None

        for attempt in range(retry_count):
            try:
                logger.debug(f"LLM request (attempt {attempt + 1}/{retry_count})")
                self._last_request_time = time.time()

                response = requests.post(
                    self.base_url,
                    headers=self.headers,
                    json=payload,
                    timeout=180  # 3 minute timeout for large prompts
                )

                response.raise_for_status()
                result = response.json()

                # Extract generated text
                # Format: {"choices": [{"message": {"content": "..."}}]}
                generated_text = result["choices"][0]["message"]["content"]

                logger.debug(f"LLM response received ({len(generated_text)} chars)")
                return generated_text

            except requests.exceptions.Timeout:
                last_error = "Request timed out"
                logger.warning(f"LLM request timed out (attempt {attempt + 1})")
                if attempt < retry_count - 1:
                    continue
                else:
                    raise TimeoutError(f"LLM request timed out after {retry_count} attempts")

            except requests.exceptions.RequestException as e:
                last_error = str(e)
                logger.error(f"LLM request failed: {e}")

                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Response status: {e.response.status_code}")
                    logger.error(f"Response body: {e.response.text[:500]}")

                if attempt < retry_count - 1:
                    # Retry on server errors (5xx) and rate limits (429)
                    if hasattr(e, 'response') and e.response is not None:
                        status_code = e.response.status_code
                        if status_code in [429, 500, 502, 503, 504]:
                            # Exponential backoff: 60s, 120s, 240s, 480s (for rate limits)
                            wait_time = self.rate_limit_base_delay * (2 ** attempt)
                            logger.info(f"Rate limit/error {status_code}, retrying in {wait_time:.0f}s... (attempt {attempt + 1}/{retry_count})")
                            time.sleep(wait_time)
                            continue

                raise RuntimeError(f"LLM request failed: {last_error}")

        raise RuntimeError(f"LLM request failed after {retry_count} attempts: {last_error}")

    def test_connection(self) -> bool:
        """
        Test connection to LLM endpoint.

        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.generate(
                prompt="Say 'Hello, Genie!' and nothing else.",
                temperature=0.0,
                max_tokens=10
            )
            logger.info(f"LLM connection test successful: {response[:50]}")
            return True
        except Exception as e:
            logger.error(f"LLM connection test failed: {e}")
            return False


# Example usage
if __name__ == "__main__":
    import os

    HOST = os.getenv("DATABRICKS_HOST", "your-workspace.cloud.databricks.com")
    TOKEN = os.getenv("DATABRICKS_TOKEN", "your-token")
    ENDPOINT = os.getenv("LLM_ENDPOINT", "databricks-gpt-5-2")

    print("Testing Databricks LLM Client")
    print("=" * 60)

    client = DatabricksLLMClient(HOST, TOKEN, ENDPOINT)

    # Test connection
    print("\n1. Testing connection...")
    if client.test_connection():
        print("✅ Connection successful!")
    else:
        print("❌ Connection failed!")
        exit(1)

    # Test JSON generation
    print("\n2. Testing JSON generation...")
    prompt = """
Generate a JSON object representing a person with name, age, and hobbies.
Return ONLY the JSON, no other text.
"""

    response = client.generate(prompt, temperature=0.1, max_tokens=200)
    print(f"Response:\n{response}")

    # Check if valid JSON
    import json
    try:
        parsed = json.loads(response)
        print("✅ Valid JSON!")
        print(f"Parsed: {parsed}")
    except json.JSONDecodeError:
        print("❌ Not valid JSON")

    print("\n" + "=" * 60)
    print("All tests complete!")
