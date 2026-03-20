"""
Batch Genie Client - Concurrent API calls with retry and rate limiting.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class BatchGenieClient:
    """Batch Genie API caller with concurrency control and retry."""

    def __init__(
        self,
        genie_client,
        config: Optional[Dict] = None,
        progress_callback=None
    ):
        self.genie_client = genie_client
        self.config = config or {}
        self.progress_callback = progress_callback

        # Config
        self.max_concurrent = self.config.get("max_concurrent", 3)
        self.retry_attempts = self.config.get("retry_attempts", 2)
        self.retry_delay = self.config.get("retry_delay", 5)
        self.query_timeout = self.config.get("query_timeout", 120)

        # Shared state for real-time progress (reset per batch)
        self._completed = 0
        self._successful = 0
        self._total = 0
        self._lock = None  # Created per batch call

        logger.info(f"BatchGenieClient: max_concurrent={self.max_concurrent}")

    async def batch_ask(self, benchmarks: List[Dict]) -> List[Dict]:
        """Ask Genie multiple questions concurrently with real-time progress."""
        self._total = len(benchmarks)
        self._completed = 0
        self._successful = 0
        self._lock = asyncio.Lock()

        logger.info(f"Starting batch Genie calls for {self._total} questions")
        start_time = time.time()

        # Semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def ask_with_semaphore(idx: int, benchmark: Dict) -> Dict:
            async with semaphore:
                return await self._ask_single(idx, benchmark)

        # Run all concurrently
        tasks = [ask_with_semaphore(i, b) for i, b in enumerate(benchmarks)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any unhandled exceptions
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append({
                    "benchmark_id": benchmarks[i].get("id", f"benchmark_{i}"),
                    "question": benchmarks[i]["question"],
                    "success": False,
                    "response": None,
                    "error": str(result),
                    "attempts": 1,
                    "duration": 0
                })
            else:
                processed.append(result)

        duration = time.time() - start_time
        success_count = sum(1 for r in processed if r["success"])
        logger.info(f"Batch complete: {success_count}/{self._total} in {duration:.1f}s")

        return processed

    async def _ask_single(self, index: int, benchmark: Dict) -> Dict:
        """Ask Genie with retry, emit progress immediately on completion."""
        benchmark_id = benchmark.get("id", f"benchmark_{index}")
        question = benchmark["question"]
        error = None

        # Retry loop
        for attempt in range(1, self.retry_attempts + 1):
            try:
                start_time = time.time()

                # Call Genie with timeout
                response = await asyncio.wait_for(
                    self._call_genie_async(question),
                    timeout=self.query_timeout
                )

                duration = time.time() - start_time
                logger.info(f"[{index}] ✅ Success in {duration:.1f}s")

                result = {
                    "benchmark_id": benchmark_id,
                    "question": question,
                    "success": True,
                    "response": response,
                    "error": None,
                    "attempts": attempt,
                    "duration": duration
                }

                # Emit progress immediately
                await self._emit_progress(True)
                return result

            except asyncio.TimeoutError:
                error = f"Timeout after {self.query_timeout}s"
                logger.warning(f"[{index}] ⏱️ {error} (attempt {attempt})")

            except Exception as e:
                error = str(e)
                logger.warning(f"[{index}] ❌ {error} (attempt {attempt})")

            # Retry with backoff
            if attempt < self.retry_attempts:
                delay = self.retry_delay * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

        # All attempts failed
        logger.error(f"[{index}] ❌ Failed after {self.retry_attempts} attempts")

        result = {
            "benchmark_id": benchmark_id,
            "question": question,
            "success": False,
            "response": None,
            "error": error,
            "attempts": self.retry_attempts,
            "duration": 0
        }

        # Emit progress immediately
        await self._emit_progress(False)
        return result

    async def _emit_progress(self, success: bool):
        """Emit progress event immediately when a query completes."""
        async with self._lock:
            self._completed += 1
            if success:
                self._successful += 1

            if self.progress_callback:
                event = {
                    "event_type": "progress",
                    "phase": "genie",
                    "completed": self._completed,
                    "successful": self._successful,
                    "failed": self._completed - self._successful,
                    "total": self._total,
                    "message": f"Querying Genie: {self._completed}/{self._total}"
                }
                try:
                    self.progress_callback(event)
                except Exception as e:
                    logger.error(f"Progress callback error: {e}")

    async def _call_genie_async(self, question: str) -> Dict:
        """Async wrapper for sync Genie client."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.genie_client.ask(question, timeout=self.query_timeout)
        )
