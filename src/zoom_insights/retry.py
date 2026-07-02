"""Retry logic with exponential backoff for transient failures."""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def with_retry(fn, *args, tries: int = 6, base_delay: int = 4, **kwargs) -> Any:
    """Retry a function call on transient errors with exponential backoff.

    Retries only on 429 (rate limit), 'rate' errors, or 'timeout' errors.
    Uses exponential backoff capped at 60 seconds.

    Args:
        fn: Callable to retry.
        *args: Positional arguments to pass to fn.
        tries: Number of attempts (default 6).
        base_delay: Initial delay in seconds (default 4).
        **kwargs: Keyword arguments to pass to fn.

    Returns:
        Result of calling fn(*args, **kwargs).

    Raises:
        Exception: If all retries exhausted or error is not retryable.
    """
    delay = base_delay

    for i in range(tries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = str(e).lower()
            is_last_try = i == tries - 1

            # Only retry on rate limit / timeout errors
            is_retryable = any(k in msg for k in ("429", "rate", "timeout"))

            if is_last_try or not is_retryable:
                raise

            # Wait before retry
            logger.warning(f"Retrying attempt {i+1}/{tries} after {delay}s: {e}")
            time.sleep(delay)
            delay = min(delay * 2, 60)
