"""D1.5 Retry with exponential backoff."""
from __future__ import annotations

import functools
import random
import time
from collections.abc import Callable
from datetime import timedelta

TRANSIENT = (ConnectionError, TimeoutError)


class RetryExhausted(Exception):
    def __init__(self, attempts: int, elapsed: timedelta):
        super().__init__(f"gave up after {attempts} attempts in {elapsed.total_seconds():.2f}s")
        self.attempts = attempts
        self.elapsed = elapsed


def retry(max_attempts: int = 5, base: float = 0.5, jitter: float = 0.1,
          transient: tuple[type[BaseException], ...] = TRANSIENT,
          sleep: Callable[[float], None] = time.sleep,
          clock: Callable[[], float] = time.monotonic,
          rand: Callable[[float, float], float] = random.uniform):
    """Retry `transient` errors; anything else propagates immediately."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = clock()
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except transient as exc:
                    last = exc
                    if attempt + 1 < max_attempts:
                        sleep(base * 2 ** attempt + rand(0, jitter))
            elapsed = timedelta(seconds=clock() - start)
            raise RetryExhausted(max_attempts, elapsed) from last
        return wrapper
    return decorator


def flaky_source(rng: random.Random = random.Random()) -> list[dict]:
    """Stand-in for the provided flaky source."""
    roll = rng.random()
    if roll < 0.3:
        raise ConnectionError("connection reset")
    if roll < 0.5:
        raise TimeoutError("read timed out")
    if roll < 0.55:
        raise ValueError("bad request")
    return [{"id": 1}]


if __name__ == "__main__":
    print(retry(base=0.1)(flaky_source)())
