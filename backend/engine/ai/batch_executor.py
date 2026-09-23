"""
Batch LLM Executor with Rate Limiting.
Processes per-row LLM calls concurrently with configurable rate limits,
retry logic with exponential backoff, and ordered result accumulation.
"""
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Any, Callable, Optional

from .provider_base import LLMProvider, LLMConfig, LLMResponse


class TokenBucketRateLimiter:
    """Token bucket rate limiter for controlling requests per second."""

    def __init__(self, rate: float, capacity: float = None):
        """
        Args:
            rate: Tokens added per second (requests per second).
            capacity: Maximum burst capacity. Defaults to rate.
        """
        self.rate = max(rate, 0.1)
        self.capacity = capacity if capacity is not None else self.rate
        self.tokens = self.capacity
        self.last_update = time.monotonic()
        self.lock = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        """Attempt to consume tokens without blocking. Returns True if consumed, False otherwise."""
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def acquire(self, tokens: int = 1):
        """Block until the requested number of tokens are available."""
        while not self.consume(tokens):
            time.sleep(0.02)


def _make_error_response(error_msg: str, model: str, on_error: str) -> LLMResponse:
    """Create an LLMResponse representing a failed row."""
    return LLMResponse(
        text="" if on_error == "null" else f"[ERROR] {error_msg}",
        input_tokens=0,
        output_tokens=0,
        model=model,
        latency_ms=0.0,
        error=error_msg,
    )


def batch_execute(
    provider: LLMProvider,
    system_prompt: str,
    prompts: List[str],
    llm_config: LLMConfig,
    concurrency: int = 3,
    rate_limit_rps: float = 10.0,
    max_retries: int = 2,
    on_error: str = "null",
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> List[LLMResponse]:
    """
    Execute LLM calls for all prompts with concurrency and rate limiting.

    Args:
        provider: The LLM provider to use.
        system_prompt: System prompt shared across all rows.
        prompts: List of user prompts (one per row).
        llm_config: LLM configuration (model, temperature, etc.).
        concurrency: Max parallel requests.
        rate_limit_rps: Max requests per second.
        max_retries: Retry count on failure per row.
        on_error: 'null' (empty text), 'error_message' (error in text), 'stop' (raise).
        progress_callback: Called as (completed, total) after each row.

    Returns:
        List of LLMResponse objects in the same order as prompts.
    """
    total = len(prompts)
    if total == 0:
        return []

    results: List[Optional[LLMResponse]] = [None] * total
    rate_limiter = TokenBucketRateLimiter(rate=rate_limit_rps)
    completed_count = 0
    count_lock = threading.Lock()

    def process_row(idx: int, prompt: str) -> tuple:
        """Process a single row with retries and rate limiting."""
        nonlocal completed_count

        last_error = None
        for attempt in range(max_retries + 1):
            rate_limiter.acquire()
            try:
                response = provider.generate(system_prompt, prompt, llm_config)
                # If the provider returned an error response, retry
                if response.error and attempt < max_retries:
                    last_error = response.error
                    time.sleep(1.0 * (2 ** attempt))  # 1s, 2s, 4s
                    continue
                return idx, response
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    time.sleep(1.0 * (2 ** attempt))
                    continue

                if on_error == "stop":
                    raise

                return idx, _make_error_response(last_error, llm_config.model, on_error)

        # All retries exhausted — should not reach here normally but safety net
        return idx, _make_error_response(
            last_error or "Unknown error after retries",
            llm_config.model,
            on_error,
        )

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {
            pool.submit(process_row, i, p): i for i, p in enumerate(prompts)
        }
        for future in as_completed(futures):
            idx, response = future.result()
            results[idx] = response
            with count_lock:
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count, total)

    return results
