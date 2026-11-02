import pytest

from d1_5_retry.solution import RetryExhausted, retry


class Fake:
    """Raises the given errors in order, then returns 'ok'."""
    def __init__(self, *errors):
        self.errors, self.calls = list(errors), 0

    def __call__(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


def make(**kw):
    sleeps = []
    ticks = iter(range(100))
    deco = retry(sleep=sleeps.append, clock=lambda: next(ticks), rand=lambda a, b: b, **kw)
    return deco, sleeps


def test_succeeds_after_transient_errors():
    deco, sleeps = make(base=1, jitter=0.5)
    src = Fake(ConnectionError(), TimeoutError())
    assert deco(src)() == "ok"
    assert src.calls == 3
    assert sleeps == [1.5, 2.5]  # 1*2**0 + 0.5, 1*2**1 + 0.5


def test_value_error_not_retried():
    deco, sleeps = make()
    src = Fake(ValueError("bad request"))
    with pytest.raises(ValueError):
        deco(src)()
    assert src.calls == 1 and sleeps == []


def test_exhausted_is_chained():
    deco, sleeps = make(max_attempts=3, base=1, jitter=0)
    src = Fake(*[ConnectionError(f"e{i}") for i in range(5)])
    with pytest.raises(RetryExhausted) as e:
        deco(src)()
    assert e.value.attempts == 3
    assert e.value.elapsed.total_seconds() == 1  # injected clock ticked 0 -> 1
    assert str(e.value.__cause__) == "e2"
    assert sleeps == [1, 2]  # no sleep after the final attempt


def test_invalid_config():
    with pytest.raises(ValueError):
        retry(max_attempts=0)
