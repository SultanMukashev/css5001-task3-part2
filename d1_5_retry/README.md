# D1.5 Retry with exponential backoff

```python
@retry(max_attempts=5, base=0.5, jitter=0.1, sleep=time.sleep)
def fetch(): ...
```

- Retries only `ConnectionError` and `TimeoutError` (configurable via `transient=`). `ValueError` and
  anything else propagate immediately — retrying a bad request can never fix it.
- Delay before retry *n* (0-based): `base * 2**n + uniform(0, jitter)`. No sleep after the last attempt.
- When attempts run out: `RetryExhausted(attempts, elapsed: timedelta)` raised `from` the last error, so the
  root cause stays in the traceback (`__cause__`).
- `sleep`, `clock` and `rand` are injectable → tests run instantly and deterministically.
- `flaky_source()` is a stand-in for the provided one.

Known limit: no cap on a single delay (`max_delay`); with large `max_attempts` delays grow quickly.
