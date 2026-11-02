"""minietl-specific plugins. Importing this module registers them (plus all D2.6 plugins)."""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path

from d1_2_dates.solution import normalise_ts, partition_path
from d2_2_sources_sinks.solution import Sink, Source
from d2_3_transforms.solution import Transform
from d2_6_registry.solution import ParamError, Registered

log = logging.getLogger(__name__)


class DatedFileSource(Source, Registered, kind="source", name="dated_files"):
    """A folder of daily files; `pattern` must contain a (?P<date>YYYY-MM-DD) group."""

    def __init__(self, path: str, pattern: str, format: str = "csv", fallback_encoding: str = "cp1251"):
        try:
            self.pattern = re.compile(pattern)
        except re.error as exc:
            raise ParamError("pattern", f"invalid regex: {exc}") from exc
        if "date" not in self.pattern.groupindex:
            raise ParamError("pattern", "regex needs a named group (?P<date>...)")
        if format not in ("csv", "jsonl"):
            raise ParamError("format", f"must be 'csv' or 'jsonl', got {format!r}")
        self.path, self.format, self.fallback = Path(path), format, fallback_encoding
        self.rejects: list[dict] = []

    def list_files(self) -> list[tuple[date, Path]]:
        found = []
        for p in sorted(self.path.iterdir()) if self.path.is_dir() else []:
            m = self.pattern.fullmatch(p.name)
            try:
                found.append((date.fromisoformat(m.group("date")), p))
            except (AttributeError, ValueError):  # no match, or impossible date
                log.info("ignoring %s", p.name)
        return sorted(found)

    def fetch(self, path: Path) -> bytes:
        """The I/O step (would be a network call for a remote source); retried by the runner."""
        return path.read_bytes()

    def _reject(self, name: str, line: int, error: str, record=None) -> None:
        self.rejects.append({"record": record, "step": "source", "error": f"{name}:{line}: {error}"})

    def parse(self, name: str, data: bytes) -> Iterator[dict]:
        yield from (self._parse_csv if self.format == "csv" else self._parse_jsonl)(name, data)

    def _parse_csv(self, name, data):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            log.warning("%s is not UTF-8; decoding as %s", name, self.fallback)
            text = data.decode(self.fallback, errors="replace")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        try:
            for row in reader:
                if None in row:
                    self._reject(name, reader.line_num, "extra fields", row)
                elif None in row.values():
                    self._reject(name, reader.line_num, "too few fields", row)
                else:
                    yield row
        except csv.Error as exc:  # unreadable remainder: quarantine the file tail, keep the run
            self._reject(name, reader.line_num, f"csv error, rest of file skipped: {exc}")

    def _parse_jsonl(self, name, data):
        for lineno, raw in enumerate(data.splitlines(), start=1):
            try:
                text = raw.decode("utf-8").strip()
                if not text:
                    continue
                record = json.loads(text)
                if not isinstance(record, dict):
                    raise ValueError("not a JSON object")
            except (UnicodeDecodeError, ValueError) as exc:
                self._reject(name, lineno, str(exc), raw.decode("utf-8", "replace"))
                continue
            yield record

    def read(self) -> Iterator[dict]:
        for _, p in self.list_files():
            yield from self.parse(p.name, self.fetch(p))


class Require(Transform, Registered, kind="transform", name="require"):
    def __init__(self, columns: list):
        if not columns or not all(isinstance(c, str) for c in columns):
            raise ParamError("columns", "must be a non-empty list of column names")
        self.columns = columns

    def apply(self, record):
        missing = [c for c in self.columns if not str(record.get(c) or "").strip()]
        if missing:
            raise ValueError(f"missing {', '.join(missing)}")
        return record


class NormaliseTs(Transform, Registered, kind="transform", name="normalise_ts"):
    def __init__(self, column: str, source_tz: str = "UTC", dayfirst: bool = True):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(source_tz)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ParamError("source_tz", f"unknown time zone {source_tz!r}") from exc
        self.column, self.source_tz, self.dayfirst = column, source_tz, dayfirst

    def apply(self, record):
        return {**record, self.column: normalise_ts(record.get(self.column), self.source_tz, self.dayfirst)}


class PartitionedJsonlSink(Sink, Registered, kind="sink", name="partitioned_jsonl"):
    """Writes <path>/year=/month=/day=/<batch>.jsonl.

    Files are built as temps and swapped in on flush(), replacing every earlier file of the
    same batch, so re-processing a source file is idempotent. On an exception nothing is committed.
    """

    def __init__(self, path: str, ts_column: str):
        self.root, self.ts_column = Path(path), ts_column
        self.batch = "part"
        self.rejected: list[dict] = []
        self._open: dict[Path, io.TextIOWrapper] = {}
        self._pending = False  # a write happened since the last flush (even an empty one)

    def write(self, records: Iterable[dict]) -> int:
        self._pending = True
        n = 0
        for r in records:
            try:
                part = partition_path(r[self.ts_column])
            except (KeyError, ValueError) as exc:
                self.rejected.append({"record": r, "step": "sink", "error": f"cannot partition: {exc}"})
                continue
            final = self.root / part / f"{self.batch}.jsonl"
            fh = self._open.get(final)
            if fh is None:
                final.parent.mkdir(parents=True, exist_ok=True)
                fh = self._open[final] = open(final.with_name(final.name + ".tmp"), "w", encoding="utf-8")
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
            n += 1
        return n

    def flush(self) -> None:
        if not self._pending:
            return
        for old in self.root.glob(f"year=*/month=*/day=*/{self.batch}.jsonl"):
            if old not in self._open:
                old.unlink()  # this batch no longer has rows in that partition
        for final, fh in self._open.items():
            fh.close()
            os.replace(fh.name, final)
        self._open.clear()
        self._pending = False

    def _discard(self) -> None:
        for fh in self._open.values():
            fh.close()
            Path(fh.name).unlink(missing_ok=True)
        self._open.clear()
        self._pending = False

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type:
            self._discard()
            return False
        return super().__exit__(exc_type, exc, tb)
