"""D2.5 LSP-compliant redesign of BatchSink, DryRunSink and WarehouseSink.

Sink contract (from D2.2):
  pre:  write() accepts any iterable, including empty and one-shot generators.
  post: write() returns an int == number of records accepted.
  flush() and close() never raise for a healthy sink.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

from d2_2_sources_sinks.solution import Sink

log = logging.getLogger(__name__)


class BatchSink(Sink):
    """Buffers records and ships them in batches; the remainder ships on flush()/close()."""

    def __init__(self, batch_size: int = 100, ship: Callable[[list[dict]], None] | None = None):
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self.batch_size = batch_size
        self.shipped: list[list[dict]] = []
        self._ship = ship or self.shipped.append
        self._buffer: list[dict] = []

    def write(self, records: Iterable[dict]) -> int:
        n = 0
        for r in records:
            self._buffer.append(r)
            n += 1
            if len(self._buffer) >= self.batch_size:
                self.flush()
        return n

    def flush(self) -> None:
        if self._buffer:
            batch, self._buffer = self._buffer, []
            self._ship(batch)


class DryRunSink(Sink):
    """Writes nothing, but still reports how many records it *would* have written."""

    def write(self, records: Iterable[dict]) -> int:
        n = 0
        for r in records:
            log.info("dry run: would write %r", r)
            n += 1
        return n


class WarehouseSink(Sink):
    """Stages rows on write(); flush() commits them to the (simulated) warehouse table."""

    def __init__(self):
        self.staged: list[dict] = []
        self.table: list[dict] = []

    def write(self, records: Iterable[dict]) -> int:
        before = len(self.staged)
        self.staged.extend(records)
        return len(self.staged) - before

    def flush(self) -> None:
        self.table.extend(self.staged)
        self.staged.clear()


def contract_violations(make_sink: Callable[[], Sink]) -> list[str]:
    """Run the Sink contract against a fresh sink; return a list of broken promises."""
    problems = []
    cases = [("empty list", [], 0),
             ("generator of 3", ({"i": i} for i in range(3)), 3),
             ("list of 150", [{"i": i} for i in range(150)], 150)]
    for label, records, expected in cases:
        sink = make_sink()
        try:
            with sink:
                result = sink.write(records)
            if type(result) is not int:
                problems.append(f"{label}: returned {result!r}, not an int (weakened postcondition)")
            elif result != expected:
                problems.append(f"{label}: returned {result}, expected {expected}")
        except NotImplementedError as exc:
            problems.append(f"{label}: NotImplementedError {exc} (new exception)")
        except Exception as exc:
            problems.append(f"{label}: raised {type(exc).__name__}: {exc} (strengthened precondition)")
    return problems
