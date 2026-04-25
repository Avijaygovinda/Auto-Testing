"""
Retry wrapper for Gemini calls.

Free-tier traffic regularly bounces back 503 (overloaded) or 429 (quota).
Both are transient — exponential backoff resolves the bulk of them.
"""
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def call_with_retry(fn: Callable[[], T], *, max_attempts: int = 4, base_wait: float = 5.0,
                    label: str = "gemini") -> T:
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last_err = e
            wait = base_wait * (2 ** attempt)  # 5, 10, 20, 40
            print(f"[{label}] API error '{type(e).__name__}', retry in {wait:.0f}s "
                  f"(attempt {attempt + 1}/{max_attempts})")
            time.sleep(wait)
    raise RuntimeError(f"[{label}] failed after {max_attempts} attempts: {last_err}")
