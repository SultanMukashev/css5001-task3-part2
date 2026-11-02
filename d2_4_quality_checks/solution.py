"""D2.4 Pluggable data-quality checks."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from d1_2_dates.solution import InvalidDate, parse_ts

SAMPLE_SIZE = 5


@dataclass
class CheckResult:
    name: str
    passed: bool
    failed_count: int
    sample_failures: list = field(default_factory=list)
    severity: str = "error"


class Check(ABC):
    def __init__(self, column: str, severity: str = "error"):
        if severity not in ("error", "warning"):
            raise ValueError(f"severity must be 'error' or 'warning', got {severity!r}")
        self.column = column
        self.severity = severity

    @property
    def name(self) -> str:
        return f"{type(self).__name__}({self.column})"

    def run(self, records: Iterable[dict], now: datetime | None = None) -> CheckResult:
        """Row-level template: subclasses only say whether one value is bad."""
        self.reset()
        failed, sample = 0, []
        for r in records:
            if self.is_bad(r.get(self.column)):
                failed += 1
                if len(sample) < SAMPLE_SIZE:
                    sample.append(r)
        return CheckResult(self.name, failed == 0, failed, sample, self.severity)

    def reset(self) -> None:
        pass

    def is_bad(self, value) -> bool:
        raise NotImplementedError  # row-level checks override; dataset checks override run()


class NotNull(Check):
    def is_bad(self, value):
        return value is None or (isinstance(value, str) and not value.strip())


class Unique(Check):
    def reset(self):
        self._seen = set()

    def is_bad(self, value):
        if value is None:
            return False  # NotNull's job
        if value in self._seen:
            return True
        self._seen.add(value)
        return False


class InRange(Check):
    def __init__(self, column, low, high, severity="error"):
        super().__init__(column, severity)
        self.low, self.high = low, high

    def is_bad(self, value):
        if isinstance(value, str):
            try:
                value = Decimal(value)
            except InvalidOperation:
                return True
        try:
            return not (self.low <= value <= self.high)
        except TypeError:  # None or incomparable type
            return True


class MatchesPattern(Check):
    def __init__(self, column, regex: str, severity="error"):
        super().__init__(column, severity)
        self.pattern = re.compile(regex)

    def is_bad(self, value):
        return value is None or self.pattern.fullmatch(str(value)) is None


class Freshness(Check):
    """Dataset-level: the newest timestamp must be no older than max_age."""

    def __init__(self, column, max_age: timedelta, severity="error"):
        super().__init__(column, severity)
        self.max_age = max_age

    def run(self, records, now=None):
        now = now or datetime.now(UTC)
        newest = None
        for r in records:
            try:
                ts = parse_ts(r.get(self.column))
            except InvalidDate:
                continue  # unparsable values are other checks' job
            newest = ts if newest is None or ts > newest else newest
        if newest is None:
            return CheckResult(self.name, False, 1, [{"reason": "no valid timestamps"}], self.severity)
        age = now - newest
        ok = age <= self.max_age
        sample = [] if ok else [{"newest": newest.isoformat(), "age_seconds": int(age.total_seconds())}]
        return CheckResult(self.name, ok, 0 if ok else 1, sample, self.severity)


@dataclass
class SuiteReport:
    run_at: str
    passed: bool
    results: list[CheckResult]


class QualitySuite:
    def __init__(self, checks: list[Check], clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.checks = checks
        self.clock = clock

    def run(self, records: Iterable[dict]) -> SuiteReport:
        records = list(records)  # every check needs its own pass
        now = self.clock()
        results = []
        for check in self.checks:
            try:
                results.append(check.run(records, now))
            except Exception as exc:  # a broken check is a failed check, not a crashed run
                results.append(CheckResult(check.name, False, 0,
                                           [f"check crashed: {type(exc).__name__}: {exc}"], check.severity))
        passed = all(r.passed for r in results if r.severity == "error")
        return SuiteReport(now.astimezone(UTC).isoformat(), passed, results)

    def write_report(self, report: SuiteReport, path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2, ensure_ascii=False, default=str)
