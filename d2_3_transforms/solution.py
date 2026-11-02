"""D2.3 Chainable transforms with operator overloading."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from d2_2_sources_sinks.solution import Sink, Source


class Transform(ABC):
    @abstractmethod
    def apply(self, record: dict) -> dict | None:
        """Return a new record, or None to drop it. Never mutate the input."""

    def reset(self) -> None:
        """Clear state before a new run. Stateless transforms need nothing."""

    @property
    def name(self) -> str:
        return type(self).__name__

    def __or__(self, other: Transform) -> Chain:
        return Chain([self, other])

    def __ror__(self, source: Source) -> Pipeline:  # enables `Source | Transform`
        if not isinstance(source, Source):
            return NotImplemented
        return Pipeline(source, [self])


class Chain(Transform):
    """Several transforms behaving as one (composition)."""

    def __init__(self, steps: list[Transform]):
        self.steps = steps

    def apply(self, record):
        for step in self.steps:
            record = step.apply(record)
            if record is None:
                return None
        return record

    def reset(self):
        for step in self.steps:
            step.reset()

    def __or__(self, other):
        return Chain([*self.steps, other])


class Filter(Transform):
    def __init__(self, predicate: Callable[[dict], bool]):
        self.predicate = predicate

    def apply(self, record):
        return record if self.predicate(record) else None


class Rename(Transform):
    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping

    def apply(self, record):
        return {self.mapping.get(k, k): v for k, v in record.items()}


class Cast(Transform):
    def __init__(self, schema: dict[str, Callable]):
        self.schema = schema

    def apply(self, record):
        out = dict(record)
        for column, convert in self.schema.items():
            if column not in record:
                raise KeyError(f"missing column {column!r}")
            try:
                out[column] = convert(record[column])
            except Exception as exc:
                raise ValueError(f"cannot cast {column}={record[column]!r}: {exc}") from exc
        return out


class Deduplicate(Transform):
    def __init__(self, key: str):
        self.key = key
        self._seen: set = set()

    def reset(self):
        self._seen = set()

    def apply(self, record):
        value = record[self.key]  # missing key -> KeyError -> rejected by the pipeline
        if value in self._seen:
            return None
        self._seen.add(value)
        return record


@dataclass
class StepStats:
    name: str
    rows_in: int = 0
    rows_out: int = 0
    rejected: int = 0


@dataclass
class RunStats:
    read: int = 0
    written: int = 0
    dropped: int = 0
    rejects: list[dict] = field(default_factory=list)
    steps: list[StepStats] = field(default_factory=list)


class Pipeline:
    def __init__(self, source: Source, transforms: list[Transform] | None = None):
        self.source = source
        self.transforms = list(transforms or [])

    def __or__(self, transform: Transform) -> Pipeline:
        return Pipeline(self.source, [*self.transforms, transform])

    def _run(self, records, stats: RunStats) -> Iterator[dict]:
        for record in records:
            stats.read += 1
            for step, st in zip(self.transforms, stats.steps):
                st.rows_in += 1
                try:
                    out = step.apply(record)
                except Exception as exc:  # one bad record never stops the run
                    st.rejected += 1
                    stats.rejects.append({"record": record, "step": step.name,
                                          "error": f"{type(exc).__name__}: {exc}"})
                    break
                if out is None:
                    stats.dropped += 1
                    break
                st.rows_out += 1
                record = out
            else:
                yield record

    def process(self, records, reset: bool = True) -> tuple[Iterator[dict], RunStats]:
        """Run the transforms over any iterable. reset=False keeps state (e.g. dedupe) across batches."""
        if reset:
            for t in self.transforms:
                t.reset()
        stats = RunStats(steps=[StepStats(t.name) for t in self.transforms])
        return self._run(records, stats), stats

    def into(self, sink: Sink) -> RunStats:
        with self.source, sink:
            records, stats = self.process(self.source.read())
            stats.written = sink.write(records)
        return stats
