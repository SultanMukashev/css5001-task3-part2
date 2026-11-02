"""D2.2 Source and sink hierarchy."""
from __future__ import annotations

import csv
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from pathlib import Path

log = logging.getLogger(__name__)


class Connector(ABC):
    """Lifecycle shared by every connector; subclasses override open()/close() only."""

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False


class Source(Connector):
    @abstractmethod
    def read(self) -> Iterator[dict]:
        """Yield records one by one (must stream, never load everything)."""


class Sink(Connector):
    @abstractmethod
    def write(self, records: Iterable[dict]) -> int:
        """Accept any iterable (including empty); return how many records were written."""

    def flush(self) -> None:
        """Push anything buffered to its destination. Default: nothing buffered."""

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            self.flush()
        finally:
            self.close()
        return False


class _FileConnector(Connector):
    mode = "r"

    def __init__(self, path):
        self.path = Path(path)
        self._fh = None

    def open(self) -> None:
        if self.mode == "w":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, self.mode, encoding="utf-8", newline="")

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def _handle(self):
        if self._fh is None:
            raise RuntimeError(f"{type(self).__name__} is not open; use it in a `with` block")
        return self._fh


# ---------- sources ----------

class CsvSource(_FileConnector, Source):
    def read(self) -> Iterator[dict]:
        yield from csv.DictReader(self._handle())


class JsonLinesSource(_FileConnector, Source):
    def __init__(self, path):
        super().__init__(path)
        self.bad_lines: list[tuple[int, str]] = []

    def read(self) -> Iterator[dict]:
        for lineno, line in enumerate(self._handle(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                self.bad_lines.append((lineno, str(exc)))
                log.warning("%s:%d skipped: %s", self.path, lineno, exc)
                continue
            if isinstance(record, dict):
                yield record
            else:
                self.bad_lines.append((lineno, "not a JSON object"))


class InMemorySource(Source):
    def __init__(self, records: Iterable[dict]):
        self.records = list(records)

    def read(self) -> Iterator[dict]:
        for r in self.records:
            yield dict(r)  # copies: consumers cannot mutate our data


# ---------- sinks ----------

class CsvSink(_FileConnector, Sink):
    """Columns come from the first record; later extra keys are dropped (see README)."""
    mode = "w"

    def __init__(self, path):
        super().__init__(path)
        self._writer = None

    def close(self) -> None:
        super().close()
        self._writer = None

    def write(self, records: Iterable[dict]) -> int:
        n = 0
        for r in records:
            if self._writer is None:
                self._writer = csv.DictWriter(self._handle(), list(r), extrasaction="ignore", restval="")
                self._writer.writeheader()
            self._writer.writerow(r)
            n += 1
        return n


class JsonLinesSink(_FileConnector, Sink):
    mode = "w"

    def write(self, records: Iterable[dict]) -> int:
        fh, n = self._handle(), 0
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            n += 1
        return n


class InMemorySink(Sink):
    def __init__(self):
        self.records: list[dict] = []

    def write(self, records: Iterable[dict]) -> int:
        before = len(self.records)
        self.records.extend(dict(r) for r in records)
        return len(self.records) - before
